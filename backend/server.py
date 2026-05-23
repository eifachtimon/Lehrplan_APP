# app.py
#------------------------------------------------------------Imports------------------------------------------------------------
from flask import Flask, jsonify, request, send_from_directory
from chroma_lehrplan import get_chroma_client, load_model_and_tokenizer
from pathlib import Path
from flask_cors import CORS
import re
import os
import json
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from query_aliases import (
    active_canonical_targets,
    build_canonical_query_variant,
    canonical_match_bonus,
    expand_query_tokens,
    get_query_aliases_store,
)
from calendar_ics import fetch_subscription_events
from calendar_feed import build_ics, load_feed_ics, new_export_token, publish_feed

#------------------------------------------------------------ChromaDB------------------------------------------------------------
# ChromaDB

#TODO: Create Embeddings Collection when App ist build!
#collection = init_collection()

client = get_chroma_client()
client.heartbeat()

# Cached collection für schnellere Requests
_CACHED_COLLECTION = None
_CHROMA_EXECUTOR = ThreadPoolExecutor(max_workers=6)

FACH_ALIASES = {
    "Mathematik": ["mathematik", "mathe", "bruch", "brueche", "brüche", "bruchrechnen", "geometrie", "loesungsweg", "loesungswege", "strategie", "strategien", "modellieren", "begruenden", "begruendet"],
    "Deutsch": ["deutsch", "grammatik", "lesen", "schreiben"],
    "Französisch": ["französisch", "franzoesisch", "franzoesisch", "franz", "aussprache", "phonetik"],
    "Englisch": ["englisch", "english"],
    "Bewegung und Sport": ["sport", "bewegung", "schwimmen", "schwimmunterricht", "brustgleichschlag", "turnen"],
    "Räume, Zeiten, Gesellschaften (mit Geografie, Geschichte)": ["rzg", "geografie", "geschichte", "raum", "zeiten", "quellen", "positionen", "abwaegen", "abwaegen", "einordnen", "urteilen"],
    "Wirtschaft, Arbeit, Haushalt (mit Hauswirtschaft)": ["wah", "wirtschaft", "haushalt", "konsum", "nachhaltig", "nachhaltigem", "nachhaltigkeit", "umwelt"],
    "Natur und Technik (mit Physik, Chemie, Biologie)": ["nt", "natur und technik", "physik", "chemie", "biologie"],
    "Musik": ["musik", "rhythmus", "klang", "instrument", "koerperausdruck", "tanz", "tanzunterricht"],
}

STOPWORDS = {
    "ich", "plane", "eine", "einen", "einer", "zu", "mit", "und", "oder", "fuer", "für",
    "das", "der", "die", "den", "dem", "des", "im", "in", "an", "auf", "von", "am",
    "stunde", "unterricht", "gruppenarbeit",
    "lektion", "lektionen", "doppelstunde", "klassen", "klasse",
}

INTENT_HINTS = {
    "kommunikation": ["argumentieren", "diskutieren", "praesentieren", "präsentieren", "erklaeren", "erklären"],
    "methodik": ["gruppenarbeit", "teamarbeit", "stationenlernen", "projekt", "rollenspiel"],
    "analyse": ["analysieren", "bewerten", "beurteilen", "reflektieren", "quellen"],
}

SEMANTIC_CONCEPTS = {
    "beurteilen": ["bewerten", "reflektieren", "kritisch einordnen", "urteilen"],
    "analysieren": ["untersuchen", "auswerten", "strukturieren", "zusammenhaenge erkennen"],
    "argumentieren": ["begruenden", "standpunkt vertreten", "diskutieren", "schlussfolgern"],
    "kooperieren": ["gruppenarbeit", "teamarbeit", "partnerarbeit", "gemeinsam loesen"],
    "problemloesen": ["strategie entwickeln", "loesungsweg planen", "modellieren", "anwenden"],
}

def init_collection():
    global _CACHED_COLLECTION
    if _CACHED_COLLECTION is not None:
        return _CACHED_COLLECTION
    try:
        collection = client.get_collection(name="Lehrplan_Basel_Stadt3")
        _CACHED_COLLECTION = collection
        return collection
    except Exception as e:
        print("Error:", e)
        collection = load_model_and_tokenizer()
        _CACHED_COLLECTION = collection
        return collection


def normalize_text(value):
    if not value:
        return ""
    value = value.lower()
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return value


def tokenize_query(query_text):
    """
    Tokenliste für Keyword-Matching / Score-Normalisierung.
    Nutzt versionierte Aliase (query_aliases.json + Legacy-Merge in query_aliases.py);
    verwandte Tokens nur konservativ (Caps), ohne den Roh-Query-Text zu verändern.
    """
    store = get_query_aliases_store()
    normalized = normalize_text(query_text)
    raw_tokens = re.findall(r"\w+", normalized)
    return expand_query_tokens(raw_tokens, store["related_tokens"], STOPWORDS)


def detect_fach_signals(query_text):
    normalized_query = normalize_text(query_text)
    signals = set()
    for fach, aliases in FACH_ALIASES.items():
        if any(alias in normalized_query for alias in aliases):
            signals.add(fach)
    return signals


def detect_zyklus_from_query(query_text):
    normalized_query = normalize_text(query_text)
    if "zyklus 1" in normalized_query or re.search(r"\b[1-2]\.\s*klasse\b", normalized_query):
        return {"1"}
    if "zyklus 2" in normalized_query or re.search(r"\b[3-6]\.\s*klasse\b", normalized_query):
        return {"2"}
    if "zyklus 3" in normalized_query or re.search(r"\b[7-9]\.\s*klasse\b", normalized_query):
        return {"3"}
    return set()


def split_query_into_intents(query_text):
    normalized = re.sub(r"\s+", " ", query_text or "").strip()
    if not normalized:
        return []
    parts = re.split(r"\b(?:und|sowie|mit|plus|,|;)\b", normalized, flags=re.IGNORECASE)
    cleaned = []
    for part in parts:
        item = part.strip(" ,;")
        if len(item) >= 4:
            cleaned.append(item)
    return cleaned[:8]


def build_query_variants(query_text, query_schlagwort, alias_to_canonical=None):
    """Varianten für Retrieval; optional eine Kanonisierungs-Zeile wenn Platz unter dem Cap von 4."""
    alias_to_canonical = alias_to_canonical or {}
    base_query = f"{query_text} {query_schlagwort}".strip() if query_schlagwort else query_text
    intent_queries = split_query_into_intents(base_query)
    variants = [base_query] + intent_queries
    deduplicated = []
    seen = set()
    for variant in variants:
        key = normalize_text(variant)
        if key and key not in seen:
            deduplicated.append(variant)
            seen.add(key)

    if len(deduplicated) < 4 and alias_to_canonical:
        canon = build_canonical_query_variant(base_query, alias_to_canonical)
        if canon:
            ck = normalize_text(canon)
            if ck and ck not in seen:
                deduplicated.append(canon)
                seen.add(ck)

    return deduplicated[:4]


def build_semantic_variants(query_text, fach_signals, intent_signals):
    base = re.sub(r"\s+", " ", query_text or "").strip()
    if not base:
        return []

    prompts = [f"Kompetenzbeschreibung: {base}"]
    for fach in sorted(fach_signals):
        prompts.append(f"Kompetenzen im Fach {fach}: {base}")

    for intent in sorted(intent_signals):
        aliases = INTENT_HINTS.get(intent, [])
        if aliases:
            prompts.append(f"{base}; Fokus: {' '.join(aliases[:3])}")

    normalized_query = normalize_text(query_text)
    for concept, aliases in SEMANTIC_CONCEPTS.items():
        if concept in normalized_query or any(alias in normalized_query for alias in aliases):
            prompts.append(f"{base}; Kompetenzverb: {concept}; Synonyme: {' '.join(aliases[:3])}")

    deduplicated = []
    seen = set()
    for prompt in prompts:
        key = normalize_text(prompt)
        if key and key not in seen:
            deduplicated.append(prompt)
            seen.add(key)
    return deduplicated[:3]


def detect_intent_signals(query_text):
    normalized_query = normalize_text(query_text)
    hits = set()
    for intent, aliases in INTENT_HINTS.items():
        if any(alias in normalized_query for alias in aliases):
            hits.add(intent)
    return hits


def classify_query_profile(query_text, query_tokens, intent_signals):
    normalized_query = normalize_text(query_text)
    token_count = len(query_tokens)
    has_grade_hint = bool(re.search(r"\b(?:[1-9]\.\s*klasse|zyklus\s*[1-3])\b", normalized_query))
    has_planning_hint = any(
        hint in normalized_query
        for hint in ["planung", "lektion", "lernsequenz", "projekt", "unterrichtsidee", "lernarrangement"]
    )
    is_complex = token_count >= 8 or len(intent_signals) >= 2 or (has_planning_hint and has_grade_hint)

    if is_complex:
        return "planning_complex"
    if token_count <= 3 and not intent_signals:
        return "lookup_short"
    return "standard"


def get_score_weights(query_profile):
    if query_profile == "planning_complex":
        return {
            "vector": 0.27,
            "keyword": 0.19,
            "metadata": 0.24,
            "variant": 0.10,
            "rrf": 0.20,
            "semantic_weight": 0.95,
        }
    if query_profile == "lookup_short":
        return {
            "vector": 0.30,
            "keyword": 0.30,
            "metadata": 0.24,
            "variant": 0.06,
            "rrf": 0.10,
            "semantic_weight": 0.45,
        }
    return {
        "vector": 0.31,
        "keyword": 0.23,
        "metadata": 0.18,
        "variant": 0.08,
        "rrf": 0.20,
        "semantic_weight": 0.75,
    }


