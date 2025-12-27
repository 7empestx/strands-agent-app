const cdk = require('aws-cdk-lib');
const ec2 = require('aws-cdk-lib/aws-ec2');
const ecs = require('aws-cdk-lib/aws-ecs');
const ecr = require('aws-cdk-lib/aws-ecr');
const elbv2 = require('aws-cdk-lib/aws-elasticloadbalancingv2');
const iam = require('aws-cdk-lib/aws-iam');
const logs = require('aws-cdk-lib/aws-logs');
const route53 = require('aws-cdk-lib/aws-route53');
const route53targets = require('aws-cdk-lib/aws-route53-targets');
const acm = require('aws-cdk-lib/aws-certificatemanager');
const dynamodb = require('aws-cdk-lib/aws-dynamodb');
const secretsmanager = require('aws-cdk-lib/aws-secretsmanager');
const { addOfficeIngressRules } = require('./constants/office-ips');
const { VPCS, HOSTED_ZONES, DNS_SUBDOMAINS } = require('./constants/aws-accounts');

class StrandsAgentECSStack extends cdk.Stack {
  constructor(scope, id, props) {
    super(scope, id, props);

    // Get environment from props (defaults to 'dev')
    const environment = props?.environment || 'dev';

    // Environment-specific configuration
    const vpcId = VPCS[environment];
    const hostedZoneConfig = HOSTED_ZONES[environment];
    const dnsSubdomains = DNS_SUBDOMAINS[environment];

    if (!vpcId || !hostedZoneConfig) {
      throw new Error(`Missing configuration for environment: ${environment}`);
    }

    // VPC - use existing nonpci VPC
    const vpc = ec2.Vpc.fromLookup(this, 'NonPciVPC', {
      vpcId: vpcId
    });

    // ========================================================================
    // ECR Repositories - use existing ones
    // ========================================================================
    const streamlitRepo = ecr.Repository.fromRepositoryName(this, 'StreamlitRepo', 'mrrobot-streamlit');
    const mcpServerRepo = ecr.Repository.fromRepositoryName(this, 'McpServerRepo', 'mrrobot-mcp-server');

    // ========================================================================
    // Security Groups
    // ========================================================================
    const albSecurityGroup = new ec2.SecurityGroup(this, 'ALBSecurityGroup', {
      vpc,
      description: 'Security group for ALB',
      allowAllOutbound: true
    });

    // ALB ingress - HTTP from office/VPN IPs only (redirects to HTTPS)
    addOfficeIngressRules(albSecurityGroup, ec2.Port.tcp(80), 'HTTP redirect', ec2);

    // ALB ingress - HTTPS from office/VPN IPs only
    addOfficeIngressRules(albSecurityGroup, ec2.Port.tcp(443), 'HTTPS', ec2);

    const ecsSecurityGroup = new ec2.SecurityGroup(this, 'ECSSecurityGroup', {
      vpc,
      description: 'Security group for ECS tasks',
      allowAllOutbound: true
    });

    // ECS ingress - from ALB
    ecsSecurityGroup.addIngressRule(
      albSecurityGroup,
      ec2.Port.tcp(8501),
      'Allow Streamlit from ALB'
    );

    ecsSecurityGroup.addIngressRule(
      albSecurityGroup,
      ec2.Port.tcp(8080),
      'Allow MCP from ALB'
    );

    // ========================================================================
    // IAM Roles
    // ========================================================================
    // Task Execution Role (pulls images, logs, secrets)
    const taskExecutionRole = new iam.Role(this, 'ECSTaskExecutionRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      description: 'Role for ECS task execution'
    });

    // Add standard ECS task execution permissions
    taskExecutionRole.addManagedPolicy(
      iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonECSTaskExecutionRolePolicy')
    );

