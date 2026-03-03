from pathlib import Path
import json
import faiss
import numpy as np
import google.generativeai as genai
from dotenv import load_dotenv
import os

# ======================================================
# ENV SETUP
# ======================================================
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in .env")

genai.configure(api_key=API_KEY)

# ======================================================
# EMBEDDING CONFIG (MUST MATCH INDEX CREATION)
# ======================================================
EMBED_MODEL = "models/gemini-embedding-001"

# ======================================================
# VECTOR STORE PATHS
# ======================================================
VECTOR_DIR = ROOT_DIR / "vectorstore"
INDEX_PATH = VECTOR_DIR / "class10_maths.index"
META_PATH = VECTOR_DIR / "class10_maths_meta.json"

if not INDEX_PATH.exists():
    raise RuntimeError(
        f"FAISS index not found at {INDEX_PATH}. "
        f"Rebuild the vector store."
    )

if not META_PATH.exists():
    raise RuntimeError(
        f"Metadata file not found at {META_PATH}. "
        f"Rebuild the vector store."
    )

# ======================================================
# LOAD FAISS INDEX + METADATA
# ======================================================
index = faiss.read_index(str(INDEX_PATH))

with open(META_PATH, "r", encoding="utf-8") as f:
    metadata = json.load(f)

# ======================================================
# EMBEDDING FUNCTION
# ======================================================
def embed_query(text: str) -> np.ndarray:
    result = genai.embed_content(
        model=EMBED_MODEL,
        content=text
    )

    vec = np.array(result["embedding"], dtype="float32").reshape(1, -1)

    # HARD GUARD — NEVER REMOVE
    if vec.shape[1] != index.d:
        raise RuntimeError(
            f"EMBEDDING DIMENSION MISMATCH → "
            f"query dim = {vec.shape[1]}, "
            f"index dim = {index.d}. "
            f"Delete and rebuild FAISS index."
        )

    return vec

# ======================================================
# RETRIEVER
# ======================================================
def retrieve(question: str, top_k: int = 3):
    q_vec = embed_query(question)

    distances, indices = index.search(q_vec, 40)

    q_lower = question.lower()

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

        if any(sig in text_lower for sig in real_numbers_signals):
            strict.append(meta)
        else:
            fallback.append(meta)

    results = strict[:top_k]

    if len(results) < top_k:
        results.extend(fallback[: top_k - len(results)])

    return results
