import argparse
import json
from pathlib import Path

from search import search as keyword_search
from semantic_search import SemanticSearch


def hybrid_search(
    query,
    organism=None,
    tissue=None,
    top_k=5,
    engine=None,
):
    if not query.strip():
        raise ValueError("Enter a question.")

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    catalog = json.loads(
        Path("data/processed/catalog.json").read_text(
            encoding="utf-8"
        )
    )
    candidate_count = len(catalog)

    if not candidate_count:
        raise ValueError("The catalog is empty.")

    keyword_results = keyword_search(
        query,
        organism=organism,
        tissue=tissue,
        top_k=candidate_count,
    )

    if engine is None:
        engine = SemanticSearch()

    semantic_results = engine.search(
        query,
        organism=organism,
        tissue=tissue,
        top_k=candidate_count,
    )

    combined = {}

    for method, results in (
        ("keyword", keyword_results),
        ("semantic", semantic_results),
    ):
        for rank, result in enumerate(results, start=1):
            record = result["record"]
            accession = record["accession"]

            if accession not in combined:
                combined[accession] = {
                    "record": record,
                    "rrf_score": 0.0,
                    "keyword_rank": None,
                    "semantic_rank": None,
                    "matched_terms": [],
                    "passage": "",
                    "matched_samples": result["matched_samples"],
                }

            item = combined[accession]
            item["rrf_score"] += 1.0 / (60 + rank)
            item[f"{method}_rank"] = rank

            if method == "keyword":
                item["matched_terms"] = result["matched_terms"]
            else:
                item["passage"] = result["passage"]

    return sorted(
        combined.values(),
        key=lambda item: (
            -item["rrf_score"],
            item["record"]["accession"],
        ),
    )[:top_k]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--organism")
    parser.add_argument("--tissue")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    if args.top_k < 1:
        parser.error("--top-k must be at least 1")

    try:
        results = hybrid_search(
            args.query,
            organism=args.organism,
            tissue=args.tissue,
            top_k=args.top_k,
        )
    except ValueError as error:
        parser.error(str(error))

    if not results:
        print("No candidates satisfy your filters in this catalog.")
        return

    print("\nHybrid candidates — check each requirement against metadata.")

    for rank, result in enumerate(results, start=1):
        record = result["record"]

        print(f"\n{rank}. {record['accession']} | {record['title']}")
        print(
            f"Keyword rank: {result['keyword_rank']} | "
            f"Semantic rank: {result['semantic_rank']}"
        )
        print("Matched keywords:", ", ".join(result["matched_terms"]))
        print("Organisms:", ", ".join(record["organisms"]) or "Unknown")
        print("Tissues:", ", ".join(record["tissues"]) or "Unknown")

        if args.organism or args.tissue:
            print(
                "Samples satisfying all filters:",
                len(result["matched_samples"]),
            )

        print("Best semantic passage:")
        print(result["passage"])
        print("NASA metadata:", record["metadata_url"])


if __name__ == "__main__":
    main()