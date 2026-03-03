from pathlib import Path
import json
import faiss
import numpy as np
import google.generativeai as genai
from dotenv import load_dotenv
import os

# --------------------------------------------------
# ENV
# --------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[0]
load_dotenv(ROOT_DIR / ".env")

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

EMBED_MODEL = "models/gemini-embedding-001"

VECTOR_DIR = ROOT_DIR / "vectorstore"
VECTOR_DIR.mkdir(exist_ok=True)

INDEX_PATH = VECTOR_DIR / "class10_maths.index"
META_PATH = VECTOR_DIR / "class10_maths_meta.json"

# --------------------------------------------------
# YOUR DOCUMENTS (example — replace with real data)
# --------------------------------------------------
documents = [
    "Euclid’s division lemma states that a = bq + r",
    "HCF of two numbers can be found using Euclid's algorithm",
    "Integers include positive integers, negative integers, and zero"
]

# --------------------------------------------------
# EMBED DOCUMENTS
# --------------------------------------------------
embeddings = []

for doc in documents:
    res = genai.embed_content(
        model=EMBED_MODEL,
        content=doc
    )
    embeddings.append(res["embedding"])

embeddings = np.array(embeddings, dtype="float32")

# --------------------------------------------------
# BUILD FAISS INDEX
# --------------------------------------------------
dim = embeddings.shape[1]   # THIS WILL BE 3072
index = faiss.IndexFlatL2(dim)
index.add(embeddings)

faiss.write_index(index, str(INDEX_PATH))

with open(META_PATH, "w", encoding="utf-8") as f:
    json.dump(
        [{"text": d} for d in documents],
        f,
        indent=2
    )

print("✅ FAISS index rebuilt with dim =", dim)
