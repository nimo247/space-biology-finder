# Space Biology Finder

A research prototype that helps users discover public NASA
space-biology datasets through everyday-language questions.

Built by Naman Verma using NASA Open Science Data Repository
(OSDR) metadata.

## Current snapshot

- 60 studies
- 3,399 sample records
- 178 indexed metadata passages

Sample records are metadata entries, not necessarily independent
biological replicates.

## Features

- Keyword search using BM25
- Semantic search using all-MiniLM-L6-v2
- Reciprocal rank fusion of keyword and semantic rankings
- Supported organism and tissue names inferred from questions
- Explicit dropdown filters that override inferred values
- Organism and tissue constraints matched within the same sample
- Limited evidence checks for post-return measurements and
  gene-expression assays
- Supporting metadata excerpts, sample details and NASA study links
- Downloadable results with evidence and source information

## Run locally

Use a Python environment compatible with the dependencies.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The committed catalog supplies the dataset snapshot.
The first search downloads the embedding model and builds the local
semantic index. Later searches reuse the cached model and index.

For Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Example questions

- How does spaceflight affect mouse liver?
- Find gene expression datasets from mice liver
- What happens to gene activity after returning to Earth?
- Find mouse liver proteomics datasets after returning to Earth

## Development evaluation

```bash
python evaluate.py
```

Current results:

- 15/15 development checks passed
- Known-positive Hit@5: 11/11 retrieval questions
- Known-positive MRR@5: 1.0
- Input-handling checks: 4/4

These questions were used during development. Relevance judgments
are incomplete, and unjudged results are not automatically irrelevant.
These results do not establish general search accuracy or precision.

The report is saved to:
`evaluation/development_results.json`

## Data collection

```bash
python collect_studies.py
python build_catalog.py
```

Collection retrieves public metadata, not the underlying experimental
data files. NASA metadata can change; rebuilding the catalog creates
a new snapshot that should be evaluated again.

## Limitations

- The snapshot covers 60 studies, not the entire repository.
- Organism aliases and tissue-name interpretation are limited.
- Missing annotations can exclude relevant studies.
- Timing and assay checks use limited rules.
- Study-level evidence does not establish sample-to-assay linkage.
- Not every condition in a natural-language question is enforced.
- Semantic similarity is not a confidence probability.
- Unrelated questions can still produce ranked candidates.
- The tool retrieves studies; it does not establish biological findings.

## Sources

- Repository: https://osdr.nasa.gov/bio/repo/
- Biological Data API:
  https://visualization.osdr.nasa.gov/biodata/api/
- NASA API documentation: https://api.nasa.gov/#osdr

Study records retain source URLs, metadata versions and retrieval
timestamps where available.

This is an independent prototype using public NASA data.