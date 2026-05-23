"""Veröffentlichter iCal-Feed für Apple Kalender / andere Abonnenten."""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

FEED_DIR = Path(__file__).resolve().parent / "data" / "calendar_feeds"
CALNAME = "Lehrplan Planung"


def ensure_feed_dir() -> None:
    FEED_DIR.mkdir(parents=True, exist_ok=True)


def _escape_ics(text: str) -> str:
    s = (text or "").replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,")
    return re.sub(r"[;\r]", "", s)


def _format_dt(value: str, all_day: bool) -> str:
    if not value:
        return ""
    if all_day:
        return value[:10].replace("-", "")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y%m%dT%H%M%SZ")
    except ValueError:
        return ""


def build_ics(events: list[dict]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//LehrplanAPP//Planung//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape_ics(CALNAME)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT15M",
        "X-PUBLISHED-TTL:PT15M",
    ]
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for ev in events:
        uid = _escape_ics(str(ev.get("uid") or ev.get("id") or secrets.token_hex(8)))
        summary = _escape_ics(str(ev.get("summary") or ev.get("title") or "Termin"))
        all_day = bool(ev.get("allDay"))
        dtstart = _format_dt(ev.get("start") or "", all_day)
        dtend = _format_dt(ev.get("end") or ev.get("start") or "", all_day)
        if not dtstart:
            continue
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{uid}@lehrplan-app")
        lines.append(f"DTSTAMP:{now}")
        if all_day:
            lines.append(f"DTSTART;VALUE=DATE:{dtstart}")
            if dtend and dtend != dtstart:
                lines.append(f"DTEND;VALUE=DATE:{dtend}")
        else:
            lines.append(f"DTSTART:{dtstart}")
            if dtend:
                lines.append(f"DTEND:{dtend}")
        lines.append(f"SUMMARY:{summary}")
        desc = ev.get("description") or ev.get("notes") or ""
        if desc:
            lines.append(f"DESCRIPTION:{_escape_ics(str(desc))}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def publish_feed(token: str, events: list[dict]) -> None:
    ensure_feed_dir()
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", token)[:64]
    if not safe:
        raise ValueError("Ungültiger Token")
    path = FEED_DIR / f"{safe}.json"
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "events": events,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_feed_ics(token: str) -> str | None:
    safe = re.sub(r"[^a-zA-Z0-9_-]", "", token)[:64]
    path = FEED_DIR / f"{safe}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        events = data.get("events") or []
        return build_ics(events)
    except (json.JSONDecodeError, OSError):
        return None


def new_export_token() -> str:
    return secrets.token_urlsafe(24)
