#!/usr/bin/env python3
"""
Sync Bitbucket repos to S3 for Bedrock Knowledge Base indexing.

This script:
1. Clones/updates all repos from Bitbucket
2. Filters to relevant code files
3. Uploads to S3 with metadata
4. Triggers Knowledge Base sync

Usage:
    python sync-repos-to-s3.py --bucket mrrobot-code-kb-dev-123456789 --kb-id XXXXXX --ds-id YYYYYY

Environment variables:
    CVE_BB_TOKEN - Bitbucket API token
    AWS_PROFILE - AWS profile to use (default: dev)
"""

import os
import sys
import json
import subprocess
import argparse
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed

# File extensions to index (code files)
CODE_EXTENSIONS = {
    # JavaScript/TypeScript
    '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
    # Python
    '.py',
    # Java/Kotlin
    '.java', '.kt',
    # Configuration
    '.json', '.yaml', '.yml', '.toml',
    '.env.example', '.env.sample',
    # Infrastructure
    '.tf', '.tfvars',
    # Docker
    'Dockerfile', '.dockerignore',
    # Shell
    '.sh', '.bash',
    # Web
    '.html', '.css', '.scss', '.less',
    # Documentation
    '.md', '.rst',
    # SQL
    '.sql',
    # GraphQL
    '.graphql', '.gql',
}

# Files to always include (exact names)
INCLUDE_FILES = {
    'package.json',
    'tsconfig.json',
    'serverless.yml',
    'serverless.yaml',
    'docker-compose.yml',
    'docker-compose.yaml',
    'Dockerfile',
    '.env.example',
    'requirements.txt',
    'pyproject.toml',
    'Cargo.toml',
    'go.mod',
    'pom.xml',
    'build.gradle',
    'Makefile',
}

# Directories to skip
SKIP_DIRS = {
    'node_modules',
    '.git',
    '.next',
    '.nuxt',
    'dist',
    'build',
    'out',
    '__pycache__',
    '.pytest_cache',
    '.tox',
    'venv',
    'env',
    '.venv',
    'vendor',
    'coverage',
    '.nyc_output',
    'target',
    '.idea',
    '.vscode',
}

# Max file size (1MB)
MAX_FILE_SIZE = 1024 * 1024


def should_include_file(file_path: Path) -> bool:
    """Determine if a file should be included in the knowledge base."""
    # Check if in skip directory
    for part in file_path.parts:
        if part in SKIP_DIRS:
            return False

    # Check if file is too large
    try:
        if file_path.stat().st_size > MAX_FILE_SIZE:
            return False
    except OSError:
        return False

    # Check exact filename matches
    if file_path.name in INCLUDE_FILES:
        return True

    # Check extension
    suffix = file_path.suffix.lower()
    if suffix in CODE_EXTENSIONS:
        return True

    return False


def get_bitbucket_repos(workspace: str, token: str, email: str) -> list:
    """Fetch all repos from Bitbucket workspace."""
    import requests

    repos = []
    page = 1

    while True:
        url = f"https://api.bitbucket.org/2.0/repositories/{workspace}?page={page}&pagelen=100"
        response = requests.get(url, auth=(email, token))

        if response.status_code != 200:
            print(f"Error fetching repos: {response.status_code}")
            break

        data = response.json()
        values = data.get('values', [])

        if not values:
            break

        for repo in values:
            name = repo['name']
            ssh_url = None
            for link in repo.get('links', {}).get('clone', []):
                if link.get('name') == 'ssh':
                    ssh_url = link.get('href')
                    break

            if ssh_url:
                repos.append({
                    'name': name,
                    'ssh_url': ssh_url,
                    'full_name': repo.get('full_name', f"{workspace}/{name}"),
                    'description': repo.get('description', ''),
                    'language': repo.get('language', 'unknown'),
                    'updated_on': repo.get('updated_on', ''),
                })

        if 'next' not in data:
            break

        page += 1

    return repos


