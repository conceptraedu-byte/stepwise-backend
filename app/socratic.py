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
# QUESTION TYPE DETECTION (ADDED)
# =============================
def is_definition_question(text: str) -> bool:
    t = text.lower().strip()
    return t.startswith(("define", "state", "what is", "give the definition of"))


def is_procedural_question(text: str) -> bool:
    keywords = (
        "find", "calculate", "solve",
        "using", "hcf", "lcm",
        "prove", "show that", "derive"
    )
    t = text.lower()
    return any(k in t for k in keywords)


def is_proof_question(text: str) -> bool:
    t = text.lower()
    return t.startswith("prove") or "prove that" in t



def build_forced_output_format(question: str) -> str:
    q = question.lower()

    if is_definition_question(question):
        return """
MANDATORY OUTPUT FORMAT:
- Write ONLY the definition.
- One paragraph.
- No introduction.
- No explanation.
- No example.
"""

    if "prove" in q or "show that" in q:
        return """
MANDATORY OUTPUT FORMAT:
Step 1: State the assumption clearly.
Step 2: Express the assumption in mathematical form.
Step 3: Apply known theorems or properties.
Step 4: Reach a contradiction.
Conclusion: State why the assumption is false.
(No introduction. No explanation outside steps.)
"""

    if any(k in q for k in ("hcf", "lcm", "find", "calculate", "prove")):
        return """
MANDATORY OUTPUT FORMAT:
Step 1:
Step 2:
Step 3:
Final Answer:
(No introduction sentence allowed.)
"""

    return ""


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
# SYSTEM PROMPT (STRENGTHENED)
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

ABSOLUTE RULES (NO EXCEPTIONS):
- NEVER explain what you are going to do.
- NEVER write introductory sentences.
- NEVER stop mid-answer.
- NEVER summarise instead of solving.
- Plain text only. No markdown. No LaTeX.

ANSWER DISCIPLINE:
- Definition → exact NCERT definition only.
- Numerical / Algorithm → every step must be shown.
- Proof / Derivation → logical steps until conclusion.
- End numericals with a clear final answer.

{board_hint}
{importance_hint}
"""


# =============================
# PROMPT BUILDER (CRITICAL FIX)
# =============================
def build_prompt(chat_id: int, user_text: str) -> str:
    state = get_chat_state(chat_id)

    history = ""
    for m in state["messages"]:
        history += f"{m['role'].upper()}: {m['content']}\n"

    rag_context = build_rag_context(user_text)
    forced_format = build_forced_output_format(user_text)

    return f"""
{build_system_prompt(state["board"], state["importance"])}

{forced_format}

REFERENCE MATERIAL (NCERT – use only if relevant):
{rag_context if rag_context else "No reference available."}

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
            config={"max_output_tokens": 700, "temperature": 0.2}
        )
    except Exception:
        return None


# =============================
# RESPONSE EXTRACTION (SAFE)
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
Show full steps.
Do not explain intentions.

{build_forced_output_format(question)}

QUESTION:
{question}
"""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={"max_output_tokens": 700, "temperature": 0.2}
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
