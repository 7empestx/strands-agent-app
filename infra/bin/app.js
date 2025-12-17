#!/usr/bin/env node
const cdk = require('aws-cdk-lib');
const { StrandsAgentStack } = require('../lib/strands-agent-stack');
const { KnowledgeBaseStack } = require('../lib/knowledge-base-stack');
const { getKbEnv, getEc2Env } = require('../lib/constants/aws-accounts');

const app = new cdk.App();

// EC2 + CloudFront stack for Streamlit app
new StrandsAgentStack(app, 'StrandsAgentStack', {
  env: getEc2Env('dev'),
  description: 'Strands Agent with Streamlit on EC2 behind CloudFront'
});

// Knowledge Base stack for code search (us-east-1)
new KnowledgeBaseStack(app, 'CodeKnowledgeBaseStack', {
  env: getKbEnv('dev'),
  environment: 'dev',
  description: 'Bedrock Knowledge Base for MrRobot code repositories'
});

app.synth();
