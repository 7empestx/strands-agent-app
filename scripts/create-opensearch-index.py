#!/usr/bin/env python3
"""
Create OpenSearch Serverless index for Bedrock Knowledge Base.

This script should be run AFTER the CDK stack deploys the OpenSearch collection
but BEFORE creating the Knowledge Base.

Usage:
    python scripts/create-opensearch-index.py --endpoint <endpoint> --region us-east-1

The script will retry multiple times until the data access policy propagates.
"""

import argparse
import json
import time
import urllib3
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


def create_index(endpoint: str, index_name: str, region: str, max_retries: int = 20) -> bool:
    """Create the OpenSearch index for Bedrock Knowledge Base."""

    # Remove https:// if present
    endpoint = endpoint.replace('https://', '')

    # Index mapping for Bedrock Knowledge Base (Titan v2 = 1024 dimensions)
    index_body = {
        "settings": {
            "index": {
                "number_of_shards": 2,
                "number_of_replicas": 0,
                "knn": True,
                "knn.algo_param.ef_search": 512
            }
        },
        "mappings": {
            "properties": {
                "bedrock-knowledge-base-vector": {
                    "type": "knn_vector",
                    "dimension": 1024,
                    "method": {
                        "engine": "faiss",
                        "space_type": "l2",
                        "name": "hnsw",
                        "parameters": {
                            "ef_construction": 512,
                            "m": 16
                        }
                    }
                },
                "AMAZON_BEDROCK_TEXT_CHUNK": {
                    "type": "text"
                },
                "AMAZON_BEDROCK_METADATA": {
                    "type": "text"
                }
            }
        }
    }

    http = urllib3.PoolManager()
    url = f"https://{endpoint}/{index_name}"
    body = json.dumps(index_body)

    print(f"Creating index '{index_name}' on endpoint: {endpoint}")
    print(f"Region: {region}")
    print()

    for attempt in range(max_retries):
        # Get fresh credentials for each attempt
        session = boto3.Session()
        credentials = session.get_credentials()

        request = AWSRequest(method='PUT', url=url, data=body, headers={
            'Content-Type': 'application/json',
            'Host': endpoint
        })
        SigV4Auth(credentials, 'aoss', region).add_auth(request)

        try:
            print(f"Attempt {attempt + 1}/{max_retries}...")
            response = http.request(
                'PUT',
                url,
                body=body.encode('utf-8'),
                headers=dict(request.headers)
            )

            response_body = response.data.decode('utf-8')

            if response.status in [200, 201]:
                print(f"SUCCESS! Index '{index_name}' created.")
                print(f"Response: {response_body}")
                return True

            elif response.status == 400 and 'resource_already_exists_exception' in response_body:
                print(f"Index '{index_name}' already exists. Continuing...")
                return True

            elif response.status == 403:
                # Data access policy hasn't propagated yet
                wait_time = min(30 + (15 * attempt), 120)  # Start at 30s, increase by 15s each time
                print(f"Got 403 (policy not propagated yet). Response: {response_body}")
                print(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                continue

            else:
                print(f"Unexpected response status: {response.status}")
                print(f"Response: {response_body}")
                wait_time = min(30 + (15 * attempt), 120)
                print(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
                continue

        except Exception as e:
            print(f"Error: {str(e)}")
            wait_time = min(30 + (15 * attempt), 120)
            print(f"Waiting {wait_time}s before retry...")
            time.sleep(wait_time)

    print(f"FAILED: Could not create index after {max_retries} attempts")
    return False


def main():
    parser = argparse.ArgumentParser(description='Create OpenSearch index for Bedrock Knowledge Base')
    parser.add_argument('--endpoint', required=True, help='OpenSearch Serverless endpoint')
    parser.add_argument('--index-name', default='bedrock-knowledge-base-index', help='Index name')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--max-retries', type=int, default=20, help='Max retry attempts')
    args = parser.parse_args()

    success = create_index(
        endpoint=args.endpoint,
        index_name=args.index_name,
        region=args.region,
        max_retries=args.max_retries
    )

    exit(0 if success else 1)


if __name__ == '__main__':
    main()
