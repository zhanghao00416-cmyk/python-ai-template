"""Built-in tool: datetime_now — current date/time with optional timezone.

TOOLS_MCP_SPEC §5: datetime_now | tool | 获取当前日期/时间 | F10
"""

from __future__ import annotations

from datetime import datetime, timezone


async def datetime_now(tz: str = "UTC") -> dict[str, str]:
    """Return current date/time in ISO format.

    Args:
        tz: Timezone name. Currently supports 'UTC' and 'local'.
    """
    if tz.lower() in ("utc",):
        dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now()

    return {
        "iso": dt.isoformat(),
        "date": dt.strftime("%Y-%m-%d"),
        "time": dt.strftime("%H:%M:%S"),
        "tz": tz,
    }
