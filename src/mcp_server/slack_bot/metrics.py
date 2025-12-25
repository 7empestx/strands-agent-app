"""Metrics tracking for Clippy Slack bot.

Provides request tracking, tool usage statistics, and performance monitoring.
"""

import threading


class ClippyMetrics:
    """Track metrics for monitoring and debugging."""

    def __init__(self):
        self.total_requests = 0
        self.truncations = 0
        self.tool_limit_hits = 0
        self.tool_usage = {}
        self.errors = 0
        self.response_times = []
        self._lock = threading.Lock()

    def record_request(
        self,
        duration_ms: float,
        tools_used: list,
        was_truncated: bool,
        hit_limit: bool,
        error: bool = False,
    ):
        """Record a request with its metrics.

        Args:
            duration_ms: Time taken to process the request
            tools_used: List of tool names that were called
            was_truncated: Whether any tool results were truncated
            hit_limit: Whether max tool calls limit was reached
            error: Whether an error occurred
        """
        with self._lock:
            self.total_requests += 1
            self.response_times.append(duration_ms)
            if was_truncated:
                self.truncations += 1
            if hit_limit:
                self.tool_limit_hits += 1
            if error:
                self.errors += 1
            for tool in tools_used:
                self.tool_usage[tool] = self.tool_usage.get(tool, 0) + 1

    def get_stats(self) -> dict:
        """Get current statistics.

        Returns:
            dict with statistics including request counts, rates, and tool usage
        """
        with self._lock:
            avg_response = (
                sum(self.response_times[-100:]) / len(self.response_times[-100:]) if self.response_times else 0
            )
            return {
                "total_requests": self.total_requests,
                "truncations": self.truncations,
                "truncation_rate": f"{100 * self.truncations / max(1, self.total_requests):.1f}%",
                "tool_limit_hits": self.tool_limit_hits,
                "tool_limit_rate": f"{100 * self.tool_limit_hits / max(1, self.total_requests):.1f}%",
                "errors": self.errors,
                "avg_response_ms": f"{avg_response:.0f}",
                "tool_usage": dict(sorted(self.tool_usage.items(), key=lambda x: -x[1])),
            }

    def log_summary(self):
        """Log a summary of current metrics."""
        stats = self.get_stats()
        print(
            f"[Clippy Metrics] Requests: {stats['total_requests']} | "
            f"Truncations: {stats['truncations']} ({stats['truncation_rate']}) | "
            f"Tool limits: {stats['tool_limit_hits']} ({stats['tool_limit_rate']}) | "
            f"Errors: {stats['errors']} | "
            f"Avg response: {stats['avg_response_ms']}ms"
        )


# Global metrics instance
_metrics = ClippyMetrics()


def get_metrics() -> ClippyMetrics:
    """Get the global metrics instance."""
    return _metrics