def clone_or_update_repo(repo: dict, base_dir: Path) -> Path:
    """Clone or update a repository."""
    repo_dir = base_dir / repo['name']

    if repo_dir.exists():
        # Update existing repo
        try:
            subprocess.run(
                ['git', 'pull', '--ff-only'],
                cwd=repo_dir,
                capture_output=True,
                check=True,
                timeout=120
            )
            print(f"  Updated: {repo['name']}")
        except subprocess.CalledProcessError:
            # Try to reset
            try:
                subprocess.run(['git', 'fetch', 'origin'], cwd=repo_dir, capture_output=True, timeout=60)
                result = subprocess.run(
                    ['git', 'remote', 'show', 'origin'],
                    cwd=repo_dir,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                for line in result.stdout.split('\n'):
                    if 'HEAD branch' in line:
                        branch = line.split(':')[-1].strip()
                        subprocess.run(
                            ['git', 'reset', '--hard', f'origin/{branch}'],
                            cwd=repo_dir,
                            capture_output=True,
                            timeout=60
                        )
                        print(f"  Reset: {repo['name']}")
                        break
            except Exception as e:
                print(f"  Error updating {repo['name']}: {e}")
    else:
        # Clone new repo
        try:
            subprocess.run(
                ['git', 'clone', '--depth', '1', repo['ssh_url'], str(repo_dir)],
                capture_output=True,
                check=True,
                timeout=180
            )
            print(f"  Cloned: {repo['name']}")
        except subprocess.CalledProcessError as e:
            print(f"  Error cloning {repo['name']}: {e}")
            return None

    return repo_dir


def upload_repo_to_s3(repo: dict, repo_dir: Path, s3_client, bucket: str) -> int:
    """Upload repo files to S3 with metadata."""
    uploaded = 0

    if not repo_dir or not repo_dir.exists():
        return 0

    for file_path in repo_dir.rglob('*'):
        if not file_path.is_file():
            continue

        if not should_include_file(file_path):
            continue

        try:
            # Read file content
            try:
                content = file_path.read_text(encoding='utf-8')
            except UnicodeDecodeError:
                continue  # Skip binary files

            # Create S3 key with repo prefix
            relative_path = file_path.relative_to(repo_dir)
            s3_key = f"repos/{repo['name']}/{relative_path}"

            # Create metadata for the file
            metadata = {
                'repo_name': repo['name'],
                'file_path': str(relative_path),
                'language': repo.get('language', 'unknown'),
                'repo_full_name': repo.get('full_name', ''),
                'file_extension': file_path.suffix,
            }

            # Wrap content with metadata header for better RAG
            wrapped_content = f"""# Repository: {repo['name']}
# File: {relative_path}
# Language: {repo.get('language', 'unknown')}
# Full path: {repo['full_name']}/{relative_path}

{content}
"""

            # Upload to S3
            s3_client.put_object(
                Bucket=bucket,
                Key=s3_key,
                Body=wrapped_content.encode('utf-8'),
                ContentType='text/plain',
                Metadata=metadata
            )

            uploaded += 1

        except Exception as e:
            print(f"    Error uploading {file_path}: {e}")

    return uploaded


def trigger_kb_sync(kb_id: str, ds_id: str, region: str):
    """Trigger Knowledge Base data source sync."""
    client = boto3.client('bedrock-agent', region_name=region)

    try:
        response = client.start_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            description=f"Sync triggered at {datetime.now().isoformat()}"
        )

        job_id = response.get('ingestionJob', {}).get('ingestionJobId')
        print(f"\nTriggered Knowledge Base sync: Job ID = {job_id}")
        return job_id

    except Exception as e:
        print(f"Error triggering KB sync: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Sync Bitbucket repos to S3 for Bedrock KB')
    parser.add_argument('--bucket', required=True, help='S3 bucket name')
    parser.add_argument('--kb-id', help='Bedrock Knowledge Base ID (optional, for auto-sync)')
    parser.add_argument('--ds-id', help='Bedrock Data Source ID (optional, for auto-sync)')
    parser.add_argument('--region', default='us-west-2', help='AWS region')
    parser.add_argument('--workspace', default='mrrobot-labs', help='Bitbucket workspace')
    parser.add_argument('--email', default='gstarkman@nex.io', help='Bitbucket email')
    parser.add_argument('--temp-dir', help='Temp directory for cloning (default: system temp)')
    parser.add_argument('--keep-repos', action='store_true', help='Keep cloned repos after upload')
    args = parser.parse_args()

    # Check for Bitbucket token
    bb_token = os.environ.get('CVE_BB_TOKEN')
    if not bb_token:
        print("Error: CVE_BB_TOKEN environment variable not set")
        sys.exit(1)

    # Setup AWS
    profile = os.environ.get('AWS_PROFILE', 'dev')
    session = boto3.Session(profile_name=profile, region_name=args.region)
    s3_client = session.client('s3')

    print(f"=== MrRobot Code Knowledge Base Sync ===")
    print(f"Bucket: {args.bucket}")
    print(f"Workspace: {args.workspace}")
    print(f"Region: {args.region}")
    print()

    # Create temp directory for repos
    if args.temp_dir:
        base_dir = Path(args.temp_dir)
        base_dir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        temp_dir = tempfile.mkdtemp(prefix='mrrobot-kb-sync-')
        base_dir = Path(temp_dir)
        cleanup = not args.keep_repos

    print(f"Working directory: {base_dir}")
    print()

    try:
        # Fetch repos from Bitbucket
        print("Fetching repository list from Bitbucket...")
        repos = get_bitbucket_repos(args.workspace, bb_token, args.email)
        print(f"Found {len(repos)} repositories")
        print()

        # Clone/update and upload repos
        total_files = 0

        print("Cloning and uploading repositories...")
        for i, repo in enumerate(repos, 1):
            print(f"[{i}/{len(repos)}] {repo['name']}")

            # Clone or update
            repo_dir = clone_or_update_repo(repo, base_dir)

            if repo_dir:
                # Upload to S3
                uploaded = upload_repo_to_s3(repo, repo_dir, s3_client, args.bucket)
                total_files += uploaded
                print(f"    Uploaded {uploaded} files")

        print()
        print(f"=== Summary ===")
        print(f"Repositories processed: {len(repos)}")
        print(f"Total files uploaded: {total_files}")

        # Trigger KB sync if IDs provided
        if args.kb_id and args.ds_id:
            trigger_kb_sync(args.kb_id, args.ds_id, args.region)

    finally:
        if cleanup:
            print(f"\nCleaning up temp directory: {base_dir}")
            shutil.rmtree(base_dir, ignore_errors=True)


if __name__ == '__main__':
    main()
