const cdk = require('aws-cdk-lib');
const ec2 = require('aws-cdk-lib/aws-ec2');
const iam = require('aws-cdk-lib/aws-iam');
const cloudfront = require('aws-cdk-lib/aws-cloudfront');
const origins = require('aws-cdk-lib/aws-cloudfront-origins');

class StrandsAgentStack extends cdk.Stack {
  constructor(scope, id, props) {
    super(scope, id, props);

    // VPC - use default VPC for simplicity
    const vpc = ec2.Vpc.fromLookup(this, 'DefaultVPC', {
      isDefault: true
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

    // Add SSM for Session Manager access
    ec2Role.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore')
    );

    // User data script to set up the EC2 instance
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      '#!/bin/bash',
      'set -e',
      '',
      '# Update system',
      'yum update -y',
      '',
      '# Install Python 3.11 and pip',
      'yum install -y python3.11 python3.11-pip git',
      '',
      '# Create app directory',
      'mkdir -p /opt/strands-agent-app',
      'cd /opt/strands-agent-app',
      '',
      '# Clone or copy your app (placeholder - replace with your repo)',
      '# git clone https://github.com/YOUR_REPO/strands-agent-app.git .',
      '',
      '# Create a simple placeholder app for now',
      'cat > requirements.txt << \'EOF\'',
      'streamlit>=1.28.0',
      'strands-agents>=1.0.0',
      'boto3>=1.26.0',
      'pandas>=1.3.0',
      'plotly>=5.0.0',
      'EOF',
      '',
      '# Install dependencies',
      'python3.11 -m pip install -r requirements.txt',
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
      'WorkingDirectory=/opt/strands-agent-app',
      'Environment=AWS_DEFAULT_REGION=us-west-2',
      'ExecStart=/usr/bin/python3.11 -m streamlit run app.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true',
      'Restart=always',
      'RestartSec=3',
      '',
      '[Install]',
      'WantedBy=multi-user.target',
      'EOF',
      '',
      '# Set permissions',
      'chown -R ec2-user:ec2-user /opt/strands-agent-app',
      '',
      '# Enable and start service (will fail until app is deployed)',
      'systemctl daemon-reload',
      'systemctl enable streamlit',
      '# systemctl start streamlit  # Uncomment after deploying app code'
    );

    // EC2 Instance
    const instance = new ec2.Instance(this, 'StreamlitInstance', {
      vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T3, ec2.InstanceSize.MEDIUM),
      machineImage: ec2.MachineImage.latestAmazonLinux2023(),
      securityGroup,
      role: ec2Role,
      userData,
      keyPair: ec2.KeyPair.fromKeyPairName(this, 'KeyPair', 'streamlit-key'), // Create this key pair first
      blockDevices: [{
        deviceName: '/dev/xvda',
        volume: ec2.BlockDeviceVolume.ebs(30, {
          volumeType: ec2.EbsDeviceVolumeType.GP3
        })
      }]
    });

    // CloudFront Distribution
    const distribution = new cloudfront.Distribution(this, 'StreamlitDistribution', {
      defaultBehavior: {
        origin: new origins.HttpOrigin(instance.instancePublicDnsName, {
          protocolPolicy: cloudfront.OriginProtocolPolicy.HTTP_ONLY,
          httpPort: 8501
        }),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_ALL,
        cachePolicy: cloudfront.CachePolicy.CACHING_DISABLED, // Disable caching for dynamic content
        originRequestPolicy: cloudfront.OriginRequestPolicy.ALL_VIEWER
      },
      comment: 'Strands Agent Streamlit App'
    });

    // Outputs
    new cdk.CfnOutput(this, 'EC2InstanceId', {
      value: instance.instanceId,
      description: 'EC2 Instance ID'
    });

    new cdk.CfnOutput(this, 'EC2PublicIP', {
      value: instance.instancePublicIp,
      description: 'EC2 Public IP'
    });

    new cdk.CfnOutput(this, 'EC2PublicDNS', {
      value: instance.instancePublicDnsName,
      description: 'EC2 Public DNS'
    });

    new cdk.CfnOutput(this, 'CloudFrontURL', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'CloudFront Distribution URL'
    });

    new cdk.CfnOutput(this, 'StreamlitDirectURL', {
      value: `http://${instance.instancePublicDnsName}:8501`,
      description: 'Direct Streamlit URL (for testing)'
    });
  }
}

module.exports = { StrandsAgentStack };