def resolve_n_results(requested_n_results, query_profile):
    if isinstance(requested_n_results, int) and requested_n_results > 0:
        return min(requested_n_results, 25)

    if query_profile == "planning_complex":
        return 14
    if query_profile == "lookup_short":
        return 8
    return 10


def build_where_clause(filters):
    where_conditions = []

    fach_filters = filters.get("fach", [])
    if fach_filters:
        if len(fach_filters) == 1:
            where_conditions.append({"fach": {"$eq": fach_filters[0]}})
        else:
            where_conditions.append({"$or": [{"fach": {"$eq": fach}} for fach in fach_filters]})

    zyklus_filters = filters.get("zyklus", [])
    if zyklus_filters:
        zyklus_mapping = {
            "1": {"1", "12"},
            "2": {"2", "12", "23"},
            "3": {"3", "23"},
        }
        accepted_zyklus = set()
        for zyklus in zyklus_filters:
            key = str(zyklus).strip()
            accepted_zyklus.update(zyklus_mapping.get(key, {key}))
        where_conditions.append({"$or": [{"zyklus": {"$eq": item}} for item in sorted(accepted_zyklus)]})

    if len(where_conditions) == 1:
        return where_conditions[0]
    if len(where_conditions) > 1:
        return {"$and": where_conditions}
    return None


# --- Kompetenzcode-Suche (Code steht nur in Metadaten, nicht im Embedding-Text) --------------

COMPETENCY_CODE_FRAGMENT_RE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z0-9]+)+")

_CODE_SEGMENT_CHUNK_RE = re.compile(r"(\d+)|(\D+)")


def _competency_code_segment_sort_key(segment):
    """Sortierschlüssel für ein Code-Segment (z. B. 1a < 1b < 2a < 10a)."""
    if segment is None:
        return ()
    seg = str(segment).strip().lower()
    if not seg:
        return ()
    parts = []
    for m in _CODE_SEGMENT_CHUNK_RE.finditer(seg):
        digits, nondigits = m.group(1), m.group(2)
        if digits is not None:
            parts.append((0, int(digits)))
        elif nondigits:
            parts.append((1, nondigits.lower()))
    return tuple(parts) if parts else ((1, seg),)


def competency_code_sort_tuple(code):
    """Tupel-Vergleich über alle mit '.' getrennten Segmente (offizielle Code-Reihenfolge)."""
    if not code:
        return ()
    segments = [s for s in str(code).strip().lower().split(".") if s != ""]
    return tuple(_competency_code_segment_sort_key(s) for s in segments)


def metadata_competency_code(meta):
    if not meta:
        return ""
    return str(meta.get("code") or meta.get("competency_code") or "").strip()


def is_pure_competency_code_query(query_text, query_schlagwort):
    """True, wenn die Anfrage nur aus einem Kompetenzcode-Fragment besteht (ohne Freitext)."""
    combined = f"{query_text} {query_schlagwort}".strip()
    if not combined:
        return False
    compact = re.sub(r"\s+", "", combined)
    return bool(COMPETENCY_CODE_FRAGMENT_RE.fullmatch(compact))


_competency_code_index_cache = None
_COMPETENCY_CODE_INDEX_VERSION = 2

LP21_ROW_PREFIX = "lp21:"


def parse_lp21_row_index(chain_id):
    """Chroma-/Such-ID: 'lp21:88175' → Zeilenindex in Lehrplan21.json (eindeutig pro Eintrag)."""
    if chain_id is None:
        return None
    text = str(chain_id).strip()
    if not text.startswith(LP21_ROW_PREFIX):
        return None
    tail = text[len(LP21_ROW_PREFIX) :].strip()
    if not tail.isdigit():
        return None
    return int(tail)


def _get_competency_code_index():
    global _competency_code_index_cache
    if _competency_code_index_cache is not None and _competency_code_index_cache.get(
        "v"
    ) == _COMPETENCY_CODE_INDEX_VERSION:
        return _competency_code_index_cache

    code_to_uids = {}
    all_codes = []
    path = Path(os.getenv("LEHRPLAN_JSON_PATH", str(Path(__file__).resolve().parent / "Lehrplan21.json")))
    if path.is_file():
        try:
            with open(path, "r", encoding="utf-8") as handle:
                rows = json.load(handle)
            if isinstance(rows, list):
                for i, row in enumerate(rows):
                    code = row.get("code")
                    if not code:
                        continue
                    key = str(code).strip()
                    if not key:
                        continue
                    all_codes.append(key)
                    lower = key.lower()
                    stable_id = f"{LP21_ROW_PREFIX}{i}"
                    code_to_uids.setdefault(lower, []).append(stable_id)
        except (OSError, json.JSONDecodeError):
            pass

    _competency_code_index_cache = {
        "code_to_uids": code_to_uids,
        "all_codes": all_codes,
        "v": _COMPETENCY_CODE_INDEX_VERSION,
    }
    return _competency_code_index_cache


def extract_competency_code_candidates(query_text):
    text = (query_text or "").strip()
    if not text:
        return []
    found = {m.group(0) for m in COMPETENCY_CODE_FRAGMENT_RE.finditer(text)}
    compact = re.sub(r"\s+", "", text)
    if COMPETENCY_CODE_FRAGMENT_RE.fullmatch(compact):
        found.add(compact)
    return list(found)


def metadata_matches_request_filters(metadata, filters):
    if not filters:
        return True
    meta = metadata or {}

    fach_filters = filters.get("fach") or []
    if fach_filters:
        if meta.get("fach") not in fach_filters:
            return False

    zyklus_filters = filters.get("zyklus") or []
    if zyklus_filters:
        zyklus_mapping = {
            "1": {"1", "12"},
            "2": {"2", "12", "23"},
            "3": {"3", "23"},
        }
        accepted = set()
        for zyklus in zyklus_filters:
            key = str(zyklus).strip()
            accepted.update(zyklus_mapping.get(key, {key}))
        if str(meta.get("zyklus", "")).strip() not in accepted:
            return False

    return True


def resolve_exact_competency_codes_in_query(query_text, query_schlagwort):
    """
    Liefert UIDs, wenn mindestens ein erkanntes Fragment exakt einem gespeicherten
    Kompetenzcode entspricht (kein Präfix).
    """
    combined = f"{query_text} {query_schlagwort}".strip()
    candidates = extract_competency_code_candidates(combined)
    if not candidates:
        return {"uids": [], "codes_lower": []}

    index = _get_competency_code_index()
    code_to_uids = index["code_to_uids"]
    uids = []
    codes_lower = []
    seen_stable = set()
    for cand in candidates:
        ck = cand.strip().lower()
        if ck not in code_to_uids:
            continue
        codes_lower.append(ck)
        for stable_id in code_to_uids[ck]:
            if stable_id not in seen_stable:
                seen_stable.add(stable_id)
                uids.append(stable_id)
    return {"uids": uids, "codes_lower": codes_lower}


def resolve_uids_from_competency_code_candidates(candidates):
    index = _get_competency_code_index()
    code_to_uids = index["code_to_uids"]
    all_codes = index["all_codes"]
    if not code_to_uids:
        return []

    ordered_uids = []
    seen = set()

    def append_uids_for_code(lower_key):
        for stable_id in code_to_uids.get(lower_key, []):
            if stable_id not in seen:
                seen.add(stable_id)
                ordered_uids.append(stable_id)

    prefix_codes_seen = set()

    for cand in candidates:
        raw = cand.strip()
        if not raw:
            continue
        ck = raw.lower()
        if ck in code_to_uids:
            append_uids_for_code(ck)
            continue

        dot_count = raw.count(".")
        if len(raw) < 6 or (dot_count < 2 and len(raw) < 10):
            continue

        matching_codes = [fc for fc in all_codes if fc.lower().startswith(ck)]
        matching_codes.sort(key=competency_code_sort_tuple)
        if len(matching_codes) > 48:
            matching_codes = matching_codes[:48]
        for fc in matching_codes:
            if fc not in prefix_codes_seen:
                prefix_codes_seen.add(fc)
                append_uids_for_code(fc.lower())

    max_uids = 72
    return ordered_uids[:max_uids]


def competency_code_lookup_retrieve(
    collection, query_text, query_schlagwort, filters, candidate_map, resolved_uids=None
):
    combined = f"{query_text} {query_schlagwort}".strip()
    if resolved_uids is not None:
        uids = list(resolved_uids)
    else:
        candidates = extract_competency_code_candidates(combined)
        if not candidates:
            return
        uids = resolve_uids_from_competency_code_candidates(candidates)
    if not uids:
        return

    batch = collection.get(ids=uids, include=["documents", "metadatas"])
    ids_out = batch.get("ids") or []
    documents = batch.get("documents") or []
    metadatas = batch.get("metadatas") or []
    variant_label = combined[:160]

    for idx, doc_id in enumerate(ids_out):
        meta = metadatas[idx] if idx < len(metadatas) else {}
        if not metadata_matches_request_filters(meta, filters):
            continue
        doc = documents[idx] if idx < len(documents) else ""
        upsert_candidate(
            candidate_map,
            [doc_id],
            [doc],
            [meta],
            [0.015],
            "competency_code",
            variant=variant_label,
            source_weight=2.2,
        )


def upsert_candidate(candidate_map, ids, documents, metadatas, distances, source, token=None, variant=None, source_weight=1.0):
    for idx, doc_id in enumerate(ids):
        entry = candidate_map.setdefault(
            doc_id,
            {
                "id": doc_id,
                "document": documents[idx],
                "metadata": metadatas[idx] or {},
                "best_distance": None,
                "keyword_hits": set(),
                "sources": set(),
                "query_variants": set(),
                "rrf_score": 0.0,
            },
        )

        if distances and idx < len(distances) and distances[idx] is not None:
            distance = distances[idx]
            if entry["best_distance"] is None or distance < entry["best_distance"]:
                entry["best_distance"] = distance

        if source == "keyword" and token:
            entry["keyword_hits"].add(token)

        if variant:
            entry["query_variants"].add(variant)

        rank = idx + 1
        entry["rrf_score"] += source_weight / (60.0 + rank)
        entry["sources"].add(source)


