#!/usr/bin/env python3
"""Generate service registry from S3 code repos.

Scans repos synced to S3 (from the Knowledge Base bucket) and extracts:
- Service name and full name
- Type (frontend/backend) based on dependencies
- Tech stack from package.json, serverless.yml, etc.
- Aliases based on common naming patterns

Usage:
    AWS_PROFILE=dev python scripts/generate-service-registry.py
    AWS_PROFILE=dev python scripts/generate-service-registry.py --upload
    AWS_PROFILE=dev python scripts/generate-service-registry.py --dry-run
"""

import argparse
import json

import boto3
from botocore.exceptions import ClientError

# S3 config
S3_BUCKET = "mrrobot-code-kb-dev-720154970215"
S3_REPOS_PREFIX = "repos/"
S3_CONFIG_KEY = "clippy-config/services.json"


def get_s3_client():
    return boto3.client("s3", region_name="us-east-1")


def list_repos() -> list[str]:
    """List all repo directories in S3."""
    s3 = get_s3_client()
    repos = []

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_REPOS_PREFIX, Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            repo_name = prefix["Prefix"].replace(S3_REPOS_PREFIX, "").rstrip("/")
            if repo_name:
                repos.append(repo_name)

    return sorted(repos)


def get_file_content(repo: str, file_path: str) -> str | None:
    """Get file content from S3.

    Note: S3 files have a header comment added by sync script.
    We strip lines starting with # before returning.
    """
    s3 = get_s3_client()
    key = f"{S3_REPOS_PREFIX}{repo}/{file_path}"

    try:
        response = s3.get_object(Bucket=S3_BUCKET, Key=key)
        content = response["Body"].read().decode("utf-8")

        # Strip header comments added by sync script
        lines = content.split("\n")
        while lines and lines[0].startswith("#"):
            lines.pop(0)
        # Also strip any leading empty lines
        while lines and not lines[0].strip():
            lines.pop(0)

        return "\n".join(lines)
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return None
        print(f"  [Debug] ClientError for {repo}/{file_path}: {e.response['Error']['Code']}")
        return None
    except Exception as e:
        print(f"  [Debug] Exception for {repo}/{file_path}: {e}")
        return None


def detect_service_type(package_json: dict | None, files: list) -> str:
    """Detect if service is frontend or backend."""
    if not package_json:
        if any(f in files for f in ["serverless.yml", "serverless.yaml", "handler.py"]):
            return "backend"
        if any(f in files for f in ["requirements.txt", "pyproject.toml"]):
            return "backend"
        return "unknown"

    deps = package_json.get("dependencies", {})
    dev_deps = package_json.get("devDependencies", {})
    all_deps = {**deps, **dev_deps}

    # Frontend indicators
    frontend_deps = ["react", "vue", "angular", "next", "nuxt", "vite", "@vitejs/plugin-react", "svelte"]
    if any(dep in all_deps for dep in frontend_deps):
        return "frontend"

    # Backend indicators
    backend_deps = [
        "express",
        "fastify",
        "hapi",
        "@hapi/hapi",
        "koa",
        "aws-sdk",
        "@aws-sdk/client-lambda",
        "serverless",
    ]
    if any(dep in all_deps for dep in backend_deps):
        return "backend"

    # Check scripts
    scripts = package_json.get("scripts", {})
    if "start" in scripts:
        start_cmd = scripts["start"].lower()
        if any(x in start_cmd for x in ["react-scripts", "vite", "next", "webpack"]):
            return "frontend"
        if any(x in start_cmd for x in ["node", "serverless", "ts-node"]):
            return "backend"

    return "unknown"


def detect_tech_stack(package_json: dict | None, files: list) -> list:
    """Detect tech stack from dependencies and files."""
    stack = []

    # File-based detection
    if any(f in files for f in ["serverless.yml", "serverless.yaml"]):
        stack.append("Serverless")
    if "Dockerfile" in files:
        stack.append("Docker")
    if any(f in files for f in ["requirements.txt", "pyproject.toml"]):
        stack.append("Python")

    if not package_json:
        return stack if stack else ["Unknown"]

    deps = package_json.get("dependencies", {})
    dev_deps = package_json.get("devDependencies", {})
    all_deps = {**deps, **dev_deps}

    # Frameworks
    if "react" in all_deps:
        stack.append("React")
    if "vue" in all_deps:
        stack.append("Vue")
    if "next" in all_deps:
        stack.append("Next.js")
    if "express" in all_deps:
        stack.append("Express")
    if "@hapi/hapi" in all_deps or "hapi" in all_deps:
        stack.append("Hapi")
    if "fastify" in all_deps:
        stack.append("Fastify")

    # Languages
    if "typescript" in all_deps:
        stack.append("TypeScript")
    else:
        stack.append("Node.js")

    # Databases
    if any(k for k in all_deps if "dynamodb" in k.lower() or k == "dynamoose"):
        stack.append("DynamoDB")
    if "pg" in all_deps or "postgres" in str(all_deps).lower():
        stack.append("PostgreSQL")
    if "mysql" in all_deps or "mysql2" in all_deps:
        stack.append("MySQL")
    if "redis" in all_deps or "ioredis" in all_deps:
        stack.append("Redis")

    # AWS
    if "aws-sdk" in all_deps or any(k.startswith("@aws-sdk") for k in all_deps):
        stack.append("AWS SDK")

    return stack if stack else ["Unknown"]


