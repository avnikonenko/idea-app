from datetime import datetime


def readable_time(value: str) -> str:
    """Show stored timestamps in local time with an explicit timezone."""
    return datetime.fromisoformat(value).astimezone().strftime("%d.%m.%Y, %H:%M:%S %Z")
