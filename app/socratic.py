import os
import time
from datetime import datetime
from google import genai
from app.rag.retriever import retrieve

print("🚨 APP/SOCRATIC.PY LOADED 🚨")

# =============================
# Gemini client
# =============================
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL = "models/gemini-flash-latest"

# =============================
# Per-user conversation state
# =============================
MAX_HISTORY = 8
chat_states = {}  # chat_id -> state


def get_chat_state(chat_id: int):
    if chat_id not in chat_states:
        chat_states[chat_id] = {
            "messages": [],
            "class": None,
            "subject": None,
            "chapter": None,
            "last_topic": None,
            "importance": None,
            "board": "CBSE"
        }
    return chat_states[chat_id]


# =============================
# SAFE LOGGING (never breaks app)
# =============================
LOG_DIR = "logs"
TRUNCATION_LOG = os.path.join(LOG_DIR, "truncated_generations.log")
ANALYTICS_LOG = os.path.join(LOG_DIR, "topic_analytics.log")

def safe_log(path: str, text: str):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


# =============================
# SYLLABUS + IMPORTANCE
# =============================
SYLLABUS = {
    "class_10": {
        "physics": {
            "motion": {
                "topics": {
                    "distance": "basic",
                    "velocity": "important",
                    "acceleration": "very_important",
                    "equations of motion": "very_important",
                    "graphs of motion": "important"
                }
            },
            "electricity": {
                "topics": {
                    "electric current": "important",
                    "potential difference": "important",
                    "ohm's law": "very_important",
                    "resistance": "important",
                    "electric power": "very_important"
                }
            }
        }
    },
    "class_12": {
        "physics": {
            "electrostatics": {
                "topics": {
                    "coulomb's law": "very_important",
                    "electric field": "important",
                    "electric potential": "very_important"
                }
            }
        }
    }
}

OFF_SYLLABUS_KEYWORDS = {
    "schrodinger", "quantum", "wave function",
    "relativity", "string theory", "black hole"
}


# =============================
# Topic detection
# =============================
def detect_topic(text: str):
    t = text.lower()
    for cls, subjects in SYLLABUS.items():
        for subject, chapters in subjects.items():
            for chapter, data in chapters.items():
                for topic, importance in data["topics"].items():
                    if topic in t:
                        return {
                            "class": cls.replace("_", " "),
                            "subject": subject,
                            "chapter": chapter,
                            "last_topic": topic,
                            "importance": importance
                        }
    return None


def is_off_syllabus(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in OFF_SYLLABUS_KEYWORDS)


# =============================
# Incomplete sentence guard
# =============================
def is_incomplete_sentence(text: str) -> bool:
    bad_endings = (
        "of", "to", "for", "with", "that",
        "which", "because", "and", "or"
    )
    t = text.strip().lower()
    return any(t.endswith(w) for w in bad_endings)


def build_rag_context(question: str) -> str:
    try:
        chunks = retrieve(question, top_k=3)
        if not chunks:
            return ""

        context = "\n\n".join(
            f"- {c['text']}" for c in chunks
        )
        return context
    except Exception:
        return ""


# =============================
# SYSTEM PROMPT
# =============================
def build_system_prompt(board: str, importance: str | None):
    board_hint = (
        "Use strict NCERT wording."
        if board == "CBSE"
        else "Use simple State Board language."
    )

    importance_hint = ""
    if importance == "very_important":
        importance_hint = "This topic is very important for exams."
    elif importance == "important":
        importance_hint = "This topic is frequently asked."

    return f"""
You are a Class 10 & 12 board exam tutor.

RULES:
- Never stop mid-sentence.
- Always complete thoughts.
- Start directly with the answer.
- Plain text only. Unicode allowed (², −).
- No LaTeX, no markdown.

{board_hint}
{importance_hint}

Length rules:
- Define / State: 2–4 lines
- Explain: 5–8 short lines
- Derive: step-wise only if syllabus allows

If out of syllabus:
Say so clearly and offer only a basic idea.
"""


# =============================
# Prompt builder
# =============================
def build_prompt(chat_id: int, user_text: str) -> str:
    state = get_chat_state(chat_id)

    history = ""
    for m in state["messages"]:
        history += f"{m['role'].upper()}: {m['content']}\n"

    rag_context = build_rag_context(user_text)

    return f"""
{build_system_prompt(state["board"], state["importance"])}

REFERENCE MATERIAL (NCERT – use if relevant):
{rag_context if rag_context else "No reference available."}

Conversation context:
{history}

STUDENT QUESTION:
{user_text}
"""


# =============================
# Gemini call (retry-safe)
# =============================
def generate_response(prompt: str):
    for _ in range(2):
        try:
            return client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={"max_output_tokens": 500, "temperature": 0.3}
            )
        except Exception:
            time.sleep(1)
    return None


# =============================
# Response extraction
# =============================
def extract_text(chat_id: int, question: str, response) -> str:
    if not response or not response.candidates:
        return generate_fallback_answer(question)

    texts = []
    for c in response.candidates:
        content = c.content
        if not content:
            continue
        if getattr(content, "text", None):
            texts.append(content.text)
        for p in getattr(content, "parts", []) or []:
            if getattr(p, "text", None):
                texts.append(p.text)

    if not texts:
        return generate_fallback_answer(question)

    final = "\n".join(dict.fromkeys(texts)).strip()

    if is_incomplete_sentence(final):
        safe_log(
            TRUNCATION_LOG,
            f"[{datetime.now()}]\nQ: {question}\nOUT: {final}\n\n"
        )
        return (
            "This topic is outside the CBSE and State Board syllabus.\n\n"
            "At this level, only a basic idea is expected."
        )

    if final[-1] not in ".!?":
        final += "."

    return final


#===========
# fallback answers
#============

def generate_fallback_answer(question: str) -> str:
    prompt = f"""
You are a Class 10 board exam tutor.

Answer the following question step by step.
Use simple language.
Follow NCERT style.
Do not skip steps.

QUESTION:
{question}
"""

    response = generate_response(prompt)
    if not response:
        return "Please rephrase the question."

    return extract_raw_text(response)


# =============================
# Clear chat
# =============================
def clear_chat(chat_id: int) -> str:
    chat_states.pop(chat_id, None)
    return "🆕 New chat started. Ask a fresh question."


# =============================
# Main entry
# =============================
def chat_reply(
    chat_id: int,
    user_text: str,
    reset: bool = False,
    board: str | None = None
) -> str:

    if reset:
        return clear_chat(chat_id)

    if not user_text or not user_text.strip():
        return "Please type your question."

    state = get_chat_state(chat_id)

    if board in ("CBSE", "STATE"):
        state["board"] = board

    detected = detect_topic(user_text)
    if detected:
        state.update(detected)
        safe_log(
            ANALYTICS_LOG,
            f"[{datetime.now()}] {chat_id} {detected}\n"
        )

    if not detected and is_off_syllabus(user_text):
        return (
            "This topic is outside the CBSE and State Board syllabus.\n\n"
            "At this level, only a basic idea is expected."
        )

    prompt = build_prompt(chat_id, user_text)
    response = generate_response(prompt)
    reply = extract_text(chat_id, user_text, response)

    state["messages"].append({"role": "user", "content": user_text})
    state["messages"].append({"role": "assistant", "content": reply})
    state["messages"] = state["messages"][-MAX_HISTORY:]

    return reply
