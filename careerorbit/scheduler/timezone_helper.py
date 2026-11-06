"""Timezone interpretation, verification, and trigger calculation for CareerOrbit AI.

Ensures that the intended daily execution time of 08:00 AM Asia/Kolkata (IST, UTC+05:30)
is reliably scheduled and executed regardless of the host machine's system timezone.
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

IST = timezone(timedelta(hours=5, minutes=30), "Asia/Kolkata")
TARGET_IST_HOUR = 8
TARGET_IST_MINUTE = 0
IST_OFFSET_MINUTES = 330  # 5 hours 30 minutes


def get_machine_timezone_info(
    custom_offset_seconds: Optional[int] = None,
    custom_tz_name: Optional[str] = None
) -> Dict[str, Any]:
    """Retrieve machine timezone identifier and current UTC offset."""
    if custom_offset_seconds is not None:
        offset_sec = custom_offset_seconds
        tz_name = custom_tz_name or ("India Standard Time" if offset_sec == 19800 else "Custom Timezone")
    else:
        local_now = datetime.now().astimezone()
        offset = local_now.utcoffset()
        offset_sec = int(offset.total_seconds()) if offset else 0
        tz_name = local_now.tzname() or time.strftime("%Z") or "Local Time"

    sign = "+" if offset_sec >= 0 else "-"
    total_minutes = abs(offset_sec) // 60
    hours = total_minutes // 60
    minutes = total_minutes % 60
    offset_str = f"{sign}{hours:02d}:{minutes:02d}"

    is_ist = (offset_sec == 19800)

    return {
        "timezone_name": tz_name,
        "utc_offset_seconds": offset_sec,
        "utc_offset_string": offset_str,
        "is_ist": is_ist,
    }


def compute_local_trigger_time(
    target_ist_hour: int = TARGET_IST_HOUR,
    target_ist_minute: int = TARGET_IST_MINUTE,
    system_offset_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """Calculate the local machine trigger time corresponding to target IST time.
    
    Example:
    - On IST (UTC+05:30): 08:00 IST -> Local 08:00 AM
    - On UTC (UTC+00:00): 08:00 IST -> Local 02:30 AM
    - On EST (UTC-05:00): 08:00 IST -> Local 09:30 PM (21:30)
    - On PST (UTC-08:00): 08:00 IST -> Local 06:30 PM (18:30)
    """
    tz_info = get_machine_timezone_info(custom_offset_seconds=system_offset_seconds)
    offset_minutes = tz_info["utc_offset_seconds"] // 60

    # 1. Target IST to UTC
    ist_minutes = target_ist_hour * 60 + target_ist_minute
    utc_minutes = (ist_minutes - IST_OFFSET_MINUTES) % 1440
    utc_hour = utc_minutes // 60
    utc_min = utc_minutes % 60

    # 2. UTC to Local machine time
    local_minutes = (utc_minutes + offset_minutes) % 1440
    local_hour = local_minutes // 60
    local_min = local_minutes % 60

    # 12-hour format with AM/PM for Windows Task Scheduler
    period = "PM" if local_hour >= 12 else "AM"
    hour_12 = 12 if (local_hour % 12 == 0) else (local_hour % 12)
    trigger_12h = f"{hour_12:02d}:{local_min:02d} {period}"
    trigger_24h = f"{local_hour:02d}:{local_min:02d}"

    if tz_info["is_ist"]:
        diag = "Machine is in India Standard Time. Local trigger matches target IST directly."
    else:
        diag = (
            f"Machine timezone ({tz_info['timezone_name']}, UTC{tz_info['utc_offset_string']}) "
            f"differs from Asia/Kolkata (UTC+05:30). Configured local trigger {trigger_12h} "
            f"executes precisely at {target_ist_hour:02d}:{target_ist_minute:02d} IST."
        )

    return {
        "target_ist_time": f"{target_ist_hour:02d}:{target_ist_minute:02d} Asia/Kolkata",
        "target_utc_time": f"{utc_hour:02d}:{utc_min:02d} UTC",
        "local_trigger_time_12h": trigger_12h,
        "local_trigger_time_24h": trigger_24h,
        "machine_timezone": tz_info["timezone_name"],
        "machine_utc_offset": tz_info["utc_offset_string"],
        "is_native_ist": tz_info["is_ist"],
        "diagnostic_message": diag,
    }


def validate_timezone_compatibility(
    configured_trigger_12h: Optional[str] = None,
    custom_offset_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """Validate whether the configured trigger will execute at 08:00 AM IST."""
    calc = compute_local_trigger_time(system_offset_seconds=custom_offset_seconds)
    expected_trigger = calc["local_trigger_time_12h"].upper()

    if configured_trigger_12h is None:
        is_compatible = True
        status = "NATIVE_IST" if calc["is_native_ist"] else "OFFSET_ADJUSTED"
        note = "No existing trigger supplied; calculation generated intended trigger."
    else:
        norm_configured = configured_trigger_12h.strip().upper()
        if norm_configured == expected_trigger:
            is_compatible = True
            status = "NATIVE_IST" if calc["is_native_ist"] else "OFFSET_ADJUSTED"
            note = f"Configured trigger ({norm_configured}) matches expected IST equivalent ({expected_trigger})."
        else:
            is_compatible = False
            status = "TIMEZONE_MISMATCH"
            note = (
                f"Configured trigger ({norm_configured}) does not match required local trigger "
                f"({expected_trigger}) for 08:00 AM IST on {calc['machine_timezone']}."
            )

    return {
        "is_compatible": is_compatible,
        "status": status,
        "note": note,
        "expected_trigger": expected_trigger,
        "machine_timezone": calc["machine_timezone"],
        "machine_utc_offset": calc["machine_utc_offset"],
        "target_schedule": calc["target_ist_time"],
    }
