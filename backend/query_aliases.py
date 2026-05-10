"""
Versionierte Query-Aliase (JSON + Legacy-Fallback).

Semantik:
- related_tokens: Schlüssel = normalisiertes Wort (ae-Umlaute); Werte = Liste verwandter Ausdrücke
  (werden normalisiert; Mehrwort-Einträge zu Einzel-Tokens >= 4 Zeichen zerlegt).
  Expansion ist konservativ: höchstens MAX_RELATED_PER_TOKEN Erweiterungen pro Query-Token und
  höchstens MAX_EXTRA_SYNONYM_TOKENS zusätzliche Tokens gesamt (über alle Roh-Tokens).
- alias_to_canonical: Wenn die Nutzeranfrage ein Alias als Wort enthält, kann eine Kanon-Variante
  der gesamten Query für Retrieval erzeugt werden; aktivierte Kanon-Ziele boosten Treffer leicht,
  wenn das Dokument diese Kanon-Tokens enthält.

Merge: Datei query_aliases.json (QUERY_ALIASES_JSON) überschreibt pro Schlüssel die Legacy-Listen;
fehlende Datei → nur Legacy.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# --- Legacy (früher QUERY_SYNONYMS in server.py), Fallback wenn JSON fehlt -----------------

LEGACY_RELATED_TOKENS = {
    "bruchrechnen": ["bruch", "brüche", "brueche", "nenner", "zähler", "zaehler", "bruchzahl"],
    "mathe": ["mathematik"],
    "unterrichtsidee": ["unterricht", "lernaufgabe", "sequenz", "projekt", "lernsequenz", "doppelstunde"],
    "gruppenarbeit": ["teamarbeit", "kooperativ", "partnerarbeit"],
    "bewerten": ["beurteilen", "einschaetzen", "einschätzen", "reflektieren"],
    "analysieren": ["untersuchen", "auswerten", "strukturieren"],
    "argumentieren": ["begruenden", "begründen", "diskutieren", "eroertern", "erörtern"],
}

# Minimal Legacy-Kanon (wenn JSON fehlt), konsistent mit früherem impliziten „mathe“-Bezug
LEGACY_ALIAS_TO_CANONICAL = {
    "mathe": "mathematik",
}

MAX_RELATED_PER_TOKEN = 3
MAX_EXTRA_SYNONYM_TOKENS = 12

CANONICAL_MATCH_BONUS_CAP = 0.05

_QUERY_ALIASES_STORE = None


def normalize_text(value: str) -> str:
    if not value:
        return ""
    value = value.lower()
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return value


def _parse_related_map(raw: dict | None) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        nk = normalize_text(str(key))
        if not nk or not isinstance(val, list):
            continue
        cleaned = []
        for item in val:
            if isinstance(item, str) and item.strip():
                cleaned.append(item.strip())
        if cleaned:
            out[nk] = cleaned
    return out


def _parse_alias_to_canonical(raw: dict | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        nk = normalize_text(str(key))
        if not nk or not isinstance(val, str) or not val.strip():
            continue
        canon = normalize_text(val.strip())
        if canon:
            out[nk] = canon
    return out


def _deep_merge_related(base: dict[str, list[str]], override: dict[str, list[str]]) -> dict[str, list[str]]:
    merged = {k: list(v) for k, v in base.items()}
    for k, v in override.items():
        merged[k] = list(v)
    return merged


def load_query_aliases_from_path(path: Path) -> dict:
    """Liest JSON; bei Fehler leeres Default-Dict."""
    default = {
        "version": 0,
        "related_tokens": {},
        "alias_to_canonical": {},
    }
    if not path.is_file():
        return default
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return default
    if not isinstance(raw, dict):
        return default
    version = raw.get("version", 0)
    try:
        version = int(version)
    except (TypeError, ValueError):
        version = 0
    return {
        "version": version,
        "related_tokens": _parse_related_map(raw.get("related_tokens")),
        "alias_to_canonical": _parse_alias_to_canonical(raw.get("alias_to_canonical")),
    }


def build_merged_store(json_path: Path | None = None) -> dict:
    """
    Legacy-Listen mergen: JSON-Keys ersetzen gleichnamige Legacy-Einträge vollständig.
    """
    path = json_path or Path(
        os.getenv("QUERY_ALIASES_JSON", str(Path(__file__).resolve().parent / "query_aliases.json"))
    )
    loaded = load_query_aliases_from_path(path)
    related = _deep_merge_related(LEGACY_RELATED_TOKENS, loaded["related_tokens"])
    canon = dict(LEGACY_ALIAS_TO_CANONICAL)
    canon.update(loaded["alias_to_canonical"])

    file_version = loaded["version"]
    effective_version = file_version if file_version else 1

    return {
        "version": effective_version,
        "related_tokens": related,
        "alias_to_canonical": canon,
        "source_path": str(path) if path.is_file() else None,
    }


def get_query_aliases_store() -> dict:
    """Globally cached store für Request-Pfad."""
    global _QUERY_ALIASES_STORE
    if _QUERY_ALIASES_STORE is None:
        _QUERY_ALIASES_STORE = build_merged_store()
    return _QUERY_ALIASES_STORE


def reset_query_aliases_cache() -> None:
    """Nur für Tests: Cache der gemergten Aliase zurücksetzen."""
    global _QUERY_ALIASES_STORE
    _QUERY_ALIASES_STORE = None


def expand_query_tokens(raw_tokens: list[str], related_tokens: dict[str, list[str]], stopwords: set[str]) -> list[str]:
    """
    Roh-Tokens (bereits normalisiert) um verwandte Tokens erweitern; Caps gegen Überschwemmung.
    """
    expanded: set[str] = set(raw_tokens)
    extra_added = 0

    for token in raw_tokens:
        if extra_added >= MAX_EXTRA_SYNONYM_TOKENS:
            break
        rel_list = related_tokens.get(token) or []
        added_for_token = 0
        for item in rel_list:
            if extra_added >= MAX_EXTRA_SYNONYM_TOKENS or added_for_token >= MAX_RELATED_PER_TOKEN:
                break
            for word in re.findall(r"\w+", normalize_text(item)):
                if extra_added >= MAX_EXTRA_SYNONYM_TOKENS or added_for_token >= MAX_RELATED_PER_TOKEN:
                    break
                if len(word) < 4 or word in stopwords or word in expanded:
                    continue
                expanded.add(word)
                extra_added += 1
                added_for_token += 1

    return sorted(
        t for t in expanded if len(t) >= 4 and t not in stopwords
    )


def active_canonical_targets(query_text: str, alias_to_canonical: dict[str, str]) -> set[str]:
    """Kanon-Tokens, für die die Anfrage ein Alias-Wort enthält (normalisiert)."""
    if not query_text or not alias_to_canonical:
        return set()
    normalized = normalize_text(query_text)
    targets: set[str] = set()
    for t in re.findall(r"\w+", normalized):
        if t in alias_to_canonical:
            c = alias_to_canonical[t]
            if c:
                targets.add(c)
    return targets


def build_canonical_query_variant(query_text: str, alias_to_canonical: dict[str, str]) -> str | None:
    """
    Ersetzt ganze Wörter, die als Alias gemappt sind, durch Kanonisierung (case-insensitive).
    Gibt None zurück, wenn keine Ersetzung oder Text unverändert (normalisiert).
    """
    if not query_text or not alias_to_canonical:
        return None
    before_norm = normalize_text(query_text)
    result = query_text
    for alias in sorted(alias_to_canonical.keys(), key=len, reverse=True):
        canon = alias_to_canonical[alias]
        pattern = re.compile(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", re.IGNORECASE)
        result = pattern.sub(canon, result)
    after_norm = normalize_text(result)
    if not after_norm or after_norm == before_norm:
        return None
    return re.sub(r"\s+", " ", result).strip()


def canonical_match_bonus(document_text: str, canonical_targets: set[str]) -> float:
    """Kleiner Bonus (0…CANONICAL_MATCH_BONUS_CAP), wenn Dokument Kanon-Tokens aus der Query enthält."""
    if not canonical_targets or not document_text:
        return 0.0
    doc_tokens = set(re.findall(r"\w+", normalize_text(document_text)))
    overlap = doc_tokens & canonical_targets
    if not overlap:
        return 0.0
    return min(0.02 + 0.015 * (len(overlap) - 1), CANONICAL_MATCH_BONUS_CAP)