def vector_retrieve(collection, query_text, where_clause, limit):
    query_kwargs = {"query_texts": [query_text], "n_results": limit}
    if where_clause:
        query_kwargs["where"] = where_clause
    return collection.query(**query_kwargs)


def keyword_retrieve_and_upsert(collection, query_text, query_tokens, where_clause, per_token_limit, candidate_map, variant):
    unique_tokens = query_tokens[:4]
    full_query_kwargs = {
        "query_texts": [query_text],
        "where_document": {"$contains": query_text},
        "n_results": per_token_limit,
    }
    if where_clause:
        full_query_kwargs["where"] = where_clause
    full_result = collection.query(**full_query_kwargs)
    upsert_candidate(
        candidate_map,
        full_result.get("ids", [[]])[0],
        full_result.get("documents", [[]])[0],
        full_result.get("metadatas", [[]])[0],
        full_result.get("distances", [[]])[0],
        "keyword",
        token="__full_query__",
        variant=variant,
        source_weight=1.15,
    )

    for token in unique_tokens:
        query_kwargs = {
            "query_texts": [query_text],
            "where_document": {"$contains": token},
            "n_results": per_token_limit,
        }
        if where_clause:
            query_kwargs["where"] = where_clause
        result = collection.query(**query_kwargs)
        upsert_candidate(
            candidate_map,
            result.get("ids", [[]])[0],
            result.get("documents", [[]])[0],
            result.get("metadatas", [[]])[0],
            result.get("distances", [[]])[0],
            "keyword",
            token=token,
            variant=variant,
            source_weight=1.0,
        )


def parallel_retrieve_all(collection, query_variants, semantic_variants, where_clause, n_results, weights):
    """
    Führt alle Vector- und Keyword-Queries parallel aus.
    Gibt candidate_map zurück.
    """
    vector_limit = max(40, n_results * 4)
    keyword_limit = max(10, n_results * 2)
    candidate_map = {}

    def do_vector_query(variant, source, source_weight):
        limit = vector_limit if source == "vector" else max(25, n_results * 3)
        return ("vector", variant, source, source_weight, vector_retrieve(collection, variant, where_clause, limit=limit))

    def do_keyword_query(variant, token, is_full_query):
        query_kwargs = {"query_texts": [variant], "n_results": keyword_limit}
        if is_full_query:
            query_kwargs["where_document"] = {"$contains": variant}
        else:
            query_kwargs["where_document"] = {"$contains": token}
        if where_clause:
            query_kwargs["where"] = where_clause
        return ("keyword", variant, token, is_full_query, collection.query(**query_kwargs))

    futures = []
    
    for variant in query_variants:
        futures.append(_CHROMA_EXECUTOR.submit(do_vector_query, variant, "vector", 1.0))
        futures.append(_CHROMA_EXECUTOR.submit(do_keyword_query, variant, "__full_query__", True))
        vtokens = tokenize_query(variant)[:4]
        for token in vtokens:
            futures.append(_CHROMA_EXECUTOR.submit(do_keyword_query, variant, token, False))

    for semantic_variant in semantic_variants:
        futures.append(_CHROMA_EXECUTOR.submit(do_vector_query, semantic_variant, "semantic_vector", weights["semantic_weight"]))

    for future in as_completed(futures):
        try:
            result = future.result()
            if result[0] == "vector":
                _, variant, source, source_weight, data = result
                upsert_candidate(
                    candidate_map,
                    data.get("ids", [[]])[0],
                    data.get("documents", [[]])[0],
                    data.get("metadatas", [[]])[0],
                    data.get("distances", [[]])[0],
                    source,
                    variant=variant,
                    source_weight=source_weight,
                )
            else:
                _, variant, token, is_full_query, data = result
                upsert_candidate(
                    candidate_map,
                    data.get("ids", [[]])[0],
                    data.get("documents", [[]])[0],
                    data.get("metadatas", [[]])[0],
                    data.get("distances", [[]])[0],
                    "keyword",
                    token=token,
                    variant=variant,
                    source_weight=1.15 if is_full_query else 1.0,
                )
        except Exception as e:
            print(f"[parallel_retrieve] Error: {e}")

    return candidate_map


# --- Ranking: Themenbereich, Phrase, 2. Stufe, MMR ---------------------------------

SECOND_STAGE_POOL_CAP = 100
SECOND_STAGE_LEX_WEIGHT = 0.12
MMR_LAMBDA = 0.68
MMR_POOL_MIN = 36


def themenbereich_query_overlap(query_text, themenbereich):
    """Anteil der Themenbereich-Tokens, die in der Query vorkommen (0–1)."""
    if not themenbereich:
        return 0.0
    qt = {
        t
        for t in re.findall(r"\w+", normalize_text(query_text))
        if len(t) >= 3 and t not in STOPWORDS
    }
    tb = {t for t in re.findall(r"\w+", normalize_text(themenbereich)) if len(t) >= 2}
    if not tb:
        return 0.0
    inter = len(qt & tb)
    return inter / len(tb)


def phrase_presence_bonus(combined_query, document_text):
    """Boost wenn die normalisierte Query (oder ein längerer Präfix) im Kompetenztext vorkommt."""
    nq = normalize_text(combined_query).strip()
    nd = normalize_text(document_text)
    if len(nq) < 10:
        return 0.0
    if nq in nd:
        return 1.0
    chunk = nq[:72].rstrip()
    if len(chunk) >= 10 and chunk in nd:
        return 0.88
    return 0.0


def lexical_overlap_ratio(query_text, document_text):
    """Anteil der Query-Stichwörter (>=3), die im Dokument vorkommen — zweite Ranking-Stufe."""
    q_tokens = {
        t
        for t in re.findall(r"\w+", normalize_text(query_text))
        if len(t) >= 3 and t not in STOPWORDS
    }
    if not q_tokens:
        return 0.0
    d_tokens = set(re.findall(r"\w+", normalize_text(document_text)))
    return len(q_tokens & d_tokens) / len(q_tokens)


def document_token_set_for_mmr(document_text):
    return {t for t in re.findall(r"\w+", normalize_text(document_text)) if len(t) >= 3}


def jaccard_tokens(set_a, set_b):
    if not set_a or not set_b:
        return 0.0
    inter = len(set_a & set_b)
    union = len(set_a | set_b)
    return inter / union if union else 0.0


def apply_second_stage_rerank(scored_items, combined_query, pool_cap=SECOND_STAGE_POOL_CAP):
    """Erhöht die Gewichtung lexikalischer Übereinstimmung für die obersten Treffer und sortiert neu."""
    if not scored_items or not combined_query.strip():
        return scored_items
    pool_cap = min(pool_cap, len(scored_items))
    for i in range(pool_cap):
        item = scored_items[i]
        lex = lexical_overlap_ratio(combined_query, item["document"])
        item["final_score"] = item["final_score"] + SECOND_STAGE_LEX_WEIGHT * lex
    scored_items.sort(key=lambda entry: entry["final_score"], reverse=True)
    return scored_items


def mmr_diversify(ranked_items, n_results, lambda_param=MMR_LAMBDA):
    """Maximal Marginal Relevance: Relevanz vs. Redundanz (Jaccard auf Dokument-Tokens)."""
    if n_results <= 0:
        return []
    if not ranked_items:
        return []

    pool_size = min(
        len(ranked_items),
        max(MMR_POOL_MIN, n_results * 5),
    )
    pool = ranked_items[:pool_size]
    doc_tokens = [document_token_set_for_mmr(item["document"]) for item in pool]

    scores = [item["final_score"] for item in pool]
    max_s, min_s = max(scores), min(scores)
    span = (max_s - min_s) if max_s > min_s else 1.0

    def relevance_at(idx):
        return (pool[idx]["final_score"] - min_s) / span

    selected_idx = []
    remaining = set(range(len(pool)))

    while len(selected_idx) < n_results and remaining:
        best_i = None
        best_mmr = -1e9
        for i in remaining:
            rel = relevance_at(i)
            if selected_idx:
                max_sim = max(jaccard_tokens(doc_tokens[i], doc_tokens[j]) for j in selected_idx)
            else:
                max_sim = 0.0
            mmr_score = lambda_param * rel - (1.0 - lambda_param) * max_sim
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_i = i
        selected_idx.append(best_i)
        remaining.discard(best_i)

    return [pool[i] for i in selected_idx]


