#!/usr/bin/env node
const cdk = require('aws-cdk-lib');
const { StrandsAgentStack } = require('../lib/strands-agent-stack');

const app = new cdk.App();

new StrandsAgentStack(app, 'StrandsAgentStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-west-2'
  },
  description: 'Strands Agent with Streamlit on EC2 behind CloudFront'
});

app.synth();
