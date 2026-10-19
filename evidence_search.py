import argparse
import json
import re
from pathlib import Path

from hybrid_search import hybrid_search
from query_filters import resolve_filters


def excerpt(text, start, end):
    left = max(0, start - 80)
    right = min(len(text), end + 160)

    while left > 0 and not text[left - 1].isspace():
        left -= 1

    while right < len(text) and not text[right].isspace():
        right += 1

    passage = text[left:right].strip()

    if left > 0:
        passage = "… " + passage
    if right < len(text):
        passage += " …"

    return passage


def recovery_after_flight_evidence(text):
    # Require an explicit statement of actual flight exposure.
    # "30 days of simulated spaceflight" does not match this pattern.
    flight_exposure = re.compile(
        r"\b(?:experienced|completed|spent)\s+"
        r"(?:(?:about|approximately|over|nearly)\s+)?"
        r"\d+(?:\.\d+)?\s*[- ]?\s*"
        r"(?:days?|weeks?|months?)\s+"
        r"(?:of\s+)?"
        r"(?:space[- ]?flights?|in\s+space)\b",
        flags=re.IGNORECASE,
    )

    # Require recovery/re-adaptation explicitly AFTER flight or return.
    recovery = re.compile(
        r"\b(?:re[-\s]?adapt\w*|recovery)\b"
        r"[^.!?]{0,100}?\bafter\b"
        r"[^.!?]{0,60}?\b"
        r"(?:space[- ]?flights?|landing"
        r"|return(?:ing)?\s+to\s+earth)\b",
        flags=re.IGNORECASE,
    )

    preserved_on_orbit = re.compile(
        r"\b(?:fixed|preserved|frozen)\b"
        r"[^.!?]{0,60}?"
        r"\b(?:on[- ]orbit|in\s+orbit)\b",
        flags=re.IGNORECASE,
    )

    for flight in flight_exposure.finditer(text):
        # Recovery evidence must follow the exposure statement.
        for match in recovery.finditer(text, flight.end()):
            context = text[flight.start():match.end()]

            # Returned, preserved material does not demonstrate
            # biological recovery after return.
            if preserved_on_orbit.search(context):
                continue

            return excerpt(
                text,
                match.start(),
                match.end(),
            )

    return None


