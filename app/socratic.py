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
MAX_HISTORY = 10
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
# ✅ NEW: SYLLABUS + IMPORTANT TOPICS (CBSE + STATE BOARDS)
# =========================================================

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
                },
                "boards": ["CBSE", "TN", "AP", "TS", "KA"]
            },
            "electricity": {
                "topics": {
                    "electric current": "important",
                    "potential difference": "important",
                    "ohm's law": "very_important",
                    "resistance": "important",
                    "electric power": "very_important"
                },
                "boards": ["CBSE", "TN", "AP", "TS"]
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
                },
                "boards": ["CBSE", "TN", "AP"]
            }
        }
    }
}

# =========================================================
# ✅ NEW: TOPIC DETECTION (LIGHTWEIGHT, RULE-BASED)
# =========================================================

def detect_topic(user_text: str):
    text = user_text.lower()

    for class_key, subjects in SYLLABUS.items():
        for subject, chapters in subjects.items():
            for chapter, data in chapters.items():
                for topic in data["topics"]:
                    if topic in text:
                        return {
                            "class": class_key.replace("_", " "),
                            "subject": subject,
                            "chapter": chapter,
                            "topic": topic,
                            "importance": data["topics"][topic]
                        }
    return None

# -----------------------------
# SYSTEM PROMPTS (UX-FIRST)
# -----------------------------
BASE_SYSTEM_PROMPT = """
You are a CBSE Class 10 & 12 tutor.

GENERAL RULES (VERY IMPORTANT):
- Give SHORT, exam-ready answers by default.
- Start directly with the definition or final answer.
- Use plain-text math only (no LaTeX, no markdown).
- Use Unicode symbols where helpful (², −).
- Write as if evaluated by a CBSE examiner.
- Focus only on the concept asked.
- Do not introduce related concepts unless requested.
- Assume the student is reading on a mobile phone.

ANSWER LENGTH CONTROL:
- "Define", "State", "Give" → 3–5 lines only.
- "Explain", "Why", "How" → 6–8 short lines.
- "Derive", "Prove" → step-wise format only.

INTERACTIVITY RULE:
- After a SHORT answer, end with ONE prompt:
  "Want steps or an example?"
- Do NOT ask follow-up questions after expanded answers.
- If the answer is complete, STOP.

FOLLOW-UP HANDLING:
- If the student asks "steps", "explain", "example", or similar,
  treat it as a follow-up to the PREVIOUS concept.
- Do not restart the topic.

STEP-WISE EXPLANATION RULES:
- Use 3 to 5 short numbered steps only.
- Use plain text (no headings, no bold, no markdown).
- Do NOT use words like "derivation".
- Use simple formulas like: a = (v − u) / t
- Do NOT ask another follow-up question.

If the student asks "explain in detail":
- Explain the SAME answer again in simple language.
- Use at most 6–8 short lines.
- Do NOT restart the proof from scratch.
- Do NOT introduce new steps.
- Do NOT stop mid-sentence.

CLARITY RULE:
- If the student question is vague or incomplete,
  ask ONE clarification question instead of assuming.
"""

SOCRATIC_RULES = """
You are acting as a Socratic tutor.

RULES:
- Do NOT give the final answer.
- Ask ONLY ONE guiding question.
- Keep it simple and exam-oriented.
- No explanations, no hints beyond one question.
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

    history_text = ""
    for m in state["messages"]:
        history_text += f"{m['role'].upper()}: {m['content']}\n"

    mode_prompt = SOCRATIC_RULES if state["mode"] == "socratic" else ""

    return f"""
{BASE_SYSTEM_PROMPT}
{mode_prompt}

The student may ask follow-up questions referring to the previous answer.

Previous conversation (for context only):
{history_text}

STUDENT QUESTION:
{user_text}
"""

# -----------------------------
# Gemini call with retry
# -----------------------------
def generate_with_retry(prompt, retries=2, delay=2):
    for attempt in range(retries + 1):
        try:
            return client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "max_output_tokens": 600,
                    "temperature": 0.4
                }
            )
        except Exception as e:
            if "503" in str(e) and attempt < retries:
                time.sleep(delay)
                continue
            raise

# -----------------------------
# Response extraction
# -----------------------------
def extract_text(response) -> str:
    texts = []

    try:
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

    except Exception:
        return "⚠️ Response parsing error. Please try again."

    if texts:
        return "\n".join(dict.fromkeys(texts)).strip()

    return "⚠️ I couldn’t generate a response. Please try again."

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

    # 🔍 Detect topic (NEW)
    detected = detect_topic(user_text)
    if detected:
        state["class"] = detected["class"]
        state["subject"] = detected["subject"]
        state["chapter"] = detected["chapter"]
        state["last_topic"] = detected["topic"]

    if mode in ("direct", "socratic"):
        state["mode"] = mode

    prompt = build_prompt(chat_id, user_text)

    try:
        response = generate_with_retry(prompt)
        reply = extract_text(response)

        add_message(chat_id, "user", user_text)
        add_message(chat_id, "assistant", reply)

        return reply

    except Exception:
        return "⚠️ System busy. Please try again."
