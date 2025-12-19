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
const { addOfficeIngressRules } = require('./constants/office-ips');

// DNS Configuration
const DNS_DOMAIN = 'mrrobot.dev';
const DNS_HOSTED_ZONE_ID = 'Z00099541PMCE1WUL76PK';

class StrandsAgentECSStack extends cdk.Stack {
  constructor(scope, id, props) {
    super(scope, id, props);

    // VPC - use existing nonpci VPC in us-east-1
    const vpc = ec2.Vpc.fromLookup(this, 'NonPciVPC', {
      vpcId: 'vpc-5c8c1725'  // mrrobot-nonpci VPC in dev
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

    // ALB ingress - HTTP from anywhere
    albSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(80),
      'Allow HTTP'
    );

    // ALB ingress - HTTPS from anywhere
    albSecurityGroup.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(443),
      'Allow HTTPS'
    );

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

    // ========================================================================
    // ECS Cluster
    // ========================================================================
    const cluster = new ecs.Cluster(this, 'MrRobotCluster', {
      vpc,
      clusterName: 'mrrobot-ai-core',
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
      loadBalancerName: 'mrrobot-alb'
    });

    // ========================================================================
    // CloudWatch Log Groups
    // ========================================================================
    const streamlitLogGroup = new logs.LogGroup(this, 'StreamlitLogGroup', {
      logGroupName: '/ecs/mrrobot-streamlit',
      retention: logs.RetentionDays.TWO_WEEKS,
      removalPolicy: cdk.RemovalPolicy.DESTROY
    });

    const mcpLogGroup = new logs.LogGroup(this, 'McpLogGroup', {
      logGroupName: '/ecs/mrrobot-mcp-server',
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
      targetGroupName: 'mrrobot-streamlit',
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
      targetGroupName: 'mrrobot-mcp-server',
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
    // Import existing certificate (created via AWS CLI)
    // To recreate: aws acm request-certificate --domain-name mcp.mrrobot.dev --validation-method DNS
    const mcpCertificate = acm.Certificate.fromCertificateArn(
      this,
      'McpCertificate',
      'arn:aws:acm:us-east-1:720154970215:certificate/febd3527-ede0-49a4-b383-8429febfcf32'
    );

    // ========================================================================
    // ALB Listeners & Rules
    // ========================================================================
    // HTTP Listener - redirect to HTTPS for MCP, serve Streamlit directly
    const httpListener = alb.addListener('HttpListener', {
      port: 80,
      protocol: elbv2.ApplicationProtocol.HTTP,
      defaultTargetGroups: [streamlitTargetGroup]
    });

    // Route mcp.mrrobot.dev to MCP server (HTTP)
    httpListener.addTargetGroups('McpHostRuleHttp', {
      conditions: [
        elbv2.ListenerCondition.hostHeaders(['mcp.mrrobot.dev'])
      ],
      targetGroups: [mcpTargetGroup],
      priority: 1
    });

    // HTTPS Listener for MCP server
    const httpsListener = alb.addListener('HttpsListener', {
      port: 443,
      protocol: elbv2.ApplicationProtocol.HTTPS,
      certificates: [mcpCertificate],
      defaultTargetGroups: [mcpTargetGroup]  // Default to MCP for HTTPS
    });

    // Also route ai-agent.mrrobot.dev to Streamlit on HTTPS (if cert covers it)
    // For now, HTTPS is primarily for MCP server

    // ========================================================================
    // ECS Services
    // ========================================================================
    const streamlitService = new ecs.FargateService(this, 'StreamlitService', {
      cluster,
      taskDefinition: streamlitTaskDefinition,
      desiredCount: 2,
      serviceName: 'mrrobot-streamlit',
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

    // Auto-scaling for Streamlit
    const streamlitScaling = streamlitService.autoScaleTaskCount({
      minCapacity: 2,
      maxCapacity: 4
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
      serviceName: 'mrrobot-mcp-server',
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
    // Route53 DNS
    // ========================================================================
    const hostedZone = route53.HostedZone.fromHostedZoneAttributes(this, 'HostedZone', {
      hostedZoneId: DNS_HOSTED_ZONE_ID,
      zoneName: DNS_DOMAIN,
    });

    // A record for Streamlit (via ALB)
    new route53.ARecord(this, 'StreamlitDnsRecord', {
      zone: hostedZone,
      recordName: 'ai-agent',
      target: route53.RecordTarget.fromAlias(new route53targets.LoadBalancerTarget(alb)),
      ttl: cdk.Duration.minutes(5),
      comment: 'Streamlit AI Agent UI (via ALB)'
    });

    // A record for MCP server (via ALB with path routing)
    new route53.ARecord(this, 'McpDnsRecord', {
      zone: hostedZone,
      recordName: 'mcp',
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

    new cdk.CfnOutput(this, 'StreamlitURL', {
      value: `http://ai-agent.${DNS_DOMAIN}`,
      description: 'Streamlit URL'
    });

    new cdk.CfnOutput(this, 'MCPServerURL', {
      value: `https://mcp.${DNS_DOMAIN}/sse`,
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
  }
}

module.exports = { StrandsAgentECSStack };
