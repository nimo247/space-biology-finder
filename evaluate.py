import hashlib
import json
from pathlib import Path
from time import perf_counter

from evidence_search import evidence_search
from semantic_search import SemanticSearch


CASES = [
    {
        "id": "mouse_liver",
        "query": "How does spaceflight affect mouse liver?",
        "relevant": ["OSD-137", "OSD-209"],
        "exclude": ["OSD-915", "OSD-250"],
    },
    {
        "id": "mouse_liver_gene_expression",
        "query": "Find gene expression datasets from mice liver",
        "relevant": ["OSD-137"],
        "exclude": ["OSD-209", "OSD-915"],
    },
    {
        "id": "post_return_gene_activity",
        "query": "What happens to gene activity after returning to Earth?",
        "relevant": ["OSD-613", "OSD-915"],
        "exclude": ["OSD-175", "OSD-37", "OSD-147"],
    },
    {
        "id": "post_return_mouse_lung",
        "query": (
            "Find mouse lung gene expression datasets "
            "after returning to Earth"
        ),
        "relevant": ["OSD-915"],
        "exclude": ["OSD-137", "OSD-209"],
    },
    {
        "id": "post_return_mouse_thymus",
        "query": (
            "Find mouse thymus gene expression datasets "
            "after returning to Earth"
        ),
        "relevant": ["OSD-515"],
        "exclude": ["OSD-915", "OSD-137"],
    },
    {
        "id": "post_return_mouse_quadriceps",
        "query": (
            "Find RNA-seq datasets from mouse right quadriceps "
            "femoris after returning to Earth"
        ),
        "relevant": ["OSD-666"],
        "exclude": ["OSD-515", "OSD-915"],
    },
    {
        "id": "soleus_recovery",
        "query": "Find RNA-seq studies of recovery in mouse soleus",
        "relevant": ["OSD-295"],
        "exclude": ["OSD-137", "OSD-209"],
    },
    {
        "id": "arabidopsis_seedlings",
        "query": (
            "Find gene expression datasets from "
            "Arabidopsis seedlings in space"
        ),
        "relevant": ["OSD-37", "OSD-321"],
        "exclude": ["OSD-16", "OSD-137"],
    },
    {
        "id": "human_parabolic_flight",
        "query": (
            "Find human U937 gene expression datasets "
            "from parabolic flight"
        ),
        "relevant": ["OSD-283"],
        "exclude": ["OSD-137", "OSD-915"],
    },
    {
        "id": "human_alpha_radiation",
        "query": (
            "Find human gene expression datasets "
            "about alpha particle radiation"
        ),
        "relevant": ["OSD-175"],
        "exclude": ["OSD-137", "OSD-915"],
    },
    {
        "id": "post_return_liver_proteomics",
        "query": (
            "Find mouse liver proteomics datasets "
            "after returning to Earth"
        ),
        "relevant": ["OSD-209"],
        "exclude": ["OSD-915"],
    },
    {
        "id": "empty_question",
        "query": "   ",
        "expected_error": "Enter a research question",
    },
    {
        "id": "unsupported_negation",
        "query": "Find mouse datasets excluding liver",
        "expected_error": "Negated requirements",
    },
    {
        "id": "multiple_organisms",
        "query": "Find human and mouse liver datasets",
        "expected_error": "Multiple organism",
    },
    {
        "id": "multiple_tissues",
        "query": "Find mouse liver and lung datasets",
        "expected_error": "Multiple tissue",
    },
]