    // Add ECR pull permissions
    taskExecutionRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'ecr:GetAuthorizationToken',
        'ecr:BatchGetImage',
        'ecr:GetDownloadUrlForLayer'
      ],
      resources: ['*']
    }));

    // Add CloudWatch logs permissions
    taskExecutionRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'logs:CreateLogGroup',
        'logs:CreateLogStream',
        'logs:PutLogEvents'
      ],
      resources: ['arn:aws:logs:*:*:*']
    }));

    // Add Secrets Manager permissions
    taskExecutionRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['secretsmanager:GetSecretValue'],
      resources: [
        `arn:aws:secretsmanager:${this.region}:${this.account}:secret:mrrobot-ai-core/*`
      ]
    }));

    // Task Role (Bedrock, DynamoDB, S3, etc.)
    const taskRole = new iam.Role(this, 'ECSTaskRole', {
      assumedBy: new iam.ServicePrincipal('ecs-tasks.amazonaws.com'),
      description: 'Role for ECS task application permissions'
    });

    // Bedrock permissions
    taskRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'bedrock:InvokeModel',
        'bedrock:InvokeModelWithResponseStream',
        'bedrock-runtime:InvokeModel',
        'bedrock-runtime:InvokeModelWithResponseStream',
        'bedrock:Retrieve',
        'bedrock:RetrieveAndGenerate',
        'bedrock-agent-runtime:Retrieve',
        'bedrock-agent-runtime:RetrieveAndGenerate'
      ],
      resources: ['*']
    }));

    // S3 bucket name for this environment
    const s3BucketName = `mrrobot-code-kb-${environment}-${this.account}`;

    // S3 permissions for Clippy config (system prompt, service registry)
    taskRole.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        's3:GetObject',
        's3:ListBucket'
      ],
      resources: [
        `arn:aws:s3:::${s3BucketName}`,
        `arn:aws:s3:::${s3BucketName}/clippy-config/*`
      ]
    }));

    // ========================================================================
    // DynamoDB - Feedback Table
    // ========================================================================
    const feedbackTable = new dynamodb.Table(this, 'FeedbackTable', {
      tableName: `mrrobot-ai-feedback-${environment}`,
      partitionKey: { name: 'id', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.STRING },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: cdk.RemovalPolicy.RETAIN,
      pointInTimeRecovery: true,
    });

    // Grant permissions to task role
    feedbackTable.grantReadWriteData(taskRole);

    // ========================================================================
    // ECS Cluster
    // ========================================================================
    const cluster = new ecs.Cluster(this, 'MrRobotCluster', {
      vpc,
      clusterName: `mrrobot-ai-core-${environment}`,
      containerInsights: true,
      defaultCloudMapNamespace: {
        name: 'mrrobot.local'
      }
    });

    // ========================================================================
    // Application Load Balancer
    // ========================================================================
    const alb = new elbv2.ApplicationLoadBalancer(this, 'ALB', {
      vpc,
      internetFacing: true,
      securityGroup: albSecurityGroup,
      loadBalancerName: `mrrobot-ai-alb-${environment}`,
      // Select public subnets for internet-facing ALB (one per AZ)
      vpcSubnets: {
        subnetType: ec2.SubnetType.PUBLIC,
        onePerAz: true
      }
    });

    // ========================================================================
    // CloudWatch Log Groups
    // ========================================================================
    const streamlitLogGroup = new logs.LogGroup(this, 'StreamlitLogGroup', {
      logGroupName: `/ecs/mrrobot-streamlit-${environment}`,
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY
    });

    const mcpLogGroup = new logs.LogGroup(this, 'McpLogGroup', {
      logGroupName: `/ecs/mrrobot-mcp-server-${environment}`,
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY
    });

    // ========================================================================
    // Streamlit Task Definition
    // ========================================================================
    const streamlitTaskDefinition = new ecs.FargateTaskDefinition(this, 'StreamlitTask', {
      memoryLimitMiB: 1024,
      cpu: 512,
      taskRole,
      executionRole: taskExecutionRole,
      family: 'mrrobot-streamlit',
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.ARM64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX
      }
    });

    const streamlitContainer = streamlitTaskDefinition.addContainer('StreamlitContainer', {
      image: ecs.ContainerImage.fromEcrRepository(streamlitRepo, 'latest'),
      containerName: 'streamlit',
      portMappings: [
        {
          containerPort: 8501,
          protocol: ecs.Protocol.TCP
        }
      ],
      logging: ecs.LogDriver.awsLogs({
        logGroup: streamlitLogGroup,
        streamPrefix: 'ecs',
      }),
      environment: {
        'AWS_REGION': 'us-east-1'
      }
    });

    // ========================================================================
    // MCP Server Task Definition
    // ========================================================================
    const mcpTaskDefinition = new ecs.FargateTaskDefinition(this, 'McpServerTask', {
      memoryLimitMiB: 512,
      cpu: 256,
      taskRole,
      executionRole: taskExecutionRole,
      family: 'mrrobot-mcp-server',
      runtimePlatform: {
        cpuArchitecture: ecs.CpuArchitecture.ARM64,
        operatingSystemFamily: ecs.OperatingSystemFamily.LINUX
      }
    });

    // Reference to secrets in Secrets Manager
    const appSecrets = secretsmanager.Secret.fromSecretNameV2(this, 'AppSecrets', 'mrrobot-ai-core/secrets');

    const mcpContainer = mcpTaskDefinition.addContainer('McpServerContainer', {
      image: ecs.ContainerImage.fromEcrRepository(mcpServerRepo, 'latest'),
      containerName: 'mcp-server',
      portMappings: [
        {
          containerPort: 8080,
          protocol: ecs.Protocol.TCP
        }
      ],
      logging: ecs.LogDriver.awsLogs({
        logGroup: mcpLogGroup,
        streamPrefix: 'ecs',
      }),
      environment: {
        'AWS_REGION': 'us-east-1',
        'CODE_KB_ID': 'SAJJWYFTNG'
      },
      secrets: {
        // Bitbucket API credentials
        'BITBUCKET_TOKEN': ecs.Secret.fromSecretsManager(appSecrets, 'BITBUCKET_TOKEN'),
        'BITBUCKET_AUTH_TYPE': ecs.Secret.fromSecretsManager(appSecrets, 'BITBUCKET_AUTH_TYPE'),
        'BITBUCKET_EMAIL': ecs.Secret.fromSecretsManager(appSecrets, 'BITBUCKET_EMAIL'),
        // Coralogix API
        'CORALOGIX_AGENT_KEY': ecs.Secret.fromSecretsManager(appSecrets, 'CORALOGIX_AGENT_KEY'),
        // Slack API
        'SLACK_BOT_TOKEN': ecs.Secret.fromSecretsManager(appSecrets, 'SLACK_BOT_TOKEN'),
        'SLACK_APP_TOKEN': ecs.Secret.fromSecretsManager(appSecrets, 'SLACK_APP_TOKEN'),
        // Jira API
        'JIRA_API_TOKEN': ecs.Secret.fromSecretsManager(appSecrets, 'JIRA_API_TOKEN'),
        // PagerDuty API
        'PAGERDUTY_API_TOKEN': ecs.Secret.fromSecretsManager(appSecrets, 'PAGERDUTY_API_TOKEN'),
        // Atlassian API (for Confluence)
        'ATLASSIAN_API_TOKEN': ecs.Secret.fromSecretsManager(appSecrets, 'ATLASSIAN_API_TOKEN'),
      }
    });

    // ========================================================================
    // Target Groups
    // ========================================================================
    const streamlitTargetGroup = new elbv2.ApplicationTargetGroup(this, 'StreamlitTargetGroup', {
      vpc,
      port: 8501,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      targetGroupName: `mrrobot-streamlit-${environment}`,
      healthCheck: {
        path: '/',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3
      }
    });

    const mcpTargetGroup = new elbv2.ApplicationTargetGroup(this, 'McpTargetGroup', {
      vpc,
      port: 8080,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targetType: elbv2.TargetType.IP,
      targetGroupName: `mrrobot-mcp-server-${environment}`,
      healthCheck: {
        path: '/health',
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        healthyThresholdCount: 2,
        unhealthyThresholdCount: 3
      }
    });

    // ========================================================================
    // ACM Certificate for HTTPS
    // ========================================================================
    // Create certificate for the environment's domain with DNS validation
    const certificate = new acm.Certificate(this, 'Certificate', {
      domainName: `*.${hostedZoneConfig.zoneName}`,
      subjectAlternativeNames: [hostedZoneConfig.zoneName],
      validation: acm.CertificateValidation.fromDns(
        route53.HostedZone.fromHostedZoneAttributes(this, 'ValidationZone', {
          hostedZoneId: hostedZoneConfig.hostedZoneId,
          zoneName: hostedZoneConfig.zoneName,
        })
      ),
    });

    // Import Route53 hosted zone for DNS records
    const hostedZone = route53.HostedZone.fromHostedZoneAttributes(this, 'HostedZone', {
      hostedZoneId: hostedZoneConfig.hostedZoneId,
      zoneName: hostedZoneConfig.zoneName,
    });

    // ========================================================================
    // ALB Listeners & Rules
    // ========================================================================
    // HTTP Listener - redirect all traffic to HTTPS
    const httpListener = alb.addListener('HttpListener', {
      port: 80,
      protocol: elbv2.ApplicationProtocol.HTTP,
      defaultAction: elbv2.ListenerAction.redirect({
        protocol: 'HTTPS',
        port: '443',
        permanent: true,
      })
    });

    // HTTPS Listener - routes both MCP and Streamlit
    const httpsListener = alb.addListener('HttpsListener', {
      port: 443,
      protocol: elbv2.ApplicationProtocol.HTTPS,
      certificates: [certificate],
      defaultTargetGroups: [streamlitTargetGroup]  // Default to Streamlit
    });

    // Route MCP subdomain to MCP server (HTTPS)
    const mcpHostname = `${dnsSubdomains.mcp}.${hostedZoneConfig.zoneName}`;
    httpsListener.addTargetGroups('McpHostRuleHttps', {
      conditions: [
        elbv2.ListenerCondition.hostHeaders([mcpHostname])
      ],
      targetGroups: [mcpTargetGroup],
      priority: 1
    });

    // Route dashboard subdomain to MCP server (React Dashboard) (HTTPS)
    const dashboardHostname = `${dnsSubdomains.dashboard}.${hostedZoneConfig.zoneName}`;
    httpsListener.addTargetGroups('DashboardHostRuleHttps', {
      conditions: [
        elbv2.ListenerCondition.hostHeaders([dashboardHostname])
      ],
      targetGroups: [mcpTargetGroup],
      priority: 2
    });

    // ========================================================================
    // ECS Services
    // ========================================================================
    // DEPRECATED: Streamlit service - set to 0 tasks
    // React Dashboard is now served from MCP server
    const streamlitService = new ecs.FargateService(this, 'StreamlitService', {
      cluster,
      taskDefinition: streamlitTaskDefinition,
      desiredCount: 0,  // Deprecated - dashboard now served from MCP server
      serviceName: `mrrobot-streamlit-${environment}`,
      assignPublicIp: false,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS
      },
      securityGroups: [ecsSecurityGroup],
      circuitBreaker: {
        rollback: true
      }
    });

    // Attach target group
    streamlitService.attachToApplicationTargetGroup(streamlitTargetGroup);

    // Auto-scaling for Streamlit (disabled - service deprecated)
    const streamlitScaling = streamlitService.autoScaleTaskCount({
      minCapacity: 0,
      maxCapacity: 0
    });

    streamlitScaling.scaleOnCpuUtilization('StreamlitCpuScaling', {
      targetUtilizationPercent: 70
    });

    streamlitScaling.scaleOnMemoryUtilization('StreamlitMemoryScaling', {
      targetUtilizationPercent: 80
    });

    const mcpService = new ecs.FargateService(this, 'McpService', {
      cluster,
      taskDefinition: mcpTaskDefinition,
      desiredCount: 2,
      serviceName: `mrrobot-mcp-server-${environment}`,
      assignPublicIp: false,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS
      },
      securityGroups: [ecsSecurityGroup],
      circuitBreaker: {
        rollback: true
      }
    });

    // Attach target group
    mcpService.attachToApplicationTargetGroup(mcpTargetGroup);

    // Auto-scaling for MCP
    const mcpScaling = mcpService.autoScaleTaskCount({
      minCapacity: 2,
      maxCapacity: 4
    });

    mcpScaling.scaleOnCpuUtilization('McpCpuScaling', {
      targetUtilizationPercent: 70
    });

    // ========================================================================
    // Route53 DNS Records
    // ========================================================================

    // A record for Dashboard (via ALB)
    new route53.ARecord(this, 'DashboardDnsRecord', {
      zone: hostedZone,
      recordName: dnsSubdomains.dashboard,
      target: route53.RecordTarget.fromAlias(new route53targets.LoadBalancerTarget(alb)),
      ttl: cdk.Duration.minutes(5),
      comment: 'AI Agent Dashboard UI (via ALB)'
    });

    // A record for MCP server (via ALB with host routing)
    new route53.ARecord(this, 'McpDnsRecord', {
      zone: hostedZone,
      recordName: dnsSubdomains.mcp,
      target: route53.RecordTarget.fromAlias(new route53targets.LoadBalancerTarget(alb)),
      ttl: cdk.Duration.minutes(5),
      comment: 'MCP Server (via ALB)'
    });

    // ========================================================================
    // Outputs
    // ========================================================================
    new cdk.CfnOutput(this, 'ALBDnsName', {
      value: alb.loadBalancerDnsName,
      description: 'ALB DNS Name'
    });

    new cdk.CfnOutput(this, 'DashboardURL', {
      value: `https://${dashboardHostname}`,
      description: 'Dashboard URL (HTTPS)'
    });

    new cdk.CfnOutput(this, 'MCPServerURL', {
      value: `https://${mcpHostname}/sse`,
      description: 'MCP Server URL (HTTPS)'
    });

    new cdk.CfnOutput(this, 'StreamlitRepoUri', {
      value: streamlitRepo.repositoryUri,
      description: 'Streamlit ECR Repository URI'
    });

    new cdk.CfnOutput(this, 'McpServerRepoUri', {
      value: mcpServerRepo.repositoryUri,
      description: 'MCP Server ECR Repository URI'
    });

    new cdk.CfnOutput(this, 'ClusterName', {
      value: cluster.clusterName,
      description: 'ECS Cluster Name'
    });

    new cdk.CfnOutput(this, 'Environment', {
      value: environment,
      description: 'Deployment Environment'
    });
  }
}

module.exports = { StrandsAgentECSStack };
