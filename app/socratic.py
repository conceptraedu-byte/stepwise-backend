import os
import google.generativeai as genai

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

model = genai.GenerativeModel("gemini-pro")

def socratic_reply(user_text: str) -> str:
    user_text = user_text.strip()

    if not user_text:
        return "Please type your question."

    prompt = f"""
You are a Socratic tutor for CBSE Class 10 & 12 students.

Rules:
- Do NOT give the final answer
- Ask ONLY one guiding question
- Be exam-oriented (NCERT, marks-focused)
- Keep tone calm and encouraging

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

        return response.text.strip()

    except Exception as e:
        return "Let’s pause and think. What concept from the syllabus does this question test?"
