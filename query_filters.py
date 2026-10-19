import re


ORGANISM_ALIASES = {
    "mouse": "Mus musculus",
    "mice": "Mus musculus",
    "human": "Homo sapiens",
    "humans": "Homo sapiens",
    "rat": "Rattus norvegicus",
    "rats": "Rattus norvegicus",
    "arabidopsis": "Arabidopsis thaliana",
}

IGNORE_TISSUES = {
    "unknown", "not applicable", "none", "n/a",
    "cells", "cell", "tissue", "samples",
}


def normalize(value):
    return " ".join(value.casefold().split())


def mentioned(phrase, question):
    return bool(re.search(
        r"(?<!\w)" + re.escape(phrase) + r"(?!\w)",
        question,
    ))


def choose_match(matches, field):
    # Prefer a complete phrase over a nested shorter phrase:
    # "left lung" takes precedence over "lung".
    specific = {
        name: value
        for name, value in matches.items()
        if not any(
            name != other and mentioned(name, other)
            for other in matches
        )
    }

    values = sorted(set(specific.values()))

    if len(values) > 1:
        raise ValueError(
            f"Multiple {field} values detected: {', '.join(values)}. "
            f"Choose one using the {field} dropdown."
        )

    return values[0] if values else None


def resolve_filters(query, catalog, organism=None, tissue=None):
    question = normalize(query)

    organism_values = {
        normalize(value): value
        for record in catalog
        for value in record["organisms"]
    }
    tissue_values = {
        normalize(value): value
        for record in catalog
        for value in record["tissues"]
        if normalize(value) not in IGNORE_TISSUES
    }

    # Explicit dropdown selections take precedence.
    if organism is None:
        matches = {
            name: value
            for name, value in organism_values.items()
            if mentioned(name, question)
        }

        for alias, canonical in ORGANISM_ALIASES.items():
            canonical_value = organism_values.get(normalize(canonical))
            if canonical_value and mentioned(alias, question):
                matches[alias] = canonical_value

        organism = choose_match(matches, "organism")

    if tissue is None:
        matches = {
            name: value
            for name, value in tissue_values.items()
            if mentioned(name, question)
        }
        tissue = choose_match(matches, "tissue")

    return {
        "organism": organism,
        "tissue": tissue,
    }