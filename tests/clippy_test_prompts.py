"""
Test prompts for Clippy AI Slack bot.

Based on real patterns from DevOps Slack history.
Run with: python tests/clippy_test_prompts.py

Usage:
  python tests/clippy_test_prompts.py                    # Run all tests
  python tests/clippy_test_prompts.py -c troubleshooting # Run one category
  python tests/clippy_test_prompts.py -p "check errors"  # Test single prompt
  python tests/clippy_test_prompts.py -i                 # Interactive mode
  python tests/clippy_test_prompts.py --list             # List all prompts
"""

import sys
import os
import json
from datetime import datetime

# Add mcp-servers to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mcp-servers"))

# Test prompts organized by category
TEST_PROMPTS = {
    "troubleshooting": [
        ("504 Errors", "We're seeing 504 errors on Cast staging for syncAll endpoint. Can you check CloudWatch?"),
        ("Permission Issues", "I'm having permissions issues uploading documents on dashboard-app in dev - works locally"),
        ("CORS Errors", "Getting CORS errors on the S3 bucket for document uploads"),
        ("Lambda Timeout", "The payment webhook Lambda is timing out in prod"),
        ("Database Connection", "Getting connection refused errors to the RDS instance"),
    ],
    "pr_and_deploys": [
        ("PR Approval", "Can I get an approval on this PR? https://bitbucket.org/mrrobot-labs/cast-core-service/pull-requests/717"),
        ("Reenable Pipelines", "How do we reenable pipelines for emvio-api-documentation?"),
        ("Deploy Status", "What's the status of recent deploys to staging?"),
        ("Failed Build", "The latest build on mrrobot-auth-rest is failing, can you check?"),
        ("PR Review", "Can you review this PR? https://bitbucket.org/mrrobot-labs/emvio-gateway/pull-requests/123"),
    ],
    "history_and_precedent": [
        ("Past 504s", "How did we handle the 504 errors on Cast before?"),
        ("S3 Issues", "Have we seen S3 permission issues on dashboard-app before?"),
        ("Readme Auth", "What was the resolution for the readme.com authentication issue?"),
        ("Similar Outage", "Have we had this type of outage before?"),
        ("Past Solution", "How did we fix the CORS issue last time?"),
    ],
    "access_requests": [
        ("SFTP Setup", "Can someone set up an SFTP user with root access for a new merchant?"),
        ("New User", "Can we get a new AWS IAM user for the contractor?"),
        ("VPN Access", "I need VPN access for a new team member"),
        ("SSH Key", "I accidentally overwrote my SSH key, can someone help?"),
        ("API Credentials", "Need API credentials for the new integration"),
    ],
    "code_search": [
        ("Find Config", "Where is the S3 bucket configuration for document uploads?"),
        ("Auth Flow", "How does authentication work in mrrobot-auth-rest?"),
        ("Lambda Handler", "Find the Lambda handler for payment webhooks"),
        ("Database Schema", "Where are the database migrations for the user table?"),
        ("API Endpoint", "Where is the syncAll endpoint defined in cast-core?"),
    ],
    "conversational": [
        ("Greeting", "Hi Clippy!"),
        ("Help", "What can you help me with?"),
        ("Thanks", "Thanks for the help!"),
        ("Unclear Request", "There's an issue"),
        ("Follow Up", "Can you tell me more about that?"),
    ],
    "vague_requests": [
        ("Generic Issue", "something's broken"),
        ("Unspecified Error", "getting errors"),
        ("No Details", "it's not working"),
        ("Help Request", "can someone help?"),
        ("Partial Info", "prod is down"),
    ],
}


class TestMetrics:
    """Track metrics across test runs."""

    def __init__(self):
        self.results = []
        self.truncations = 0
        self.max_tools_hit = 0
        self.tool_usage = {}
        self.response_times = []

    def record(self, result: dict):
        self.results.append(result)

        # Track tool usage
        tool = result.get('tool_used') or 'respond_directly'
        self.tool_usage[tool] = self.tool_usage.get(tool, 0) + 1

        # Track all tools if multiple were used
        for t in result.get('all_tools_used', []):
            if t != tool:
                self.tool_usage[t] = self.tool_usage.get(t, 0) + 1

        # Track truncations and limits
        if result.get('was_truncated'):
            self.truncations += 1
        if result.get('hit_tool_limit'):
            self.max_tools_hit += 1

    def summary(self):
        total = len(self.results)
        if total == 0:
            return "No tests run"

        passed = sum(1 for r in self.results if r.get("success"))

        lines = [
            f"\n{'='*80}",
            "METRICS SUMMARY",
            "="*80,
            f"Total tests: {total}",
            f"Passed: {passed} ({100*passed//total}%)",
            f"Failed: {total - passed}",
            f"Truncations: {self.truncations}",
            f"Hit max tool limit: {self.max_tools_hit}",
            "",
            "Tool usage:",
        ]

        for tool, count in sorted(self.tool_usage.items(), key=lambda x: -x[1]):
            lines.append(f"  {tool}: {count}")

        return "\n".join(lines)


