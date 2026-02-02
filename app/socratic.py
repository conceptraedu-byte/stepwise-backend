import os
import google.generativeai as genai

# -------------------------------
# Gemini setup
# -------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set")

genai.configure(api_key=GEMINI_API_KEY)

model = genai.GenerativeModel("gemini-1.5-flash")


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
- Keep it exam-focused (marks, concept, NCERT)
- Prefer “what should we check first” or “why”

Student question:
\"\"\"{user_text}\"\"\"
"""

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.4,
                "max_output_tokens": 120
            }
        )

        # ✅ Correct way to extract text
        if (
            not response.candidates
            or not response.candidates[0].content.parts
        ):
            raise RuntimeError("Empty Gemini response")

        return response.candidates[0].content.parts[0].text.strip()

    except Exception as e:
        # TEMPORARY: show real error during debugging
        return f"⚠️ Gemini error: {str(e)}"
