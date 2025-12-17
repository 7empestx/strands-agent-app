#!/usr/bin/env node
const cdk = require('aws-cdk-lib');
const { MrRobotAiCoreStack } = require('../lib/mrrobot-ai-core-stack');
const { KnowledgeBaseStack } = require('../lib/knowledge-base-stack');
const { getKbEnv, getEc2Env } = require('../lib/constants/aws-accounts');

const app = new cdk.App();

// EC2 + CloudFront stack for Streamlit app
new MrRobotAiCoreStack(app, 'MrRobotAiCoreStack', {
  env: getEc2Env('dev'),
  description: 'MrRobot AI Core - DevOps agents and MCP server on EC2'
});

// Knowledge Base stack for code search (us-east-1)
new KnowledgeBaseStack(app, 'CodeKnowledgeBaseStack', {
  env: getKbEnv('dev'),
  environment: 'dev',
  description: 'Bedrock Knowledge Base for MrRobot code repositories'
});

app.synth();
