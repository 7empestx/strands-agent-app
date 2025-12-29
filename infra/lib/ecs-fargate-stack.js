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
const events = require('aws-cdk-lib/aws-events');
const eventsTargets = require('aws-cdk-lib/aws-events-targets');
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
    // DynamoDB - Feedback Table (import existing)
    // ========================================================================
    const feedbackTableName = `mrrobot-ai-feedback-${environment}`;
    const feedbackTable = dynamodb.Table.fromTableName(this, 'FeedbackTable', feedbackTableName);

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
    const mcpLogGroup = new logs.LogGroup(this, 'McpLogGroup', {
      logGroupName: `/ecs/mrrobot-mcp-server-${environment}`,
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY
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
        'CODE_KB_ID': 'SAJJWYFTNG',
        'ENVIRONMENT': environment,
        'ENABLE_SLACK': environment === 'dev' ? 'true' : 'false',
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
    // Import existing wildcard certificate (already validated)
    // Dev: arn:aws:acm:us-east-1:720154970215:certificate/41d8ef46-ac6c-4b72-b15c-3152f978967d
    const certificateArn = environment === 'dev'
      ? 'arn:aws:acm:us-east-1:720154970215:certificate/41d8ef46-ac6c-4b72-b15c-3152f978967d'
      : `arn:aws:acm:us-east-1:${this.account}:certificate/REPLACE_WITH_PROD_CERT`;
    const certificate = acm.Certificate.fromCertificateArn(this, 'Certificate', certificateArn);

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

    // HTTPS Listener - routes to MCP server
    const httpsListener = alb.addListener('HttpsListener', {
      port: 443,
      protocol: elbv2.ApplicationProtocol.HTTPS,
      certificates: [certificate],
      defaultTargetGroups: [mcpTargetGroup]
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
    // Daily Digest Scheduled Task (dev only)
    // ========================================================================
    if (environment === 'dev') {
      // Log group for daily digest
      const digestLogGroup = new logs.LogGroup(this, 'DigestLogGroup', {
        logGroupName: `/ecs/mrrobot-daily-digest-${environment}`,
        retention: logs.RetentionDays.TWO_WEEKS,
        removalPolicy: cdk.RemovalPolicy.DESTROY
      });

      // Task definition for daily digest
      const digestTaskDefinition = new ecs.FargateTaskDefinition(this, 'DigestTask', {
        memoryLimitMiB: 512,
        cpu: 256,
        taskRole,
        executionRole: taskExecutionRole,
        family: 'mrrobot-daily-digest',
        runtimePlatform: {
          cpuArchitecture: ecs.CpuArchitecture.ARM64,
          operatingSystemFamily: ecs.OperatingSystemFamily.LINUX
        }
      });

      // Use the same MCP server image (has all dependencies)
      digestTaskDefinition.addContainer('DigestContainer', {
        image: ecs.ContainerImage.fromEcrRepository(mcpServerRepo, 'latest'),
        containerName: 'daily-digest',
        command: ['python', 'src/scheduled/daily_digest.py'],
        logging: ecs.LogDriver.awsLogs({
          logGroup: digestLogGroup,
          streamPrefix: 'ecs',
        }),
        environment: {
          'AWS_REGION': 'us-east-1',
          'ENVIRONMENT': environment,
          'SLACK_CHANNEL': '#clippy-ai-dev',
        },
        secrets: {
          'CORALOGIX_AGENT_KEY': ecs.Secret.fromSecretsManager(appSecrets, 'CORALOGIX_AGENT_KEY'),
          'BITBUCKET_TOKEN': ecs.Secret.fromSecretsManager(appSecrets, 'BITBUCKET_TOKEN'),
          'BITBUCKET_AUTH_TYPE': ecs.Secret.fromSecretsManager(appSecrets, 'BITBUCKET_AUTH_TYPE'),
          'BITBUCKET_EMAIL': ecs.Secret.fromSecretsManager(appSecrets, 'BITBUCKET_EMAIL'),
        }
      });

      // EventBridge rule to trigger daily at 9am EST (14:00 UTC)
      const digestRule = new events.Rule(this, 'DigestScheduleRule', {
        ruleName: `mrrobot-daily-digest-${environment}`,
        description: 'Triggers daily DevOps digest at 9am EST weekdays',
        schedule: events.Schedule.cron({
          minute: '0',
          hour: '14',  // 9am EST = 14:00 UTC
          weekDay: 'MON-FRI',
        }),
        enabled: true,
      });

      // Add ECS task as target
      digestRule.addTarget(new eventsTargets.EcsTask({
        cluster,
        taskDefinition: digestTaskDefinition,
        taskCount: 1,
        subnetSelection: {
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS
        },
        securityGroups: [ecsSecurityGroup],
      }));

      new cdk.CfnOutput(this, 'DigestScheduleRuleArn', {
        value: digestRule.ruleArn,
        description: 'Daily Digest EventBridge Rule ARN'
      });
    }

    // ========================================================================
    // Route53 DNS Records
    // ========================================================================
    // NOTE: DNS records are managed outside CDK (already exist in Route53)
    // ai-agent.mrrobot.dev -> ALB
    // mcp.mrrobot.dev -> ALB
    // If you need to recreate them, uncomment the code below

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
