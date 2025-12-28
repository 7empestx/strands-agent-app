"""AI-powered alert enhancement for CloudWatch alarms.

This module provides rich AI analysis for alerts before they go to PagerDuty/Slack:
- Uses Strands investigation agent for autonomous multi-tool investigation
- Searches logs for recent errors via Coralogix
- Searches codebase for relevant files via Bedrock Knowledge Base
- Generates Claude-powered root cause analysis and recommendations

The investigation agent uses Claude Sonnet to autonomously gather evidence,
correlate patterns, and provide actionable insights.
"""

import os
import re
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.lib.code_search import search_knowledge_base
from src.lib.config_loader import lookup_service
from src.lib.coralogix import handle_get_recent_errors
from src.lib.investigation_agent import investigate_issue

# Error code to description mapping for Cast Core
CAST_CORE_ERROR_DESCRIPTIONS = {
    "EWriteBackPayment": "Payment sync to QuickBooks/integration failed",
    "EProcessPayment": "Payment processing failed",
    "EPaymentsClient": "Payments client connection/communication error",
    "ERefund": "Refund processing failed",
    "EVoid": "Void transaction failed",
    "EPostRefundReceiptToQBO": "Failed to post refund receipt to QuickBooks",
    "ECheckPayment": "Check payment processing failed",
    "ESendEmail": "Email notification failed",
    "ESendSMS": "SMS notification failed",
}

# Severity to priority mapping
SEVERITY_PRIORITY = {
    "Critical": "high",
    "High": "high",
    "Medium": "medium",
    "Low": "low",
}

# Service name to Bitbucket repo slug mapping
# Maps CloudWatch/alarm service names to actual Bitbucket repository slugs
SERVICE_TO_REPO = {
    "mrrobot-cast-core": "cast-core-service",
    "cast-core": "cast-core-service",
    "mrrobot-cast-quickbooks": "cast-quickbooks-service",
    "mrrobot-cast-housecallpro": "cast-housecallpro-service",
    "mrrobot-cast-service-titan": "cast-service-titan-service",
}


def enhance_alert(alarm_data: dict) -> dict:
    """
    Enhance a CloudWatch alarm with AI-powered analysis.

    Uses the Strands investigation agent (Claude Sonnet) for autonomous
    multi-tool investigation, providing intelligent root cause analysis.

    Args:
        alarm_data: Dict containing alarm details:
            - alarm_name: CloudWatch alarm name
            - service: Service name (e.g., "mrrobot-cast-core")
            - error_code: Specific error code (optional)
            - severity: Alert severity (optional)
            - reason: CloudWatch state reason (optional)
            - log_group: CloudWatch log group (optional)
            - timestamp: ISO timestamp (optional)
            - environment: prod/staging/dev (optional)

    Returns:
        Dict with AI analysis including summary, root cause, affected code, etc.
    """
    try:
        service_name = alarm_data.get("service", "unknown")
        error_code = alarm_data.get("error_code")
        severity = alarm_data.get("severity", "Medium")
        alarm_name = alarm_data.get("alarm_name", "")
        reason = alarm_data.get("reason", "")
        log_group = alarm_data.get("log_group")
        environment = alarm_data.get("environment", "prod")

        print(f"[AlertEnhancer] Enhancing alert for {service_name} - {error_code or alarm_name}")

        # 1. Get service info from registry
        service_info = lookup_service(service_name)

        # 2. Build description for investigation agent
        description_parts = []
        if error_code and error_code in CAST_CORE_ERROR_DESCRIPTIONS:
            description_parts.append(CAST_CORE_ERROR_DESCRIPTIONS[error_code])
        description_parts.append(f"Alarm: {alarm_name}")
        if reason:
            description_parts.append(f"Reason: {reason}")
        description = ". ".join(description_parts)

        # 3. Try the investigation agent (Claude-powered autonomous investigation)
        investigation_result = None
        report = ""
        try:
            print(f"[AlertEnhancer] Running investigation agent for {service_name} in {environment}...")
            investigation_result = investigate_issue(
                service=service_name,
                environment=environment,
                description=description,
                max_steps=8,  # Limit steps for faster response
            )
            report = investigation_result.get("report", "")
            print(f"[AlertEnhancer] Investigation complete. Report length: {len(report)} chars")
        except Exception as agent_error:
            print(f"[AlertEnhancer] Investigation agent failed: {agent_error}")
            # Continue with fallback analysis

        # 4. Search codebase for relevant files (fast KB lookup)
        code_results = _search_relevant_code(service_name, error_code, alarm_name)

        # 5. If investigation agent succeeded and returned a good report, parse it
        # Otherwise fall back to rule-based analysis
        # Ensure report is a string for comparison
        report_str = str(report) if not isinstance(report, str) else report
        investigation_failed = (
            investigation_result is None
            or investigation_result.get("status") == "error"
            or "error" in report_str.lower()[:100]
            or len(report_str) < 100
        )

        if investigation_failed:
            print("[AlertEnhancer] Using fallback rule-based analysis")
            # Get logs for rule-based analysis
            logs_result = _get_recent_logs(service_name, error_code, hours_back=1)
            analysis = _generate_rule_based_analysis(
                service_name=service_name,
                service_info=service_info,
                error_code=error_code,
                severity=severity,
                alarm_name=alarm_name,
                reason=reason,
                logs_result=logs_result,
                code_results=code_results,
            )
        else:
            # 6. Structure the investigation results for Slack/PagerDuty
            analysis = _parse_investigation_report(
                report=report_str,
                service_name=service_name,
                service_info=service_info,
                error_code=error_code,
                severity=severity,
                code_results=code_results,
            )

        return {
            "status": "success",
            "analysis": analysis,
        }

    except Exception as e:
        print(f"[AlertEnhancer] Error enhancing alert: {e}")
        import traceback

        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
            "analysis": _generate_fallback_analysis(alarm_data),
        }