def generate_aliases(repo_slug: str) -> list:
    """Generate common aliases for a repo name."""
    aliases = [repo_slug]
    name = repo_slug.lower()

    # Remove common prefixes
    for prefix in ["mrrobot-", "emvio-", "cforce-", "cast-", "apm-", "etl-", "payment-"]:
        if name.startswith(prefix):
            short = name[len(prefix) :]
            if short and short not in aliases:
                aliases.append(short)
            break

    # Remove common suffixes
    for suffix in ["-service", "-app", "-rest", "-api", "-lambda", "-util", "-provider", "-connector"]:
        if name.endswith(suffix):
            short = name[: -len(suffix)]
            if short and short not in aliases:
                aliases.append(short)
            # Also try without prefix AND suffix
            for prefix in ["mrrobot-", "emvio-", "cforce-", "cast-"]:
                if short.startswith(prefix):
                    shorter = short[len(prefix) :]
                    if shorter and shorter not in aliases:
                        aliases.append(shorter)
            break

    # Add no-hyphen version
    no_hyphens = repo_slug.replace("-", "")
    if no_hyphens != repo_slug and no_hyphens not in aliases:
        aliases.append(no_hyphens)

    return aliases


def analyze_repo(repo: str) -> dict | None:
    """Analyze a repo and extract service info."""
    # Skip obvious non-service repos
    skip_exact = {
        "emvio-config",
        "cforce-config",
        "emvio-url-config",
        "etl-fdr-config",
        "git-training",
        "emvio-documentation",
        "emvio-api-documentation",
        "devops-scripts",
        "ip-ranges",
        "sumo-queries",
        "snyk-config",
        "emvio-developer-tools",
        "Default",
    }
    if repo in skip_exact:
        return None

    # Skip terraform/infrastructure repos
    if any(x in repo.lower() for x in ["-terraform", "-tf-", "terraform-"]):
        return None

    # Try to find package.json in multiple locations
    package_json = None
    package_location = None

    for path in ["package.json", "service/package.json", "src/package.json", "app/package.json"]:
        content = get_file_content(repo, path)
        if content:
            try:
                package_json = json.loads(content)
                package_location = path
                break
            except json.JSONDecodeError:
                pass

    # Check for other indicator files
    existing_files = []
    check_files = [
        "package.json",
        "service/package.json",
        "serverless.yml",
        "serverless.yaml",
        "service/serverless.yml",
        "Dockerfile",
        "requirements.txt",
        "pyproject.toml",
        "handler.py",
        "handler.js",
    ]

    for f in check_files:
        if get_file_content(repo, f):
            existing_files.append(f.split("/")[-1])  # Just the filename

    # Skip if nothing useful found
    if not package_json and not existing_files:
        return None

    # Detect type and stack
    service_type = detect_service_type(package_json, existing_files)
    tech_stack = detect_tech_stack(package_json, existing_files)

    # Get description
    description = ""
    if package_json:
        description = package_json.get("description", "")

    # Build result
    return {
        "full_name": repo,
        "type": service_type,
        "aliases": generate_aliases(repo),
        "tech_stack": tech_stack,
        "description": description[:200] if description else f"{repo}",
        "repo": repo,
        "package_location": package_location,
    }


def generate_key(repo: str) -> str:
    """Generate a short key for the service."""
    key = repo.lower()

    # Remove prefixes
    for prefix in ["mrrobot-", "emvio-", "cforce-", "cast-", "apm-", "etl-", "payment-"]:
        if key.startswith(prefix):
            key = key[len(prefix) :]
            break

    # Remove suffixes
    for suffix in ["-service", "-app"]:
        if key.endswith(suffix):
            key = key[: -len(suffix)]
            break

    return key


def main():
    parser = argparse.ArgumentParser(description="Generate service registry from S3 repos")
    parser.add_argument("--upload", action="store_true", help="Upload to S3")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    parser.add_argument("--output", default="services.json", help="Output file")
    args = parser.parse_args()

    print("=" * 60)
    print("Service Registry Generator (S3)")
    print("=" * 60)

    # List repos from S3
    print("\n[S3] Listing repos...")
    repos = list_repos()
    print(f"[S3] Found {len(repos)} repos")

    # Analyze each repo
    print(f"\n[Analyzing] {len(repos)} repos...")
    services = {}
    stats = {"frontend": 0, "backend": 0, "unknown": 0, "skipped": 0}

    for i, repo in enumerate(repos):
        result = analyze_repo(repo)

        if result:
            key = generate_key(repo)
            services[key] = result
            stype = result.get("type", "unknown")
            stats[stype] = stats.get(stype, 0) + 1
            stack_str = ", ".join(result.get("tech_stack", [])[:3])
            print(f"  [{i+1}/{len(repos)}] {key}: {stype} ({stack_str})")
        else:
            stats["skipped"] += 1
            print(f"  [{i+1}/{len(repos)}] {repo}: skipped")

    print(f"\n[Result] Found {len(services)} services")

    if args.dry_run:
        print("\n[Dry Run] Sample output:")
        sample = dict(list(services.items())[:5])
        print(json.dumps(sample, indent=2))
        return

    # Save locally
    with open(args.output, "w") as f:
        json.dump(services, f, indent=2)
    print(f"\n[Saved] {args.output}")

    # Upload to S3
    if args.upload:
        print(f"\n[Uploading] to s3://{S3_BUCKET}/{S3_CONFIG_KEY}")
        s3 = get_s3_client()
        s3.put_object(
            Bucket=S3_BUCKET, Key=S3_CONFIG_KEY, Body=json.dumps(services, indent=2), ContentType="application/json"
        )
        print("[Done] Uploaded to S3")

    print("\n" + "=" * 60)
    print(f"Summary: {len(services)} services")
    print("=" * 60)
    for stype, count in sorted(stats.items()):
        if count > 0:
            print(f"  {stype}: {count}")


if __name__ == "__main__":
    main()
