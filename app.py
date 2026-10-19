import hashlib
import json
import threading
import traceback
from pathlib import Path

import streamlit as st

from evidence_search import evidence_search
from semantic_search import SemanticSearch


st.set_page_config(
    page_title="Space Biology Finder",
    page_icon="🧬",
    layout="wide",
)

APP_STATE_VERSION = 2
CATALOG_PATH = Path("data/processed/catalog.json")

if not CATALOG_PATH.exists():
    st.error("The dataset catalog is unavailable.")
    st.stop()

catalog_bytes = CATALOG_PATH.read_bytes()
catalog_hash = hashlib.sha256(catalog_bytes).hexdigest()
catalog = json.loads(catalog_bytes)

if not catalog:
    st.error("The dataset catalog is empty.")
    st.stop()

organisms = sorted({
    value
    for record in catalog
    for value in record["organisms"]
})

tissues = sorted({
    value
    for record in catalog
    for value in record["tissues"]
})

LABELS = {
    "post_return": "Measurements after return to Earth",
    "gene_expression": "Gene-expression assay",
}


@st.cache_resource(show_spinner=False, max_entries=2)
def load_engine(snapshot_hash):
    # A changed catalog hash creates a fresh cached engine.
    return SemanticSearch(), threading.Lock()


def nasa_study_url(accession):
    return (
        "https://osdr.nasa.gov/bio/repo/data/studies/"
        f"{accession}"
    )


with st.sidebar:
    st.title("🧬 Space Biology Finder")
    st.caption("Discover studies. Inspect the evidence.")

    st.divider()
    st.subheader("Current collection")

    st.metric("Studies", len(catalog))
    st.metric(
        "Sample records",
        f"{sum(record['sample_count'] for record in catalog):,}",
    )
    st.metric("Organism annotations", len(organisms))

    with st.expander("Coverage and interpretation"):
        st.write(
            "This prototype searches a local snapshot of public "
            "NASA OSDR metadata."
        )
        st.write(
            "Supported organism and tissue names can be inferred "
            "from your question. Explicit dropdown selections "
            "take precedence."
        )
        st.write(
            "Organism and tissue filters must match within "
            "the same sample record."
        )
        st.write(
            "Missing annotations can exclude relevant studies. "
            "Timing and assay checks recognise limited wording "
            "and operate at study level."
        )

    st.divider()
    st.caption(
        "Independent prototype by Naman Verma. "
        "Uses public NASA OSDR data."
    )


st.title("Find space-biology datasets")
st.write(
    "Ask a research question in everyday language, "
    "then inspect the metadata behind each candidate."
)

with st.form("dataset_search"):
    query = st.text_area(
        "Your research question",
        value="What happens to gene activity after returning to Earth?",
        height=95,
    )

    left, right = st.columns(2)

    with left:
        organism = st.selectbox(
            "Organism",
            ["Any organism"] + organisms,
        )

    with right:
        tissue = st.selectbox(
            "Tissue or material",
            ["Any tissue"] + tissues,
        )

    st.caption(
        "Leave a dropdown on Any to infer supported names from "
        "your question, or select a value to set the filter yourself."
    )

    with st.expander("Additional requirements"):
        require_post_return = st.checkbox(
            "Require evidence of measurements after return to Earth",
        )

        require_gene_expression = st.checkbox(
            "Require a gene-expression assay",
        )

        st.caption(
            "These requirements can also be inferred from supported "
            "wording in your question. Selecting them enforces them "
            "even when they are not stated."
        )

        top_k = st.slider(
            "Maximum results",
            min_value=1,
            max_value=10,
            value=5,
        )

    submitted = st.form_submit_button(
        "Find datasets",
        type="primary",
    )


if submitted:
    st.session_state.pop("last_search", None)

    selected_organism = (
        None if organism == "Any organism" else organism
    )
    selected_tissue = (
        None if tissue == "Any tissue" else tissue
    )

    if not query.strip():
        st.warning("Enter a research question first.")
    else:
        try:
            with st.spinner("Searching studies and checking metadata…"):
                engine, lock = load_engine(catalog_hash)

                with lock:
                    output = evidence_search(
                        query.strip(),
                        organism=selected_organism,
                        tissue=selected_tissue,
                        top_k=top_k,
                        engine=engine,
                        require_post_return=require_post_return,
                        require_gene_expression=require_gene_expression,
                    )

            st.session_state["last_search"] = {
                "app_version": APP_STATE_VERSION,
                "query": query.strip(),
                "organism": output["filters"]["organism"],
                "tissue": output["filters"]["tissue"],
                "catalog_hash": catalog_hash,
                "output": output,
            }

        except ValueError as error:
            st.warning(str(error))

        except Exception:
            traceback.print_exc()
            st.error("Search could not complete. Please try again.")


saved = st.session_state.get("last_search")

# Discard results from an older app version or catalog snapshot.
if saved and (
    saved.get("app_version") != APP_STATE_VERSION
    or saved.get("catalog_hash") != catalog_hash
):
    st.session_state.pop("last_search", None)
    saved = None


