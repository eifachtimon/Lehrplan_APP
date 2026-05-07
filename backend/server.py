# app.py
#------------------------------------------------------------Imports------------------------------------------------------------
from flask import Flask, jsonify, request, send_from_directory
from chroma_lehrplan import load_model_and_tokenizer
import chromadb
from pathlib import Path
from flask_cors import CORS
import re


#------------------------------------------------------------ChromaDB------------------------------------------------------------
# ChromaDB

#TODO: Create Embeddings Collection when App ist build!
#collection = init_collection()

client = chromadb.PersistentClient()
client.heartbeat()

FACH_ALIASES = {
    "Mathematik": ["mathematik", "mathe", "bruch", "brueche", "brüche", "bruchrechnen", "geometrie"],
    "Deutsch": ["deutsch", "grammatik", "lesen", "schreiben"],
    "Französisch": ["französisch", "franzoesisch", "franzoesisch", "franz"],
    "Englisch": ["englisch", "english"],
    "Bewegung und Sport": ["sport", "bewegung", "schwimmen", "turnen"],
}

QUERY_SYNONYMS = {
    "bruchrechnen": ["bruch", "brüche", "brueche", "nenner", "zähler", "zaehler", "bruchzahl"],
    "mathe": ["mathematik"],
    "unterrichtsidee": ["unterricht", "lernaufgabe", "sequenz", "projekt"],
}

STOPWORDS = {
    "ich", "plane", "eine", "einen", "einer", "zu", "mit", "und", "oder", "fuer", "für",
    "das", "der", "die", "den", "dem", "des", "im", "in", "an", "auf", "von", "am",
    "stunde", "unterricht", "gruppenarbeit",
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


def upsert_candidate(candidate_map, ids, documents, metadatas, distances, source, token=None):
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
            },
        )

        if distances and idx < len(distances) and distances[idx] is not None:
            distance = distances[idx]
            if entry["best_distance"] is None or distance < entry["best_distance"]:
                entry["best_distance"] = distance

        if source == "keyword" and token:
            entry["keyword_hits"].add(token)

        entry["sources"].add(source)


def vector_retrieve(collection, query_text, where_clause, limit):
    query_kwargs = {"query_texts": [query_text], "n_results": limit}
    if where_clause:
        query_kwargs["where"] = where_clause
    return collection.query(**query_kwargs)


def keyword_retrieve(collection, query_text, query_tokens, where_clause, per_token_limit):
    keyword_results = []
    unique_tokens = query_tokens[:8]

    full_query_kwargs = {
        "query_texts": [query_text],
        "where_document": {"$contains": query_text},
        "n_results": per_token_limit,
    }
    if where_clause:
        full_query_kwargs["where"] = where_clause
    keyword_results.append(("__full_query__", collection.query(**full_query_kwargs)))

    for token in unique_tokens:
        query_kwargs = {
            "query_texts": [query_text],
            "where_document": {"$contains": token},
            "n_results": per_token_limit,
        }
        if where_clause:
            query_kwargs["where"] = where_clause
        keyword_results.append((token, collection.query(**query_kwargs)))

    return keyword_results


def merge_and_score(vector_results, keyword_results, query_tokens, fach_signals):
    candidate_map = {}

    vector_ids = vector_results.get("ids", [[]])[0]
    vector_documents = vector_results.get("documents", [[]])[0]
    vector_metadatas = vector_results.get("metadatas", [[]])[0]
    vector_distances = vector_results.get("distances", [[]])[0]
    upsert_candidate(candidate_map, vector_ids, vector_documents, vector_metadatas, vector_distances, "vector")

    for token, result in keyword_results:
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        upsert_candidate(candidate_map, ids, documents, metadatas, distances, "keyword", token=token)

    scored_items = []
    token_count = max(len(query_tokens), 1)

    for item in candidate_map.values():
        distance = item["best_distance"] if item["best_distance"] is not None else 2.5
        vector_score = 1.0 / (1.0 + max(distance, 0.0))
        keyword_score = min(len(item["keyword_hits"]) / token_count, 1.0)

        metadata_score = 0.0
        fach = item["metadata"].get("fach")
        if fach_signals and fach in fach_signals:
            metadata_score += 1.0

        if "__full_query__" in item["keyword_hits"]:
            keyword_score = min(keyword_score + 0.25, 1.0)

        final_score = (0.45 * vector_score) + (0.25 * keyword_score) + (0.30 * metadata_score)
        item["final_score"] = final_score
        scored_items.append(item)

    scored_items.sort(key=lambda entry: entry["final_score"], reverse=True)
    return scored_items


def format_response(scored_items, n_results):
    top_items = scored_items[:n_results]
    return {
        "documents": [[item["document"] for item in top_items]],
        "metadatas": [[item["metadata"] for item in top_items]],
        "ids": [[item["id"] for item in top_items]],
        "distances": [[item["best_distance"] if item["best_distance"] is not None else 1.0 for item in top_items]],
    }

#------------------------------------------------------------App------------------------------------------------------------

#App
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public"
app = Flask(__name__, static_folder=str(FRONTEND_DIR))
CORS(app)
    
@app.route('/')
def serve_index():
    #return "main"
    print('homepage')
    return send_from_directory(str(FRONTEND_DIR), 'index.html')

@app.route('/<path:path>')
def static_proxy(path):
    # send_static_file verwendet static_folder
    return send_from_directory(str(FRONTEND_DIR), path)




@app.route('/search', methods=['POST'])
def search():
    collection = init_collection()

    data = request.json or {}
    query_text = (data.get('query_texts') or '').strip()
    query_schlagwort = (data.get('querySchlagwort') or '').strip()
    n_results = data.get('n_results') or 10
    filters = data.get('filters', {})

    if not query_text:
        return jsonify({"documents": [[]], "metadatas": [[]], "ids": [[]], "distances": [[]]})

    where_clause = build_where_clause(filters)
    query_tokens = tokenize_query(query_text)
    fach_signals = detect_fach_signals(query_text)

    vector_results = vector_retrieve(collection, query_text, where_clause, limit=max(40, n_results * 4))
    keyword_seed = f"{query_text} {query_schlagwort}".strip() if query_schlagwort else query_text
    keyword_results = keyword_retrieve(
        collection,
        keyword_seed,
        query_tokens,
        where_clause,
        per_token_limit=max(10, n_results * 2),
    )

    scored_items = merge_and_score(vector_results, keyword_results, query_tokens, fach_signals)
    response = format_response(scored_items, n_results)
    return jsonify(response)


if __name__ == '__main__':
    app.run(debug=True)
#------------------------------------------------------------End------------------------------------------------------------