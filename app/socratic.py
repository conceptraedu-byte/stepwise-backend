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

Rules you MUST follow:
- Do NOT give the final answer.
- Do NOT solve the problem.
- Ask only ONE guiding question.
- Keep the tone calm, exam-focused, and encouraging.
- Relate the question to board exam relevance (marks / concept).
- Assume the syllabus is strictly NCERT (2025–26).
- Prefer “why” and “what should we check first” questions.

Student question:
\"\"\"{user_text}\"\"\"

Respond as a Socratic tutor.
"""

    try:
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.4,   # keeps answers focused
                "max_output_tokens": 120
            }
        )

        if not response or not response.text:
            return (
                "Let’s think about this step by step.\n\n"
                "What concept from the syllabus does this question mainly test?"
            )

        return response.text.strip()

    except Exception as e:
        # Failsafe — bot should NEVER crash
        return (
            "Let’s pause for a moment.\n\n"
            "What is the first concept you would identify in this question?"
        )
