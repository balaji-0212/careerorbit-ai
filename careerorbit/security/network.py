"""Network-boundary helpers for the local-only, single-user application."""

import ipaddress


def is_loopback_host(host: str) -> bool:
    """Return whether a host literal or localhost name is confined to this device."""
    normalized = str(host or "").strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized.strip("[]")).is_loopback
    except ValueError:
        return False
