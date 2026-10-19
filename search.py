import argparse
import json
import re
from pathlib import Path

from rank_bm25 import BM25Okapi


STOPWORDS = set("""
a an the and or of in on for to from with
find show me datasets dataset studies study
please about how does do is are
""".split())

TISSUE_FIELDS = {"material type", "tissue", "tissue type"}


def normalize(value):
    return " ".join(str(value or "").casefold().split())


def tokenize(text):
    return [
        token
        for token in re.findall(r"[a-z0-9]+", text.casefold())
        if token not in STOPWORDS
    ]


def sample_matches(sample, organism=None, tissue=None):
    attributes = sample.get("characteristics", [])

    def has_value(fields, wanted):
        return any(
            normalize(item.get("field")) in fields
            and normalize(item.get("value")) == normalize(wanted)
            for item in attributes
        )

    if organism and not has_value({"organism"}, organism):
        return False

    if tissue and not has_value(TISSUE_FIELDS, tissue):
        return False

    return True


def search(query, organism=None, tissue=None, top_k=5):
    records = json.loads(
        Path("data/processed/catalog.json").read_text(
            encoding="utf-8"
        )
    )

    if not records:
        raise ValueError("The catalog is empty.")

    query_tokens = list(dict.fromkeys(tokenize(query)))

    if not query_tokens:
        raise ValueError("Enter at least one searchable keyword.")

    corpus = [tokenize(record["search_text"]) for record in records]
    index = BM25Okapi(corpus)
    scores = index.get_scores(query_tokens)

    results = []

    for position in sorted(
        range(len(records)),
        key=lambda i: (-float(scores[i]), records[i]["accession"]),
    ):
        record = records[position]
        matched_terms = sorted(
            set(query_tokens).intersection(corpus[position])
        )

        # Do not return documents with no keyword overlap.
        if not matched_terms:
            continue

        matched_samples = []

        if organism or tissue:
            matched_samples = [
                sample
                for sample in record.get("samples", [])
                if sample_matches(sample, organism, tissue)
            ]

            # Both filters must match within one sample.
            if not matched_samples:
                continue

        results.append({
            "record": record,
            "score": float(scores[position]),
            "matched_terms": matched_terms,
            "matched_samples": matched_samples,
        })

        if len(results) >= top_k:
            break

    return results


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
        results = search(
            args.query,
            organism=args.organism,
            tissue=args.tissue,
            top_k=args.top_k,
        )
    except ValueError as error:
        parser.error(str(error))

    if not results:
        print("No keyword matches satisfy your filters in this catalog.")
        return

    for rank, result in enumerate(results, start=1):
        record = result["record"]

        print(f"\n{rank}. {record['accession']} | {record['title']}")
        print(f"BM25 score: {result['score']:.3f}")
        print("Matched keywords:", ", ".join(result["matched_terms"]))
        print("Organisms:", ", ".join(record["organisms"]) or "Unknown")
        print("Tissues:", ", ".join(record["tissues"]) or "Unknown")

        if args.organism or args.tissue:
            print(
                "Samples satisfying all filters:",
                len(result["matched_samples"]),
            )

            for sample in result["matched_samples"][:2]:
                evidence = [
                    f"{item['field']}={item['value']}"
                    for item in sample["characteristics"]
                    if normalize(item.get("field"))
                    in TISSUE_FIELDS | {"organism"}
                ]
                print(f"  {sample['name']}: {'; '.join(evidence)}")

        print("Description:", record["description"][:350])
        print("NASA metadata:", record["metadata_url"])


if __name__ == "__main__":
    main()