# AI Alert Enhancement Integration Guide

## For: mrrobot-service-observability cloudwatchAlarmNotifier Lambda

This document describes how to integrate with the AI Alert Enhancement API provided by the MCP Server (strands-agent-app).

## Overview

The MCP Server exposes a `/api/enhance-alert` endpoint that accepts alarm data and returns AI-powered analysis including:
- Root cause hypothesis
- Affected code locations (with Bitbucket URLs)
- Suggested fixes
- Recent deployments that may have caused the issue
- Relevant log excerpts

## API Endpoint

**URL:** `http://internal-mrrobot-ai-core-alb-XXXXXXXXX.us-east-1.elb.amazonaws.com:8080/api/enhance-alert`

**Method:** `POST`

**Content-Type:** `application/json`

## Request Format

```json
{
  "alarm_name": "CAST [PROD] - EWriteBackPayment",
  "service": "mrrobot-cast-core",
  "error_code": "EWriteBackPayment",
  "severity": "Critical",
  "reason": "Threshold Crossed: 1 out of the last 1 datapoints [5.0] was >= the threshold (1.0)",
  "log_group": "/aws/lambda/mrrobot-cast-core-prod",
  "timestamp": "2025-12-26T18:00:00Z",
  "environment": "prod",
  "aws_account": "246295362269"
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `alarm_name` | string | CloudWatch alarm name |
| `service` | string | Service name (e.g., "mrrobot-cast-core") |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `error_code` | string | Specific error code (e.g., "EWriteBackPayment") |
| `severity` | string | Alert severity: "Critical", "High", "Medium", "Low" |
| `reason` | string | CloudWatch alarm state reason |
| `log_group` | string | CloudWatch log group for the service |
| `timestamp` | string | ISO 8601 timestamp of the alarm |
| `environment` | string | Environment: "prod", "staging", "dev" |
| `aws_account` | string | AWS account ID |

## Response Format

```json
{
  "status": "success",
  "analysis": {
    "summary": "Payment sync failures detected in mrrobot-cast-core. The EWriteBackPayment error indicates QuickBooks integration issues. A deployment 2 hours ago modified the payment sync logic.",
    "root_cause": "NullPointerException in PaymentSyncService.java:312 when QuickBooks returns empty response",
    "severity": "high",
    "affected_code": [
      {
        "file": "src/main/java/com/mrrobot/cast/service/PaymentSyncService.java",
        "line": 312,
        "snippet": "qboResponse.getPayment().getId()",
        "url": "https://bitbucket.org/mrrobotpay/mrrobot-cast-core/src/main/..."
      }
    ],
    "suggested_fixes": [
      "Add null check before accessing QuickBooks response fields",
      "Implement retry logic for transient QuickBooks API failures",
      "Consider rollback if error rate exceeds threshold"
    ],
    "recent_deployments": [
      {
        "commit": "abc123def",
        "author": "jsmith",
        "message": "Refactor payment sync to use batch API",
        "time": "2025-12-26T16:00:00Z",
        "pipeline_status": "successful"
      }
    ],
    "log_excerpts": [
      "[ERROR] PaymentSyncService - Failed to sync payment txn_12345: NullPointerException",
      "[ERROR] PaymentSyncService - QuickBooks API returned empty response for invoice INV-001"
    ],
    "error_count": 47,
    "error_rate": "15/min",
    "first_occurrence": "2025-12-26T17:45:00Z"
  }
}
```

### Error Response

```json
{
  "status": "error",
  "error": "Service not found in registry",
  "message": "Could not find service 'unknown-service' in the service registry"
}
```

## Integration Code (JavaScript/Node.js)

Add this to `cloudwatchAlarmNotifier/index.js`:

```javascript
const https = require('https');
const http = require('http');

// MCP Server URL - get from environment variable or Secrets Manager
const MCP_SERVER_URL = process.env.MCP_SERVER_URL || 'http://internal-mrrobot-ai-core-alb.us-east-1.elb.amazonaws.com:8080';

/**
 * Call the AI enhancement API to get enriched alert analysis
 * @param {Object} alarmData - Parsed CloudWatch alarm data
 * @returns {Promise<Object>} AI analysis or null if unavailable
 */
