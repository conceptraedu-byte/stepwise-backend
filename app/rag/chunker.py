from pathlib import Path
import re

DATA_PATH = Path("data\class10\maths.txt")

def clean_para(p: str) -> str:
    low = p.lower()

    # remove obvious junk only
    if (
        "reprint" in low
        or "print" in low
        or "====" in p
    ):
        return ""

    return p


def split_by_chapter(text: str):
    """
    Splits text by CHAPTER headings.
    Assumes headings like: CHAPTER 1: REAL NUMBERS
    """
    pattern = re.compile(r"(CHAPTER\s+\d+[:\s].*)", re.IGNORECASE)
    parts = pattern.split(text)

    chapters = []
    for i in range(1, len(parts), 2):
        title = parts[i].strip()
        content = parts[i + 1].strip()
        chapters.append((title, content))

    return chapters


def chunk_chapter(chapter_title: str, content: str):
    paragraphs = [
        clean_para(p.strip())
        for p in content.split("\n\n")
        if clean_para(p.strip())
    ]

    chunks = []
    buffer = []
    buffer_len = 0

    for para in paragraphs:
        buffer.append(para)
        buffer_len += len(para.split())

        if buffer_len >= 180:
            chunks.append(" ".join(buffer))
            buffer = []
            buffer_len = 0

    if buffer:
        chunks.append(" ".join(buffer))

    return chunks


def build_chunks():
    raw_text = DATA_PATH.read_text(encoding="utf-8", errors="ignore")

    # 🔑 split by SINGLE newline, not double
    lines = [
        clean_para(line.strip())
        for line in raw_text.splitlines()
        if clean_para(line.strip())
    ]

    all_chunks = []
    buffer = []
    buffer_len = 0
    part = 1

    for line in lines:
        buffer.append(line)
        buffer_len += len(line.split())

        if buffer_len >= 180:
            all_chunks.append({
                "class": "10",
                "subject": "maths",
                "chapter": "Class 10 Maths",
                "topic": f"Part {part}",
                "text": " ".join(buffer)
            })
            buffer = []
            buffer_len = 0
            part += 1

    if buffer:
        all_chunks.append({
            "class": "10",
            "subject": "maths",
            "chapter": "Class 10 Maths",
            "topic": f"Part {part}",
            "text": " ".join(buffer)
        })

    return all_chunks




if __name__ == "__main__":
    chunks = build_chunks()
    print(f"Total chunks created: {len(chunks)}")

    # Print sample
    print("\n--- SAMPLE CHUNK ---\n")
    if chunks:
        print(chunks[0])
    else:
        print("⚠️ No chunks created")