def score_candidates(
    candidate_map,
    query_tokens,
    fach_signals,
    intent_signals,
    weights,
    combined_query="",
    canonical_boost_terms=None,
):
    scored_items = []
    token_count = max(len(query_tokens), 1)
    intent_count = max(len(intent_signals), 1)
    boost_targets = canonical_boost_terms or set()

    for item in candidate_map.values():
        distance = item["best_distance"] if item["best_distance"] is not None else 2.5
        vector_score = 1.0 / (1.0 + max(distance, 0.0))
        keyword_score = min(len(item["keyword_hits"]) / token_count, 1.0)
        variant_score = min(len(item["query_variants"]) / 4.0, 1.0)
        rrf_score = min(item.get("rrf_score", 0.0) * 3.5, 1.0)

        metadata_score = 0.0
        fach = item["metadata"].get("fach")
        if fach_signals and fach in fach_signals:
            metadata_score += 1.2
        elif fach_signals:
            metadata_score -= 0.4

        if "competency_code" in item["sources"]:
            metadata_score += 3.0

        query_text_blob = normalize_text(item["document"])
        if intent_signals:
            matched_intents = sum(
                1 for intent, aliases in INTENT_HINTS.items()
                if intent in intent_signals and any(alias in query_text_blob for alias in aliases)
            )
            metadata_score += min(matched_intents / intent_count, 1.0) * 0.7

        if combined_query.strip():
            tb = item["metadata"].get("themenbereich") or ""
            tb_ov = themenbereich_query_overlap(combined_query, tb)
            metadata_score += min(tb_ov * 1.15, 1.15)

            ph = phrase_presence_bonus(combined_query, item["document"])
            keyword_score = min(keyword_score + 0.32 * ph, 1.0)

        if "__full_query__" in item["keyword_hits"]:
            keyword_score = min(keyword_score + 0.25, 1.0)

        final_score = (
            (weights["vector"] * vector_score)
            + (weights["keyword"] * keyword_score)
            + (weights["metadata"] * metadata_score)
            + (weights["variant"] * variant_score)
            + (weights["rrf"] * rrf_score)
        )
        if boost_targets:
            final_score += canonical_match_bonus(item["document"], boost_targets)
        item["final_score"] = final_score
        scored_items.append(item)

    scored_items.sort(key=lambda entry: entry["final_score"], reverse=True)
    return scored_items


# --- Kompetenz-Aufbaukette (muss vor format_response stehen) -----------------

LEHRPLAN_JSON_PATH = Path(
    os.getenv("LEHRPLAN_JSON_PATH", str(Path(__file__).resolve().parent / "Lehrplan21.json"))
)
CHAIN_KEY_FIELDS = ("fb_id", "f_id", "kb_id", "ha_id", "k_id", "aufbau")

_CHAIN_GROUP_ROWS_CACHE_EPOCH = 2
_chain_group_rows_cache_epoch = 0
_chain_group_rows_cache = {}
_lehrplan_json_rows = None
# Cache: (fach, kb_code) -> gemeinsamer NFC-Präfix der Themenbereiche unter diesem KB, oder None
_TB_KB_LCP_CACHE = {}


def _normalize_uid(uid):
    if uid is None:
        return None
    text = str(uid).strip()
    return text if text else None


def _uid_base_for_chain_match(uid):
    """API-/URL-Suffixe (z. B. .u0) von der logischen Lehrplan-uid trennen."""
    if uid is None:
        return ""
    text = str(uid).strip()
    if not text:
        return ""
    return text.split(".")[0]


def _uids_equivalent_for_chain(a, b):
    """Zwei uid-Strings bezeichnen dieselbe Lehrplan-Zeile (inkl. Basis bei Suffix)."""
    if a is None or b is None:
        return False
    sa = str(a).strip()
    sb = str(b).strip()
    if not sa or not sb:
        return False
    if sa == sb:
        return True
    ba = _uid_base_for_chain_match(sa)
    bb = _uid_base_for_chain_match(sb)
    return bool(ba and bb and ba == bb)


def _format_chain_item(item):
    if not item:
        return None
    out = {
        "uid": item.get("uid"),
        "code": item.get("code"),
        "text": item.get("text"),
        "zyklus": item.get("zyklus"),
        "fach": item.get("fach"),
        "themenbereich": item.get("themenbereich"),
        "url": item.get("url"),
        "folge_in_aufbaute": item.get("folge_in_aufbaute"),
    }
    dk = item.get("doc_key")
    if dk:
        out["doc_key"] = str(dk).strip()
    return out


def _merge_adjacent_chain_steps_by_code(steps):
    """
    Aufeinanderfolgende Stufen mit gleichem Kompetenzcode (z. B. zwei Zeilen D.3.C.1.B)
    zu einer Karte zusammenfassen: ein Code, mehrere Kompetenztexte.
    """
    if not steps:
        return []
    out = []
    i = 0
    n = len(steps)
    while i < n:
        step = steps[i]
        code = str(step.get("code") or "").strip()
        if not code:
            out.append(dict(step))
            i += 1
            continue
        run = [step]
        j = i + 1
        while j < n and str(steps[j].get("code") or "").strip() == code:
            run.append(steps[j])
            j += 1
        if len(run) == 1:
            out.append(dict(step))
            i = j
            continue
        merged = dict(run[0])
        texts_ordered = []
        seen_text = set()
        merged_uids = []
        merged_doc_keys = []
        link_out = []
        seen_link_target = set()
        for s in run:
            t = str(s.get("text") or "").strip()
            if t and t not in seen_text:
                seen_text.add(t)
                texts_ordered.append(t)
            u = s.get("uid")
            if u:
                us = str(u).strip()
                if us and us not in merged_uids:
                    merged_uids.append(us)
            dk = s.get("doc_key")
            if dk:
                dks = str(dk).strip()
                if dks and dks not in merged_doc_keys:
                    merged_doc_keys.append(dks)
            for lk in s.get("network_links") or []:
                if not isinstance(lk, dict):
                    continue
                tid = lk.get("uid")
                if tid and str(tid) not in seen_link_target:
                    seen_link_target.add(str(tid))
                    link_out.append(lk)
        merged["text"] = texts_ordered[0] if texts_ordered else merged.get("text")
        if len(texts_ordered) > 1:
            merged["text_variants"] = texts_ordered
        merged["merged_uids"] = merged_uids
        merged["merged_doc_keys"] = merged_doc_keys
        if link_out:
            merged["network_links"] = link_out
        out.append(merged)
        i = j
    return out


def _merged_chain_index_for_row(merged_steps, uid, doc_key):
    """Index der zusammengeführten Karte, die die gegebene Stufe (uid/doc_key) enthält."""
    uid_s = str(uid or "").strip()
    dk_s = str(doc_key or "").strip()

    def step_matches(m):
        if dk_s and m.get("doc_key") and str(m["doc_key"]).strip() == dk_s:
            return True
        if uid_s and m.get("uid") and _uids_equivalent_for_chain(m.get("uid"), uid_s):
            return True
        for x in m.get("merged_doc_keys") or []:
            if dk_s and str(x).strip() == dk_s:
                return True
        for x in m.get("merged_uids") or []:
            if uid_s and _uids_equivalent_for_chain(x, uid_s):
                return True
        return False

    for idx, m in enumerate(merged_steps):
        if step_matches(m):
            return idx
    return None


def _load_lehrplan_rows():
    """Rohe Zeilen aus Lehrplan21.json (optional Cache für Fallback)."""
    global _lehrplan_json_rows, _TB_KB_LCP_CACHE
    if _lehrplan_json_rows is not None:
        return _lehrplan_json_rows

    if not LEHRPLAN_JSON_PATH.is_file():
        print(f"Aufbau-Kette: Lehrplan21.json fehlt unter {LEHRPLAN_JSON_PATH}")
        _lehrplan_json_rows = []
        _TB_KB_LCP_CACHE = {}
        return _lehrplan_json_rows

    with open(LEHRPLAN_JSON_PATH, encoding="utf-8") as json_file:
        _lehrplan_json_rows = json.load(json_file)
    _TB_KB_LCP_CACHE = {}

    return _lehrplan_json_rows


def _dedupe_chain_rows(rows):
    """
    Sortierung für die Aufbau-Reihenfolge. Echte Duplikate nur bei gleicher uid und gleichem Text
    (identische Zeile); unterschiedliche Formulierungen mit gleicher offizieller uid bleiben erhalten.
    """
    rows = list(rows)
    rows.sort(
        key=lambda row: (
            int(str(row.get("folge_in_aufbaute") or "0")),
            str(row.get("uid") or ""),
            str(row.get("text") or "")[:96],
        )
    )
    deduped = []
    seen_sig = set()
    for row in rows:
        uid_key = _normalize_uid(row.get("uid"))
        text_key = (row.get("text") or "").strip()
        sig = (uid_key, text_key)
        if sig in seen_sig:
            continue
        seen_sig.add(sig)
        deduped.append(row)
    return deduped


def _deduped_group_rows_for_key(group_key):
    """Sortierte Zeilen einer Aufbau-Gruppe (Cache pro Gruppe; Epoch bei Dedupe-Änderung)."""
    global _chain_group_rows_cache, _chain_group_rows_cache_epoch
    if _chain_group_rows_cache_epoch != _CHAIN_GROUP_ROWS_CACHE_EPOCH:
        _chain_group_rows_cache.clear()
        _chain_group_rows_cache_epoch = _CHAIN_GROUP_ROWS_CACHE_EPOCH
    if group_key in _chain_group_rows_cache:
        return _chain_group_rows_cache[group_key]

    json_data = _load_lehrplan_rows()
    if not json_data:
        _chain_group_rows_cache[group_key] = []
        return []

    group_rows = [
        row
        for row in json_data
        if row.get("strukturtyp") == "Kompetenzstufe"
        and tuple(str(row.get(k, "") or "") for k in CHAIN_KEY_FIELDS) == group_key
    ]
    deduped = _dedupe_chain_rows(group_rows)
    _chain_group_rows_cache[group_key] = deduped
    return deduped


_KOMPETENZTITEL_PATTERN = re.compile(
    r'class="kompetenztitel[^>]*>[\s\S]*?komptitelnr[^<]*</p>\s*<p>\s*([^<]+)',
    re.IGNORECASE,
)

_CHAIN_HEADINGS_STORE = None
_HTTP_CHAIN_HEADING_CACHE = {}

CHAIN_HEADINGS_JSON = Path(
    os.getenv("CHAIN_HEADINGS_JSON", str(Path(__file__).resolve().parent / "chain_headings.json"))
)