def main():
    catalog_path = Path("data/processed/catalog.json")
    catalog_bytes = catalog_path.read_bytes()
    catalog = json.loads(catalog_bytes)
    available_ids = {record["accession"] for record in catalog}

    # Ensure the reviewed positive examples exist in this snapshot.
    required_ids = {
        accession
        for case in CASES
        for accession in case.get("relevant", [])
    }
    missing_ids = sorted(required_ids - available_ids)

    if missing_ids:
        raise SystemExit(
            "These evaluation studies are missing from the catalog: "
            + ", ".join(missing_ids)
        )

    print("Loading the model once for all evaluation questions...")
    engine = SemanticSearch()

    rows = []

    for case in CASES:
        started = perf_counter()

        row = {
            "id": case["id"],
            "query": case["query"],
            "kind": (
                "input_handling"
                if "expected_error" in case
                else "retrieval"
            ),
        }

        try:
            output = evidence_search(
                case["query"],
                top_k=5,
                engine=engine,
            )

            returned_ids = [
                result["record"]["accession"]
                for result in output["results"]
            ]

            row["returned_ids"] = returned_ids
            row["effective_filters"] = output["filters"]
            row["requirements"] = output["requirements"]

            if "expected_error" in case:
                row["passed"] = False
                row["reason"] = (
                    "Expected a clarification/error, but search completed."
                )

            else:
                relevant = set(case["relevant"])
                forbidden = set(case.get("exclude", []))

                positive_ranks = [
                    rank
                    for rank, accession in enumerate(
                        returned_ids,
                        start=1,
                    )
                    if accession in relevant
                ]

                incompatible = sorted(
                    set(returned_ids) & forbidden
                )

                row["reviewed_relevant_ids"] = case["relevant"]
                row["reviewed_incompatible_ids"] = case.get(
                    "exclude", []
                )
                row["known_positive_hit_at_5"] = bool(positive_ranks)
                row["known_positive_reciprocal_rank_at_5"] = (
                    1.0 / positive_ranks[0]
                    if positive_ranks
                    else 0.0
                )
                row["returned_incompatible_ids"] = incompatible
                row["passed"] = (
                    bool(positive_ranks)
                    and not incompatible
                )

                reasons = []

                if not positive_ranks:
                    reasons.append(
                        "No reviewed positive appeared in the top five."
                    )

                if incompatible:
                    reasons.append(
                        "Returned incompatible studies: "
                        + ", ".join(incompatible)
                    )

                row["reason"] = (
                    " ".join(reasons)
                    if reasons
                    else "Reviewed-positive and exclusion checks passed."
                )

        except ValueError as error:
            message = str(error)
            expected = case.get("expected_error")

            row["returned_ids"] = []
            row["error"] = message
            row["passed"] = (
                expected is not None
                and expected.casefold() in message.casefold()
            )
            row["reason"] = (
                "Expected clarification/error received."
                if row["passed"]
                else f"Unexpected error: {message}"
            )

        except Exception as error:
            row["returned_ids"] = []
            row["passed"] = False
            row["reason"] = (
                f"Unexpected {type(error).__name__}: {error}"
            )

        row["seconds"] = round(
            perf_counter() - started,
            3,
        )
        rows.append(row)

        status = "PASS" if row["passed"] else "FAIL"

        print(f"\n{status} | {row['id']}")
        print("Results:", ", ".join(row["returned_ids"]) or "(none)")
        print(row["reason"])

    retrieval_rows = [
        row for row in rows
        if row["kind"] == "retrieval"
    ]
    handling_rows = [
        row for row in rows
        if row["kind"] == "input_handling"
    ]

    hits = sum(
        row.get("known_positive_hit_at_5", False)
        for row in retrieval_rows
    )
    mean_reciprocal_rank = sum(
        row.get("known_positive_reciprocal_rank_at_5", 0.0)
        for row in retrieval_rows
    ) / len(retrieval_rows)

    summary = {
        "development_checks_passed": sum(
            row["passed"] for row in rows
        ),
        "development_checks_total": len(rows),
        "retrieval_questions": len(retrieval_rows),
        "known_positive_hits_at_5": hits,
        "known_positive_hit_rate_at_5": (
            hits / len(retrieval_rows)
        ),
        "known_positive_mrr_at_5": mean_reciprocal_rank,
        "input_handling_checks_passed": sum(
            row["passed"] for row in handling_rows
        ),
        "input_handling_checks_total": len(handling_rows),
    }

    report = {
        "evaluation_type": "development",
        "catalog_sha256": hashlib.sha256(
            catalog_bytes
        ).hexdigest(),
        "catalog_studies": len(catalog),
        "limitations": [
            "Questions use studies already reviewed during development.",
            "Positive relevance judgments are incomplete.",
            "Unjudged results are not automatically considered irrelevant.",
            "These checks do not establish general search accuracy.",
            "Study-level evidence does not verify sample-to-assay linkage.",
        ],
        "summary": summary,
        "cases": rows,
    }

    output_path = Path("evaluation/development_results.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nDEVELOPMENT EVALUATION SUMMARY")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved report to {output_path}")


if __name__ == "__main__":
    main()