def run_tests(categories=None, verbose=True, save_results=False):
    """Run test prompts against Clippy.

    Args:
        categories: List of categories to test (None = all)
        verbose: Print full responses
        save_results: Save results to JSON file
    """
    from slack_bot import invoke_claude_with_tools

    metrics = TestMetrics()
    results = []

    for category, prompts in TEST_PROMPTS.items():
        if categories and category not in categories:
            continue

        print(f"\n{'='*80}")
        print(f"CATEGORY: {category.upper()}")
        print("="*80)

        for name, prompt in prompts:
            print(f"\n[{name}]")
            print(f"PROMPT: {prompt[:70]}{'...' if len(prompt) > 70 else ''}")
            print("-"*60)

            try:
                result = invoke_claude_with_tools(prompt)
                tool = result.get('tool_used') or 'respond_directly'
                all_tools = result.get('all_tools_used', [])
                response = result.get('response', 'No response')

                # Check for truncation warning in response
                was_truncated = 'truncated' in response.lower() or result.get('was_truncated')
                hit_limit = 'need more information' in response.lower()

                print(f"TOOL: {tool}")
                if len(all_tools) > 1:
                    print(f"ALL TOOLS: {' -> '.join(all_tools)}")

                if was_truncated:
                    print("WARNING: Results were truncated")
                if hit_limit:
                    print("WARNING: Hit max tool call limit")

                if verbose:
                    print(f"\nRESPONSE:\n{response[:600]}")
                    if len(response) > 600:
                        print(f"... [{len(response) - 600} more chars]")

                result_record = {
                    "category": category,
                    "name": name,
                    "prompt": prompt,
                    "tool_used": tool,
                    "all_tools_used": all_tools,
                    "response": response,
                    "was_truncated": was_truncated,
                    "hit_tool_limit": hit_limit,
                    "success": "error" not in response.lower() and "encountered an error" not in response.lower()
                }

                results.append(result_record)
                metrics.record(result_record)

            except Exception as e:
                print(f"ERROR: {e}")
                import traceback
                traceback.print_exc()

                result_record = {
                    "category": category,
                    "name": name,
                    "prompt": prompt,
                    "tool_used": "error",
                    "response": str(e),
                    "success": False
                }
                results.append(result_record)
                metrics.record(result_record)

    print(metrics.summary())

    if save_results:
        filename = f"test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {filename}")

    return results, metrics


def run_single_prompt(prompt: str, thread_context: list = None):
    """Test a single prompt with optional thread context."""
    from slack_bot import invoke_claude_with_tools

    print(f"\nPROMPT: {prompt}")
    if thread_context:
        print(f"CONTEXT: {len(thread_context)} previous messages")
    print("="*60)

    result = invoke_claude_with_tools(prompt, thread_context=thread_context)
    tool = result.get('tool_used') or 'respond_directly'
    all_tools = result.get('all_tools_used', [])
    response = result.get('response', 'No response')

    print(f"\nTOOL: {tool}")
    if len(all_tools) > 1:
        print(f"ALL TOOLS: {' -> '.join(all_tools)}")
    print(f"\nRESPONSE:\n{response}")

    return result


