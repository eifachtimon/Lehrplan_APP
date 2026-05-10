import json
from pathlib import Path
import sys
import urllib.request

SEARCH_URL = "http://127.0.0.1:5001/search"

EVAL_FILE = Path(__file__).resolve().parent / "eval_queries.json"
TARGETS = {
    "top1_min": 0.95,
    "top3_min": 0.98,
    "diversity10_min": 0.60,
}


def load_eval_queries():
    with EVAL_FILE.open("r", encoding="utf-8") as file_handle:
        payload = json.load(file_handle)
    return payload if isinstance(payload, list) else []


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
    eval_queries = load_eval_queries()
    if not eval_queries:
        print("No evaluation queries found in eval_queries.json")
        return

    top1_hits = 0
    top3_hits = 0
    score_payload_hits = 0
    diversity_sum = 0.0
    diversity_top10_sum = 0.0

    print("Hybrid Retrieval Evaluation (next level)")
    print("=" * 80)

    for idx, test_case in enumerate(eval_queries, start=1):
        results = run_query(test_case["query"])
        fach_ranking = [item.get("fach", "N/A") for item in results]
        expected_fach = test_case["expected_fach"]
        if results and "_score" in results[0]:
            score_payload_hits += 1

        top1_match = len(fach_ranking) > 0 and fach_ranking[0] == expected_fach
        top3_match = expected_fach in fach_ranking[:3]
        unique_fach_top5 = len(set(fach_ranking[:5])) if fach_ranking else 0
        unique_fach_top10 = len(set(fach_ranking[:10])) if fach_ranking else 0
        diversity_at_5 = unique_fach_top5 / max(min(5, len(fach_ranking)), 1)
        diversity_at_10 = unique_fach_top10 / max(min(10, len(fach_ranking)), 1)

        if top1_match:
            top1_hits += 1
        if top3_match:
            top3_hits += 1
        diversity_sum += diversity_at_5
        diversity_top10_sum += diversity_at_10

        print(f"[{idx}] Query: {test_case['query']}")
        print(f"    Expected fach: {expected_fach}")
        print(f"    Top 5 fach: {fach_ranking[:5]}")
        print(f"    Diversity@5: {diversity_at_5:.2f} ({unique_fach_top5} unique)")
        print(f"    Diversity@10: {diversity_at_10:.2f} ({unique_fach_top10} unique)")
        if results:
            print(
                "    Top result diagnostics: "
                f"score={results[0].get('_score')} "
                f"sources={results[0].get('_match_sources')} "
                f"variant_hits={results[0].get('_query_variant_hits')}"
            )
        print(f"    Top1 hit: {top1_match}, Top3 hit: {top3_match}")

    total = len(eval_queries)
    top1_score = top1_hits / total
    top3_score = top3_hits / total
    avg_diversity_5 = diversity_sum / total
    avg_diversity_10 = diversity_top10_sum / total

    print("=" * 80)
    print(f"Top-1 fach accuracy: {top1_score:.2%}")
    print(f"Top-3 fach accuracy: {top3_score:.2%}")
    print(f"Average Diversity@5: {avg_diversity_5:.2%}")
    print(f"Average Diversity@10: {avg_diversity_10:.2%}")
    print(f"Score payload coverage: {score_payload_hits}/{total}")

    checks = [
        ("Top-1 fach accuracy", top1_score, TARGETS["top1_min"]),
        ("Top-3 fach accuracy", top3_score, TARGETS["top3_min"]),
        ("Average Diversity@10", avg_diversity_10, TARGETS["diversity10_min"]),
    ]
    failing_checks = [item for item in checks if item[1] < item[2]]

    print("-" * 80)
    for label, value, target in checks:
        status = "PASS" if value >= target else "FAIL"
        print(f"{status} | {label}: {value:.2%} (target >= {target:.2%})")

    if failing_checks:
        print("Quality gate failed.")
        sys.exit(1)

    print("Quality gate passed.")

    if top3_score < 0.80:
        print("Decision: Add a cross-encoder reranker (top-30 candidates).")
    else:
        print("Decision: Keep current hybrid setup and tune weights incrementally.")


if __name__ == "__main__":
    main()