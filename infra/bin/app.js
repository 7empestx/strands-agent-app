#!/usr/bin/env node
const cdk = require('aws-cdk-lib');
const { MrRobotAiCoreStack } = require('../lib/mrrobot-ai-core-stack');
const { StrandsAgentECSStack } = require('../lib/ecs-fargate-stack');
const { KnowledgeBaseStack } = require('../lib/knowledge-base-stack');
const { getKbEnv, getEc2Env } = require('../lib/constants/aws-accounts');

const app = new cdk.App();

// EC2 stack (legacy - can be deprecated after ECS migration)
new MrRobotAiCoreStack(app, 'MrRobotAiCoreStack', {
  env: getEc2Env('dev'),
  description: 'MrRobot AI Core - DevOps agents and MCP server on EC2 (DEPRECATED - use ECS instead)'
});

// NEW: ECS Fargate stack for Streamlit + MCP Server
new StrandsAgentECSStack(app, 'StrandsAgentECSStack', {
  env: getEc2Env('dev'),
  description: 'Strands Agent App - Streamlit + MCP Server on ECS Fargate'
});

// Knowledge Base stack for code search (us-east-1)
new KnowledgeBaseStack(app, 'CodeKnowledgeBaseStack', {
  env: getKbEnv('dev'),
  environment: 'dev',
  description: 'Bedrock Knowledge Base for MrRobot code repositories'
});

app.synth();
