#!/usr/bin/env python3
"""Generate repo usage metrics from Lambda invocation data.

Pulls CloudWatch metrics for all Lambda functions in production,
maps them to repos, and outputs a ranked CSV report.

Usage:
    AWS_PROFILE=prod python scripts/repo-metrics.py
    AWS_PROFILE=prod python scripts/repo-metrics.py --months 12 --output repo-metrics.csv
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import boto3


def get_lambda_functions(lambda_client):
    """Get all Lambda functions with their tags."""
    functions = []
    paginator = lambda_client.get_paginator("list_functions")

    for page in paginator.paginate():
        for func in page["Functions"]:
            functions.append(
                {
                    "name": func["FunctionName"],
                    "runtime": func.get("Runtime", "unknown"),
                    "last_modified": func.get("LastModified", ""),
                }
            )

    return functions


def get_lambda_tags(lambda_client, function_name):
    """Get tags for a Lambda function."""
    try:
        # Need the full ARN for get_function
        response = lambda_client.get_function(FunctionName=function_name)
        arn = response["Configuration"]["FunctionArn"]
        tags_response = lambda_client.list_tags(Resource=arn)
        return tags_response.get("Tags", {})
    except Exception as e:
        return {}


def extract_repo_name(function_name, tags):
    """Extract repo name from function name or tags."""
    # Check tags first
    repo = tags.get("repo") or tags.get("repository") or tags.get("Repo")
    if repo:
        return repo

    # Extract from function name pattern: {repo}-{env}-{handler}
    # Examples:
    #   emvio-pay-production-processPayment -> emvio-pay
    #   cforce-service-production-getMerchant -> cforce-service
    #   mrrobot-cast-support-portal-rest-prod -> mrrobot-cast-support-portal-rest

    parts = function_name.split("-")

    # Handle -production- or -prod- patterns
    for env_marker in ["production", "prod", "staging", "dev", "sandbox"]:
        if env_marker in parts:
            idx = parts.index(env_marker)
            return "-".join(parts[:idx])

    # Fallback: use first 2-3 parts
    if len(parts) >= 3:
        return "-".join(parts[:3])
    return function_name


def get_invocation_count(cloudwatch_client, function_name, start_time, end_time):
    """Get total invocation count for a Lambda function."""
    try:
        response = cloudwatch_client.get_metric_statistics(
            Namespace="AWS/Lambda",
            MetricName="Invocations",
            Dimensions=[{"Name": "FunctionName", "Value": function_name}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400 * 30,  # 30-day periods
            Statistics=["Sum"],
        )

        total = sum(dp["Sum"] for dp in response.get("Datapoints", []))
        return int(total)
    except Exception as e:
        print(f"  Warning: Could not get metrics for {function_name}: {e}", file=sys.stderr)
        return 0


def get_monthly_invocations(cloudwatch_client, function_name, months=12):
    """Get invocation counts by month for a Lambda function."""
    monthly_data = {}
    end_time = datetime.now(timezone.utc)

    for i in range(months):
        # Calculate month boundaries
        month_end = end_time - timedelta(days=30 * i)
        month_start = month_end - timedelta(days=30)
        month_key = month_start.strftime("%Y-%m")

        try:
            response = cloudwatch_client.get_metric_statistics(
                Namespace="AWS/Lambda",
                MetricName="Invocations",
                Dimensions=[{"Name": "FunctionName", "Value": function_name}],
                StartTime=month_start,
                EndTime=month_end,
                Period=86400 * 30,
                Statistics=["Sum"],
            )

            total = sum(dp["Sum"] for dp in response.get("Datapoints", []))
            monthly_data[month_key] = int(total)
        except Exception:
            monthly_data[month_key] = 0

    return monthly_data


def main():
    parser = argparse.ArgumentParser(description="Generate repo usage metrics from Lambda invocations")
    parser.add_argument("--months", type=int, default=12, help="Number of months to analyze (default: 12)")
    parser.add_argument("--output", "-o", type=str, default="repo-metrics.csv", help="Output CSV file")
    parser.add_argument("--region", type=str, default="us-east-1", help="AWS region")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    print(f"Connecting to AWS ({args.region})...")
    lambda_client = boto3.client("lambda", region_name=args.region)
    cloudwatch_client = boto3.client("cloudwatch", region_name=args.region)

    # Get all Lambda functions
    print("Fetching Lambda functions...")
    functions = get_lambda_functions(lambda_client)
    print(f"Found {len(functions)} Lambda functions")

    # Calculate time range
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(days=30 * args.months)
    print(f"Analyzing period: {start_time.strftime('%Y-%m-%d')} to {end_time.strftime('%Y-%m-%d')}")

    # Aggregate by repo
    repo_metrics = defaultdict(lambda: {"invocations": 0, "functions": [], "monthly": defaultdict(int)})

    for i, func in enumerate(functions):
        if args.verbose or (i + 1) % 50 == 0:
            print(f"Processing {i + 1}/{len(functions)}: {func['name'][:50]}...")

        # Get tags and extract repo name
        tags = get_lambda_tags(lambda_client, func["name"])
        repo = extract_repo_name(func["name"], tags)

        # Get invocation count
        invocations = get_invocation_count(cloudwatch_client, func["name"], start_time, end_time)

        # Aggregate
        repo_metrics[repo]["invocations"] += invocations
        repo_metrics[repo]["functions"].append(func["name"])

    # Sort by invocations
    sorted_repos = sorted(repo_metrics.items(), key=lambda x: -x[1]["invocations"])

    # Output CSV
    print(f"\nWriting results to {args.output}...")
    with open(args.output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Rank", "Repo", "Total Invocations (12mo)", "Function Count", "Functions (sample)"])

        for rank, (repo, data) in enumerate(sorted_repos, 1):
            sample_funcs = ", ".join(data["functions"][:3])
            if len(data["functions"]) > 3:
                sample_funcs += f" (+{len(data['functions']) - 3} more)"

            writer.writerow(
                [
                    rank,
                    repo,
                    f"{data['invocations']:,}",
                    len(data["functions"]),
                    sample_funcs,
                ]
            )

    # Print top 20 to console
    print("\n" + "=" * 80)
    print(f"TOP 20 REPOS BY LAMBDA INVOCATIONS (Last {args.months} months)")
    print("=" * 80)
    print(f"{'Rank':<6} {'Invocations':>15} {'Funcs':>6}  Repo")
    print("-" * 80)

    for rank, (repo, data) in enumerate(sorted_repos[:20], 1):
        print(f"{rank:<6} {data['invocations']:>15,} {len(data['functions']):>6}  {repo}")

    print("-" * 80)
    total_invocations = sum(d["invocations"] for d in repo_metrics.values())
    print(f"{'TOTAL':<6} {total_invocations:>15,} {len(functions):>6}  ({len(repo_metrics)} repos)")
    print(f"\nFull results saved to: {args.output}")


if __name__ == "__main__":
    main()
