const cdk = require('aws-cdk-lib');
const ec2 = require('aws-cdk-lib/aws-ec2');
const iam = require('aws-cdk-lib/aws-iam');
const route53 = require('aws-cdk-lib/aws-route53');
const { addOfficeIngressRules } = require('./constants/office-ips');

// DNS Configuration
const DNS_DOMAIN = 'mrrobot.dev';
const DNS_HOSTED_ZONE_ID = 'Z00099541PMCE1WUL76PK';

class MrRobotAiCoreStack extends cdk.Stack {
  constructor(scope, id, props) {
    super(scope, id, props);

    // VPC - use existing nonpci VPC in us-east-1
    const vpc = ec2.Vpc.fromLookup(this, 'NonPciVPC', {
      vpcId: 'vpc-5c8c1725'  // mrrobot-nonpci VPC in dev
    });

    // Security Group for EC2
    const securityGroup = new ec2.SecurityGroup(this, 'StreamlitSG', {
      vpc,
      description: 'Security group for Streamlit EC2 instance',
      allowAllOutbound: true
    });

    // Allow HTTP from CloudFront (we'll use origin shield)
    securityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(8501),
      'Allow Streamlit port'
    );

    // Allow MCP server port from office/VPN IPs only
    addOfficeIngressRules(securityGroup, ec2.Port.tcp(8080), 'MCP server', ec2);

