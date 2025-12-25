"""Tool execution and result compaction for Clippy.

Handles executing MCP tools and compacting results to reduce token usage.
"""

from src.mcp_server.slack_bot.alerting import alert_error


def _summarize_logs(logs: list, max_logs: int = 20) -> list:
    """Summarize log entries to reduce token usage.

    Extracts key fields and truncates long messages.
    """
    summarized = []
    for log in logs[:max_logs]:
        entry = {
            "timestamp": log.get("timestamp", log.get("@timestamp", "")),
            "level": log.get("level", log.get("severity", "")),
            "service": log.get("logGroup", log.get("service", ""))[-50:],  # Last 50 chars
        }
        # Get message and truncate
        msg = log.get("message", log.get("msg", str(log)))
        if isinstance(msg, str):
            entry["message"] = msg[:500] + "..." if len(msg) > 500 else msg
        else:
            entry["message"] = str(msg)[:500]
        summarized.append(entry)
    return summarized


def _compact_tool_result(tool_name: str, result: dict) -> dict:
    """Compact tool results to reduce size while preserving key information.

    This is critical for preventing truncation when sending results to Claude.
    Each tool type gets specific compaction logic to preserve the most useful info.
    """
    if tool_name in ["search_logs", "get_recent_errors"]:
        # Summarize log results
        if "logs" in result:
            result["logs"] = _summarize_logs(result["logs"], max_logs=15)
            result["_compacted"] = True
        if "errors_by_service" in result:
            # Keep only top 5 services, 5 errors each
            errors_by_service = result["errors_by_service"]
            compacted = {}
            for svc, data in list(errors_by_service.items())[:5]:
                if isinstance(data, dict) and "recent_errors" in data:
                    data["recent_errors"] = _summarize_logs(data["recent_errors"], max_logs=5)
                compacted[svc] = data
            result["errors_by_service"] = compacted
            result["_compacted"] = True

    elif tool_name == "search_code":
        # Truncate code snippets
        if "results" in result:
            for r in result["results"]:
                if "content" in r and len(r["content"]) > 800:
                    r["content"] = r["content"][:800] + "\n... [truncated]"
            result["_compacted"] = True

    elif tool_name == "search_devops_history":
        # Summarize Slack history results
        if "results" in result:
            for r in result["results"]:
                if "content" in r and len(r["content"]) > 600:
                    r["content"] = r["content"][:600] + "... [more context available]"
            result["_compacted"] = True

    elif tool_name == "get_pr_details":
        # Limit files shown and truncate descriptions
        if "files_changed" in result and len(result["files_changed"]) > 10:
            result["files_changed"] = result["files_changed"][:10]
            result["more_files"] = True
        if "description" in result and len(result["description"]) > 500:
            result["description"] = result["description"][:500] + "..."
        # Keep comments summary but truncate individual comments
        if "comments" in result:
            for c in result.get("comments", [])[:5]:
                if "content" in c and len(c["content"]) > 200:
                    c["content"] = c["content"][:200] + "..."
            if len(result["comments"]) > 5:
                result["comments"] = result["comments"][:5]
                result["more_comments"] = True

    elif tool_name == "investigate_issue":
        # This returns a full report - keep key sections, summarize details
        if "logs" in result:
            result["logs"] = _summarize_logs(result["logs"], max_logs=10)
        if "recent_deploys" in result and len(result["recent_deploys"]) > 3:
            result["recent_deploys"] = result["recent_deploys"][:3]

    return result


def execute_tool(tool_name: str, tool_input: dict) -> dict:
    """Execute an MCP tool and return the result.

    This maps Claude's tool calls to our actual MCP tool implementations.
    Results are compacted to reduce token usage.
    """
    result = _execute_tool_internal(tool_name, tool_input)

    # Compact results to reduce size (prevents truncation)
    if isinstance(result, dict) and "error" not in result:
        result = _compact_tool_result(tool_name, result)

    return result


