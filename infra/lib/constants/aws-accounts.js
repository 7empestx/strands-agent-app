/**
 * AWS Account and Environment Configuration
 * Centralized config for CDK stacks across environments.
 *
 * Usage:
 *   const { getEnv, ACCOUNTS, REGIONS } = require('./constants/aws-accounts');
 *
 *   // Get environment for a specific use case
 *   const kbEnv = getEnv('dev', 'us-east-1');
 *   const ec2Env = getEnv('dev');  // uses default region (us-west-2)
 *
 *   // Use in stack
 *   new MyStack(app, 'MyStack', { env: kbEnv });
 */

const ACCOUNTS = {
  dev: '720154970215',
  prod: '246295362269',
};

// VPC IDs per environment
const VPCS = {
  dev: 'vpc-5c8c1725',   // mrrobot-nonpci-vpc-dev (10.1.0.0/16)
  prod: 'vpc-1630aa6f',  // mrrobot-nonpci-vpc-prod (10.3.0.0/16)
};

// Route53 Hosted Zones per environment
const HOSTED_ZONES = {
  dev: {
    zoneName: 'mrrobot.dev',
    hostedZoneId: 'Z00099541PMCE1WUL76PK',
  },
  prod: {
    zoneName: 'nex.io',
    hostedZoneId: 'Z00877603802KT7RM0LE9',
  },
};

// DNS subdomains for services (same across environments, just different domains)
const DNS_SUBDOMAINS = {
  dev: {
    mcp: 'mcp',           // mcp.mrrobot.dev
    dashboard: 'ai-agent', // ai-agent.mrrobot.dev
  },
  prod: {
    mcp: 'mcp',           // mcp.nex.io
    dashboard: 'ai-agent', // ai-agent.nex.io
  },
};

const REGIONS = {
  default: 'us-east-1',
  knowledgeBase: 'us-east-1',  // Bedrock KB uses us-east-1
  ec2: 'us-east-1',  // EC2 uses nonpci VPC in us-east-1
};

/**
 * Get CDK environment configuration for a given account and region.
 *
 * @param {string} environment - Environment name ('dev', 'prod', etc.)
 * @param {string} [region] - AWS region (defaults to REGIONS.default)
 * @returns {object} CDK environment config { account, region }
 */
function getEnv(environment, region) {
  const account = process.env.CDK_DEFAULT_ACCOUNT || ACCOUNTS[environment];
  if (!account) {
    throw new Error(`Unknown environment: ${environment}. Available: ${Object.keys(ACCOUNTS).join(', ')}`);
  }

  return {
    account,
    region: region || process.env.CDK_DEFAULT_REGION || REGIONS.default,
  };
}

/**
 * Get environment for Knowledge Base stacks (us-east-1).
 *
 * @param {string} environment - Environment name
 * @returns {object} CDK environment config
 */
function getKbEnv(environment) {
  return getEnv(environment, REGIONS.knowledgeBase);
}

/**
 * Get environment for EC2/compute stacks (us-west-2).
 *
 * @param {string} environment - Environment name
 * @returns {object} CDK environment config
 */
function getEc2Env(environment) {
  return getEnv(environment, REGIONS.ec2);
}

module.exports = {
  ACCOUNTS,
  REGIONS,
  VPCS,
  HOSTED_ZONES,
  DNS_SUBDOMAINS,
  getEnv,
  getKbEnv,
  getEc2Env,
};