    // Allow SSH for debugging (restrict in production)
    securityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(22),
      'Allow SSH'
    );

    // IAM Role for EC2 with Bedrock access
    const ec2Role = new iam.Role(this, 'StreamlitEC2Role', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      description: 'Role for Streamlit EC2 instance with Bedrock access'
    });

    // Add Bedrock permissions
    ec2Role.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'bedrock:InvokeModel',
        'bedrock:InvokeModelWithResponseStream',
        'bedrock-runtime:InvokeModel',
        'bedrock-runtime:InvokeModelWithResponseStream'
      ],
      resources: ['*']
    }));

    // Add Bedrock Knowledge Base retrieve permissions (for MCP server)
    ec2Role.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'bedrock:Retrieve',
        'bedrock:RetrieveAndGenerate',
        'bedrock-agent-runtime:Retrieve',
        'bedrock-agent-runtime:RetrieveAndGenerate'
      ],
      resources: ['*']
    }));

    // Add SSM for Session Manager access
    ec2Role.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore')
    );

    // Add Secrets Manager access for API tokens (Bitbucket, etc.)
    ec2Role.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'secretsmanager:GetSecretValue'
      ],
      resources: [
        `arn:aws:secretsmanager:${this.region}:${this.account}:secret:mrrobot-ai-core/*`
      ]
    }));

    // User data script - install system dependencies only
    // App code is deployed separately via: ./scripts/deploy-to-ec2.sh
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      '#!/bin/bash',
      'set -e',
      '',
      '# Install Python 3.11 and dependencies',
      'yum update -y',
      'yum install -y python3.11 python3.11-pip git',
      '',
      '# Create app directory with correct ownership',
      'mkdir -p /opt/mrrobot-ai-core',
      'chown -R ec2-user:ec2-user /opt/mrrobot-ai-core',
      '',
      '# Create systemd service for Streamlit',
      'cat > /etc/systemd/system/streamlit.service << \'EOF\'',
      '[Unit]',
      'Description=Streamlit App',
      'After=network.target',
      '',
      '[Service]',
      'Type=simple',
      'User=ec2-user',
      'WorkingDirectory=/opt/mrrobot-ai-core',
      'Environment=AWS_DEFAULT_REGION=us-east-1',
      'ExecStart=/usr/bin/python3.11 -m streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true',
      'Restart=always',
      'RestartSec=3',
      '',
      '[Install]',
      'WantedBy=multi-user.target',
      'EOF',
      '',
      '# Create systemd service for MCP server',
      'cat > /etc/systemd/system/mcp-server.service << \'EOF\'',
      '[Unit]',
      'Description=MCP Server for Bedrock KB',
      'After=network.target',
      '',
      '[Service]',
      'Type=simple',
      'User=ec2-user',
      'WorkingDirectory=/opt/mrrobot-ai-core/mcp-servers',
      'Environment=AWS_DEFAULT_REGION=us-east-1',
      'Environment=CODE_KB_ID=SAJJWYFTNG',
      'ExecStart=/usr/bin/python3.11 /opt/mrrobot-ai-core/mcp-servers/bedrock-kb-server.py --sse --port 8080',
      'Restart=always',
      'RestartSec=3',
      '',
      '[Install]',
      'WantedBy=multi-user.target',
      'EOF',
      '',
      '# Enable services (start after deploy)',
      'systemctl daemon-reload',
      'systemctl enable streamlit mcp-server'
    );

    // EC2 Instance - use a specific public subnet
    const instance = new ec2.Instance(this, 'StreamlitInstance', {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
      machineImage: ec2.MachineImage.latestAmazonLinux2023(),
      securityGroup,
      role: ec2Role,
      userData,
      keyPair: ec2.KeyPair.fromKeyPairName(this, 'KeyPair', 'streamlit-key'),
      blockDevices: [{
        deviceName: '/dev/xvda',
        volume: ec2.BlockDeviceVolume.ebs(30, {
          volumeType: ec2.EbsDeviceVolumeType.GP3
        })
      }],
      associatePublicIpAddress: true,  // Request public IP assignment
    });

    // Elastic IP for consistent public access
    const eip = new ec2.CfnEIP(this, 'StreamlitEIP', {
      domain: 'vpc',
    });

    // Associate EIP with instance
    new ec2.CfnEIPAssociation(this, 'StreamlitEIPAssociation', {
      instanceId: instance.instanceId,
      allocationId: eip.attrAllocationId,
    });

    // ========================================================================
    // DNS Records (Route53)
    // ========================================================================
    const hostedZone = route53.HostedZone.fromHostedZoneAttributes(this, 'HostedZone', {
      hostedZoneId: DNS_HOSTED_ZONE_ID,
      zoneName: DNS_DOMAIN,
    });

    // A record for MCP server: mcp.mrrobot.dev
    new route53.ARecord(this, 'McpDnsRecord', {
      zone: hostedZone,
      recordName: 'mcp',
      target: route53.RecordTarget.fromIpAddresses(eip.ref),
      ttl: cdk.Duration.minutes(5),
      comment: 'MCP Server for AI IDE integration',
    });

    // A record for Streamlit: ai-agent.mrrobot.dev
    new route53.ARecord(this, 'StreamlitDnsRecord', {
      zone: hostedZone,
      recordName: 'ai-agent',
      target: route53.RecordTarget.fromIpAddresses(eip.ref),
      ttl: cdk.Duration.minutes(5),
      comment: 'Streamlit AI Agent UI',
    });

    // Outputs
    new cdk.CfnOutput(this, 'EC2InstanceId', {
      value: instance.instanceId,
      description: 'EC2 Instance ID'
    });

    new cdk.CfnOutput(this, 'EC2PublicIP', {
      value: eip.ref,
      description: 'EC2 Elastic IP'
    });

    new cdk.CfnOutput(this, 'StreamlitURL', {
      value: `http://ai-agent.${DNS_DOMAIN}:8501`,
      description: 'Streamlit URL'
    });

    new cdk.CfnOutput(this, 'MCPServerURL', {
      value: `http://mcp.${DNS_DOMAIN}:8080/sse`,
      description: 'MCP Server URL for Cursor'
    });

    new cdk.CfnOutput(this, 'CursorMCPConfig', {
      value: `{"mcpServers":{"mrrobot-code-kb":{"url":"http://mcp.${DNS_DOMAIN}:8080/sse","transport":"sse"}}}`,
      description: 'Cursor MCP config JSON'
    });

    new cdk.CfnOutput(this, 'McpDnsName', {
      value: `mcp.${DNS_DOMAIN}`,
      description: 'MCP Server DNS name'
    });

    new cdk.CfnOutput(this, 'StreamlitDnsName', {
      value: `ai-agent.${DNS_DOMAIN}`,
      description: 'Streamlit DNS name'
    });
  }
}

module.exports = { MrRobotAiCoreStack };
