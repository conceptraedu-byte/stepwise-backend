from pathlib import Path
import json
import faiss
from google import genai
from dotenv import load_dotenv
import os
import numpy as np

load_dotenv()


print("CWD:", os.getcwd())
print("GEMINI_API_KEY =", os.getenv("GEMINI_API_KEY"))

from chunker import build_chunks

# -----------------------------
# CONFIG
# -----------------------------
INDEX_PATH = Path("vectorstore/class10_maths.index")
META_PATH = Path("vectorstore/class10_maths_meta.json")






client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

# -----------------------------
# EMBEDDING FUNCTION
# -----------------------------
def embed_texts(texts, batch_size=100):
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        print(f"Embedding batch {i // batch_size + 1} ({len(batch)} items)")

        response = client.models.embed_content(
            model="models/text-embedding-004",
            contents=batch
        )

        all_embeddings.extend([e.values for e in response.embeddings])

    return all_embeddings


# -----------------------------
# MAIN
# -----------------------------
def main():
    chunks = build_chunks()
    texts = [c["text"] for c in chunks]

    print(f"Embedding {len(texts)} chunks...")

    embeddings = embed_texts(texts)

    dim = len(embeddings[0])
    index = faiss.IndexFlatL2(dim)
    embedding_matrix = np.array(embeddings).astype("float32")
    index.add(embedding_matrix)
    INDEX_PATH.parent.mkdir(exist_ok=True)
    faiss.write_index(index, str(INDEX_PATH))

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print("✅ Embeddings stored successfully")
    print(f"Index: {INDEX_PATH}")
    print(f"Metadata: {META_PATH}")

if __name__ == "__main__":
    main()
