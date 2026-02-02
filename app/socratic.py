import os
from google import genai

# -----------------------------
# Gemini client (NEW SDK)
# -----------------------------
client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL = "models/gemini-2.0-flash"  # ✅ CURRENTLY SUPPORTED


def socratic_reply(user_text: str) -> str:
    if not user_text or not user_text.strip():
        return "Please type your question."

    prompt = f"""
You are a Socratic tutor for CBSE Class 10 & 12 students.

Rules:
- Do NOT give the final answer.
- Ask ONLY ONE guiding question.
- Focus on NCERT concepts.
- Be exam-oriented.
- Encourage thinking, not solving.

Student question:
{user_text}

Ask your Socratic question now.
"""

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt
        )

        return response.text.strip()

    except Exception as e:
        return (
            "Let’s pause and think carefully.\n\n"
            "Which chapter or core concept does this question belong to?"
        )
