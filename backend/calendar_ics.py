"""Fetch and parse external iCalendar (.ics) feeds for /api/calendar/fetch."""

from __future__ import annotations

import ipaddress
import re
import socket
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from icalendar import Calendar

MAX_ICS_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT_SEC = 20
USER_AGENT = "LehrplanAPP-Calendar/1.0"


def _is_blocked_host(host: str) -> bool:
    if not host:
        return True
    host = host.strip().lower()
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return True
    try:
        for info in socket.getaddrinfo(host, None):
            addr = info[4][0]
            ip = ipaddress.ip_address(addr)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
            ):
                return True
    except socket.gaierror:
        return True
    return False


def validate_calendar_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("https", "http", "webcal"):
        raise ValueError("Nur http(s)- oder webcal-URLs erlaubt.")
    if not parsed.netloc:
        raise ValueError("Ungültige URL.")
    host = parsed.hostname or ""
    if _is_blocked_host(host):
        raise ValueError("Diese URL ist nicht erlaubt.")
    normalized = parsed._replace(scheme="https" if parsed.scheme == "webcal" else parsed.scheme)
    return normalized.geturl()


def fetch_ics_text(url: str) -> str:
    safe_url = validate_calendar_url(url)
    req = Request(
        safe_url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/calendar,*/*"},
    )
    with urlopen(req, timeout=FETCH_TIMEOUT_SEC) as resp:
        data = resp.read(MAX_ICS_BYTES + 1)
    if len(data) > MAX_ICS_BYTES:
        raise ValueError("Kalenderdatei ist zu gross (max. 2 MB).")
    return data.decode("utf-8", errors="replace")


def _to_iso(dt) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return None


def parse_ics_events(ics_text: str, subscription_id: str) -> list[dict]:
    cal = Calendar.from_ical(ics_text)
    events = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        uid = str(component.get("UID", ""))
        title = str(component.get("SUMMARY", "Termin"))
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        if not dtstart:
            continue
        start = dtstart.dt
        end = dtend.dt if dtend else start
        all_day = not isinstance(start, datetime)
        if all_day:
            start_iso = start.isoformat() if hasattr(start, "isoformat") else str(start)
            end_iso = end.isoformat() if hasattr(end, "isoformat") else str(end)
        else:
            start_iso = _to_iso(start)
            end_iso = _to_iso(end) if isinstance(end, datetime) else start_iso
        events.append(
            {
                "id": f"sub-{subscription_id}-{re.sub(r'[^a-zA-Z0-9_-]', '_', uid)[:80]}",
                "title": title,
                "start": start_iso,
                "end": end_iso,
                "allDay": all_day,
                "subscriptionId": subscription_id,
            }
        )
    return events


def fetch_subscription_events(url: str, subscription_id: str) -> dict:
    try:
        text = fetch_ics_text(url)
        events = parse_ics_events(text, subscription_id)
        return {"ok": True, "events": events, "fetchedAt": datetime.now(timezone.utc).isoformat()}
    except (URLError, ValueError, OSError) as exc:
        return {"ok": False, "error": str(exc), "events": []}
