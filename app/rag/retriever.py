from pathlib import Path
import json
import faiss
import numpy as np
from google import genai
from dotenv import load_dotenv
import os

# -----------------------------
# ENV
# -----------------------------
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY not found")

client = genai.Client(api_key=api_key)

# -----------------------------
# PATHS
# -----------------------------
INDEX_PATH = ROOT_DIR / "vectorstore" / "class10_maths.index"
META_PATH = ROOT_DIR / "vectorstore" / "class10_maths_meta.json"

# -----------------------------
# LOAD INDEX + METADATA
# -----------------------------
index = faiss.read_index(str(INDEX_PATH))

with open(META_PATH, "r", encoding="utf-8") as f:
    metadata = json.load(f)

# -----------------------------
# EMBED QUERY
# -----------------------------
def embed_query(text: str):
    response = client.models.embed_content(
        model="models/text-embedding-004",
        contents=[text]
    )
    vec = response.embeddings[0].values
    return np.array([vec], dtype="float32")

# -----------------------------
# RETRIEVE
# -----------------------------
def retrieve(question: str, top_k: int = 3):
    q_vec = embed_query(question)
    distances, indices = index.search(q_vec, 40)

    q_lower = question.lower()

    # Domain anchors for Real Numbers (Euclid lives here)
    real_numbers_signals = [
        "integer",
        "positive integer",
        "hcf",
        "remainder",
        "divisor",
        "a = bq",
        "algorithm",
        "euclid"
    ]

    strict = []
    fallback = []

    for idx in indices[0]:
        meta = metadata[idx]
        text_lower = meta["text"].lower()

        # STRONG FILTER: must look like Real Numbers
        if any(sig in text_lower for sig in real_numbers_signals):
            strict.append(meta)
        else:
            fallback.append(meta)

    results = strict[:top_k]

    # Absolute fallback — never return empty
    if len(results) < top_k:
        results.extend(fallback[: top_k - len(results)])

    return results


# -----------------------------
# TEST
# -----------------------------
if __name__ == "__main__":
    q = "Define Euclid’s division lemma"
    results = retrieve(q)

    print(f"\nQUESTION: {q}\n")
    for i, r in enumerate(results, start=1):
        print(f"--- RESULT {i} ---")
        print(r["text"][:500])
        print()