def _load_chain_headings_store():
    """Liest chain_headings.json (von build_chain_headings.py erzeugt) — kein Netzwerk zur Laufzeit."""
    global _CHAIN_HEADINGS_STORE
    if _CHAIN_HEADINGS_STORE is not None:
        return _CHAIN_HEADINGS_STORE
    _CHAIN_HEADINGS_STORE = {}
    path = CHAIN_HEADINGS_JSON
    if not path.is_file():
        return _CHAIN_HEADINGS_STORE
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _CHAIN_HEADINGS_STORE
    if not isinstance(raw, dict):
        return _CHAIN_HEADINGS_STORE
    for key, val in raw.items():
        if not key or not isinstance(val, str):
            continue
        uid_base = str(key).strip().split(".")[0]
        text = val.strip()
        if uid_base and text:
            _CHAIN_HEADINGS_STORE[uid_base] = text
    return _CHAIN_HEADINGS_STORE


def _fetch_bs_chain_heading_http(uid_base):
    """Nur für Entwicklung / fehlende Einträge; Production nutzt chain_headings.json."""
    req = urllib.request.Request(
        f"https://BS.lehrplan.ch/{uid_base}",
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; LehrplanBaselSearch/1.0)",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None
    match = _KOMPETENZTITEL_PATTERN.search(html)
    return match.group(1).strip() if match else None


def fetch_bs_chain_heading(uid):
    """
    Übergeordnete Kompetenzformulierung (kompetenztitel auf BS-Lehrplan).
    Standard: nur aus chain_headings.json (offline, schnell bei /search).
    Optional: CHAIN_HEADING_HTTP_FALLBACK=1 lädt einzelne fehlende Titel nach (langsam).
    DISABLE_BS_CHAIN_HEADING=1 schaltet alles ab.
    """
    if os.getenv("DISABLE_BS_CHAIN_HEADING", "").strip().lower() in ("1", "true", "yes"):
        return None
    if not uid:
        return None
    base = str(uid).strip().split(".")[0]
    if not base:
        return None

    store = _load_chain_headings_store()
    if base in store:
        return store[base]

    if os.getenv("CHAIN_HEADING_HTTP_FALLBACK", "").strip().lower() in ("1", "true", "yes"):
        if base in _HTTP_CHAIN_HEADING_CACHE:
            return _HTTP_CHAIN_HEADING_CACHE[base]
        title = _fetch_bs_chain_heading_http(base)
        if title:
            _HTTP_CHAIN_HEADING_CACHE[base] = title
        return title

    return None


def _minimal_chain_from_chroma(chain_key):
    """Wenn Lehrplan21.json fehlt oder UID dort nicht vorkommt: nur aktuelle Stufe aus Chroma."""
    normalized_uid = _normalize_uid(chain_key)
    if not normalized_uid:
        return None
    try:
        collection = init_collection()
        result = collection.get(ids=[normalized_uid], include=["metadatas", "documents"])
        ids_out = result.get("ids") or []
        if not ids_out:
            return None
        meta = (result.get("metadatas") or [None])[0] or {}
        docs = result.get("documents") or []
        text_body = docs[0] if docs else ""
        synthetic = {**meta, "text": text_body}
        dk = meta.get("doc_key") or (
            f"{LP21_ROW_PREFIX}{meta['lp21_row_index']}"
            if meta.get("lp21_row_index") not in (None, "")
            else None
        )
        if dk:
            synthetic["doc_key"] = str(dk).strip()
        item = _format_chain_item(synthetic)
        if not item or not item.get("uid"):
            return None
        heading_uid = _normalize_uid(item.get("uid"))
        heading = fetch_bs_chain_heading(heading_uid)
        return {
            "previous": None,
            "current": item,
            "next": None,
            "full_chain": [item],
            "_chain_partial": True,
            "chain_heading": heading,
        }
    except Exception as exc:
        print(f"Aufbau-Kette Chroma-Fallback fehlgeschlagen ({normalized_uid}): {exc}")
        return None


def lookup_competency_chain(uid):
    """Vorgänger, aktuelle Stufe, Nachfolger und volle Kette (für Navigation ohne zweiten Request)."""
    raw = _normalize_uid(uid)
    if not raw:
        return None

    if not raw.lower().startswith(LP21_ROW_PREFIX.lower()):
        candidates = extract_competency_code_candidates(raw) or [raw]
        resolved = resolve_uids_from_competency_code_candidates(candidates)
        if resolved:
            raw = resolved[0]

    json_data = _load_lehrplan_rows()
    row_index = parse_lp21_row_index(raw)
    target_row = None

    if json_data:
        if row_index is not None:
            if 0 <= row_index < len(json_data):
                target_row = json_data[row_index]
        else:
            for row in json_data:
                if row.get("strukturtyp") != "Kompetenzstufe":
                    continue
                if _uids_equivalent_for_chain(row.get("uid"), raw):
                    target_row = row
                    break

    if target_row and target_row.get("strukturtyp") == "Kompetenzstufe":
        group_key = tuple(str(target_row.get(k, "") or "") for k in CHAIN_KEY_FIELDS)
        rows = _deduped_group_rows_for_key(group_key)
        if rows:
            pos = next((i for i, r in enumerate(rows) if r is target_row), None)
            if pos is not None:
                full_formatted = []
                for r in rows:
                    try:
                        ri = json_data.index(r)
                    except ValueError:
                        ri = None
                    row_payload = dict(r)
                    if ri is not None:
                        row_payload["doc_key"] = f"{LP21_ROW_PREFIX}{ri}"
                    item = _format_chain_item(row_payload)
                    links = _network_links_for_row(r)
                    if links:
                        item["network_links"] = links
                    full_formatted.append(item)
                merged_chain = _merge_adjacent_chain_steps_by_code(full_formatted)
                current_row = rows[pos]
                current_links = _network_links_for_row(current_row)
                heading = fetch_bs_chain_heading(_normalize_uid(target_row.get("uid")))
                cur_uid = full_formatted[pos].get("uid")
                cur_doc = full_formatted[pos].get("doc_key")
                mpos = _merged_chain_index_for_row(merged_chain, cur_uid, cur_doc)
                if mpos is None:
                    mpos = 0
                cur_merged = merged_chain[mpos]
                cur_merged["uid"] = _normalize_uid(current_row.get("uid"))
                try:
                    ri_nav = json_data.index(current_row)
                    cur_merged["doc_key"] = f"{LP21_ROW_PREFIX}{ri_nav}"
                except ValueError:
                    pass
                cur_code = str(current_row.get("code") or "").strip()
                tb_kb, tb_aspect = _themenbereich_kb_aspect_for_row(current_row, json_data)
                cluster_c = _competenz_cluster_code(cur_code)
                return {
                    "previous": merged_chain[mpos - 1] if mpos > 0 else None,
                    "current": cur_merged,
                    "next": merged_chain[mpos + 1] if mpos < len(merged_chain) - 1 else None,
                    "full_chain": merged_chain,
                    "_has_network": bool(current_links),
                    "chain_heading": heading,
                    "themenbereich_kb": tb_kb or None,
                    "themenbereich_aspect": tb_aspect or None,
                    "cluster_code": cluster_c,
                }

    return _minimal_chain_from_chroma(raw)


# LP21-Fachkürzel (Lehrplan 21 „Abkürzungen und Codes“) → JSON-Schreibweise „fach“.
LP21_FACH_NAME_TO_TOKEN = {
    "Deutsch": "D",
    "Englisch": "FS1E",
    "Französisch": "FS2F",
    "Italienisch": "FS3I",
    "Latein": "LAT",
    "Mathematik": "MA",
    "Natur, Mensch, Gesellschaft (1./2. Zyklus)": "NMG",
    "Natur und Technik (mit Physik, Chemie, Biologie)": "NT",
    "Wirtschaft, Arbeit, Haushalt (mit Hauswirtschaft)": "WAH",
    "Räume, Zeiten, Gesellschaften (mit Geografie, Geschichte)": "RZG",
    "Ethik, Religionen, Gemeinschaft (mit Lebenskunde)": "ERG",
    "Bildnerisches Gestalten": "BG",
    "Textiles und Technisches Gestalten": "TTG",
    "Musik": "MU",
    "Bewegung und Sport": "BS",
    "Medien und Informatik": "MI",
    "Berufliche Orientierung": "BO",
}


def _competenz_cluster_code(code):
    """
    Code ohne Kompetenzstufe: letztes Segment ist z. B. ein Buchstabe (… .c)
    oder zusammengezogen (… .1a). Wird für Themen-„Code-Hinweise“ je Kette genutzt.
    """
    if not code or not isinstance(code, str):
        return None
    parts = [p.strip() for p in code.strip().split(".") if p.strip()]
    if len(parts) <= 1:
        return parts[0] if parts else None
    last = parts[-1]
    if len(last) == 1 and last.isalpha():
        return ".".join(parts[:-1])
    merged = re.fullmatch(r"(\d+)([a-zA-Z])", last)
    if merged:
        return ".".join(parts[:-1] + [merged.group(1)])
    return ".".join(parts[:-1])


def _ordered_chain_stage_codes(rows):
    """Alle Kompetenzstufen-Codes einer Kette, sortiert nach Aufbau-Reihenfolge."""
    ordered = sorted(
        rows,
        key=lambda r: (int(str(r.get("folge_in_aufbaute") or "0")), str(r.get("uid") or "")),
    )
    out = []
    seen = set()
    for r in ordered:
        c = r.get("code")
        if not c:
            continue
        text = str(c).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _lp_themenbereich_prefix(code):
    """
    Themen-/Strukturebene im LP21-Code: erste drei Segmente
    (Fach · Kompetenzbereich · Handlungs-/Themenaspekt), soweit vorhanden.
    """
    if not code:
        return None
    parts = [p.strip() for p in str(code).strip().split(".") if p.strip()]
    if len(parts) >= 3:
        return ".".join(parts[:3])
    return parts[0] if parts else None


