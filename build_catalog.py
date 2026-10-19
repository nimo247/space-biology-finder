import json
from pathlib import Path


def text(value):
    """Read an ISA annotation or a plain value."""
    if isinstance(value, dict):
        return text(value.get("annotationValue"))
    if value is None:
        return ""
    return str(value).strip()


def read_attributes(items, categories, units):
    result = []

    for item in items:
        category_id = item.get("category", {}).get("@id")
        unit_id = item.get("unit", {}).get("@id")

        result.append({
            "field": categories.get(category_id),
            "category_id": category_id,
            "value": text(item.get("value")),
            "unit": units.get(unit_id),
        })

    return result


def unique_values(samples, field_names):
    return sorted({
        attribute["value"]
        for sample in samples
        for attribute in sample["characteristics"]
        if (attribute["field"] or "").casefold() in field_names
        and attribute["value"]
    })


records = []

for path in sorted(Path("data/raw").glob("OSD-*.json")):
    saved = json.loads(path.read_text(encoding="utf-8"))
    accession = saved["accession"]
    investigation = saved["metadata"]["study"][accession]
    studies = investigation.get("studies", [])

    if len(studies) != 1:
        raise ValueError(
            f"{accession}: expected one study, found {len(studies)}"
        )

    study = studies[0]
    title = text(study.get("title"))
    description = text(study.get("description"))

    if not title:
        raise ValueError(f"{accession}: missing study title")

    categories = {
        item["@id"]: text(item.get("characteristicType"))
        for item in study.get("characteristicCategories", [])
        if item.get("@id")
    }

    factors = {
        item["@id"]: text(item.get("factorName"))
        for item in study.get("factors", [])
        if item.get("@id")
    }

    units = {
        item["@id"]: text(item)
        for item in study.get("unitCategories", [])
        if item.get("@id")
    }

    samples = []

    for sample in study.get("materials", {}).get("samples", []):
        samples.append({
            "sample_id": sample.get("@id"),
            "name": sample.get("name"),
            "characteristics": read_attributes(
                sample.get("characteristics", []),
                categories,
                units,
            ),
            "factors": read_attributes(
                sample.get("factorValues", []),
                factors,
                units,
            ),
        })

    assays = [
        {
            "filename": assay.get("filename"),
            "measurement": text(assay.get("measurementType")),
            "technology": text(assay.get("technologyType")),
            "platform": text(assay.get("technologyPlatform")),
        }
        for assay in study.get("assays", [])
    ]

    organisms = unique_values(samples, {"organism"})
    tissues = unique_values(
        samples, {"material type", "tissue", "tissue type"}
    )

    search_parts = [title, description]

    for sample in samples:
        for attribute in sample["characteristics"] + sample["factors"]:
            if attribute["field"] and attribute["value"]:
                search_parts.append(
                    f"{attribute['field']}: {attribute['value']}"
                )

    for assay in assays:
        search_parts.extend([
            assay["measurement"],
            assay["technology"],
            assay["platform"],
        ])

    record = {
        "accession": accession,
        "title": title,
        "description": description,
        "version": investigation.get("version"),
        "public_release_date": study.get("publicReleaseDate"),
        "organisms": organisms,
        "tissues": tissues,
        "sample_count": len(samples),
        "assay_count": len(assays),
        "samples": samples,
        "assays": assays,
        "metadata_url": saved["source_url"],
        "fetched_at": saved["fetched_at"],
        "raw_file": path.as_posix(),
        "search_text": "\n".join(dict.fromkeys(
            part for part in search_parts if part
        )),
    }
    records.append(record)

    print(f"\n{accession}: {title}")
    print("Organisms:", organisms)
    print("Tissues:", tissues)
    print("Samples:", len(samples))
    print("Assay technologies:", [a["technology"] for a in assays])

    unresolved = {
        attribute["category_id"]
        for sample in samples
        for attribute in sample["characteristics"] + sample["factors"]
        if not attribute["field"]
    }
    print("Unresolved category IDs:", sorted(
        str(value) for value in unresolved
    ))

    if samples:
        print("\nFirst parsed sample:")
        print(json.dumps(samples[0], indent=2))

if not records:
    raise SystemExit("No downloaded studies found in data/raw")

output = Path("data/processed/catalog.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(
    json.dumps(records, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print(f"\nSaved {len(records)} record(s) to {output}")