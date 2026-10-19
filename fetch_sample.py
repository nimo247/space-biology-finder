import json
from datetime import datetime, timezone
from pathlib import Path

import requests

study_id = "OSD-137"
url = "https://osdr.nasa.gov/osdr/data/osd/meta/137"

print(f"Fetching {study_id}...")

response = requests.get(url, timeout=60)
response.raise_for_status()
metadata = response.json()

if not metadata.get("study"):
    raise ValueError(
        "Response did not contain study metadata. "
        "Inspect the API response before continuing."
    )

record = {
    "accession": study_id,
    "source_url": url,
    "fetched_at": datetime.now(timezone.utc).isoformat(),
    "metadata": metadata,
}

output = Path("data/raw") / f"{study_id}.json"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps(record, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(f"Saved metadata to {output}")
print("Study keys:", list(metadata["study"]))