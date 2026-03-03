import os
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("models/gemini-flash-latest")


def generate_explanation(question_text: str,
                               correct_option: str,
                               selected_option: str,
                               subject: str,
                               class_level: int):

    prompt = f"""
You are a CBSE {class_level} {subject} teacher.

A student answered this question incorrectly.

Question:
{question_text}

Student's Answer:
{selected_option}

Correct Answer:
{correct_option}

Explain clearly in 3–4 lines:
1. Why the correct answer is correct.
2. Why the student's answer is wrong (if applicable).
3. Keep it simple and exam-focused.
No long paragraphs.
No markdown.
No extra commentary
"""

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.3,
            "max_output_tokens": 200
        }
    )

    return response.text.strip()
