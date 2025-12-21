"""AWS CLI tool for MCP server.

Provides a general-purpose AWS CLI agent that can run read-only AWS commands.
This allows Clippy to query any AWS resource without needing individual tools.
"""

import json
import subprocess
import shlex

# Allowed AWS CLI commands (read-only operations)
ALLOWED_COMMANDS = [
    # EC2
    "ec2 describe-instances",
    "ec2 describe-security-groups",
    "ec2 describe-vpcs",
    "ec2 describe-subnets",
    "ec2 describe-nat-gateways",
    # ECS
    "ecs describe-services",
    "ecs describe-clusters",
    "ecs describe-task-definition",
    "ecs list-services",
    "ecs list-tasks",
    "ecs list-clusters",
    # ELB/ALB
    "elbv2 describe-load-balancers",
    "elbv2 describe-target-groups",
    "elbv2 describe-listeners",
    "elbv2 describe-rules",
    # WAF
    "wafv2 list-web-acls",
    "wafv2 get-web-acl",
    "wafv2 list-resources-for-web-acl",
    # Lambda
    "lambda list-functions",
    "lambda get-function",
    "lambda get-function-configuration",
    # CloudWatch
    "cloudwatch describe-alarms",
    "logs describe-log-groups",
    # IAM (read-only)
    "iam list-roles",
    "iam get-role",
    "iam list-policies",
    # S3 (read-only)
    "s3 ls",
    "s3api list-buckets",
    "s3api get-bucket-policy",
    "s3api get-bucket-cors",
    # Route53
    "route53 list-hosted-zones",
    "route53 list-resource-record-sets",
    # Secrets Manager (list only, not get-secret-value)
    "secretsmanager list-secrets",
    # RDS
    "rds describe-db-instances",
    "rds describe-db-clusters",
    # CloudFormation
    "cloudformation list-stacks",
    "cloudformation describe-stacks",
    "cloudformation describe-stack-resources",
]

# Explicitly blocked commands (dangerous operations)
BLOCKED_PATTERNS = [
    "delete",
    "terminate",
    "remove",
    "update",
    "create",
    "put-",
    "modify",
    "start",
    "stop",
    "reboot",
    "get-secret-value",  # Don't expose secrets
    "get-authorization-token",
]


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Check if a command is allowed to run.

    Returns:
        tuple of (is_allowed, reason)
    """
    command_lower = command.lower()

    # Check for blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if pattern in command_lower:
            return False, f"Command contains blocked pattern: {pattern}"

    # Check if command starts with an allowed prefix
    for allowed in ALLOWED_COMMANDS:
        if command_lower.startswith(allowed):
            return True, "Command is in allowlist"

    return False, f"Command not in allowlist. Allowed commands: {', '.join(ALLOWED_COMMANDS[:10])}..."


def run_aws_command(command: str, region: str = "us-east-1", profile: str = None) -> dict:
    """Run an AWS CLI command and return the result.

    This tool allows querying AWS resources using the AWS CLI.
    Only read-only commands are allowed for safety.

    Args:
        command: AWS CLI command WITHOUT 'aws' prefix (e.g., 'ec2 describe-instances')
        region: AWS region (default: us-east-1)
        profile: AWS profile to use (optional, uses default credentials if not specified)

    Returns:
        dict with 'output' (parsed JSON or raw text) or 'error'

    Examples:
        - "elbv2 describe-load-balancers" - List all ALBs
        - "wafv2 list-web-acls --scope REGIONAL" - List WAF ACLs
        - "ecs describe-services --cluster mrrobot-ai-core --services mrrobot-mcp-server"
    """
    # Validate command
    is_allowed, reason = is_command_allowed(command)
    if not is_allowed:
        return {"error": f"Command not allowed: {reason}"}

    # Build the full command
    full_command = ["aws"] + shlex.split(command)
    full_command.extend(["--region", region, "--output", "json"])

    if profile:
        full_command.extend(["--profile", profile])

    print(f"[AWS CLI] Running: {' '.join(full_command)}")

    try:
        result = subprocess.run(
            full_command,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or "Command failed"
            print(f"[AWS CLI] Error: {error_msg}")
            return {"error": error_msg}

        # Try to parse as JSON
        try:
            output = json.loads(result.stdout)
            print(f"[AWS CLI] Success: got JSON response")
            return {"output": output, "command": command}
        except json.JSONDecodeError:
            # Return raw text if not JSON
            print(f"[AWS CLI] Success: got text response")
            return {"output": result.stdout.strip(), "command": command}

    except subprocess.TimeoutExpired:
        return {"error": "Command timed out after 30 seconds"}
    except Exception as e:
        return {"error": f"Failed to run command: {str(e)}"}


def describe_load_balancers(name_filter: str = None) -> dict:
    """Describe ALB/NLB load balancers.

    Args:
        name_filter: Optional filter by load balancer name

    Returns:
        dict with load balancer details
    """
    command = "elbv2 describe-load-balancers"
    if name_filter:
        command += f" --names {name_filter}"

    result = run_aws_command(command)

    if "error" in result:
        return result

    # Simplify the output
    lbs = []
    for lb in result.get("output", {}).get("LoadBalancers", []):
        lbs.append({
            "name": lb.get("LoadBalancerName"),
            "dns": lb.get("DNSName"),
            "scheme": lb.get("Scheme"),  # "internal" or "internet-facing"
            "type": lb.get("Type"),
            "vpc": lb.get("VpcId"),
            "state": lb.get("State", {}).get("Code"),
            "arn": lb.get("LoadBalancerArn"),
        })

    return {"load_balancers": lbs, "count": len(lbs)}


def describe_waf_for_resource(resource_arn: str) -> dict:
    """Get WAF WebACL attached to a resource (ALB, API Gateway, etc).

    Args:
        resource_arn: ARN of the resource to check

    Returns:
        dict with WAF details or message if no WAF attached
    """
    command = f"wafv2 get-web-acl-for-resource --resource-arn {resource_arn}"
    result = run_aws_command(command)

    if "error" in result:
        if "WAFNonexistentItemException" in str(result.get("error", "")):
            return {"message": "No WAF WebACL attached to this resource"}
        return result

    acl = result.get("output", {}).get("WebACL", {})
    return {
        "web_acl_name": acl.get("Name"),
        "web_acl_id": acl.get("Id"),
        "web_acl_arn": acl.get("ARN"),
        "rules_count": len(acl.get("Rules", [])),
    }