_KNOWN_MULTIWORD_KB_PREFIXES = (
    # Mathematik (häufigster Fehlerfall)
    "Grössen, Funktionen, Daten und Zufall",
    "Zahl und Variable",
    "Form und Raum",
    # Weitere LP21-Mehrwort-Bezeichnungen (robuster für ähnliche Fälle)
    "Ethik, Religionen, Gemeinschaft",
    "Räume, Zeiten, Gesellschaften",
    "Wirtschaft, Arbeit, Haushalt",
    "Natur und Technik",
    # NT Handlungsfeld (Lehrplan21.json, oft NFD — Vergleich über NFC)
    "Mechanische und elektrische Phänomene untersuchen",
    "Fortpflanzung und Entwicklung analysieren",
    "Körperfunktionen verstehen",
    "Wesen und Bedeutung von Naturwissenschaften und Technik verstehen",
    "Medien und Informatik",
    "Textiles und Technisches Gestalten",
    "Bildnerisches Gestalten",
    "Bewegung und Sport",
    "Berufliche Orientierung",
    "Praxis des musikalischen Wissens",
)


def _split_themenbereich_head(tb):
    """
    Trennt Themenbereich in Kompetenzbereich-Label und Rest.

    Priorität:
    1) bekannte mehrteilige LP21-Titel als Präfix erkennen (z. B. "Zahl und Variable")
    2) sonst kompatibler Fallback: erstes Wort + Rest
    """
    text = unicodedata.normalize("NFC", (tb or "").strip())
    if not text:
        return "", ""

    for prefix in _KNOWN_MULTIWORD_KB_PREFIXES:
        pfx = unicodedata.normalize("NFC", prefix)
        if text == pfx:
            return text, ""
        if text.startswith(pfx + " "):
            return pfx, text[len(pfx) + 1 :].strip()

    idx = text.find(" ")
    if idx == -1:
        return text, ""
    return text[:idx].strip(), text[idx + 1 :].strip()


def _kb_tb_nfc_list_for_fach_kb(fach, kb_code, json_data):
    """Alle NFC-Themenbereich-Texte zu Kompetenzstufen unter fach + Codes kb_code.* (Reihenfolge stabil)."""
    fach_k = (fach or "").strip()
    kb_k = (kb_code or "").strip()
    if not fach_k or not kb_k or not json_data:
        return []
    prefix = kb_k + "."
    out = []
    for r in json_data:
        if str(r.get("strukturtyp") or "") != "Kompetenzstufe":
            continue
        if (r.get("fach") or "").strip() != fach_k:
            continue
        c = str(r.get("code") or "").strip()
        if not c.startswith(prefix):
            continue
        tb = (r.get("themenbereich") or "").strip()
        if tb:
            out.append(unicodedata.normalize("NFC", tb))
    return out


def _kb_tb_lcp_raw(fach, kb_code, json_data):
    """
    Längster gemeinsamer Zeichen-Präfix aller Themenbereiche unter (fach, kb_code.*).

    LP21 liefert oft KB-Titel und Aspekt-Titel in einem String ohne Trennzeichen
    (z. B. „Bewegen und Tanzen Sensomotorische Schulung“). Unter demselben KB unterscheiden
    sich die Aspekte nur im Suffix → der gemeinsame Präfix ist der KB-Titel inkl. Leerzeichen.
    """
    cache_key = (fach or "", kb_code or "")
    if cache_key in _TB_KB_LCP_CACHE:
        return _TB_KB_LCP_CACHE[cache_key]
    tbs = _kb_tb_nfc_list_for_fach_kb(fach, kb_code, json_data)
    uniq = list(dict.fromkeys(tbs))
    if len(uniq) < 2:
        _TB_KB_LCP_CACHE[cache_key] = None
        return None
    lcp_s = uniq[0]
    for s in uniq[1:]:
        i = 0
        lim = min(len(lcp_s), len(s))
        while i < lim and lcp_s[i] == s[i]:
            i += 1
        lcp_s = lcp_s[:i]
    _TB_KB_LCP_CACHE[cache_key] = lcp_s if lcp_s else None
    return _TB_KB_LCP_CACHE[cache_key]


def _themenbereich_kb_aspect_for_row(row, json_data):
    """
    Zeile 1/2 im Kettenkopf: KB-Bezeichnung und Aspekt-Bezeichnung aus dem zusammengefügten themenbereich.

    1) LCP über alle Themenbereiche desselben (fach, KB) (robust für Musik, Mathematik, …)
    2) sonst _split_themenbereich_head (Mehrwort-Whitelist + erstes Wort)
    """
    tb = (row.get("themenbereich") or "").strip()
    if not tb:
        return "", ""
    code = str(row.get("code") or "").strip()
    parts = [p.strip() for p in code.split(".") if p.strip()]
    if len(parts) < 2:
        return _split_themenbereich_head(tb)
    kb_key = ".".join(parts[:2])
    fach = (row.get("fach") or "").strip()
    tb_n = unicodedata.normalize("NFC", tb)
    raw_lcp = _kb_tb_lcp_raw(fach, kb_key, json_data)
    if raw_lcp and tb_n.startswith(raw_lcp):
        asp = tb_n[len(raw_lcp) :].strip()
        kb_label = raw_lcp.rstrip()
        if asp:
            return kb_label, asp
    return _split_themenbereich_head(tb)


def _longest_common_word_prefix(texts):
    """Gemeinsamer Wort-Präfix über mehrere Themenbereich-Texte."""
    cleaned = []
    for t in texts or []:
        s = unicodedata.normalize("NFC", (t or "").strip())
        if s:
            cleaned.append(s)
    if not cleaned:
        return ""
    prefix = cleaned[0].split()
    for txt in cleaned[1:]:
        words = txt.split()
        i = 0
        limit = min(len(prefix), len(words))
        while i < limit and prefix[i] == words[i]:
            i += 1
        prefix = prefix[:i]
        if not prefix:
            break
    return " ".join(prefix).strip()


def _strip_prefix_label(text, prefix):
    """Entfernt einen exakten Präfix (falls vorhanden) und trimmt den Rest."""
    s = unicodedata.normalize("NFC", (text or "").strip())
    p = unicodedata.normalize("NFC", (prefix or "").strip())
    if not s or not p:
        return s
    if s == p:
        return ""
    if s.startswith(p + " "):
        return s[len(p) + 1 :].strip()
    return s


_NO_ASPECT_KEY = "__no_aspect__"


# Reihenfolge wie Frontend fachOptions (Landkarte / Übersicht).
_CURRICULUM_FACH_ORDER = (
    "Italienisch",
    "Französisch",
    "Englisch",
    "Latein",
    "Deutsch",
    "Bewegung und Sport",
    "Natur, Mensch, Gesellschaft (1./2. Zyklus)",
    "Ethik, Religionen, Gemeinschaft (mit Lebenskunde)",
    "Räume, Zeiten, Gesellschaften (mit Geografie, Geschichte)",
    "Natur und Technik (mit Physik, Chemie, Biologie)",
    "Wirtschaft, Arbeit, Haushalt (mit Hauswirtschaft)",
    "Medien und Informatik",
    "Musik",
    "Bildnerisches Gestalten",
    "Textiles und Technisches Gestalten",
    "Mathematik",
    "Berufliche Orientierung",
)

_curriculum_overview_cache = None


