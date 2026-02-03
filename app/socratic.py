import os
import time
from datetime import datetime
from google import genai

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

# =============================
# LOGGING FILES
# =============================
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

TRUNCATION_LOG = os.path.join(LOG_DIR, "truncated_generations.log")
ANALYTICS_LOG = os.path.join(LOG_DIR, "topic_analytics.log")

# =============================
# Utilities
# =============================
def log_truncation(chat_id: int, question: str, raw_text: str):
    with open(TRUNCATION_LOG, "a", encoding="utf-8") as f:
        f.write(
            f"[{datetime.now()}] chat_id={chat_id}\n"
            f"QUESTION: {question}\n"
            f"RAW_OUTPUT: {raw_text}\n\n"
        )


def log_topic_analytics(chat_id: int, state: dict):
    with open(ANALYTICS_LOG, "a", encoding="utf-8") as f:
        f.write(
            f"[{datetime.now()}] chat_id={chat_id} | "
            f"class={state.get('class')} | "
            f"subject={state.get('subject')} | "
            f"chapter={state.get('chapter')} | "
            f"topic={state.get('last_topic')} | "
            f"importance={state.get('importance')}\n"
        )


def get_chat_state(chat_id: int):
    if chat_id not in chat_states:
        chat_states[chat_id] = {
            "mode": "direct",
            "messages": [],
            "class": None,
            "subject": None,
            "chapter": None,
            "last_topic": None,
            "importance": None,
            "board": "CBSE"  # default
        }
    return chat_states[chat_id]


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

OFF_SYLLABUS_KEYWORDS = [
    "schrodinger", "quantum", "wave function",
    "relativity", "string theory", "black hole"
]

# =============================
# Topic detection
# =============================
def detect_topic(user_text: str):
    text = user_text.lower()

    for cls, subjects in SYLLABUS.items():
        for subject, chapters in subjects.items():
            for chapter, data in chapters.items():
                for topic, importance in data["topics"].items():
                    if topic in text:
                        return {
                            "class": cls.replace("_", " "),
                            "subject": subject,
                            "chapter": chapter,
                            "topic": topic,
                            "importance": importance
                        }
    return None


def is_off_syllabus(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in OFF_SYLLABUS_KEYWORDS)


# =============================
# Sentence completeness guard
# =============================
def is_incomplete_sentence(text: str) -> bool:
    text = text.strip().lower()
    incomplete_endings = (
        "of", "to", "for", "with", "that", "which",
        "because", "and", "or"
    )
    return any(text.endswith(" " + w) or text.endswith(w) for w in incomplete_endings)


# =============================
# SYSTEM PROMPT (BOARD-TUNED)
# =============================
def build_system_prompt(board: str, importance: str | None):
    board_hint = (
        "Follow strict NCERT wording." if board == "CBSE"
        else "Use simpler language commonly used in State Board answers."
    )

    importance_hint = ""
    if importance == "very_important":
        importance_hint = "This topic is very important for board exams. Be precise."
    elif importance == "important":
        importance_hint = "This topic is frequently asked in exams."
    elif importance == "basic":
        importance_hint = "Keep the explanation basic and clear."

    return f"""
You are a Class 10 & 12 tutor for CBSE and State Boards.

ABSOLUTE RULES:
- NEVER stop mid-sentence or mid-step.
- ALWAYS complete the answer.
- Do NOT answer out-of-syllabus questions fully.

ANSWER STYLE:
- Start directly with the answer.
- Use short, exam-ready language.
- Use plain-text math and Unicode (², −).
- No LaTeX, no markdown.

{board_hint}
{importance_hint}

LENGTH RULES:
- Define / State → short (2–4 lines)
- Explain → 5–8 short lines
- Derive → step-wise ONLY if syllabus allows

If out-of-syllabus:
Politely state it is out of syllabus and offer a conceptual explanation.
"""


# =============================
# Prompt builder
# =============================
def build_prompt(chat_id: int, user_text: str) -> str:
    state = get_chat_state(chat_id)

    history = ""
    for m in state["messages"]:
        history += f"{m['role'].upper()}: {m['content']}\n"

    system_prompt = build_system_prompt(
        board=state["board"],
        importance=state["importance"]
    )

    return f"""
{system_prompt}

Conversation context:
{history}

STUDENT QUESTION:
{user_text}
"""


# =============================
# Gemini call
# =============================
def generate_response(prompt):
    return client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "max_output_tokens": 500,
            "temperature": 0.3
        }
    )


# =============================
# Response extraction (SAFE)
# =============================
def extract_text(chat_id: int, question: str, response) -> str:
    texts = []

    for candidate in (response.candidates or []):
        content = candidate.content
        if not content:
            continue

        if hasattr(content, "text") and content.text:
            texts.append(content.text)

        parts = getattr(content, "parts", None)
        if parts:
            for part in parts:
                if hasattr(part, "text") and part.text:
                    texts.append(part.text)

    if not texts:
        return "⚠️ I couldn’t generate a response. Please try again."

    final = "\n".join(dict.fromkeys(texts)).strip()

    if is_incomplete_sentence(final):
        log_truncation(chat_id, question, final)
        return (
            "This topic is outside the CBSE and State Board syllabus.\n\n"
            "At this level, only the basic idea is expected.\n"
            "If you want, I can explain the concept in simple terms."
        )

    if final[-1] not in ".!?":
        final += "."

    return final


# =============================
# Main entry function
# =============================
def chat_reply(
    chat_id: int,
    user_text: str,
    mode: str | None = None,
    reset: bool = False,
    board: str | None = None
) -> str:

    state = get_chat_state(chat_id)

    if reset:
        state.update({
            "mode": "direct",
            "messages": [],
            "class": None,
            "subject": None,
            "chapter": None,
            "last_topic": None,
            "importance": None
        })
        return "🆕 New chat started. Ask a fresh question."

    if not user_text or not user_text.strip():
        return "Please type your question."

    if board in ("CBSE", "STATE"):
        state["board"] = board

    detected = detect_topic(user_text)
    if detected:
        state.update(detected)
        log_topic_analytics(chat_id, state)

    if detected is None and is_off_syllabus(user_text):
        return (
            "This topic is outside the CBSE and State Board syllabus.\n\n"
            "At this level, only the basic idea is expected.\n"
            "If you want, I can explain the concept in simple terms."
        )

    prompt = build_prompt(chat_id, user_text)

    try:
        response = generate_response(prompt)
        reply = extract_text(chat_id, user_text, response)

        state["messages"].append({"role": "user", "content": user_text})
        state["messages"].append({"role": "assistant", "content": reply})
        state["messages"] = state["messages"][-MAX_HISTORY:]

        return reply

    except Exception:
        return "⚠️ System busy. Please try again."
