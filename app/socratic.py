import os
from google import genai

# -------------------------------
# Gemini setup (NEW SDK)
# -------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set")

client = genai.Client(api_key=GEMINI_API_KEY)


# -------------------------------
# Core Socratic reply function
# -------------------------------
def socratic_reply(user_text: str) -> str:
    user_text = user_text.strip()

    if not user_text:
        return "Please type your question."

    prompt = f"""
You are a Socratic tutor for Indian board exam students (CBSE Class 10 & 12).

Rules:
- Do NOT give the final answer
- Do NOT solve the problem
- Ask only ONE guiding question
- Be exam-focused (marks, NCERT relevance)
- Prefer “what should we check first” or “why”

Student question:
\"\"\"{user_text}\"\"\"
"""

    try:
        response = client.models.generate_content(
            model="gemini-1.0-pro",
            contents=prompt,
            config={
                "temperature": 0.4,
                "max_output_tokens": 120
            }
        )

        if not response.text:
            raise RuntimeError("Empty Gemini response")

        return response.text.strip()

    except Exception as e:
        # keep bot alive, but expose error during dev
        return f"⚠️ Gemini error: {str(e)}"