def interactive_mode():
    """Interactive testing mode - type prompts and see responses.

    Supports simulated thread context for testing follow-ups.
    """
    from slack_bot import invoke_claude_with_tools

    print("\n" + "="*60)
    print("CLIPPY INTERACTIVE TEST MODE")
    print("="*60)
    print("Commands:")
    print("  /quit or /q      - Exit")
    print("  /clear or /c     - Clear thread context")
    print("  /context         - Show current thread context")
    print("  /rate <1-5>      - Rate last response quality")
    print("  /save            - Save session to file")
    print("  /help            - Show this help")
    print("="*60 + "\n")

    thread_context = []
    session_log = []
    last_response = None

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.startswith("/"):
            cmd = user_input.lower().split()[0]

            if cmd in ["/quit", "/q"]:
                break
            elif cmd in ["/clear", "/c"]:
                thread_context = []
                print("Thread context cleared.")
                continue
            elif cmd == "/context":
                if thread_context:
                    print(f"\nThread context ({len(thread_context)} messages):")
                    for msg in thread_context[-5:]:
                        print(f"  {msg[:80]}...")
                else:
                    print("No thread context.")
                continue
            elif cmd == "/rate":
                parts = user_input.split()
                if len(parts) == 2 and parts[1].isdigit():
                    rating = int(parts[1])
                    if 1 <= rating <= 5 and last_response:
                        session_log[-1]["rating"] = rating
                        print(f"Rated last response: {rating}/5")
                    else:
                        print("Usage: /rate <1-5>")
                continue
            elif cmd == "/save":
                filename = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(filename, 'w') as f:
                    json.dump(session_log, f, indent=2)
                print(f"Session saved to {filename}")
                continue
            elif cmd == "/help":
                print("Commands: /quit /clear /context /rate /save /help")
                continue
            else:
                print(f"Unknown command: {cmd}")
                continue

        # Run the prompt
        print("\nClippy: ", end="", flush=True)

        try:
            result = invoke_claude_with_tools(user_input, thread_context=thread_context)
            response = result.get('response', 'No response')
            tool = result.get('tool_used') or 'respond_directly'
            all_tools = result.get('all_tools_used', [])

            print(response)

            if tool and tool != 'respond_directly':
                tools_str = ' -> '.join(all_tools) if len(all_tools) > 1 else tool
                print(f"\n[Tools: {tools_str}]")

            # Update thread context
            thread_context.append(f"User: {user_input}")
            thread_context.append(f"Clippy: {response[:500]}")

            # Log for session
            last_response = result
            session_log.append({
                "timestamp": datetime.now().isoformat(),
                "prompt": user_input,
                "tool": tool,
                "all_tools": all_tools,
                "response": response,
                "context_size": len(thread_context)
            })

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()

    # Offer to save on exit
    if session_log:
        save = input("\nSave session log? (y/n): ").lower().strip()
        if save == 'y':
            filename = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w') as f:
                json.dump(session_log, f, indent=2)
            print(f"Saved to {filename}")


def test_follow_up_scenario():
    """Test a multi-turn conversation scenario."""
    from slack_bot import invoke_claude_with_tools

    print("\n" + "="*60)
    print("FOLLOW-UP SCENARIO TEST")
    print("="*60)

    # Simulate a real conversation
    conversation = [
        "We're seeing 504 errors on cast-core in prod",
        "When did this start?",
        "Were there any recent deploys?",
        "Can you check the logs for more details?",
    ]

    thread_context = []

    for i, prompt in enumerate(conversation):
        print(f"\n--- Turn {i+1} ---")
        print(f"User: {prompt}")

        result = invoke_claude_with_tools(prompt, thread_context=thread_context)
        response = result.get('response', 'No response')
        tool = result.get('tool_used', 'none')

        print(f"Tool: {tool}")
        print(f"Clippy: {response[:300]}...")

        # Add to context for next turn
        thread_context.append(f"User: {prompt}")
        thread_context.append(f"Clippy: {response[:500]}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test Clippy with sample prompts")
    parser.add_argument("--category", "-c", help="Category to test")
    parser.add_argument("--prompt", "-p", help="Single prompt to test")
    parser.add_argument("--quiet", "-q", action="store_true", help="Less verbose output")
    parser.add_argument("--list", "-l", action="store_true", help="List all prompts")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--save", "-s", action="store_true", help="Save results to JSON")
    parser.add_argument("--followup", "-f", action="store_true", help="Test follow-up scenario")

    args = parser.parse_args()

    if args.list:
        for category, prompts in TEST_PROMPTS.items():
            print(f"\n{category}:")
            for name, prompt in prompts:
                print(f"  - {name}: {prompt[:50]}...")
    elif args.interactive:
        interactive_mode()
    elif args.followup:
        test_follow_up_scenario()
    elif args.prompt:
        run_single_prompt(args.prompt)
    else:
        categories = [args.category] if args.category else None
        run_tests(categories=categories, verbose=not args.quiet, save_results=args.save)
