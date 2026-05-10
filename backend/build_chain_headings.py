#!/usr/bin/env python3
"""
Erzeugt chain_headings.json: UID (Kompetenzstufe, Basis ohne .u0) → Langtext aus dem
HTML-Block kompetenztitel auf https://BS.lehrplan.ch/{uid}

Einmalig oder nach Aktualisierung von Lehrplan21.json ausführen:

  cd backend && python3 build_chain_headings.py

Die JSON wird von server.py geladen — keine langsamen HTTP-Zugriffe bei der Suche.

Optional: bestehende Datei wird gemerged (--resume), bereits vorhandene UIDs werden übersprungen.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_KOMPETENZTITEL_PATTERN = re.compile(
    r'class="kompetenztitel[^>]*>[\s\S]*?komptitelnr[^<]*</p>\s*<p>\s*([^<]+)',
    re.IGNORECASE,
)


def collect_uid_bases(lehrplan_path: Path) -> list[str]:
    data = json.loads(lehrplan_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Lehrplan21.json muss eine Liste sein")
    bases = set()
    for row in data:
        if row.get("strukturtyp") != "Kompetenzstufe":
            continue
        uid = row.get("uid")
        if not uid:
            continue
        bases.add(str(uid).strip().split(".")[0])
    return sorted(bases)


def fetch_heading(uid_base: str, user_agent: str) -> str | None:
    req = urllib.request.Request(
        f"https://BS.lehrplan.ch/{uid_base}",
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    match = _KOMPETENZTITEL_PATTERN.search(html)
    return match.group(1).strip() if match else None


def main() -> int:
    parser = argparse.ArgumentParser(description="chain_headings.json aus BS-Lehrplan HTML erzeugen")
    parser.add_argument(
        "--lehrplan",
        type=Path,
        default=None,
        help="Pfad zu Lehrplan21.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Ausgabe chain_headings.json",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.06,
        help="Pause zwischen Requests (Sekunden)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="output mergen: vorhandene Einträge nicht neu laden",
    )
    parser.add_argument("--limit", type=int, default=0, help="Nur erste N UIDs (Test)")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    lehrplan_path = args.lehrplan or (backend_dir / "Lehrplan21.json")
    output_path = args.output or (backend_dir / "chain_headings.json")

    if not lehrplan_path.is_file():
        print(f"Nicht gefunden: {lehrplan_path}", file=sys.stderr)
        return 2

    bases = collect_uid_bases(lehrplan_path)
    if args.limit and args.limit > 0:
        bases = bases[: args.limit]

    result: dict[str, str] = {}
    if args.resume and output_path.is_file():
        try:
            prev = json.loads(output_path.read_text(encoding="utf-8"))
            if isinstance(prev, dict):
                for k, v in prev.items():
                    if isinstance(k, str) and isinstance(v, str) and v.strip():
                        result[str(k).strip().split(".")[0]] = v.strip()
        except (json.JSONDecodeError, OSError):
            pass

    ua = os.getenv(
        "CHAIN_HEADINGS_USER_AGENT",
        "Mozilla/5.0 (compatible; LehrplanBaselSearch-build/1.0)",
    )

    todo = [b for b in bases if b not in result]
    total = len(todo)
    ok = 0
    fail = 0

    print(f"Zu laden: {total} UIDs (Schon im Cache: {len(result)}) → {output_path}", flush=True)

    def save_partial() -> None:
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")

    for i, base in enumerate(todo):
        title = fetch_heading(base, ua)
        if title:
            result[base] = title
            ok += 1
        else:
            fail += 1
        if args.delay > 0:
            time.sleep(args.delay)
        if (i + 1) % 100 == 0 or i + 1 == total:
            save_partial()
            print(f"  … {i + 1}/{total} (ok {ok}, fehlend {fail})", flush=True)

    save_partial()
    print(f"Fertig: {len(result)} Einträge in {output_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
