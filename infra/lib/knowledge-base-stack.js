const cdk = require('aws-cdk-lib');
const s3 = require('aws-cdk-lib/aws-s3');
const iam = require('aws-cdk-lib/aws-iam');
const opensearchserverless = require('aws-cdk-lib/aws-opensearchserverless');
const bedrock = require('aws-cdk-lib/aws-bedrock');

/**
 * CDK Stack for MrRobot Code Knowledge Base
 *
 * Deployment is split into two phases due to OpenSearch policy propagation delays:
 *
 * Phase 1: Deploy with SKIP_KB=true
 *   - Creates OpenSearch collection and policies
 *   - Creates IAM roles and S3 bucket reference
 *   - Wait for collection to become ACTIVE
 *
 * Phase 2: Create index and deploy KB
 *   - Run: python scripts/create-opensearch-index.py --endpoint <endpoint>
 *   - Deploy again with SKIP_KB=false (default)
 *
 * Usage:
 *   # Phase 1: Deploy collection only
 *   SKIP_KB=true cdk deploy CodeKnowledgeBaseStack
 *
 *   # Wait ~10 min for policy propagation, then create index
 *   python scripts/create-opensearch-index.py --endpoint <collection-endpoint>
 *
 *   # Phase 2: Deploy Knowledge Base
 *   cdk deploy CodeKnowledgeBaseStack
 */
class KnowledgeBaseStack extends cdk.Stack {
  constructor(scope, id, props) {
    super(scope, id, props);

    const projectName = 'mrrobot-code-kb';
    const environment = props?.environment || 'dev';
    const indexName = 'bedrock-knowledge-base-index';

    // Check if we should skip KB creation (for phase 1 deployment)
    const skipKb = process.env.SKIP_KB === 'true';

    // ========================================================================
    // S3 Bucket for Code Storage
    // ========================================================================
    // Import existing bucket that was created from previous deployment
    const bucketName = `${projectName}-${environment}-${this.account}`;
    const codeBucket = s3.Bucket.fromBucketName(this, 'CodeBucket', bucketName);

    // ========================================================================
    // IAM Role for Bedrock Knowledge Base
    // ========================================================================
    const bedrockKbRole = new iam.Role(this, 'BedrockKBRole', {
      roleName: `${projectName}-bedrock-kb-role`,
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
      description: 'Role for Bedrock Knowledge Base to access S3 and OpenSearch',
    });

    // ========================================================================
    // OpenSearch Serverless Collection
    // ========================================================================

    // Encryption policy (required before creating collection)
    const encryptionPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'EncryptionPolicy', {
      name: `${projectName}-encryption`,
      type: 'encryption',
      description: `Encryption policy for ${projectName}`,
      policy: JSON.stringify({
        Rules: [
          {
            Resource: [`collection/${projectName}-vectors`],
            ResourceType: 'collection',
          },
        ],
        AWSOwnedKey: true,
      }),
    });

