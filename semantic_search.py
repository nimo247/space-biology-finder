import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from search import sample_matches


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
CATALOG_PATH = Path("data/processed/catalog.json")
INDEX_PATH = Path("data/processed/semantic_index.npz")
INDEX_VERSION = 1


class SemanticSearch:
    def __init__(self):
        catalog_bytes = CATALOG_PATH.read_bytes()
        self.records = json.loads(catalog_bytes)
        fingerprint = hashlib.sha256(catalog_bytes).hexdigest()

        if not self.records:
            raise ValueError("The catalog is empty.")

        print("Loading embedding model...")
        self.model = SentenceTransformer(MODEL_NAME, device="cpu")

        if INDEX_PATH.exists():
            with np.load(INDEX_PATH, allow_pickle=False) as cached:
                metadata = json.loads(cached["metadata"].item())

                if (
                    metadata["catalog_sha256"] == fingerprint
                    and metadata["model"] == MODEL_NAME
                    and metadata["version"] == INDEX_VERSION
                ):
                    self.chunks = metadata["chunks"]
                    self.vectors = cached["vectors"].copy()
                    print(f"Loaded {len(self.chunks)} cached passages.")
                    return

        self.chunks = []

        # Use short, overlapping passages so long records are covered.
        chunk_size = min(200, self.model.max_seq_length - 8)
        step = chunk_size - 32

        for record_index, record in enumerate(self.records):
            source_text = record["search_text"]
            encoded = self.model.tokenizer(
                source_text,
                add_special_tokens=False,
                truncation=False,
                return_offsets_mapping=True,
            )
            offsets = encoded["offset_mapping"]

            for start in range(0, len(offsets), step):
                end = min(start + chunk_size, len(offsets))
                char_start = offsets[start][0]
                char_end = offsets[end - 1][1]
                passage = source_text[char_start:char_end]

                if passage.strip():
                    self.chunks.append({
                        "record_index": record_index,
                        "text": passage,
                        "char_start": char_start,
                        "char_end": char_end,
                    })

                if end == len(offsets):
                    break

        if not self.chunks:
            raise ValueError("No searchable passages found.")

        print(f"Embedding {len(self.chunks)} passages...")
        self.vectors = self.model.encode(
            [chunk["text"] for chunk in self.chunks],
            batch_size=32,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=True,
        )

        metadata = {
            "catalog_sha256": fingerprint,
            "model": MODEL_NAME,
            "version": INDEX_VERSION,
            "chunks": self.chunks,
        }

        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = INDEX_PATH.with_suffix(".tmp")

        with temporary.open("wb") as handle:
            np.savez_compressed(
                handle,
                vectors=self.vectors,
                metadata=np.array(json.dumps(metadata)),
            )

        temporary.replace(INDEX_PATH)
        print(f"Saved index to {INDEX_PATH}")

    def search(self, query, organism=None, tissue=None, top_k=5):
        if not query.strip():
            raise ValueError("Enter a question.")

        query_vector = self.model.encode(
            query,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        similarities = self.vectors @ query_vector

        # Keep the best passage for each study.
        best = {}

        for chunk, score in zip(self.chunks, similarities):
            record_index = chunk["record_index"]

            if (
                record_index not in best
                or float(score) > best[record_index]["score"]
            ):
                best[record_index] = {
                    "score": float(score),
                    "passage": chunk["text"],
                }

        results = []

        for record_index, match in sorted(
            best.items(),
            key=lambda item: (
                -item[1]["score"],
                self.records[item[0]]["accession"],
            ),
        ):
            record = self.records[record_index]
            matched_samples = []

            if organism or tissue:
                matched_samples = [
                    sample
                    for sample in record.get("samples", [])
                    if sample_matches(sample, organism, tissue)
                ]

                if not matched_samples:
                    continue

            results.append({
                "record": record,
                "score": match["score"],
                "passage": match["passage"],
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

    engine = SemanticSearch()
    results = engine.search(
        args.query,
        organism=args.organism,
        tissue=args.tissue,
        top_k=args.top_k,
    )

    if not results:
        print("No studies satisfy these sample filters in this catalog.")
        return

    print("\nSemantic candidates — review relevance against the metadata.")

    for rank, result in enumerate(results, start=1):
        record = result["record"]

        print(f"\n{rank}. {record['accession']} | {record['title']}")
        print(f"Cosine similarity: {result['score']:.3f}")
        print("Organisms:", ", ".join(record["organisms"]) or "Unknown")
        print("Tissues:", ", ".join(record["tissues"]) or "Unknown")

        if args.organism or args.tissue:
            print(
                "Samples satisfying all filters:",
                len(result["matched_samples"]),
            )

        print("Best matching metadata passage:")
        print(result["passage"])
        print("NASA metadata:", record["metadata_url"])


if __name__ == "__main__":
    main()