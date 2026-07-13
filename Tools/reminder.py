import re
from datetime import datetime, timedelta
from livekit.agents import function_tool


def parse_time_duration(time_str: str) -> int:
    """Parse time duration string to seconds"""
    s = time_str.lower().strip()

    patterns = [
        (r'(\d+)\s*(?:seconds?|secs?|s\b)',  1),
        (r'(\d+)\s*(?:minutes?|mins?|m\b)',   60),
        (r'(\d+)\s*(?:hours?|hrs?|h\b)',      3600),
        (r'(\d+)\s*(?:days?|d\b)',            86400),
        (r'(\d+)\s*(?:weeks?|w\b)',           604800),
    ]

    for pattern, multiplier in patterns:
        match = re.search(pattern, s)
        if match:
            return int(match.group(1)) * multiplier

    # Bare number → treat as minutes
    match = re.search(r'(\d+)', s)
    if match:
        return int(match.group(1)) * 60

    return 0


@function_tool()
async def set_reminder(
    reminder_text: str,
    time_duration: str = "10 minutes",
    reminder_type: str = "message",
) -> str:
    """
    Set a reminder for later.
    Examples:
      - "10 minutes later remind me about meeting"
      - "after 1 hour call mom"
      - "remind me in 30 seconds"

    Args:
        reminder_text: What to remind about.
        time_duration: When to remind — e.g. "10 minutes", "1 hour", "30 seconds".
        reminder_type: Type of reminder (message, alert, etc.).
    """
    try:
        import tools
        if not hasattr(tools, 'assistant_instance') or tools.assistant_instance is None:
            return "❌ Reminder system not available"

        seconds = parse_time_duration(time_duration)
        if seconds <= 0:
            return (
                "❌ Could not understand the time. "
                "Try something like '10 minutes', '1 hour', or '30 seconds'."
            )

        reminder_time = datetime.now() + timedelta(seconds=seconds)

        reminder_id = tools.assistant_instance.add_reminder(
            reminder_text=reminder_text,
            reminder_time=reminder_time,
            reminder_type=reminder_type,
        )

        # Human-readable time left
        h, rem = divmod(seconds, 3600)
        m, s   = divmod(rem, 60)
        parts  = []
        if h: parts.append(f"{h} hour{'s' if h > 1 else ''}")
        if m: parts.append(f"{m} minute{'s' if m > 1 else ''}")
        if s: parts.append(f"{s} second{'s' if s > 1 else ''}")
        human = " and ".join(parts) if parts else f"{seconds} seconds"

        return (
            f"✅ Reminder set!\n"
            f"📝 {reminder_text}\n"
            f"⏰ Due at: {reminder_time.strftime('%I:%M:%S %p on %d %b %Y')}\n"
            f"⏳ In: {human}\n"
            f"🆔 ID: {reminder_id}"
        )

    except Exception as e:
        return f"❌ Failed to set reminder: {e}"


@function_tool()
async def view_reminders() -> str:
    """View all active reminders and their remaining time."""
    try:
        import tools
        if not hasattr(tools, 'assistant_instance') or tools.assistant_instance is None:
            return "❌ Reminder system not available"

        reminders = tools.assistant_instance.get_reminders()
        if not reminders:
            return "📋 No active reminders."

        lines = ["📋 Active Reminders:\n"]
        now   = datetime.now()

        for rid, r in reminders.items():
            due       = r['time']
            left_secs = max(0, int((due - now).total_seconds()))
            h, rem    = divmod(left_secs, 3600)
            m, s      = divmod(rem, 60)
            left_str  = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

            lines.append(
                f"🆔 {rid}\n"
                f"📝 {r['text']}\n"
                f"⏰ Due: {due.strftime('%I:%M:%S %p, %d %b %Y')}\n"
                f"⏳ Time left: {left_str}\n"
            )

        return "\n".join(lines)

    except Exception as e:
        return f"❌ Failed to view reminders: {e}"


@function_tool()
async def cancel_reminder(reminder_id: str) -> str:
    """
    Cancel a specific reminder by its ID.

    Args:
        reminder_id: The ID returned when the reminder was created (e.g. reminder_0).
    """
    try:
        import tools
        if not hasattr(tools, 'assistant_instance') or tools.assistant_instance is None:
            return "❌ Reminder system not available"

        success = tools.assistant_instance.cancel_reminder(reminder_id)
        if success:
            return f"✅ Reminder '{reminder_id}' cancelled."
        else:
            return f"❌ No reminder found with ID '{reminder_id}'."

    except Exception as e:
        return f"❌ Failed to cancel reminder: {e}"