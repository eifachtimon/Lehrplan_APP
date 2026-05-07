import json
import urllib.request

SEARCH_URL = "http://127.0.0.1:5000/search"

EVAL_QUERIES = [
    {"query": "Mathematik Bruchrechnen", "expected_fach": "Mathematik"},
    {"query": "Ich plane eine Mathe Stunde zu Bruchrechnen mit Gruppenarbeit", "expected_fach": "Mathematik"},
    {"query": "Idee fuer Schwimmunterricht Brustgleichschlag", "expected_fach": "Bewegung und Sport"},
    {"query": "Unterrichtsidee zu französischer Aussprache", "expected_fach": "Französisch"},
    {"query": "Lernsequenz zum Koerperausdruck zu Musik", "expected_fach": "Musik"},
]


def run_query(query_text):
    payload = {
        "query_texts": query_text,
        "querySchlagwort": "",
        "n_results": 10,
        "filters": {"fach": [], "zyklus": []},
    }
    request = urllib.request.Request(
        SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    return body.get("metadatas", [[]])[0]


def main():
    top1_hits = 0
    top3_hits = 0

    print("Hybrid Retrieval Evaluation")
    print("=" * 80)

    for idx, test_case in enumerate(EVAL_QUERIES, start=1):
        results = run_query(test_case["query"])
        fach_ranking = [item.get("fach", "N/A") for item in results]
        expected_fach = test_case["expected_fach"]

        top1_match = len(fach_ranking) > 0 and fach_ranking[0] == expected_fach
        top3_match = expected_fach in fach_ranking[:3]

        if top1_match:
            top1_hits += 1
        if top3_match:
            top3_hits += 1

        print(f"[{idx}] Query: {test_case['query']}")
        print(f"    Expected fach: {expected_fach}")
        print(f"    Top 5 fach: {fach_ranking[:5]}")
        print(f"    Top1 hit: {top1_match}, Top3 hit: {top3_match}")

    total = len(EVAL_QUERIES)
    top1_score = top1_hits / total
    top3_score = top3_hits / total

    print("=" * 80)
    print(f"Top-1 fach accuracy: {top1_score:.2%}")
    print(f"Top-3 fach accuracy: {top3_score:.2%}")

    if top3_score < 0.80:
        print("Decision: Add a cross-encoder reranker (top-30 candidates).")
    else:
        print("Decision: Keep current hybrid setup and tune weights incrementally.")


if __name__ == "__main__":
    main()