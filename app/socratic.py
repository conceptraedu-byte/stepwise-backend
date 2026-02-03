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
- "Define", "State", "Give" → 2–3 lines only.
- "Explain", "Why", "How" → 4–6 short lines.
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
def clear_chat():
    chat_state["mode"] = "direct"
    chat_state["messages"] = []
    return "🆕 New chat started. Ask a fresh question."

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

Previous conversation (for context only):
{history_text}

STUDENT QUESTION:
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
# Robust response extraction
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

    except Exception as e:
        return f"⚠️ Response parsing error: {e}"

    if texts:
        seen = set()
        final = []
        for t in texts:
            if t not in seen:
                final.append(t)
                seen.add(t)
        return "\n".join(final).strip()

    return "⚠️ I couldn’t generate a response. Please try again."

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
        return f"⚠️ System busy. Please try again."
