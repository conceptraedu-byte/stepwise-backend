from pathlib import Path
import json
import numpy as np
import google.generativeai as genai
import os

# Try importing faiss safely
try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    print("⚠️ FAISS not installed — running without vector search")

# ======================================================
# ENV SETUP
# ======================================================
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("⚠️ GEMINI_API_KEY missing — embedding disabled")

genai.configure(api_key=API_KEY)

# ======================================================
# CONFIG
# ======================================================
ROOT_DIR = Path.cwd()

VECTOR_DIR = ROOT_DIR / "vectorstore"
INDEX_PATH = VECTOR_DIR / "class10_maths.index"
META_PATH = VECTOR_DIR / "class10_maths_meta.json"

EMBED_MODEL = "models/gemini-embedding-001"

# ======================================================
# LOAD VECTOR STORE SAFELY
# ======================================================
index = None
metadata = []

if FAISS_AVAILABLE and INDEX_PATH.exists() and META_PATH.exists():
    try:
        index = faiss.read_index(str(INDEX_PATH))

        with open(META_PATH, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        print("✅ FAISS index loaded successfully")

    except Exception as e:
        print("⚠️ Failed to load FAISS:", str(e))
else:
    print("⚠️ Vector store not found — fallback mode active")

# ======================================================
# EMBEDDING FUNCTION
# ======================================================
def embed_query(text: str):
    if not API_KEY:
        return None

    try:
        result = genai.embed_content(
            model=EMBED_MODEL,
            content=text
        )
        vec = np.array(result["embedding"], dtype="float32").reshape(1, -1)
        return vec

    except Exception as e:
        print("⚠️ Embedding failed:", str(e))
        return None

# ======================================================
# RETRIEVER
# ======================================================
def retrieve(question: str, top_k: int = 3):

    # Fallback if FAISS not ready
    if index is None or len(metadata) == 0:
        return [
            {"text": "System not ready. Vector index missing."}
        ]

    q_vec = embed_query(question)

    if q_vec is None:
        return [
            {"text": "Embedding failed. Try again later."}
        ]

    try:
        distances, indices = index.search(q_vec, 40)
    except Exception as e:
        print("⚠️ Search failed:", str(e))
        return [{"text": "Search error occurred"}]

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
        if idx >= len(metadata):
            continue

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