def _parse_investigation_report(
    report: str,
    service_name: str,
    service_info: dict | None,
    error_code: str | None,
    severity: str,
    code_results: dict,
) -> dict:
    """Parse the investigation agent's markdown report into structured data."""

    # Extract sections from the report
    summary = _extract_section(report, "Investigation Summary", "Evidence Found")
    if not summary:
        summary = _extract_section(report, "Summary", "Evidence")
    if not summary:
        # Use first paragraph as summary
        lines = [line.strip() for line in report.split("\n") if line.strip() and not line.startswith("#")]
        summary = lines[0] if lines else "Investigation completed"

    root_cause = _extract_section(report, "Root Cause", "Recommended")
    if not root_cause:
        root_cause = _extract_section(report, "Root Cause Hypothesis", "Recommended")
    if not root_cause:
        root_cause = "See investigation report for details"

    # Extract recommended actions as a list
    actions_section = _extract_section(report, "Recommended Actions", None)
    if not actions_section:
        actions_section = _extract_section(report, "Recommendations", None) or ""
    suggested_fixes = _parse_numbered_list(actions_section)
    if not suggested_fixes:
        suggested_fixes = ["Review the investigation report for detailed recommendations"]

    # Extract log excerpts from Evidence section
    evidence_section = _extract_section(report, "Evidence Found", "Root Cause")
    if not evidence_section:
        evidence_section = _extract_section(report, "Evidence", "Root Cause") or ""
    log_excerpts = []
    for line in evidence_section.split("\n"):
        line = line.strip()
        if line.startswith("-") or line.startswith("•"):
            excerpt = line.lstrip("-•").strip()[:200]
            if excerpt:
                log_excerpts.append(excerpt)
    log_excerpts = log_excerpts[:5]  # Max 5 excerpts

    # Build affected code list from KB search
    affected_code = []
    code_list = code_results.get("results", [])
    for result in code_list[:3]:
        affected_code.append(
            {
                "file": result.get("file", ""),
                "repo": result.get("repo", ""),
                "line": result.get("line_number"),
                "snippet": result.get("content", "")[:200],
                "url": result.get("bitbucket_url", ""),
            }
        )

    return {
        "summary": summary.strip()[:500],  # Limit length for Slack
        "root_cause": root_cause.strip()[:500],
        "severity": SEVERITY_PRIORITY.get(severity, "medium"),
        "affected_code": affected_code,
        "suggested_fixes": suggested_fixes[:5],  # Max 5 fixes
        "recent_deployments": [],  # Agent handles this internally
        "log_excerpts": log_excerpts,
        "error_count": 0,  # Agent provides this in the report
        "error_rate": None,
        "service_info": {
            "name": service_name,
            "type": service_info.get("type") if service_info else None,
            "tech_stack": service_info.get("tech_stack") if service_info else None,
        },
        "full_report": report,  # Include full report for debugging
    }