if saved:
    output = saved["output"]
    results = output["results"]

    active_checks = [
        LABELS[key]
        for key, enabled in output["requirements"].items()
        if enabled
    ]

    st.divider()
    st.subheader("Dataset candidates")
    st.write(f"Question: {saved['query']}")

    active_filters = []

    if saved["organism"]:
        active_filters.append(
            f"Organism: {saved['organism']}"
        )

    if saved["tissue"]:
        active_filters.append(
            f"Tissue/material: {saved['tissue']}"
        )

    if active_filters:
        st.caption(
            "Filters used: " + " · ".join(active_filters)
        )

    if active_checks:
        st.info(
            "Evidence checks: " + " · ".join(active_checks)
        )
        st.caption(
            "Supporting study-level metadata does not verify "
            "which samples were used in each assay."
        )
    else:
        st.caption(
            "Candidates are ranked by textual relevance. "
            "No timing or assay requirement was detected or selected."
        )

    passed_count = (
        output["candidate_count"]
        - len(output["unestablished"])
    )

    if active_checks:
        st.caption(
            f"{output['candidate_count']} candidates inspected · "
            f"{passed_count} have supporting metadata for the "
            f"active checks · {len(results)} displayed"
        )
    else:
        st.caption(
            f"{output['candidate_count']} candidates ranked after "
            f"sample filtering · {len(results)} displayed"
        )

    if not results:
        st.warning(
            "No candidates passed the active filters and implemented "
            "checks in this collection. Relevant studies may still "
            "exist outside this collection or use different annotations."
        )

    for rank, result in enumerate(results, start=1):
        record = result["record"]

        with st.container(border=True):
            st.caption(
                f"{rank:02d} · {record['accession']}"
            )
            st.subheader(record["title"])

            st.write(
                "**Organism:** "
                + (
                    ", ".join(record["organisms"])
                    or "Not extracted"
                )
            )

            st.write(
                "**Tissue/material:** "
                + (
                    ", ".join(record["tissues"])
                    or "Not extracted"
                )
            )

            if saved["organism"] or saved["tissue"]:
                st.caption(
                    f"{len(result['matched_samples'])} sample records "
                    "satisfy the active organism/tissue filters."
                )

            checks = result["evidence_checks"]

            if checks.get("post_return"):
                st.markdown(
                    "**Timing evidence from the description**"
                )
                st.write(checks["post_return"])

            if checks.get("gene_expression"):
                st.markdown(
                    "**Gene-expression assays in this study**"
                )

                for assay in checks["gene_expression"]:
                    st.write(f"• {assay}")

            with st.expander(
                "Study description and retrieved passage"
            ):
                st.write(record["description"])
                st.markdown(
                    "**Passage used for semantic ranking**"
                )
                st.write(result["passage"])

            if result["matched_samples"]:
                with st.expander("Sample evidence"):
                    for sample in result["matched_samples"][:5]:
                        st.markdown(
                            f"**{sample['name']}**"
                        )

                        for attribute in sample["characteristics"]:
                            if attribute["field"]:
                                value = attribute["value"]

                                if attribute.get("unit"):
                                    value = (
                                        f"{value} "
                                        f"{attribute['unit']}"
                                    )

                                st.write(
                                    f"{attribute['field']}: {value}"
                                )

                        if sample.get("factors"):
                            st.markdown("**Experimental factors**")

                            for factor in sample["factors"]:
                                if factor["field"]:
                                    st.write(
                                        f"{factor['field']}: "
                                        f"{factor['value']}"
                                    )

                    if len(result["matched_samples"]) > 5:
                        st.caption(
                            "Showing the first five matching samples."
                        )

            st.link_button(
                "Open study on NASA OSDR",
                nasa_study_url(record["accession"]),
            )

    if output["unestablished"]:
        with st.expander(
            "Related candidates with requirements not established"
        ):
            st.caption(
                "These candidates lack evidence recognised by the "
                "current checks. This is not proof of irrelevance."
            )

            for result in output["unestablished"][:5]:
                record = result["record"]

                missing = [
                    LABELS[key]
                    for key, value in result["evidence_checks"].items()
                    if not value
                ]

                st.markdown(
                    f"**{record['accession']} — "
                    f"{record['title']}**"
                )
                st.write(
                    "Not established: " + "; ".join(missing)
                )

    if results:
        export = {
            "question": saved["query"],
            "organism_filter": saved["organism"],
            "tissue_filter": saved["tissue"],
            "requirements_checked": output["requirements"],
            "catalog_sha256": catalog_hash,
            "results": [
                {
                    "accession": item["record"]["accession"],
                    "title": item["record"]["title"],
                    "study_url": nasa_study_url(
                        item["record"]["accession"]
                    ),
                    "metadata_url": item["record"]["metadata_url"],
                    "metadata_fetched_at": item["record"]["fetched_at"],
                    "evidence_checks": item["evidence_checks"],
                    "matching_sample_names": [
                        sample["name"]
                        for sample in item["matched_samples"]
                    ],
                }
                for item in results
            ],
        }

        st.download_button(
            "Download results and evidence",
            data=json.dumps(
                export,
                indent=2,
                ensure_ascii=False,
            ),
            file_name="space_biology_results.json",
            mime="application/json",
        )