#!/usr/bin/env node
const cdk = require('aws-cdk-lib');
const { StrandsAgentECSStack } = require('../lib/ecs-fargate-stack');
const { KnowledgeBaseStack } = require('../lib/knowledge-base-stack');
const { getKbEnv, getEc2Env } = require('../lib/constants/aws-accounts');

const app = new cdk.App();

// ========================================================================
// DEV Environment Stacks
// ========================================================================

// ECS Fargate stack for Streamlit + MCP Server + Slack Bot (dev)
new StrandsAgentECSStack(app, 'StrandsAgentECSStack', {
  env: getEc2Env('dev'),
  environment: 'dev',
  description: 'Strands Agent App - Streamlit + MCP Server on ECS Fargate (dev)'
});

// Knowledge Base stack for code search (dev)
new KnowledgeBaseStack(app, 'CodeKnowledgeBaseStack', {
  env: getKbEnv('dev'),
  environment: 'dev',
  description: 'Bedrock Knowledge Base for MrRobot code repositories (dev)'
});

// ========================================================================
// PROD Environment Stacks
// ========================================================================

// ECS Fargate stack for Streamlit + MCP Server + Slack Bot (prod)
new StrandsAgentECSStack(app, 'StrandsAgentECSStackProd', {
  env: getEc2Env('prod'),
  environment: 'prod',
  description: 'Strands Agent App - Streamlit + MCP Server on ECS Fargate (prod)'
});

// Knowledge Base stack for code search (prod)
new KnowledgeBaseStack(app, 'CodeKnowledgeBaseStackProd', {
  env: getKbEnv('prod'),
  environment: 'prod',
  description: 'Bedrock Knowledge Base for MrRobot code repositories (prod)'
});

app.synth();
