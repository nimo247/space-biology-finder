import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


TARGET = 60
RAW_DIR = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

session = requests.Session()
retries = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)
session.mount("https://", HTTPAdapter(max_retries=retries))


def save_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary.replace(path)


def valid_record(record, accession):
    studies = (
        record.get("metadata", {})
        .get("study", {})
        .get(accession, {})
        .get("studies")
    )
    return (
        record.get("accession") == accession
        and isinstance(studies, list)
        and bool(studies)
    )


successful = set()

for path in RAW_DIR.glob("OSD-*.json"):
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if valid_record(record, path.stem):
            successful.add(path.stem)
    except (ValueError, AttributeError):
        pass

print(f"Found {len(successful)} valid cached studies.")

index_url = (
    "https://visualization.osdr.nasa.gov/"
    "biodata/api/v2/datasets/"
)

print("Fetching NASA's dataset listing...")
response = session.get(index_url, timeout=(10, 60))
response.raise_for_status()
index = response.json()

save_json(RAW_DIR / "dataset_index.json", {
    "source_url": index_url,
    "fetched_at": datetime.now(timezone.utc).isoformat(),
    "response": index,
})

numbers = sorted({
    int(number)
    for number in re.findall(
        r"\bOSD-(\d+)\b", json.dumps(index)
    )
})

if not numbers:
    raise SystemExit(
        "No accession IDs found. Inspect data/raw/dataset_index.json."
    )

# Reproducible selection across the discovered listing.
random.Random(42).shuffle(numbers)
print(f"Discovered {len(numbers)} study accession IDs.")

failures = []
attempts = 0

for number in numbers:
    if len(successful) >= TARGET or attempts >= TARGET * 2:
        break

    accession = f"OSD-{number}"

    if accession in successful:
        continue

    attempts += 1
    url = f"https://osdr.nasa.gov/osdr/data/osd/meta/{number}"

    try:
        response = session.get(url, timeout=(10, 60))
        response.raise_for_status()

        record = {
            "accession": accession,
            "source_url": url,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "metadata": response.json(),
        }

        if not valid_record(record, accession):
            raise ValueError("Response contains no study records")

        save_json(RAW_DIR / f"{accession}.json", record)
        successful.add(accession)
        print(f"[{len(successful)}/{TARGET}] Saved {accession}")

    except (requests.RequestException, ValueError, AttributeError) as error:
        failures.append({
            "accession": accession,
            "error": str(error),
        })
        print(f"Could not fetch {accession}: {error}")

    time.sleep(0.5)

report = {
    "completed_at": datetime.now(timezone.utc).isoformat(),
    "target": TARGET,
    "successful_accessions": sorted(successful),
    "failed_requests": failures,
}
save_json(Path("data/collection_report.json"), report)

print(f"\nAvailable studies: {len(successful)}")
print(f"Failed requests this run: {len(failures)}")
print("Report saved to data/collection_report.json")