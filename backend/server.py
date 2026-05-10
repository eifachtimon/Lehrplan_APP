# app.py
#------------------------------------------------------------Imports------------------------------------------------------------
from flask import Flask, jsonify, request, send_from_directory
from chroma_lehrplan import load_model_and_tokenizer
import chromadb
from pathlib import Path
from flask_cors import CORS
import re
import os
import json


#------------------------------------------------------------ChromaDB------------------------------------------------------------
# ChromaDB

#TODO: Create Embeddings Collection when App ist build!
#collection = init_collection()

client = chromadb.PersistentClient()
client.heartbeat()

FACH_ALIASES = {
    "Mathematik": ["mathematik", "mathe", "bruch", "brueche", "brüche", "bruchrechnen", "geometrie", "loesungsweg", "loesungswege", "strategie", "strategien", "modellieren", "begruenden", "begruendet"],
    "Deutsch": ["deutsch", "grammatik", "lesen", "schreiben"],
    "Französisch": ["französisch", "franzoesisch", "franzoesisch", "franz"],
    "Englisch": ["englisch", "english"],
    "Bewegung und Sport": ["sport", "bewegung", "schwimmen", "schwimmunterricht", "brustgleichschlag", "turnen"],
    "Räume, Zeiten, Gesellschaften (mit Geografie, Geschichte)": ["rzg", "geografie", "geschichte", "raum", "zeiten", "quellen", "positionen", "abwaegen", "abwaegen", "einordnen", "urteilen"],
    "Wirtschaft, Arbeit, Haushalt (mit Hauswirtschaft)": ["wah", "wirtschaft", "haushalt", "konsum", "nachhaltig", "nachhaltigem"],
    "Natur und Technik (mit Physik, Chemie, Biologie)": ["nt", "natur und technik", "physik", "chemie", "biologie"],
    "Musik": ["musik", "rhythmus", "klang", "instrument"],
}

