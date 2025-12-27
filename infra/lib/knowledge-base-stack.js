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
      roleName: `${projectName}-${environment}-bedrock-kb-role`,
      assumedBy: new iam.ServicePrincipal('bedrock.amazonaws.com'),
      description: `Role for Bedrock Knowledge Base to access S3 and OpenSearch (${environment})`,
    });

    // ========================================================================
    // OpenSearch Serverless Collection
    // ========================================================================

    // Encryption policy (required before creating collection)
    const encryptionPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'EncryptionPolicy', {
      name: `${projectName}-${environment}-enc`,
      type: 'encryption',
      description: `Encryption policy for ${projectName} (${environment})`,
      policy: JSON.stringify({
        Rules: [
          {
            Resource: [`collection/${projectName}-${environment}-vectors`],
            ResourceType: 'collection',
          },
        ],
        AWSOwnedKey: true,
      }),
    });

    // Network policy (required before creating collection)
    const networkPolicy = new opensearchserverless.CfnSecurityPolicy(this, 'NetworkPolicy', {
      name: `${projectName}-${environment}-net`,
      type: 'network',
      description: `Network policy for ${projectName} (${environment})`,
      policy: JSON.stringify([
        {
          Rules: [
            {
              Resource: [`collection/${projectName}-${environment}-vectors`],
              ResourceType: 'collection',
            },
          ],
          AllowFromPublic: true,
        },
      ]),
    });

    // SSO role patterns per environment (for manual index creation)
    const ssoRolePatterns = {
      dev: `arn:aws:sts::${this.account}:assumed-role/AWSReservedSSO_dev_DevopsAdmin_81d454ff0550d313/*`,
      prod: `arn:aws:sts::${this.account}:assumed-role/AWSReservedSSO_prod_DevopsAdmin_3f32883e19494337/*`,
    };

    // Data access policy - includes Bedrock role for index operations
    const dataAccessPolicy = new opensearchserverless.CfnAccessPolicy(this, 'DataAccessPolicy', {
      name: `${projectName}-${environment}-data`,
      type: 'data',
      description: `Data access policy for ${projectName} (${environment})`,
      policy: JSON.stringify([
        {
          Rules: [
            {
              Resource: [`collection/${projectName}-${environment}-vectors`],
              ResourceType: 'collection',
              Permission: [
                'aoss:CreateCollectionItems',
                'aoss:DeleteCollectionItems',
                'aoss:UpdateCollectionItems',
                'aoss:DescribeCollectionItems',
              ],
            },
            {
              Resource: [`index/${projectName}-${environment}-vectors/*`],
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
            ssoRolePatterns[environment] || `arn:aws:iam::${this.account}:root`,
            // Fallback: account root
            `arn:aws:iam::${this.account}:root`,
          ],
        },
      ]),
    });

    // OpenSearch Serverless Collection
    const vectorCollection = new opensearchserverless.CfnCollection(this, 'VectorCollection', {
      name: `${projectName}-${environment}-vectors`,
      type: 'VECTORSEARCH',
      description: `Vector store for ${projectName} code embeddings (${environment})`,
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

    // AWS profile for commands based on environment
    const awsProfile = environment === 'prod' ? 'prod' : 'dev';

    new cdk.CfnOutput(this, 'IndexCreationCommand', {
      value: `AWS_PROFILE=${awsProfile} python scripts/create-opensearch-index.py --endpoint ${vectorCollection.attrCollectionEndpoint} --region ${this.region}`,
      description: 'Command to create the OpenSearch index after collection is active',
    });

    // ========================================================================
    // Bedrock Knowledge Base (Phase 2 - only when not skipping)
    // ========================================================================
    if (!skipKb) {
      const knowledgeBase = new bedrock.CfnKnowledgeBase(this, 'CodeKnowledgeBase', {
        name: `${projectName}-${environment}-knowledge-base`,
        description: `Knowledge base for MrRobot code repositories (${environment})`,
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
      // Bedrock Data Source - Code Repos (S3)
      // ========================================================================
      const codeDataSource = new bedrock.CfnDataSource(this, 'CodeDataSource', {
        name: `${projectName}-${environment}-code-source`,
        knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
        dataDeletionPolicy: 'RETAIN',
        dataSourceConfiguration: {
          type: 'S3',
          s3Configuration: {
            bucketArn: codeBucket.bucketArn,
            inclusionPrefixes: ['repos/'],
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

      // ========================================================================
      // Bedrock Data Source - Slack History (S3)
      // ========================================================================
      const slackDataSource = new bedrock.CfnDataSource(this, 'SlackDataSource', {
        name: `${projectName}-${environment}-slack-history`,
        knowledgeBaseId: knowledgeBase.attrKnowledgeBaseId,
        dataDeletionPolicy: 'RETAIN',
        dataSourceConfiguration: {
          type: 'S3',
          s3Configuration: {
            bucketArn: codeBucket.bucketArn,
            inclusionPrefixes: ['slack-history/'],
          },
        },
        vectorIngestionConfiguration: {
          chunkingConfiguration: {
            chunkingStrategy: 'FIXED_SIZE',
            fixedSizeChunkingConfiguration: {
              maxTokens: 500,
              overlapPercentage: 20,
            },
          },
        },
      });

      // Additional outputs for KB
      new cdk.CfnOutput(this, 'KnowledgeBaseId', {
        value: knowledgeBase.attrKnowledgeBaseId,
        description: 'Bedrock Knowledge Base ID',
        exportName: `${projectName}-${environment}-kb-id`,
      });

      new cdk.CfnOutput(this, 'CodeDataSourceId', {
        value: codeDataSource.attrDataSourceId,
        description: 'Bedrock Data Source ID for code repos',
        exportName: `${projectName}-${environment}-code-ds-id`,
      });

      new cdk.CfnOutput(this, 'SlackDataSourceId', {
        value: slackDataSource.attrDataSourceId,
        description: 'Bedrock Data Source ID for Slack history',
        exportName: `${projectName}-${environment}-slack-ds-id`,
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
