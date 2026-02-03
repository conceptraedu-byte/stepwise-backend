import os
import time
from google import genai

# -----------------------------
# Gemini client
# -----------------------------
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL = "models/gemini-flash-latest"

# -----------------------------
# Per-user conversation state (IN-MEMORY)
# -----------------------------
MAX_HISTORY = 8
chat_states = {}  # chat_id -> state


def get_chat_state(chat_id: int):
    if chat_id not in chat_states:
        chat_states[chat_id] = {
            "mode": "direct",
            "messages": [],
            "class": None,
            "subject": None,
            "chapter": None,
            "last_topic": None
        }
    return chat_states[chat_id]

# =========================================================
# SYLLABUS + IMPORTANT TOPICS (CBSE + STATE BOARDS)
# =========================================================

SYLLABUS = {
    "class_10": {
        "physics": {
            "motion": {
                "topics": [
                    "distance", "velocity", "acceleration",
                    "equations of motion", "graphs of motion"
                ]
            },
            "electricity": {
                "topics": [
                    "electric current", "potential difference",
                    "ohm's law", "resistance", "electric power"
                ]
            }
        }
    },
    "class_12": {
        "physics": {
            "electrostatics": {
                "topics": [
                    "coulomb's law", "electric field", "electric potential"
                ]
            }
        }
    }
}

# =========================================================
# Topic detection
# =========================================================

def detect_topic(user_text: str):
    text = user_text.lower()

    for cls, subjects in SYLLABUS.items():
        for subject, chapters in subjects.items():
            for chapter, data in chapters.items():
                for topic in data["topics"]:
                    if topic in text:
                        return {
                            "class": cls.replace("_", " "),
                            "subject": subject,
                            "chapter": chapter,
                            "topic": topic
                        }
    return None

# =========================================================
# OFF-SYLLABUS KEYWORDS (HARD GUARD)
# =========================================================

OFF_SYLLABUS_KEYWORDS = [
    "schrodinger", "quantum", "wave function",
    "relativity", "black hole", "string theory"
]

def is_off_syllabus(user_text: str) -> bool:
    text = user_text.lower()
    return any(k in text for k in OFF_SYLLABUS_KEYWORDS)

# -----------------------------
# SYSTEM PROMPTS (HARDENED)
# -----------------------------
BASE_SYSTEM_PROMPT = """
You are a CBSE and State Board tutor for Class 10 and 12 students.

ABSOLUTE RULES (DO NOT VIOLATE):
- NEVER stop mid-sentence or mid-step.
- ALWAYS complete the response you start.
- If a question is outside syllabus, do NOT attempt full derivations.
- In such cases, give a short conceptual explanation only.

ANSWER STYLE:
- Start directly with the answer.
- Keep answers exam-ready and concise.
- Use plain-text math only (no LaTeX, no markdown).
- Use Unicode symbols like ², − where helpful.

LENGTH CONTROL:
- Define / State / Give → short (2–5 lines)
- Explain / Why / How → medium (5–8 lines)
- Derive / Prove → step-wise ONLY if syllabus allows

FOLLOW-UP RULES:
- "steps", "explain", "example" refer to the previous topic.
- Do not restart the topic.
- Do not ask follow-up questions after expanded answers.
"""

SOCRATIC_RULES = """
You are acting as a Socratic tutor.

RULES:
- Ask ONLY ONE guiding question.
- Do NOT give the final answer.
- Keep it short and exam-oriented.
"""

# -----------------------------
# Utilities
# -----------------------------
def clear_chat(chat_id: int):
    state = get_chat_state(chat_id)
    state.update({
        "mode": "direct",
        "messages": [],
        "class": None,
        "subject": None,
        "chapter": None,
        "last_topic": None
    })
    return "🆕 New chat started. Ask a fresh question."


def add_message(chat_id: int, role: str, content: str):
    state = get_chat_state(chat_id)
    state["messages"].append({"role": role, "content": content})
    if len(state["messages"]) > MAX_HISTORY:
        state["messages"] = state["messages"][-MAX_HISTORY:]


def build_prompt(chat_id: int, user_text: str) -> str:
    state = get_chat_state(chat_id)

    history = ""
    for m in state["messages"]:
        history += f"{m['role'].upper()}: {m['content']}\n"

    mode_prompt = SOCRATIC_RULES if state["mode"] == "socratic" else ""

    return f"""
{BASE_SYSTEM_PROMPT}
{mode_prompt}

Conversation context:
{history}

STUDENT QUESTION:
{user_text}
"""

# -----------------------------
# Gemini call (SAFE)
# -----------------------------
def generate_response(prompt):
    return client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "max_output_tokens": 500,
            "temperature": 0.3
        }
    )

# -----------------------------
# Response extraction (GUARANTEED COMPLETE)
# -----------------------------
def extract_text(response) -> str:
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

    if texts:
        final = "\n".join(dict.fromkeys(texts)).strip()
        if final[-1] not in ".!?":
            final += "."
        return final

    return "I couldn’t generate a complete answer. Please try again."

# -----------------------------
# Main entry function
# -----------------------------
def chat_reply(
    chat_id: int,
    user_text: str,
    mode: str | None = None,
    reset: bool = False
) -> str:

    if reset:
        return clear_chat(chat_id)

    if not user_text or not user_text.strip():
        return "Please type your question."

    state = get_chat_state(chat_id)

    # 🔍 Topic detection
    detected = detect_topic(user_text)
    if detected:
        state.update(detected)

    # 🚫 HARD STOP for off-syllabus long questions
    if detected is None and is_off_syllabus(user_text):
        return (
            "This topic is outside the CBSE and State Board syllabus.\n\n"
            "At this level, only the basic idea is expected.\n"
            "If you want, I can explain the concept in simple terms."
        )

    if mode in ("direct", "socratic"):
        state["mode"] = mode

    prompt = build_prompt(chat_id, user_text)

    try:
        response = generate_response(prompt)
        reply = extract_text(response)

        add_message(chat_id, "user", user_text)
        add_message(chat_id, "assistant", reply)

        return reply

    except Exception:
        return "⚠️ System busy. Please try again."