def build_curriculum_overview():
    """
    Landkarte als Outline: Fach → Kompetenzbereich (2 Segmente) → Aspekt (3 Segmente)
    → Kompetenz (chain_heading + cluster_code) → Stufen (text + code).
    """
    global _curriculum_overview_cache
    if _curriculum_overview_cache is not None:
        return _curriculum_overview_cache

    from collections import defaultdict

    json_data = _load_lehrplan_rows()
    if not json_data:
        _curriculum_overview_cache = {"subjects": []}
        return _curriculum_overview_cache

    groups = defaultdict(list)
    for row in json_data:
        if row.get("strukturtyp") != "Kompetenzstufe":
            continue
        key = tuple(str(row.get(k, "") or "") for k in CHAIN_KEY_FIELDS)
        groups[key].append(row)

    # fach -> kb_key -> aspect_key -> [chain_payload, ...]
    bucket = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for _key, rows in groups.items():
        deduped = _dedupe_chain_rows(list(rows))
        if not deduped:
            continue
        first = deduped[0]
        fach_name = (first.get("fach") or "Unbekannt").strip()
        uid = _normalize_uid(first.get("uid"))
        if not uid:
            continue
        codes_ordered = _ordered_chain_stage_codes(deduped)
        primary_text = str(codes_ordered[0]).strip() if codes_ordered else first.get("code")
        primary_text = str(primary_text or "").strip()
        if not primary_text:
            continue
        parts = [p.strip() for p in primary_text.split(".") if p.strip()]
        if len(parts) < 2:
            continue
        kb_key = ".".join(parts[:2])
        aspect_key = ".".join(parts[:3]) if len(parts) >= 3 else _NO_ASPECT_KEY

        tb = (first.get("themenbereich") or "").strip()
        heading = fetch_bs_chain_heading(uid)
        if not heading:
            heading = str(first.get("code") or "").strip() or uid
        cluster = _competenz_cluster_code(primary_text)
        stages = []
        for r in sorted(
            deduped,
            key=lambda r: (int(str(r.get("folge_in_aufbaute") or "0")), str(r.get("uid") or "")),
        ):
            sc = r.get("code")
            if not sc:
                continue
            st_uid = _normalize_uid(r.get("uid"))
            stages.append(
                {
                    "uid": st_uid,
                    "code": str(sc).strip(),
                    "text": (r.get("text") or "").strip(),
                }
            )

        chain_obj = {
            "anchor_uid": uid,
            "cluster_code": cluster,
            "heading": heading,
            "themenbereich": tb,
            "stages": stages,
        }
        bucket[fach_name][kb_key][aspect_key].append(chain_obj)

    def _fach_sort_key(name):
        try:
            idx = _CURRICULUM_FACH_ORDER.index(name)
            return (0, idx)
        except ValueError:
            return (1, name)

    def _aspect_sort_key(k):
        if k == _NO_ASPECT_KEY:
            return "\uffff"
        return k.lower()

    subjects = []
    for fach_name in sorted(bucket.keys(), key=lambda n: (_fach_sort_key(n)[0], _fach_sort_key(n)[1])):
        kb_map = bucket[fach_name]
        kb_nodes = []
        for kb_key in sorted(kb_map.keys(), key=lambda x: (x.lower(), x)):
            aspect_map = kb_map[kb_key]
            all_tb = []
            for ak in sorted(aspect_map.keys(), key=_aspect_sort_key):
                for ch in aspect_map[ak]:
                    tbs = (ch.get("themenbereich") or "").strip()
                    if tbs:
                        all_tb.append(tbs)
            has_aspects = any(k != _NO_ASPECT_KEY for k in aspect_map.keys())
            kb_label = ""
            if has_aspects:
                raw_lcp = _kb_tb_lcp_raw(fach_name, kb_key, json_data)
                if raw_lcp and raw_lcp.strip():
                    kb_label = raw_lcp.rstrip()
                else:
                    kb_label = _longest_common_word_prefix(all_tb)
                    if len(kb_label.split()) < 2:
                        # Fallback: bekannte LP21-Mehrwort-Prefixes / altes Verhalten.
                        for tb_txt in all_tb:
                            fw, _ = _split_themenbereich_head(tb_txt)
                            if fw:
                                kb_label = fw
                                break
            else:
                # Ohne Aspekte ist der Themenbereich selbst i. d. R. der KB-Titel.
                kb_label = all_tb[0] if all_tb else ""
            if not kb_label:
                kb_label = kb_key

            aspect_nodes = []
            for aspect_key in sorted(aspect_map.keys(), key=_aspect_sort_key):
                chain_list = aspect_map[aspect_key]
                chain_list.sort(
                    key=lambda c: (str(c.get("cluster_code") or "").lower(), str(c.get("anchor_uid") or ""))
                )
                chains_out = [
                    {
                        "anchor_uid": c["anchor_uid"],
                        "cluster_code": c.get("cluster_code"),
                        "heading": c.get("heading") or "",
                        "stages": c.get("stages") or [],
                    }
                    for c in chain_list
                ]
                if aspect_key == _NO_ASPECT_KEY:
                    aspect_nodes.append(
                        {
                            "aspect_code": None,
                            "aspect_label": "",
                            "chains": chains_out,
                        }
                    )
                else:
                    aspect_label = ""
                    if chain_list:
                        for ch in chain_list:
                            tb_full = (ch.get("themenbereich") or "").strip()
                            if not tb_full:
                                continue
                            candidate = _strip_prefix_label(tb_full, kb_label)
                            if candidate:
                                aspect_label = candidate
                                break
                    if not aspect_label and chain_list:
                        first_tb = (chain_list[0].get("themenbereich") or "").strip()
                        kb_cmp = unicodedata.normalize("NFC", (kb_label or "").strip())
                        tb_cmp = unicodedata.normalize("NFC", first_tb)
                        rest_from_strip = _strip_prefix_label(first_tb, kb_label)
                        if rest_from_strip:
                            aspect_label = rest_from_strip
                        elif tb_cmp == kb_cmp:
                            # Gleicher Themenbereich für alle Aspekte unter diesem KB → kein Rest-Label
                            aspect_label = ""
                        else:
                            _fw, rest = _split_themenbereich_head(first_tb)
                            aspect_label = rest
                    aspect_nodes.append(
                        {
                            "aspect_code": aspect_key,
                            "aspect_label": aspect_label,
                            "chains": chains_out,
                        }
                    )

            kb_nodes.append(
                {
                    "kb_code": kb_key,
                    "kb_label": kb_label,
                    "aspects": aspect_nodes,
                }
            )

        subjects.append(
            {
                "name": fach_name,
                "fach_code": LP21_FACH_NAME_TO_TOKEN.get(fach_name),
                "outline": kb_nodes,
            }
        )

    _curriculum_overview_cache = {"subjects": subjects}
    return _curriculum_overview_cache


# --- Kompetenz-Vernetzung (Querverweise aus Lehrplan21.json) -----------------

REF_UID_IN_URL = re.compile(r"[?&]uid=([^&]+)", re.IGNORECASE)

_uid_row_index_cache = None


def extract_uid_from_reference_url(url):
    """Liest den ersten uid-Parameter aus Lehrplan-Ch-URLs (querverweise, hierarchie_oben)."""
    if not url:
        return None
    match = REF_UID_IN_URL.search(str(url))
    if not match:
        return None
    return _normalize_uid(match.group(1))


def _get_uid_row_index():
    """Erste Zeile pro uid (wie Dedupe-Logik), alle strukturtypen — für Auflösung von Querverweisen."""
    global _uid_row_index_cache
    if _uid_row_index_cache is not None:
        return _uid_row_index_cache

    json_data = _load_lehrplan_rows()
    index = {}
    for row in json_data:
        uid_key = _normalize_uid(row.get("uid"))
        if uid_key and uid_key not in index:
            index[uid_key] = row
    _uid_row_index_cache = index
    return _uid_row_index_cache


def _network_links_for_row(row):
    """
    Offizielle Querverweise der Kompetenzstufe → andere Kompetenzstufen (Kompetenz-zu-Kompetenz laut Lehrplan-Ch).
    Kurzinfos für Link-Buttons in der Aufbau-Kette.
    """
    if not row:
        return []
    index = _get_uid_row_index()
    normalized_self = _normalize_uid(row.get("uid"))
    refs = row.get("querverweise") or []
    if not isinstance(refs, list):
        refs = []
    out = []
    seen = set()
    for ref_url in refs:
        tid = extract_uid_from_reference_url(ref_url)
        if not tid or tid == normalized_self or tid in seen:
            continue
        seen.add(tid)
        trow = index.get(tid)
        if not trow:
            continue
        out.append(
            {
                "uid": tid,
                "code": trow.get("code"),
                "fach": trow.get("fach"),
                "text": trow.get("text"),
            }
        )
        if len(out) >= 16:
            break
    return out


def _format_parent_summary(row):
    if not row:
        return None
    return {
        "uid": row.get("uid"),
        "code": row.get("code"),
        "text": row.get("text"),
        "url": row.get("url"),
        "strukturtyp": row.get("strukturtyp"),
        "fach": row.get("fach"),
    }


def lookup_competency_network(uid):
    """
    Fokus-Kompetenzstufe + ausgehende offizielle Querverweise (aufgelöst) + optional Parent aus hierarchie_oben.
    Gibt None zurück, wenn die uid in Lehrplan21.json nicht vorkommt.
    """
    normalized = _normalize_uid(uid)
    if not normalized:
        return None

    index = _get_uid_row_index()
    focus_row = index.get(normalized)
    if not focus_row or focus_row.get("strukturtyp") != "Kompetenzstufe":
        return None

    focus = _format_chain_item(focus_row)

    parent = None
    hierarchie_oben = focus_row.get("hierarchie_oben")
    if isinstance(hierarchie_oben, str) and hierarchie_oben.strip():
        p_uid = extract_uid_from_reference_url(hierarchie_oben)
        if p_uid:
            prow = index.get(p_uid)
            if prow:
                parent = _format_parent_summary(prow)

    outgoing = []
    missing_targets = []
    seen_targets = set()

    refs = focus_row.get("querverweise") or []
    if not isinstance(refs, list):
        refs = []

    for ref_url in refs:
        target_uid = extract_uid_from_reference_url(ref_url)
        if not target_uid or target_uid == normalized:
            continue
        if target_uid in seen_targets:
            continue
        seen_targets.add(target_uid)

        target_row = index.get(target_uid)
        if target_row:
            formatted = _format_chain_item(target_row)
            if formatted:
                outgoing.append(formatted)
        else:
            missing_targets.append(target_uid)

    return {
        "focus": focus,
        "parent": parent,
        "outgoing": outgoing,
        "missing_targets": missing_targets,
    }


def infer_primary_match_channel(sources):
    """Priorisierten Kanal für die Kurzdarstellung im Frontend (ein Label pro Treffer)."""
    priority = ("competency_code", "semantic_vector", "vector", "keyword")
    for key in priority:
        if key in sources:
            return key
    return "vector"


def merge_search_candidate_group(primary, secondary):
    """
    Zwei Treffer mit gleichem Kompetenzcode: besseres Ranking (primary) behalten,
    Kompetenztexte und Ranking-Signale sinnvoll zusammenführen.
    """
    doc_p = (primary.get("document") or "").strip()
    doc_s = (secondary.get("document") or "").strip()
    if doc_s and doc_s not in doc_p:
        doc_p = f"{doc_p}\n\n{doc_s}" if doc_p else doc_s
    best_a = primary.get("best_distance")
    best_b = secondary.get("best_distance")
    best = best_a
    if best_b is not None and (best is None or best_b < best):
        best = best_b
    fs = max(float(primary.get("final_score") or 0), float(secondary.get("final_score") or 0))
    merged = dict(primary)
    merged["document"] = doc_p
    merged["best_distance"] = best
    merged["final_score"] = fs
    merged["sources"] = set(primary.get("sources") or set()) | set(secondary.get("sources") or set())
    merged["keyword_hits"] = set(primary.get("keyword_hits") or set()) | set(
        secondary.get("keyword_hits") or set()
    )
    merged["query_variants"] = set(primary.get("query_variants") or set()) | set(
        secondary.get("query_variants") or set()
    )
    merged["rrf_score"] = max(
        float(primary.get("rrf_score") or 0), float(secondary.get("rrf_score") or 0)
    )
    return merged


