"""Generate investigation reports with reasoning and command traces."""

import re
from datetime import datetime


def extract_tool_calls_from_trace(investigation_trace):
    """Extract tool calls and reasoning from the investigation trace."""
    tool_calls = []

    for i, msg in enumerate(investigation_trace):
        role = msg.get("role", "")
        content = msg.get("content", "")

        # Look for tool use patterns in assistant messages
        if role == "assistant":
            # Extract tool calls (look for function names)
            if "search_logs" in content:
                tool_calls.append(
                    {
                        "step": len(tool_calls) + 1,
                        "tool": "search_logs",
                        "reasoning": _extract_reasoning_before_tool(investigation_trace, i),
                        "content": content,
                    }
                )
            elif "check_recent_deploys" in content:
                tool_calls.append(
                    {
                        "step": len(tool_calls) + 1,
                        "tool": "check_recent_deploys",
                        "reasoning": _extract_reasoning_before_tool(investigation_trace, i),
                        "content": content,
                    }
                )
            elif "get_error_summary" in content:
                tool_calls.append(
                    {
                        "step": len(tool_calls) + 1,
                        "tool": "get_error_summary",
                        "reasoning": _extract_reasoning_before_tool(investigation_trace, i),
                        "content": content,
                    }
                )

    return tool_calls


def _extract_reasoning_before_tool(trace, current_index):
    """Extract the agent's reasoning that came before this tool call."""
    # Look backwards for reasoning text
    for i in range(current_index - 1, max(0, current_index - 3), -1):
        msg = trace[i]
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            # Extract sentences that explain why
            if "because" in content.lower() or "to check" in content.lower() or "will" in content.lower():
                return content[:200]

    return "Investigating the issue"


def generate_commands_used_report(investigation_result, output_path="/tmp/commands-used.txt"):
    """Generate a detailed commands-used.txt report with reasoning."""

    service = investigation_result.get("service", "unknown")
    environment = investigation_result.get("environment", "unknown")
    trace = investigation_result.get("investigation_trace", [])
    tool_count = investigation_result.get("tool_calls", 0)

    tool_calls = extract_tool_calls_from_trace(trace)

    with open(output_path, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("INVESTIGATION COMMAND LOG\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Service: {service}\n")
        f.write(f"Environment: {environment}\n")
        f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total tools executed: {tool_count}\n\n")

        f.write("-" * 70 + "\n")
        f.write("INVESTIGATION FLOW\n")
        f.write("-" * 70 + "\n\n")

        if tool_calls:
            for call in tool_calls:
                f.write(f"[Step {call['step']}] {call['tool']}\n")
                f.write(f"  Reasoning: {call['reasoning']}\n")

                # Extract parameters if visible
                content = call["content"]
                if "query=" in content or "service=" in content:
                    params = re.findall(r'(\w+)=[\'"]([^\'"]+)[\'"]', content)
                    if params:
                        f.write(f"  Parameters:\n")
                        for param_name, param_value in params[:3]:  # First 3 params
                            f.write(f"    - {param_name}: {param_value}\n")

                f.write("\n")
        else:
            f.write("No detailed tool execution trace available.\n")
            f.write("The agent executed tools autonomously during investigation.\n\n")

        f.write("-" * 70 + "\n")
        f.write("NOTES\n")
        f.write("-" * 70 + "\n\n")
        f.write("This log shows the investigation steps taken by the Strands AI agent.\n")
        f.write("The agent autonomously selected tools based on its analysis of the issue.\n")
        f.write("Each step includes the agent's reasoning for why it chose that action.\n")

    return output_path


def generate_full_investigation_report(investigation_result, report_path="/tmp/investigation-report.txt"):
    """Generate the full investigation report including reasoning."""

    report = investigation_result.get("report", {})
    service = investigation_result.get("service", "unknown")
    environment = investigation_result.get("environment", "unknown")

    # Extract text from Strands format if needed
    if isinstance(report, dict) and "content" in report:
        content = report.get("content", [])
        if isinstance(content, list) and len(content) > 0:
            report_text = content[0].get("text", "No report text")
        else:
            report_text = str(report)
    else:
        report_text = str(report)

    with open(report_path, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("DEVOPS INVESTIGATION REPORT\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Service: {service}\n")
        f.write(f"Environment: {environment}\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write(report_text)
        f.write("\n")

    return report_path
