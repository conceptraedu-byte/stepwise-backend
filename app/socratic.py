import os
from google import genai

# -----------------------------
# Gemini client
# -----------------------------
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL = "models/gemini-flash-latest"

# -----------------------------
# Conversation state (IN-MEMORY)
# -----------------------------
MAX_HISTORY = 10

chat_state = {
    "mode": "direct",          # direct | socratic
    "messages": []             # [{"role": "user"/"assistant", "content": "..."}]
}

# -----------------------------
# Base system prompt
# -----------------------------
BASE_SYSTEM_PROMPT = """
You are an educational assistant for CBSE Class 10 & 12 students.
Answer clearly, correctly, and exam-oriented.
Use step-by-step explanations when required.
Do not assume prior context unless provided.
"""

SOCRATIC_RULES = """
You are acting as a Socratic tutor.

Rules:
- Do NOT give the final answer.
- Ask ONLY ONE guiding question.
- Focus on NCERT concepts.
- Be exam-oriented.
- Encourage thinking, not solving.
"""

# -----------------------------
# Utilities
# -----------------------------
def clear_chat():
    chat_state["mode"] = "direct"
    chat_state["messages"] = []
    return "New chat started."

def add_message(role, content):
    chat_state["messages"].append({"role": role, "content": content})
    if len(chat_state["messages"]) > MAX_HISTORY:
        chat_state["messages"] = chat_state["messages"][-MAX_HISTORY:]

def build_prompt(user_text: str) -> str:
    history_text = ""
    for m in chat_state["messages"]:
        history_text += f"{m['role'].upper()}: {m['content']}\n"

    mode_prompt = SOCRATIC_RULES if chat_state["mode"] == "socratic" else ""

    return f"""
{BASE_SYSTEM_PROMPT}
{mode_prompt}

Conversation so far:
{history_text}

USER QUESTION:
{user_text}
"""

def extract_text(response) -> str:
    """
    Robust text extraction for google.genai SDK
    """
    texts = []

    try:
        for candidate in response.candidates:
            content = candidate.content
            if not content:
                continue

            for part in content.parts:
                if hasattr(part, "text") and part.text:
                    texts.append(part.text)

    except Exception as e:
        return f"⚠️ Response parsing error: {e}"

    if texts:
        return "\n".join(texts).strip()

    return "⚠️ Gemini returned no text output."


# -----------------------------
# Main entry function
# -----------------------------
def chat_reply(user_text: str, mode: str | None = None, reset: bool = False) -> str:
    if reset:
        return clear_chat()

    if not user_text or not user_text.strip():
        return "Please type your question."

    # Explicit mode switch
    if mode in ("direct", "socratic"):
        chat_state["mode"] = mode

    prompt = build_prompt(user_text)

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={
                "max_output_tokens": 300,
                "temperature": 0.4
            }
        )

        reply = extract_text(response)

        add_message("user", user_text)
        add_message("assistant", reply)

        return reply

    except Exception as e:
        return f"ERROR FROM GEMINI: {str(e)}"