def dedupe_top_items_by_competency_code(top_items):
    """
    Such-Treffer mit identischem metadata.code zu einem Eintrag zusammenführen
    (Reihenfolge = Ranking; erster Treffer ist Träger der stabilen lp21:id).
    """
    if not top_items:
        return []
    out = []
    code_to_out_idx = {}
    for item in top_items:
        meta = item.get("metadata") or {}
        code = str(meta.get("code") or "").strip()
        if not code:
            out.append(item)
            continue
        if code not in code_to_out_idx:
            code_to_out_idx[code] = len(out)
            out.append(item)
            continue
        idx = code_to_out_idx[code]
        out[idx] = merge_search_candidate_group(out[idx], item)
    return out


def format_response(top_items, query_profile):
    metadata_rows = []
    for rank_idx, item in enumerate(top_items, start=1):
        competency_chain = lookup_competency_chain(str(item["id"]))
        metadata_rows.append({
            **item["metadata"],
            "_score": round(item["final_score"], 5),
            "_match_sources": sorted(item["sources"]),
            "_primary_match_channel": infer_primary_match_channel(item["sources"]),
            "_result_rank": rank_idx,
            "_query_variant_hits": len(item["query_variants"]),
            "_keyword_hits": len(item["keyword_hits"]),
            "_query_profile": query_profile,
            "_competency_chain": competency_chain,
        })
    return {
        "documents": [[item["document"] for item in top_items]],
        "metadatas": [metadata_rows],
        "ids": [[item["id"] for item in top_items]],
        "distances": [[item["best_distance"] if item["best_distance"] is not None else 1.0 for item in top_items]],
    }

#------------------------------------------------------------App------------------------------------------------------------

#App
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public"
app = Flask(__name__, static_folder=str(FRONTEND_DIR))
cors_origins_raw = os.getenv("CORS_ORIGINS", "*").strip()
if cors_origins_raw == "*":
    CORS(app)
else:
    CORS(app, resources={r"/*": {"origins": [origin.strip() for origin in cors_origins_raw.split(",") if origin.strip()]}})
    
@app.route('/')
def serve_index():
    #return "main"
    print('homepage')
    return send_from_directory(str(FRONTEND_DIR), 'index.html')


@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


@app.route('/competency-chain/<uid>', methods=['GET'])
@app.route('/api/competency-chain/<uid>', methods=['GET'])
def competency_chain(uid):
    payload = lookup_competency_chain(uid)
    if payload is None:
        return jsonify({"error": "not_found", "uid": uid}), 404
    return jsonify(payload)


@app.route('/competency-network/<uid>', methods=['GET'])
@app.route('/api/competency-network/<uid>', methods=['GET'])
def competency_network(uid):
    payload = lookup_competency_network(uid)
    if payload is None:
        return jsonify({"error": "not_found", "uid": uid}), 404
    return jsonify(payload)


@app.route('/curriculum-overview', methods=['GET'])
@app.route('/api/curriculum-overview', methods=['GET'])
def curriculum_overview():
    try:
        payload = build_curriculum_overview()
        return jsonify(payload)
    except Exception as exc:
        print(f"curriculum-overview: {exc}")
        return jsonify({"subjects": [], "error": "build_failed"}), 500


@app.route('/api/calendar/publish', methods=['POST'])
def calendar_publish():
    """Planungstermine für Apple-Kalender-Abo bereitstellen."""
    data = request.json or {}
    token = (data.get("token") or "").strip()
    events = data.get("events") or []
    if not token:
        token = new_export_token()
    if not isinstance(events, list):
        return jsonify({"ok": False, "error": "events muss eine Liste sein"}), 400
    try:
        publish_feed(token, events)
        return jsonify({"ok": True, "token": token, "count": len(events)})
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route('/api/calendar/export', methods=['POST'])
def calendar_export():
    """Einmaliger .ics-Download (Import in Apple Kalender)."""
    data = request.json or {}
    events = data.get("events") or []
    if not isinstance(events, list):
        return jsonify({"ok": False, "error": "events muss eine Liste sein"}), 400
    body = build_ics(events)
    from flask import Response

    return Response(
        body,
        mimetype="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="lehrplan-planung.ics"'},
    )


@app.route('/api/calendar/feed/<token>.ics', methods=['GET'])
def calendar_feed(token):
    """Abonnement-URL für Apple Kalender (webcal://…)."""
    body = load_feed_ics(token)
    if body is None:
        return jsonify({"error": "Feed nicht gefunden — zuerst in der App synchronisieren."}), 404
    from flask import Response

    return Response(body, mimetype="text/calendar; charset=utf-8")


@app.route('/api/calendar/fetch', methods=['POST'])
def calendar_fetch():
    """Proxy für externe .ics-Abos (Schulkalender etc.) — umgeht Browser-CORS."""
    data = request.json or {}
    url = (data.get("url") or "").strip()
    subscription_id = (data.get("subscriptionId") or "sub").strip()[:64]
    if not url:
        return jsonify({"ok": False, "error": "url fehlt", "events": []}), 400
    payload = fetch_subscription_events(url, subscription_id)
    status = 200 if payload.get("ok") else 422
    return jsonify(payload), status


@app.route('/search', methods=['POST'])
def search():
    collection = init_collection()

    data = request.json or {}
    query_text = (data.get('query_texts') or '').strip()
    query_schlagwort = (data.get('querySchlagwort') or '').strip()
    requested_n_results = data.get('n_results')
    filters = data.get('filters', {})

    if not query_text:
        return jsonify({"documents": [[]], "metadatas": [[]], "ids": [[]], "distances": [[]]})

    inferred_zyklus = detect_zyklus_from_query(query_text)
    if inferred_zyklus and not filters.get("zyklus"):
        filters = {**filters, "zyklus": sorted(inferred_zyklus)}

    where_clause = build_where_clause(filters)
    combined_for_tokens = f"{query_text} {query_schlagwort}".strip()
    alias_store = get_query_aliases_store()
    query_tokens = tokenize_query(combined_for_tokens)
    alias_to_canonical = alias_store.get("alias_to_canonical") or {}
    canonical_boost_terms = active_canonical_targets(combined_for_tokens, alias_to_canonical)
    fach_signals = detect_fach_signals(query_text)
    intent_signals = detect_intent_signals(query_text)
    query_profile = classify_query_profile(query_text, query_tokens, intent_signals)
    weights = get_score_weights(query_profile)
    n_results = resolve_n_results(requested_n_results, query_profile)
    query_variants = build_query_variants(query_text, query_schlagwort, alias_to_canonical)
    semantic_variants = build_semantic_variants(query_text, fach_signals, intent_signals)

    exact_scope = resolve_exact_competency_codes_in_query(query_text, query_schlagwort)
    exact_competency_code = bool(exact_scope["codes_lower"])

    code_candidates = extract_competency_code_candidates(combined_for_tokens)
    code_lookup_uids = resolve_uids_from_competency_code_candidates(code_candidates)
    pure_code_query = is_pure_competency_code_query(query_text, query_schlagwort)
    skip_parallel_for_code = (
        pure_code_query and bool(code_lookup_uids) and not exact_competency_code
    )

    candidate_map = {}
    competency_code_lookup_retrieve(
        collection, query_text, query_schlagwort, filters, candidate_map, resolved_uids=code_lookup_uids
    )

    if not exact_competency_code and not skip_parallel_for_code:
        parallel_candidates = parallel_retrieve_all(
            collection, query_variants, semantic_variants, where_clause, n_results, weights
        )
        candidate_map.update(parallel_candidates)

    combined_query = f"{query_text} {query_schlagwort}".strip()

    scored_items = score_candidates(
        candidate_map,
        query_tokens,
        fach_signals,
        intent_signals,
        weights,
        combined_query=combined_query,
        canonical_boost_terms=canonical_boost_terms,
    )

    if exact_competency_code:
        allowed_uids = set(exact_scope["uids"])
        scored_items = [
            item
            for item in scored_items
            if item["id"] in allowed_uids and metadata_matches_request_filters(item["metadata"], filters)
        ]
        scored_items.sort(
            key=lambda it: competency_code_sort_tuple(metadata_competency_code(it.get("metadata")))
        )
        top_items = scored_items[: min(len(scored_items), 50)]
    elif skip_parallel_for_code:
        scored_items = [
            item
            for item in scored_items
            if metadata_matches_request_filters(item["metadata"], filters)
        ]
        scored_items.sort(
            key=lambda it: competency_code_sort_tuple(metadata_competency_code(it.get("metadata")))
        )
        top_items = scored_items[: min(len(scored_items), 50)]
    else:
        scored_items = apply_second_stage_rerank(scored_items, combined_query)
        top_items = mmr_diversify(scored_items, n_results)

    top_items = dedupe_top_items_by_competency_code(top_items)
    response = format_response(top_items, query_profile)
    response["meta"] = {
        "n_results_used": n_results,
        "query_profile": query_profile,
        "exact_competency_code": exact_competency_code,
        "query_aliases_version": alias_store.get("version", 0),
    }
    return jsonify(response)


@app.route('/<path:path>')
def static_proxy(path):
    # send_static_file verwendet static_folder
    return send_from_directory(str(FRONTEND_DIR), path)


if __name__ == '__main__':
    # Standard 5001: auf macOS blockiert AirPlay-Empfänger oft Port 5000.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5001")), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
#------------------------------------------------------------End------------------------------------------------------------