async function getAIEnhancement(alarmData) {
  const payload = {
    alarm_name: alarmData.AlarmName,
    service: extractServiceName(alarmData),
    error_code: extractErrorCode(alarmData.AlarmDescription),
    severity: extractSeverity(alarmData.AlarmDescription),
    reason: alarmData.NewStateReason,
    log_group: extractLogGroup(alarmData.AlarmDescription),
    timestamp: alarmData.StateChangeTime,
    environment: extractEnvironment(alarmData),
    aws_account: alarmData.AWSAccountId,
  };

  try {
    const response = await httpPost(`${MCP_SERVER_URL}/api/enhance-alert`, payload);

    if (response.status === 'success') {
      console.log('AI enhancement received successfully');
      return response.analysis;
    } else {
      console.warn('AI enhancement returned error:', response.error);
      return null;
    }
  } catch (error) {
    // Don't fail the alert if AI enhancement is unavailable
    console.error('AI enhancement unavailable:', error.message);
    return null;
  }
}

/**
 * Helper to make HTTP POST request
 */
function httpPost(url, data) {
  return new Promise((resolve, reject) => {
    const urlObj = new URL(url);
    const client = urlObj.protocol === 'https:' ? https : http;

    const options = {
      hostname: urlObj.hostname,
      port: urlObj.port || (urlObj.protocol === 'https:' ? 443 : 80),
      path: urlObj.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      timeout: 10000, // 10 second timeout
    };

    const req = client.request(options, (res) => {
      let body = '';
      res.on('data', chunk => body += chunk);
      res.on('end', () => {
        try {
          resolve(JSON.parse(body));
        } catch (e) {
          reject(new Error(`Invalid JSON response: ${body}`));
        }
      });
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Request timeout'));
    });

    req.write(JSON.stringify(data));
    req.end();
  });
}

/**
 * Extract service name from alarm data
 */
function extractServiceName(alarmData) {
  // Try to extract from alarm name pattern: "CAST [PROD] - EWriteBackPayment"
  const name = alarmData.AlarmName || '';
  if (name.includes('CAST')) return 'mrrobot-cast-core';

  // Try to extract from description
  const desc = alarmData.AlarmDescription || '';
  const logGroupMatch = desc.match(/Log Group: ([^\n]+)/);
  if (logGroupMatch) {
    const logGroup = logGroupMatch[1];
    // Extract service from log group: /aws/lambda/mrrobot-cast-core-prod
    const parts = logGroup.split('/').pop().split('-');
    parts.pop(); // Remove environment suffix
    return parts.join('-');
  }

  return 'unknown';
}

/**
 * Extract error code from alarm description
 */
function extractErrorCode(description) {
  const match = (description || '').match(/Error Code: ([^\n]+)/);
  return match ? match[1].trim() : null;
}

/**
 * Extract severity from alarm description
 */
function extractSeverity(description) {
  const match = (description || '').match(/Severity: ([^\n]+)/);
  return match ? match[1].trim() : 'Medium';
}

/**
 * Extract log group from alarm description
 */
function extractLogGroup(description) {
  const match = (description || '').match(/Log Group: ([^\n]+)/);
  return match ? match[1].trim() : null;
}

/**
 * Extract environment from alarm data
 */
function extractEnvironment(alarmData) {
  const name = alarmData.AlarmName || '';
  if (name.includes('[PROD]') || name.includes('-prod')) return 'prod';
  if (name.includes('[STAGING]') || name.includes('-staging')) return 'staging';
  if (name.includes('[DEV]') || name.includes('-dev')) return 'dev';
  return 'prod';
}
```

## Using AI Enhancement in PagerDuty Payload

```javascript
/**
 * Format PagerDuty incident with AI enhancement
 */
