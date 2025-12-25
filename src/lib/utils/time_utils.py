"""Time utilities for Clippy tools.

Provides relative time formatting to help Claude give accurate time-based responses.
"""

from datetime import datetime, timezone


def format_relative_time(timestamp: str | int | float | datetime) -> str:
    """Convert a timestamp to a human-readable relative time string.

    Args:
        timestamp: ISO 8601 string, Unix timestamp (seconds or milliseconds), or datetime object

    Returns:
        Relative time string like "5 minutes ago", "2 hours ago", "3 days ago"

    Examples:
        >>> format_relative_time("2024-12-24T10:00:00Z")  # If now is 10:05
        "5 minutes ago"
        >>> format_relative_time(1735041600000)  # Unix ms
        "2 hours ago"
    """
    try:
        now = datetime.now(timezone.utc)

        # Parse the timestamp
        if isinstance(timestamp, datetime):
            dt = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
        elif isinstance(timestamp, (int, float)):
            # Unix timestamp - check if milliseconds (>1e12) or seconds
            if timestamp > 1e12:
                timestamp = timestamp / 1000
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif isinstance(timestamp, str):
            # ISO 8601 string - handle various formats
            ts = timestamp.replace("Z", "+00:00")
            # Handle both "2024-12-24T10:00:00" and "2024-12-24 10:00:00"
            ts = ts.replace(" ", "T")
            try:
                dt = datetime.fromisoformat(ts)
            except ValueError:
                # Try parsing just date
                if len(ts) == 10:
                    dt = datetime.strptime(ts, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                else:
                    return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        else:
            return None

        # Calculate delta
        delta = now - dt
        seconds = delta.total_seconds()

        # Handle future times
        if seconds < 0:
            return "just now"

        # Format relative time
        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        elif seconds < 604800:
            days = int(seconds / 86400)
            return f"{days} day{'s' if days != 1 else ''} ago"
        elif seconds < 2592000:
            weeks = int(seconds / 604800)
            return f"{weeks} week{'s' if weeks != 1 else ''} ago"
        else:
            months = int(seconds / 2592000)
            return f"{months} month{'s' if months != 1 else ''} ago"

    except Exception as e:
        print(f"[time_utils] Error parsing timestamp {timestamp}: {e}")
        return None


def add_relative_time(data: dict, timestamp_field: str, relative_field: str = None) -> dict:
    """Add a relative time field to a dictionary based on a timestamp field.

    Args:
        data: Dictionary containing the timestamp
        timestamp_field: Key of the timestamp field
        relative_field: Key for the relative time (default: {timestamp_field}_relative)

    Returns:
        The same dictionary with relative time added

    Example:
        >>> add_relative_time({"created": "2024-12-24T10:00:00Z"}, "created")
        {"created": "2024-12-24T10:00:00Z", "created_relative": "5 minutes ago"}
    """
    if relative_field is None:
        relative_field = f"{timestamp_field}_relative"

    timestamp = data.get(timestamp_field)
    if timestamp:
        relative = format_relative_time(timestamp)
        if relative:
            data[relative_field] = relative

    return data