def _extract_section(text: str, start_header: str, end_header: str | None) -> str | None:
    """Extract a section from markdown text between headers."""
    if not text:
        return None

    # Find start
    start_patterns = [
        f"## {start_header}",
        f"### {start_header}",
        f"**{start_header}**",
        f"{start_header}:",
    ]

    start_idx = -1
    for pattern in start_patterns:
        idx = text.lower().find(pattern.lower())
        if idx != -1:
            start_idx = idx + len(pattern)
            break

    if start_idx == -1:
        return None

    # Find end
    if end_header:
        end_patterns = [
            f"## {end_header}",
            f"### {end_header}",
            f"**{end_header}**",
            f"{end_header}:",
        ]
        end_idx = len(text)
        for pattern in end_patterns:
            idx = text.lower().find(pattern.lower(), start_idx)
            if idx != -1 and idx < end_idx:
                end_idx = idx
    else:
        end_idx = len(text)

    return text[start_idx:end_idx].strip()


def _parse_numbered_list(text: str) -> list[str]:
    """Parse a numbered or bulleted list from text."""
    items = []
    for line in text.split("\n"):
        line = line.strip()
        # Match "1.", "1)", "-", "•", "*"
        match = re.match(r"^[\d]+[.\)]\s*(.+)$", line)
        if match:
            items.append(match.group(1).strip())
        elif line.startswith(("-", "•", "*")):
            item = line.lstrip("-•*").strip()
            if item:
                items.append(item)
    return items


def _get_recent_logs(service_name: str, error_code: str | None, hours_back: int = 1) -> dict:
    """Get recent error logs from Coralogix. (Legacy - kept for fallback)"""
    try:
        # Include error code in search if available
        result = handle_get_recent_errors(service_name, hours_back=hours_back, limit=20)
        return result
    except Exception as e:
        print(f"[AlertEnhancer] Error getting logs: {e}")
        return {"errors": [], "error": str(e)}


def _search_relevant_code(service_name: str, error_code: str | None, alarm_name: str) -> dict:
    """Search the knowledge base for relevant code."""
    try:
        # Build search query
        query_parts = [service_name]
        if error_code:
            query_parts.append(error_code)
            # Add known error descriptions
            if error_code in CAST_CORE_ERROR_DESCRIPTIONS:
                query_parts.append(CAST_CORE_ERROR_DESCRIPTIONS[error_code])
        else:
            query_parts.append(alarm_name)

        query = " ".join(query_parts)
        result = search_knowledge_base(query, num_results=5)
        return result
    except Exception as e:
        print(f"[AlertEnhancer] Error searching code: {e}")
        return {"results": [], "error": str(e)}


def _get_recent_deployments(service_name: str) -> list[dict]:
    """Get recent deployments from Bitbucket.

    NOTE: Currently disabled due to Bitbucket API auth issues.
    The deployment info is nice-to-have but not critical.
    The code search from Bedrock KB provides the most valuable insights.
    """
    # Skip Bitbucket API call - it's slow and currently returns 401
    # TODO: Re-enable when Bitbucket token permissions are fixed
    return []


def _generate_rule_based_analysis(
    service_name: str,
    service_info: dict | None,
    error_code: str | None,
    severity: str,
    alarm_name: str,
    reason: str,
    logs_result: dict,
    code_results: dict,
    deployments: list[dict] = None,
) -> dict:
    """Generate rule-based analysis when investigation agent is unavailable."""
    if deployments is None:
        deployments = []

    # Build summary
    summary_parts = []

    # Add error description if known
    if error_code and error_code in CAST_CORE_ERROR_DESCRIPTIONS:
        summary_parts.append(f"{CAST_CORE_ERROR_DESCRIPTIONS[error_code]} detected in {service_name}.")
    else:
        summary_parts.append(f"Alert triggered in {service_name}: {alarm_name}")

    # Check for recent deployments that might be the cause
    recent_deploy = None
    if deployments:
        recent_deploy = deployments[0]
        deploy_time = recent_deploy.get("time", "")
        if deploy_time:
            summary_parts.append(f"Recent deployment by {recent_deploy.get('author', 'unknown')} may be related.")

    summary = " ".join(summary_parts)

    # Extract error patterns from logs
    log_excerpts = []
    error_count = 0
    errors_list = logs_result.get("errors", logs_result.get("logs", []))
    if isinstance(errors_list, list):
        error_count = len(errors_list)
        for entry in errors_list[:5]:
            if isinstance(entry, dict):
                msg = entry.get("message", entry.get("error", str(entry)))
            else:
                msg = str(entry)
            log_excerpts.append(msg[:200])

    # Build affected code list
    affected_code = []
    code_list = code_results.get("results", [])
    for result in code_list[:3]:
        affected_code.append(
            {
                "file": result.get("file", ""),
                "repo": result.get("repo", ""),
                "line": result.get("line_number"),
                "snippet": result.get("content", "")[:200],
                "url": result.get("bitbucket_url", ""),
            }
        )

    # Generate root cause hypothesis
    root_cause = _hypothesize_root_cause(error_code, alarm_name, logs_result, deployments)

    # Generate suggested fixes
    suggested_fixes = _generate_suggested_fixes(error_code, service_info, code_results)

    # Calculate error rate if we have timestamps
    error_rate = None
    if error_count > 0:
        error_rate = f"{error_count}/hour"

    return {
        "summary": summary,
        "root_cause": root_cause,
        "severity": SEVERITY_PRIORITY.get(severity, "medium"),
        "affected_code": affected_code,
        "suggested_fixes": suggested_fixes,
        "recent_deployments": deployments,
        "log_excerpts": log_excerpts,
        "error_count": error_count,
        "error_rate": error_rate,
        "service_info": {
            "name": service_name,
            "type": service_info.get("type") if service_info else None,
            "tech_stack": service_info.get("tech_stack") if service_info else None,
        },
    }