def post_return_evidence(record):
    text = record.get("description", "") or ""

    # Explicit before-return and after-return comparison.
    comparison = re.search(
        r"\bone\s+before\s+returning\s+to\s+earth"
        r".{0,120}?\bone\s+after\b",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if comparison:
        return excerpt(
            text,
            comparison.start(),
            comparison.end(),
        )

    # Live return followed by recovery or tissue collection.
    live_return = re.compile(
        r"\breturned\s+(?:"
        r"(?:live|alive)\s+to\s+earth"
        r"|to\s+earth\s+(?:live|alive))\b",
        flags=re.IGNORECASE,
    )

    for match in live_return.finditer(text):
        following = text[match.end():match.end() + 1500]

        endpoint = re.search(
            r"\b(?:recover\w*|sacrific\w*|euthan\w*"
            r"|tissue\s+collection)\b",
            following,
            flags=re.IGNORECASE,
        )

        if endpoint:
            end = match.end() + endpoint.end()
            return excerpt(text, match.start(), end)

    # Recovery/re-adaptation following documented flight exposure.
    return recovery_after_flight_evidence(text)


def gene_expression_evidence(record):
    evidence = []

    for assay in record.get("assays", []):
        measurement = assay.get("measurement", "") or ""
        technology = assay.get("technology", "") or ""
        combined = f"{measurement} {technology}"

        if re.search(
            r"transcription|transcriptom|gene expression"
            r"|\brna\b|microarray",
            combined,
            flags=re.IGNORECASE,
        ):
            evidence.append(f"{measurement} | {technology}")

    return list(dict.fromkeys(evidence))


def infer_requirements(query):
    if re.search(
        r"\b(?:not|without|exclude|excluding|except)\b",
        query,
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "Negated requirements are not supported yet. "
            "Use a positively worded question."
        )

    return {
        "post_return": bool(re.search(
            r"\b(?:after|following)\b.{0,40}\b"
            r"(?:return\w*|landing)\b"
            r"|\bpost[- ]?(?:flight|landing)\b",
            query,
            flags=re.IGNORECASE,
        )),
        "gene_expression": bool(re.search(
            r"\bgene\s+(?:activity|expression)\b"
            r"|\btranscriptom\w*\b"
            r"|\brna[- ]?seq\w*\b",
            query,
            flags=re.IGNORECASE,
        )),
    }


def evidence_search(
    query,
    organism=None,
    tissue=None,
    top_k=5,
    engine=None,
    require_post_return=False,
    require_gene_expression=False,
):
    query = query.strip()

    if not query:
        raise ValueError("Enter a research question.")

    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    requirements = infer_requirements(query)
    requirements["post_return"] |= require_post_return
    requirements["gene_expression"] |= require_gene_expression

    catalog = json.loads(
        Path("data/processed/catalog.json").read_text(
            encoding="utf-8"
        )
    )

    if not catalog:
        raise ValueError("The dataset catalog is empty.")

    effective_filters = resolve_filters(
        query,
        catalog,
        organism=organism,
        tissue=tissue,
    )

    candidates = hybrid_search(
        query,
        organism=effective_filters["organism"],
        tissue=effective_filters["tissue"],
        top_k=len(catalog),
        engine=engine,
    )

    supported = []
    unestablished = []

    for candidate in candidates:
        record = candidate["record"]
        checks = {}

        if requirements["post_return"]:
            checks["post_return"] = post_return_evidence(record)

        if requirements["gene_expression"]:
            checks["gene_expression"] = gene_expression_evidence(record)

        candidate["evidence_checks"] = checks

        if all(bool(value) for value in checks.values()):
            supported.append(candidate)
        else:
            unestablished.append(candidate)

    return {
        "requirements": requirements,
        "filters": effective_filters,
        "results": supported[:top_k],
        "unestablished": unestablished,
        "candidate_count": len(candidates),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--organism")
    parser.add_argument("--tissue")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--post-return", action="store_true")
    parser.add_argument("--gene-expression", action="store_true")
    args = parser.parse_args()

    if args.top_k < 1:
        parser.error("--top-k must be at least 1")

    try:
        output = evidence_search(
            args.query,
            organism=args.organism,
            tissue=args.tissue,
            top_k=args.top_k,
            require_post_return=args.post_return,
            require_gene_expression=args.gene_expression,
        )
    except ValueError as error:
        parser.error(str(error))

    print("\nEffective sample filters:")
    print(json.dumps(output["filters"], indent=2))

    print("\nRequirements checked:")
    print(json.dumps(output["requirements"], indent=2))

    print("Candidates inspected:", output["candidate_count"])
    print(
        "Candidates with requirements not established:",
        len(output["unestablished"]),
    )

    if not output["results"]:
        print(
            "\nNo candidates passed the sample filters and implemented "
            "evidence checks. This does not establish that no relevant "
            "study exists."
        )
        return

    print("\nDataset candidates:")
    print(
        "Timing and assay evidence is at study level; "
        "inspect sample/assay linkage."
    )

    for rank, result in enumerate(output["results"], start=1):
        record = result["record"]

        print(f"\n{rank}. {record['accession']} | {record['title']}")

        for requirement, evidence in result["evidence_checks"].items():
            print(f"\n{requirement}:")

            if isinstance(evidence, list):
                for item in evidence:
                    print(" ", item)
            else:
                print(evidence)

        if (
            output["filters"]["organism"]
            or output["filters"]["tissue"]
        ):
            print(
                "Samples satisfying the active filters:",
                len(result["matched_samples"]),
            )

        print("NASA metadata:", record["metadata_url"])


if __name__ == "__main__":
    main()