    // Network policy (required before creating collection)
    const networkPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'NetworkPolicy', {
      name: `${projectName}-network`,
      type: 'network',
      description: `Network policy for ${projectName}`,
      policy: JSON.stringify([
        {
          Rules: [
            {
              Resource: [`collection/${projectName}-vectors`],
              ResourceType: 'collection',
            },
          ],
          AllowFromPublic: true,
        },
      ]),
    });

    // Data access policy - includes Bedrock role for index operations
    const dataAccessPolicy = new opensearchserverless.CfnAccessPolicy(this, 'DataAccessPolicy', {
      name: `${projectName}-data`,
      type: 'data',
      description: `Data access policy for ${projectName}`,
      policy: JSON.stringify([
        {
          Rules: [
            {
              Resource: [`collection/${projectName}-vectors`],
              ResourceType: 'collection',
              Permission: [
                'aoss:CreateCollectionItems',
                'aoss:DeleteCollectionItems',
                'aoss:UpdateCollectionItems',
                'aoss:DescribeCollectionItems',
              ],
            },
            {
              Resource: [`index/${projectName}-vectors/*`],
              ResourceType: 'index',
              Permission: [
                'aoss:CreateIndex',
                'aoss:DeleteIndex',
                'aoss:UpdateIndex',
                'aoss:DescribeIndex',
                'aoss:ReadDocument',
                'aoss:WriteDocument',
              ],
            },
          ],
          Principal: [
            bedrockKbRole.roleArn,
            // SSO DevOps Admin role for manual index creation (assumed-role format for AOSS)
            `arn:aws:sts::${this.account}:assumed-role/AWSReservedSSO_dev_DevopsAdmin_81d454ff0550d313/*`,
            // Fallback: account root
            `arn:aws:iam::${this.account}:root`,
          ],
        },
      ]),
    });

    // OpenSearch Serverless Collection
    const vectorCollection = new opensearchserverless.CfnCollection(this, 'VectorCollection', {
      name: `${projectName}-vectors`,
      type: 'VECTORSEARCH',
      description: `Vector store for ${projectName} code embeddings`,
    });

    // Add dependencies
    vectorCollection.addDependency(encryptionPolicy);
    vectorCollection.addDependency(networkPolicy);
    vectorCollection.addDependency(dataAccessPolicy);

    // ========================================================================
    // IAM Policies for Bedrock KB Role
    // ========================================================================

    // S3 access
    bedrockKbRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['s3:GetObject', 's3:ListBucket'],
      resources: [codeBucket.bucketArn, `${codeBucket.bucketArn}/*`],
    }));

    // Bedrock model access for embeddings
    bedrockKbRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['bedrock:InvokeModel'],
      resources: [`arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`],
    }));

    // OpenSearch Serverless access
    bedrockKbRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['aoss:APIAccessAll'],
      resources: [`arn:aws:aoss:${this.region}:${this.account}:collection/*`],
    }));

    // ========================================================================
    // Outputs (always available)
    // ========================================================================
    new cdk.CfnOutput(this, 'S3BucketName', {
      value: bucketName,
      description: 'S3 bucket for code storage',
      exportName: `${projectName}-bucket-name`,
    });

    new cdk.CfnOutput(this, 'OpenSearchCollectionEndpoint', {
      value: vectorCollection.attrCollectionEndpoint,
      description: 'OpenSearch Serverless collection endpoint',
    });

    new cdk.CfnOutput(this, 'OpenSearchCollectionArn', {
      value: vectorCollection.attrArn,
      description: 'OpenSearch Serverless collection ARN',
    });

    new cdk.CfnOutput(this, 'IndexCreationCommand', {
      value: `AWS_PROFILE=dev python scripts/create-opensearch-index.py --endpoint ${vectorCollection.attrCollectionEndpoint} --region ${this.region}`,
      description: 'Command to create the OpenSearch index after collection is active',
    });

    // ========================================================================
    // Bedrock Knowledge Base (Phase 2 - only when not skipping)
    // ========================================================================
    if (!skipKb) {
      const knowledgeBase = new bedrock.CfnKnowledgeBase(this, 'CodeKnowledgeBase', {
        name: `${projectName}-knowledge-base`,
        description: 'Knowledge base for MrRobot code repositories',
        roleArn: bedrockKbRole.roleArn,
        knowledgeBaseConfiguration: {
          type: 'VECTOR',
          vectorKnowledgeBaseConfiguration: {
            embeddingModelArn: `arn:aws:bedrock:${this.region}::foundation-model/amazon.titan-embed-text-v2:0`,
          },
        },
        storageConfiguration: {
          type: 'OPENSEARCH_SERVERLESS',
          opensearchServerlessConfiguration: {
            collectionArn: vectorCollection.attrArn,
            vectorIndexName: indexName,
            fieldMapping: {
              vectorField: 'bedrock-knowledge-base-vector',
              textField: 'AMAZON_BEDROCK_TEXT_CHUNK',
              metadataField: 'AMAZON_BEDROCK_METADATA',
            },
          },
        },
      });

      // Knowledge base depends on collection being ready
      knowledgeBase.node.addDependency(vectorCollection);

      // ========================================================================
      // Bedrock Data Source (S3)
      // ========================================================================
      const dataSource = new bedrock.CfnDataSource(this, 'CodeDataSource', {
        name: `${projectName}-code-source`,
        knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
        dataDeletionPolicy: 'RETAIN',
        dataSourceConfiguration: {
          type: 'S3',
          s3Configuration: {
            bucketArn: codeBucket.bucketArn,
          },
        },
        vectorIngestionConfiguration: {
          chunkingConfiguration: {
            chunkingStrategy: 'SEMANTIC',
            semanticChunkingConfiguration: {
              maxTokens: 300,
              bufferSize: 0,
              breakpointPercentileThreshold: 95,
            },
          },
        },
      });

      // Additional outputs for KB
      new cdk.CfnOutput(this, 'KnowledgeBaseId', {
        value: knowledgeBase.attrKnowledgeBaseId,
        description: 'Bedrock Knowledge Base ID',
        exportName: `${projectName}-kb-id`,
      });

      new cdk.CfnOutput(this, 'DataSourceId', {
        value: dataSource.attrDataSourceId,
        description: 'Bedrock Data Source ID',
        exportName: `${projectName}-ds-id`,
      });

      // Export for easy env var setup
      new cdk.CfnOutput(this, 'EnvVarsCommand', {
        value: `export CODE_KB_ID=${knowledgeBase.attrKnowledgeBaseId} CODE_KB_BUCKET=${bucketName}`,
        description: 'Command to set environment variables',
      });
    } else {
      // When skipping KB, output instructions
      new cdk.CfnOutput(this, 'NextSteps', {
        value: 'Phase 1 complete. Wait 10+ min for policies to propagate, then run the index creation command and redeploy without SKIP_KB.',
        description: 'Next steps for deployment',
      });
    }
  }
}

module.exports = { KnowledgeBaseStack };