def _hypothesize_root_cause(
    error_code: str | None,
    alarm_name: str,
    logs_result: dict,
    deployments: list[dict],
) -> str:
    """Generate a root cause hypothesis based on available data."""

    # Check for common patterns in logs
    errors_list = logs_result.get("errors", logs_result.get("logs", []))
    error_text = " ".join(str(e) for e in errors_list[:10]).lower()

    # Connection issues
    if any(x in error_text for x in ["econnrefused", "etimedout", "connection", "network"]):
        return "Network connectivity issue - service unable to reach external dependency"

    # Database issues
    if any(x in error_text for x in ["deadlock", "timeout", "connection pool", "database"]):
        return "Database connectivity or performance issue"

    # Auth issues
    if any(x in error_text for x in ["401", "403", "unauthorized", "forbidden", "token"]):
        return "Authentication or authorization failure - token may be expired or permissions misconfigured"

    # Null/undefined errors
    if any(x in error_text for x in ["null", "undefined", "cannot read", "typeerror"]):
        return "Null pointer or type error - likely missing data validation"

    # Memory issues
    if any(x in error_text for x in ["memory", "heap", "oom", "out of memory"]):
        return "Memory exhaustion - service may need more resources or has a memory leak"

    # Check if there's a recent deployment
    if deployments:
        recent = deployments[0]
        return f"Possible regression from recent deployment: '{recent.get('message', 'unknown change')[:50]}'"

    # Error code specific
    if error_code:
        if error_code in CAST_CORE_ERROR_DESCRIPTIONS:
            return f"{CAST_CORE_ERROR_DESCRIPTIONS[error_code]} - check integration status and credentials"

    return "Root cause under investigation - check recent deployments and service dependencies"


def _generate_suggested_fixes(
    error_code: str | None,
    service_info: dict | None,
    code_results: dict,
) -> list[str]:
    """Generate suggested fixes based on error type and code analysis."""
    fixes = []

    # Error code specific fixes
    if error_code:
        if error_code == "EWriteBackPayment":
            fixes.extend(
                [
                    "Check QuickBooks API credentials and connection",
                    "Verify QuickBooks API rate limits haven't been exceeded",
                    "Review payment data format for compatibility issues",
                ]
            )
        elif error_code == "EProcessPayment":
            fixes.extend(
                [
                    "Check payment gateway connectivity",
                    "Verify merchant credentials are valid",
                    "Review payment request for invalid data",
                ]
            )
        elif error_code in ["ESendEmail", "ESendSMS"]:
            fixes.extend(
                [
                    "Check notification service credentials",
                    "Verify recipient data is valid",
                    "Check for service rate limiting",
                ]
            )

    # Generic fixes
    if not fixes:
        fixes.extend(
            [
                "Check application logs for detailed error messages",
                "Review recent deployments for potential regressions",
                "Verify external service dependencies are healthy",
            ]
        )

    # Add rollback suggestion if there are recent deployments
    fixes.append("Consider rollback if error rate is critical")

    return fixes


def _generate_fallback_analysis(alarm_data: dict) -> dict:
    """Generate basic analysis when full analysis fails."""
    return {
        "summary": f"Alert on {alarm_data.get('service', 'unknown')}: {alarm_data.get('alarm_name', 'Unknown')}",
        "root_cause": "Unable to determine - check logs manually",
        "severity": SEVERITY_PRIORITY.get(alarm_data.get("severity", "Medium"), "medium"),
        "affected_code": [],
        "suggested_fixes": [
            "Check application logs for detailed error messages",
            "Review recent deployments",
            "Verify service dependencies are healthy",
        ],
        "recent_deployments": [],
        "log_excerpts": [],
        "error_count": 0,
        "error_rate": None,
    }