QUERY_SYNONYMS = {
    "bruchrechnen": ["bruch", "brüche", "brueche", "nenner", "zähler", "zaehler", "bruchzahl"],
    "mathe": ["mathematik"],
    "unterrichtsidee": ["unterricht", "lernaufgabe", "sequenz", "projekt"],
    "gruppenarbeit": ["teamarbeit", "kooperativ", "partnerarbeit"],
    "bewerten": ["beurteilen", "einschaetzen", "einschätzen", "reflektieren"],
    "analysieren": ["untersuchen", "auswerten", "strukturieren"],
    "argumentieren": ["begruenden", "begründen", "diskutieren", "eroertern", "erörtern"],
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
    try:
        collection = client.get_collection(name="Lehrplan_Basel_Stadt3")
        collection_size = collection.count()
        print(collection_size)
        return collection
    except Exception as e:  # Revised exception handling
        print("Error:", e)
        collection = load_model_and_tokenizer()
        return collection


def normalize_text(value):
    if not value:
        return ""
    value = value.lower()
    value = value.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return value


def tokenize_query(query_text):
    normalized = normalize_text(query_text)
    raw_tokens = re.findall(r"\w+", normalized)
    expanded_tokens = set(raw_tokens)
    for token in raw_tokens:
        if token in QUERY_SYNONYMS:
            expanded_tokens.update(normalize_text(item) for item in QUERY_SYNONYMS[token])
    return sorted(
        [
            token
            for token in expanded_tokens
            if len(token) >= 4 and token not in STOPWORDS
        ]
    )


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


def build_query_variants(query_text, query_schlagwort):
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
    return deduplicated[:10]


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
    return deduplicated[:8]


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
    unique_tokens = query_tokens[:8]
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


def score_candidates(candidate_map, query_tokens, fach_signals, intent_signals, weights):
    scored_items = []
    token_count = max(len(query_tokens), 1)
    intent_count = max(len(intent_signals), 1)

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

        query_text_blob = normalize_text(item["document"])
        if intent_signals:
            matched_intents = sum(
                1 for intent, aliases in INTENT_HINTS.items()
                if intent in intent_signals and any(alias in query_text_blob for alias in aliases)
            )
            metadata_score += min(matched_intents / intent_count, 1.0) * 0.7

        if "__full_query__" in item["keyword_hits"]:
            keyword_score = min(keyword_score + 0.25, 1.0)

        final_score = (
            (weights["vector"] * vector_score)
            + (weights["keyword"] * keyword_score)
            + (weights["metadata"] * metadata_score)
            + (weights["variant"] * variant_score)
            + (weights["rrf"] * rrf_score)
        )
        item["final_score"] = final_score
        scored_items.append(item)

    scored_items.sort(key=lambda entry: entry["final_score"], reverse=True)
    return scored_items


def diversify_by_fach(scored_items, n_results):
    if n_results <= 0:
        return []

    selected = []
    fach_counts = {}

    for item in scored_items:
        if len(selected) >= n_results:
            break

        fach = item["metadata"].get("fach", "__unknown__")
        current_count = fach_counts.get(fach, 0)
        # Keep the first pass balanced: max 2 items per fach.
        if current_count >= 2:
            continue

        selected.append(item)
        fach_counts[fach] = current_count + 1

    if len(selected) >= n_results:
        return selected[:n_results]

    selected_ids = {item["id"] for item in selected}
    for item in scored_items:
        if len(selected) >= n_results:
            break
        if item["id"] in selected_ids:
            continue
        selected.append(item)

    return selected[:n_results]


def format_response(scored_items, n_results, query_profile):
    top_items = diversify_by_fach(scored_items, n_results)
    metadata_rows = []
    for item in top_items:
        competency_chain = lookup_competency_chain(item["id"])
        metadata_rows.append({
            **item["metadata"],
            "_score": round(item["final_score"], 5),
            "_match_sources": sorted(item["sources"]),
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

# --- Kompetenz-Aufbaukette (Vorgänger / aktuell / Nachfolger) -----------------

LEHRPLAN_JSON_PATH = Path(
    os.getenv("LEHRPLAN_JSON_PATH", str(Path(__file__).resolve().parent / "Lehrplan21.json"))
)
CHAIN_KEY_FIELDS = ("fb_id", "f_id", "kb_id", "ha_id", "k_id", "aufbau")

_chain_group_rows_cache = {}
_lehrplan_json_rows = None


def _normalize_uid(uid):
    if uid is None:
        return None
    text = str(uid).strip()
    return text if text else None


def _format_chain_item(item):
    if not item:
        return None
    return {
        "uid": item.get("uid"),
        "code": item.get("code"),
        "text": item.get("text"),
        "zyklus": item.get("zyklus"),
        "fach": item.get("fach"),
        "themenbereich": item.get("themenbereich"),
        "url": item.get("url"),
        "folge_in_aufbaute": item.get("folge_in_aufbaute"),
    }


def _load_lehrplan_rows():
    """Rohe Zeilen aus Lehrplan21.json (optional Cache für Fallback)."""
    global _lehrplan_json_rows
    if _lehrplan_json_rows is not None:
        return _lehrplan_json_rows

    if not LEHRPLAN_JSON_PATH.is_file():
        _lehrplan_json_rows = []
        return _lehrplan_json_rows

    with open(LEHRPLAN_JSON_PATH, encoding="utf-8") as json_file:
        _lehrplan_json_rows = json.load(json_file)

    return _lehrplan_json_rows


def _dedupe_chain_rows(rows):
    """Lehrplan-Daten haben dieselbe uid mehrfach (Varianten); für die Kette nur erste Zeile pro uid."""
    rows.sort(
        key=lambda row: (
            int(str(row.get("folge_in_aufbaute") or "0")),
            str(row.get("uid") or ""),
        )
    )
    deduped = []
    seen_uid = set()
    for row in rows:
        uid_key = _normalize_uid(row.get("uid"))
        if not uid_key or uid_key in seen_uid:
            continue
        seen_uid.add(uid_key)
        deduped.append(row)
    return deduped


def _deduped_group_rows_for_key(group_key):
    """Sortierte, nach uid deduplizierte Zeilen einer Aufbau-Gruppe (mit Cache pro Gruppe)."""
    global _chain_group_rows_cache
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


def lookup_competency_chain(uid):
    """Vorgänger, aktuelle Stufe, Nachfolger und volle Kette (für Navigation ohne zweiten Request)."""
    normalized = _normalize_uid(uid)
    if not normalized:
        return None

    json_data = _load_lehrplan_rows()
    if not json_data:
        return None

    target_row = None
    for row in json_data:
        if row.get("strukturtyp") != "Kompetenzstufe":
            continue
        if _normalize_uid(row.get("uid")) == normalized:
            target_row = row
            break

    if not target_row:
        return None

    group_key = tuple(str(target_row.get(k, "") or "") for k in CHAIN_KEY_FIELDS)
    rows = _deduped_group_rows_for_key(group_key)
    if not rows:
        return None

    index_map = {_normalize_uid(r.get("uid")): i for i, r in enumerate(rows)}
    pos = index_map.get(normalized)
    if pos is None:
        return None

    full_formatted = [_format_chain_item(r) for r in rows]
    return {
        "previous": full_formatted[pos - 1] if pos > 0 else None,
        "current": full_formatted[pos],
        "next": full_formatted[pos + 1] if pos < len(full_formatted) - 1 else None,
        "full_chain": full_formatted,
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
def competency_chain(uid):
    payload = lookup_competency_chain(uid)
    if payload is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(payload)


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
    query_tokens = tokenize_query(f"{query_text} {query_schlagwort}".strip())
    fach_signals = detect_fach_signals(query_text)
    intent_signals = detect_intent_signals(query_text)
    query_profile = classify_query_profile(query_text, query_tokens, intent_signals)
    weights = get_score_weights(query_profile)
    n_results = resolve_n_results(requested_n_results, query_profile)
    query_variants = build_query_variants(query_text, query_schlagwort)
    semantic_variants = build_semantic_variants(query_text, fach_signals, intent_signals)

    candidate_map = {}
    vector_limit = max(40, n_results * 4)
    keyword_limit = max(10, n_results * 2)

    for variant in query_variants:
        vector_results = vector_retrieve(collection, variant, where_clause, limit=vector_limit)
        upsert_candidate(
            candidate_map,
            vector_results.get("ids", [[]])[0],
            vector_results.get("documents", [[]])[0],
            vector_results.get("metadatas", [[]])[0],
            vector_results.get("distances", [[]])[0],
            "vector",
            variant=variant,
            source_weight=1.0,
        )
        keyword_retrieve_and_upsert(
            collection,
            variant,
            tokenize_query(variant),
            where_clause,
            per_token_limit=keyword_limit,
            candidate_map=candidate_map,
            variant=variant,
        )

    for semantic_variant in semantic_variants:
        semantic_vector_results = vector_retrieve(collection, semantic_variant, where_clause, limit=max(25, n_results * 3))
        upsert_candidate(
            candidate_map,
            semantic_vector_results.get("ids", [[]])[0],
            semantic_vector_results.get("documents", [[]])[0],
            semantic_vector_results.get("metadatas", [[]])[0],
            semantic_vector_results.get("distances", [[]])[0],
            "semantic_vector",
            variant=semantic_variant,
            source_weight=weights["semantic_weight"],
        )

    scored_items = score_candidates(candidate_map, query_tokens, fach_signals, intent_signals, weights)
    response = format_response(scored_items, n_results, query_profile)
    response["meta"] = {"n_results_used": n_results, "query_profile": query_profile}
    return jsonify(response)


@app.route('/<path:path>')
def static_proxy(path):
    # send_static_file verwendet static_folder
    return send_from_directory(str(FRONTEND_DIR), path)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
#------------------------------------------------------------End------------------------------------------------------------