function formatPagerDutyPayload(alarmData, aiAnalysis) {
  const baseDescription = formatBaseDescription(alarmData);

  // If AI analysis is available, enhance the description
  let enhancedDescription = baseDescription;
  if (aiAnalysis) {
    enhancedDescription = `
🤖 *AI-Enhanced Alert*

*Summary:* ${aiAnalysis.summary}

*Root Cause:* ${aiAnalysis.root_cause || 'Under investigation'}

*Affected Code:*
${(aiAnalysis.affected_code || []).map(c => `• ${c.file}:${c.line} [View](${c.url})`).join('\n') || '• No specific code identified'}

*Suggested Fixes:*
${(aiAnalysis.suggested_fixes || []).map((f, i) => `${i + 1}. ${f}`).join('\n') || '• No specific fixes suggested'}

*Recent Deployments:*
${(aiAnalysis.recent_deployments || []).map(d => `• ${d.commit.substring(0, 7)} by ${d.author}: "${d.message}"`).join('\n') || '• No recent deployments'}

*Error Stats:* ${aiAnalysis.error_count || 'N/A'} errors (${aiAnalysis.error_rate || 'N/A'})

---
${baseDescription}
`;
  }

  return {
    routing_key: PAGERDUTY_ROUTING_KEY,
    event_action: 'trigger',
    dedup_key: `cast-core-${extractErrorCode(alarmData.AlarmDescription)}-${extractEnvironment(alarmData)}`,
    payload: {
      summary: `[AI] ${alarmData.AlarmName}`,
      severity: mapToPagerDutySeverity(extractSeverity(alarmData.AlarmDescription)),
      source: 'mrrobot-service-observability',
      custom_details: {
        alarm_name: alarmData.AlarmName,
        error_code: extractErrorCode(alarmData.AlarmDescription),
        environment: extractEnvironment(alarmData),
        ai_summary: aiAnalysis?.summary,
        ai_root_cause: aiAnalysis?.root_cause,
        ai_suggested_fixes: aiAnalysis?.suggested_fixes,
      },
    },
    links: [
      {
        href: `https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/${encodeURIComponent(extractLogGroup(alarmData.AlarmDescription))}`,
        text: 'View CloudWatch Logs',
      },
      ...(aiAnalysis?.affected_code || []).slice(0, 2).map(c => ({
        href: c.url,
        text: `View ${c.file.split('/').pop()}`,
      })),
    ],
  };
}
```

## Lambda Handler Integration

Update the handler to call AI enhancement before PagerDuty:

```javascript
async function handler(event, context) {
  for (const record of event.Records) {
    const snsMessage = JSON.parse(record.Sns.Message);
    const topicArn = record.Sns.TopicArn;

    // Existing Slack notification
    await postToSlack(snsMessage);

    // Only send to PagerDuty for Cast Core alerts
    if (topicArn.includes('cast-core')) {
      // Get AI enhancement (with timeout/fallback)
      const aiAnalysis = await getAIEnhancement(snsMessage);

      // Send to PagerDuty with enhanced payload
      const pagerDutyPayload = formatPagerDutyPayload(snsMessage, aiAnalysis);
      await postToPagerDuty(pagerDutyPayload);
    }
  }

  return { statusCode: 200 };
}
```

## Terraform Changes

Add MCP Server URL to Lambda environment variables:

```hcl
# In terraform/modules/dynamodb-table-metrics/main.tf

resource "aws_lambda_function" "main" {
  # ... existing config ...

  environment {
    variables = {
      # ... existing vars ...
      MCP_SERVER_URL = "http://internal-mrrobot-ai-core-alb-${data.aws_lb.ai_core.dns_name}:8080"
    }
  }
}

# OR use a data source to get the ALB DNS name
data "aws_lb" "ai_core" {
  name = "mrrobot-ai-core"
}
```

## Network Requirements

The Lambda must be able to reach the MCP Server:

1. **VPC Configuration:** Lambda should be in a VPC with route to the ALB
2. **Security Group:** Allow outbound to ALB on port 8080
3. **ALB Security Group:** Allow inbound from Lambda security group on port 8080

## Graceful Degradation

The integration is designed to be fault-tolerant:

- 10 second timeout on AI enhancement request
- If AI enhancement fails, the alert still goes to PagerDuty with basic info
- Errors are logged but don't prevent alerting

## Testing

Test the integration locally:

```bash
# Test the API directly
curl -X POST http://localhost:8080/api/enhance-alert \
  -H "Content-Type: application/json" \
  -d '{
    "alarm_name": "CAST [PROD] - EWriteBackPayment",
    "service": "mrrobot-cast-core",
    "error_code": "EWriteBackPayment",
    "severity": "Critical",
    "reason": "Threshold Crossed",
    "timestamp": "2025-12-26T18:00:00Z"
  }'
```

## Questions?

Contact: DevOps team or check the strands-agent-app repository.
