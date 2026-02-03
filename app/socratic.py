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
# Conversation state (IN-MEMORY)
# ⚠️ Single-user only (testing)
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

RULES:
- Start directly with the definition or final answer.
- Do NOT begin with introductory or filler sentences.
- Be concise, clear, and exam-oriented.
- Use step-by-step explanations only after the answer.
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

# -----------------------------
# Gemini call with retry (503 safe)
# -----------------------------
def generate_with_retry(prompt, retries=2, delay=2):
    for attempt in range(retries + 1):
        try:
            return client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "max_output_tokens": 700,
                    "temperature": 0.4
                }
            )
        except Exception as e:
            if "503" in str(e) and attempt < retries:
                time.sleep(delay)
                continue
            raise

# -----------------------------
# Robust response extraction
# -----------------------------
def extract_text(response) -> str:
    texts = []

    try:
        for candidate in (response.candidates or []):
            content = candidate.content
            if not content:
                continue

            # Case 1: content.text
            if hasattr(content, "text") and content.text:
                texts.append(content.text)

            # Case 2: content.parts[].text
            parts = getattr(content, "parts", None)
            if parts:
                for part in parts:
                    if hasattr(part, "text") and part.text:
                        texts.append(part.text)

    except Exception as e:
        return f"⚠️ Response parsing error: {e}"

    # Last fallback
    if not texts and hasattr(response, "text") and response.text:
        texts.append(response.text)

    if texts:
        seen = set()
        final = []
        for t in texts:
            if t not in seen:
                final.append(t)
                seen.add(t)
        return "\n".join(final).strip()

    return "⚠️ Gemini returned an empty response."

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
        response = generate_with_retry(prompt)
        reply = extract_text(response)

        add_message("user", user_text)
        add_message("assistant", reply)

        return reply

    except Exception as e:
        return f"ERROR FROM GEMINI: {str(e)}"
