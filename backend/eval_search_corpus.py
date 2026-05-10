#!/usr/bin/env python3
"""
Recall@k gegen die Live-/search-API: Queries aus Lehrplan21.json (Textauszüge),
Ziel ist die gleiche Kompetenz-UID in den ersten k Treffern.

  cd backend && python3 eval_search_corpus.py
  python3 eval_search_corpus.py --samples 200 --top-k 15 --seed 7

Ergebnis interpretieren:
- Hohe Recall@k: Embedding + Ranking passen zu Kurzqueries aus dem Kompetenztext.
- Niedrige Recall@k: siehe ausgegebene Fehlerbeispiele → STOPWORDS, Synonyme, Gewichte prüfen.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def load_corpus(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Lehrplan21.json muss eine JSON-Liste sein")
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        uid = item.get("uid")
        text = (item.get("text") or "").strip()
        code = (item.get("code") or "").strip()
        if uid and text:
            rows.append({"uid": uid, "text": text, "code": code, "fach": item.get("fach")})
    return rows


def make_query_prefix(text: str, max_words: int) -> str:
    words = text.split()
    return " ".join(words[:max_words]).strip()


def make_query_mid_span(text: str, span_words: int, rng: random.Random) -> str:
    """Schwerere Variante: zusammenhängender Ausschnitt aus der Mitte des Textes."""
    words = text.split()
    if len(words) <= span_words + 2:
        return make_query_prefix(text, span_words)
    start = rng.randint(1, max(1, len(words) - span_words - 1))
    return " ".join(words[start : start + span_words]).strip()


_CODEISH = re.compile(r"^[A-Za-z]{1,4}[0-9].*[A-Za-z0-9.]+$")


def post_search(base_url: str, query: str) -> dict:
    url = base_url.rstrip("/") + "/search"
    body = json.dumps(
        {
            "query_texts": query,
            "querySchlagwort": "",
            "filters": {"fach": [], "zyklus": []},
        }
    ).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def collect_ranked_ids(payload: dict) -> list:
    ids_nested = payload.get("ids") or []
    if ids_nested and isinstance(ids_nested[0], list):
        return list(ids_nested[0])
    if isinstance(ids_nested, list):
        return list(ids_nested)
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Corpus-Recall (Lehrplan21.json) gegen /search")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help="Pfad zu Lehrplan21.json (Standard: backend/Lehrplan21.json)",
    )
    parser.add_argument("--samples", type=int, default=120)
    parser.add_argument("--top-k", type=int, default=12)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--strategy",
        choices=("prefix", "mid_span"),
        default="prefix",
        help="prefix=Anfang des Kompetenztexts; mid_span=Mitte (schwerer)",
    )
    parser.add_argument("--prefix-words", type=int, default=14)
    parser.add_argument("--span-words", type=int, default=12)
    parser.add_argument(
        "--code-samples",
        type=int,
        default=40,
        help="Zusätzlich N Zufalls-Kompetenzen: Suche nur mit Kompetenzcode (Pfad competency_code)",
    )
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    corpus_path = args.corpus or (backend_dir / "Lehrplan21.json")
    if not corpus_path.is_file():
        print(f"Corpus nicht gefunden: {corpus_path}", file=sys.stderr)
        return 2

    corpus = load_corpus(corpus_path)
    if len(corpus) < 10:
        print("Corpus zu klein.", file=sys.stderr)
        return 2

    rng = random.Random(args.seed)
    base = args.base_url.rstrip("/")
    k = max(1, args.top_k)
    n = min(args.samples, len(corpus))
    picked = rng.sample(corpus, n)

    hits = []
    ranks = []
    failures = []

    for rec in picked:
        if args.strategy == "prefix":
            query = make_query_prefix(rec["text"], args.prefix_words)
        else:
            query = make_query_mid_span(rec["text"], args.span_words, rng)

        if len(query) < 8:
            continue

        try:
            data = post_search(base, query)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            failures.append((query[:72], rec["uid"], str(exc)))
            continue

        ranked_ids = collect_ranked_ids(data)
        slice_ids = ranked_ids[:k]

        if rec["uid"] in slice_ids:
            hits.append(1)
            ranks.append(slice_ids.index(rec["uid"]) + 1)
        else:
            hits.append(0)
            failures.append((query[:100], rec["uid"], rec.get("fach"), "not_in_top_k"))

    hit_rate = sum(hits) / len(hits) if hits else 0.0
    median_rank = statistics.median(ranks) if ranks else None

    print(
        f"Strategie: {args.strategy} · Corpus: {corpus_path.name} · Stichprobe: {len(hits)} · top-k={k}"
    )
    print(f"Recall@{k} (UID der Quelle in den ersten {k} Treffern): {sum(hits)}/{len(hits)} = {100 * hit_rate:.1f}%")
    if median_rank is not None:
        print(f"Median Rang (bei Treffer): {median_rank:.1f}")

    # --- optionale Code-Suche ---
    code_hits = 0
    code_n = 0
    if args.code_samples > 0:
        code_candidates = [r for r in corpus if r.get("code") and _CODEISH.match(r["code"])]
        if code_candidates:
            code_pick = rng.sample(code_candidates, min(args.code_samples, len(code_candidates)))
            for rec in code_pick:
                q = rec["code"]
                code_n += 1
                try:
                    data = post_search(base, q)
                except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
                    continue
                ranked_ids = collect_ranked_ids(data)
                if rec["uid"] in ranked_ids[: max(k, 25)]:
                    code_hits += 1
            print(
                f"Zusatz Code-Suche: Recall@{max(k, 25)} ≈ {code_hits}/{code_n} "
                f"({(100 * code_hits / code_n) if code_n else 0:.1f}%) bei reiner Code-Eingabe"
            )

    fails = [f for f in failures if f[-1] == "not_in_top_k"]
    if fails:
        print("\nBeispiele ohne Treffer in Top-k (Query … | erwartete UID | Fach):")
        for query_snip, uid, fach, _tag in fails[:12]:
            print(f"  … {query_snip} …")
            print(f"     uid={uid}  fach={fach}")

    http_fails = [f for f in failures if f[-1] != "not_in_top_k"]
    if http_fails:
        print(f"\nHTTP/API-Fehler: {len(http_fails)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
