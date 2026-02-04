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
# SAFE LOGGING
# =============================
LOG_DIR = "logs"
TRUNCATION_LOG = os.path.join(LOG_DIR, "truncated_generations.log")

def safe_log(path: str, text: str):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    except Exception:
        pass


# =============================
# QUESTION TYPE DETECTION (NEW)
# =============================
def is_definition_question(text: str) -> bool:
    starters = (
        "define",
        "state",
        "what is",
        "give the definition of"
    )
    t = text.lower().strip()
    return any(t.startswith(s) for s in starters)


def is_procedural_question(text: str) -> bool:
    keywords = (
        "find",
        "calculate",
        "solve",
        "using euclid",
        "hcf",
        "lcm",
        "prove",
        "show that",
        "derive"
    )
    t = text.lower()
    return any(k in t for k in keywords)


# =============================
# RAG CONTEXT
# =============================
def build_rag_context(question: str) -> str:
    try:
        chunks = retrieve(question, top_k=3)
        if not chunks:
            return ""
        return "\n\n".join(f"- {c['text']}" for c in chunks)
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

ABSOLUTE RULES:
- Never stop mid-sentence.
- Never give partial answers.
- Do not summarise when steps are required.
- Plain text only. No markdown. No LaTeX.

ANSWER DISCIPLINE:
- Definition questions → ONLY the definition.
- Numerical / Algorithm questions → MUST show every step.
- Proof / Derivation → Logical steps till conclusion.
- End numerical answers with a clear final result.

{board_hint}
{importance_hint}

If the question is outside syllabus:
Say so clearly and give only a basic idea.
"""


# =============================
# PROMPT BUILDER
# =============================
def build_prompt(chat_id: int, user_text: str) -> str:
    state = get_chat_state(chat_id)

    history = ""
    for m in state["messages"]:
        history += f"{m['role'].upper()}: {m['content']}\n"

    rag_context = build_rag_context(user_text)

    definition_rule = ""
    if is_definition_question(user_text):
        definition_rule = """
IMPORTANT:
This is a definition question.
Give ONLY the standard NCERT definition.
Do NOT add explanation, examples, variables, or applications.
"""

    procedure_rule = ""
    if is_procedural_question(user_text):
        procedure_rule = """
IMPORTANT:
This is a procedural / numerical / derivation question.
You MUST:
- Write each step explicitly
- Show all calculations or logical steps
- Continue until a final conclusion is reached
- Do NOT stop early or summarise
"""

    return f"""
{build_system_prompt(state["board"], state["importance"])}

{definition_rule}
{procedure_rule}

REFERENCE MATERIAL (NCERT – use only if relevant):
{rag_context if rag_context else "No reference available."}

Conversation context:
{history}

QUESTION:
{user_text}
"""


# =============================
# GEMINI CALL
# =============================
def generate_response(prompt: str):
    try:
        return client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={"max_output_tokens": 600, "temperature": 0.3}
        )
    except Exception:
        return None


# =============================
# RESPONSE EXTRACTION
# =============================
def extract_text_from_response(response) -> str | None:
    if not response or not response.candidates:
        return None

    parts = []

    for c in response.candidates:
        content = c.content
        if not content:
            continue

        if hasattr(content, "parts") and content.parts:
            for p in content.parts:
                if getattr(p, "text", None):
                    parts.append(p.text)
        elif getattr(content, "text", None):
            parts.append(content.text)

    if not parts:
        return None

    final = "".join(parts).strip()

    if final and final[-1] not in ".!?":
        final += "."

    return final


# =============================
# FALLBACK (ALIGNED)
# =============================
def generate_fallback_answer(question: str) -> str:
    prompt = f"""
You are a Class 10 board exam tutor.

Follow NCERT exam rules strictly.
Do not give partial answers.
Show full steps where required.

QUESTION:
{question}
"""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={"max_output_tokens": 600, "temperature": 0.3}
        )
    except Exception:
        return "Please ask the question clearly."

    text = extract_text_from_response(response)
    return text if text else "Please ask the question clearly."


# =============================
# CLEAR CHAT
# =============================
def clear_chat(chat_id: int) -> str:
    chat_states.pop(chat_id, None)
    return "🆕 New chat started. Ask a fresh question."


# =============================
# MAIN ENTRY
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

    prompt = build_prompt(chat_id, user_text)
    response = generate_response(prompt)

    answer = extract_text_from_response(response)

    if not answer:
        answer = generate_fallback_answer(user_text)

    state["messages"].append({"role": "user", "content": user_text})
    state["messages"].append({"role": "assistant", "content": answer})
    state["messages"] = state["messages"][-MAX_HISTORY:]

    return answer