def _execute_tool_internal(tool_name: str, tool_input: dict) -> dict:
    """Internal tool execution - returns raw results."""
    try:
        if tool_name == "search_logs":
            from src.lib.coralogix import handle_search_logs

            return handle_search_logs(
                query=tool_input.get("query", ""),
                hours_back=tool_input.get("hours_back", 4),
                limit=tool_input.get("limit", 50),
            )

        elif tool_name == "get_recent_errors":
            from src.lib.coralogix import handle_get_recent_errors

            return handle_get_recent_errors(
                service_name=tool_input.get("service", "all"),
                hours_back=tool_input.get("hours_back", 4),
                environment=tool_input.get("environment"),
                limit=50,
            )

        elif tool_name == "search_code":
            from src.lib.code_search import search_knowledge_base

            return search_knowledge_base(
                query=tool_input.get("query", ""), num_results=tool_input.get("num_results", 5)
            )

        elif tool_name == "get_pipeline_status":
            from src.lib.bitbucket import get_pipeline_status

            return get_pipeline_status(repo_slug=tool_input.get("repo", ""), limit=tool_input.get("limit", 5))

        elif tool_name == "get_pipeline_details":
            from src.lib.bitbucket import get_pipeline_details

            repo = tool_input.get("repo", "")
            if "/" in repo:
                repo = repo.split("/")[-1]
            return get_pipeline_details(repo_slug=repo, pipeline_id=tool_input.get("pipeline_id", 0))

        elif tool_name == "aws_cli":
            from src.lib.aws_cli import run_aws_command

            return run_aws_command(command=tool_input.get("command", ""), region=tool_input.get("region", "us-east-1"))

        elif tool_name == "list_open_prs":
            from src.lib.bitbucket import get_open_prs

            return get_open_prs(repo_slug=tool_input.get("repo", ""), limit=tool_input.get("limit", 5))

        elif tool_name == "get_pr_details":
            from src.lib.bitbucket import get_pr_details

            # Strip workspace prefix if Claude included it (e.g., "mrrobot-labs/repo" -> "repo")
            repo = tool_input.get("repo", "")
            if "/" in repo:
                repo = repo.split("/")[-1]
            return get_pr_details(repo_slug=repo, pr_id=tool_input.get("pr_id", 0))

        elif tool_name == "get_service_info":
            # Use service registry (fast lookup from S3-cached data)
            from src.lib.config_loader import lookup_service

            service_name = tool_input.get("service_name", "")
            service_info = lookup_service(service_name)

            if service_info:
                # Found in registry - return rich info
                service_type = service_info.get("type", "unknown")
                return {
                    "service_name": service_name,
                    "found": True,
                    "key": service_info.get("key"),
                    "full_name": service_info.get("full_name"),
                    "type": service_type,
                    "tech_stack": service_info.get("tech_stack", []),
                    "description": service_info.get("description", ""),
                    "aliases": service_info.get("aliases", []),
                    "repo": service_info.get("repo", service_info.get("full_name")),
                    "suggestion": (
                        "Frontend app - check deploys and browser console for API errors."
                        if service_type == "frontend"
                        else (
                            "Backend service - check logs first, then recent deploys."
                            if service_type == "backend"
                            else (
                                "Library/tool - check if dependent services are affected."
                                if service_type in ("library", "tool")
                                else "Check both logs and deploys."
                            )
                        )
                    ),
                }
            else:
                # Not in registry - fall back to KB search
                from src.lib.code_search import search_knowledge_base

                results = search_knowledge_base(query=f"{service_name} package.json README", num_results=3)
                files_found = [r.get("file", "") for r in results.get("results", [])]

                return {
                    "service_name": service_name,
                    "found": False,
                    "message": f"Service '{service_name}' not found in registry (129 known services).",
                    "files_found": files_found[:3],
                    "suggestion": "This may be a new service or misspelled. Check the files found or try a different name.",
                }

        elif tool_name == "search_devops_history":
            # Search Slack history in the Knowledge Base
            from src.lib.code_search import search_knowledge_base

            query = tool_input.get("query", "")

            # Search with context that this is for past conversations
            results = search_knowledge_base(query=f"Slack conversation: {query}", num_results=5)

            # Filter to only slack-history results if possible
            slack_results = []
            for r in results.get("results", []):
                # Include all results but flag which are from slack
                is_slack = "slack-history" in r.get("full_path", "") or r.get("file", "").endswith(".txt")
                slack_results.append(
                    {
                        "source": "slack" if is_slack else "code",
                        "content": r.get("content", "")[:500],
                        "file": r.get("file", ""),
                        "score": r.get("score", 0),
                    }
                )

            if not slack_results:
                return {
                    "found": False,
                    "message": "No past conversations found matching that query.",
                    "suggestion": "Try a different search term or check if Slack history has been synced.",
                }

            return {
                "found": True,
                "query": query,
                "results": slack_results,
                "message": f"Found {len(slack_results)} past conversation(s) that might be relevant.",
            }

        elif tool_name == "investigate_issue":
            from src.lib.investigation_agent import investigate_issue

            return investigate_issue(
                service=tool_input.get("service", ""),
                environment=tool_input.get("environment"),
                description=tool_input.get("description"),
            )

        elif tool_name == "jira_search":
            from src.lib.jira import handle_search_jira

            return handle_search_jira(
                query=tool_input.get("query", ""),
                max_results=tool_input.get("max_results", 20),
            )

        elif tool_name == "jira_cve_tickets":
            from src.lib.jira import get_open_cve_issues

            return get_open_cve_issues(max_results=tool_input.get("max_results", 50))

        elif tool_name == "jira_get_ticket":
            from src.lib.jira import get_issue

            return get_issue(issue_key=tool_input.get("issue_key", ""))

        # =====================================================================
        # CONFLUENCE TOOLS
        # =====================================================================

        elif tool_name == "search_confluence":
            from src.lib.confluence import handle_search

            return handle_search(
                query=tool_input.get("query", ""),
                space_key=tool_input.get("space_key"),
                limit=tool_input.get("limit", 10),
            )

        elif tool_name == "get_confluence_page":
            from src.lib.confluence import handle_get_page

            return handle_get_page(page_id=tool_input.get("page_id", ""))

        elif tool_name == "list_confluence_spaces":
            from src.lib.confluence import handle_list_spaces

            return handle_list_spaces(limit=50)

        elif tool_name == "recent_confluence_updates":
            from src.lib.confluence import handle_get_recent_updates

            return handle_get_recent_updates(
                space_key=tool_input.get("space_key"),
                limit=tool_input.get("limit", 15),
            )

        # =====================================================================
        # PAGERDUTY TOOLS
        # =====================================================================

        elif tool_name == "pagerduty_active_incidents":
            from src.lib.pagerduty import handle_active_incidents

            return handle_active_incidents()

        elif tool_name == "pagerduty_recent_incidents":
            from src.lib.pagerduty import handle_recent_incidents

            days = tool_input.get("days", 7)
            return handle_recent_incidents(days=days)

        elif tool_name == "pagerduty_incident_details":
            from src.lib.pagerduty import handle_incident_details

            return handle_incident_details(incident_id=tool_input.get("incident_id", ""))

        elif tool_name == "pagerduty_investigate":
            from src.lib.coralogix import handle_get_recent_errors
            from src.lib.pagerduty import extract_service_name_from_incident, handle_incident_details

            # Get incident details first
            incident = handle_incident_details(incident_id=tool_input.get("incident_id", ""))
            if "error" in incident:
                return incident

            # Try to extract service name and check logs
            service_name = extract_service_name_from_incident(incident)
            logs_result = None
            if service_name:
                try:
                    logs_result = handle_get_recent_errors(service=service_name, hours_back=4)
                except Exception as e:
                    logs_result = {"error": str(e)}

            return {
                "incident": incident,
                "service_detected": service_name,
                "related_logs": logs_result,
            }

        else:
            return {"error": f"Unknown tool: {tool_name}"}

    except Exception as e:
        print(f"[Clippy] Tool execution error: {e}")
        # Alert to dev channel for tool failures
        alert_error(
            "Tool Execution Error",
            f"Tool '{tool_name}' failed: {str(e)[:200]}",
            {"tool": tool_name, "input": str(tool_input)[:200]},
        )
        return {"error": str(e)}
