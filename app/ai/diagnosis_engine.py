def diagnose_student_answer(question: str, student_answer: str, ideal_answer: str):

    prompt = f"""
You are an expert CBSE examiner and learning scientist.

Your task is to analyze a student's answer and identify the
underlying learning mistake.

Question:
{question}

Student Answer:
{student_answer}

Ideal Answer:
{ideal_answer}

Return ONLY JSON in this structure:

{{
"correct": true/false,

"score": number_between_0_and_10,

"diagnosis_type": "",

"weak_concepts": [],

"reasoning_feedback": "",

"improvement_steps": [],

"next_difficulty": "easy | medium | hard"
}}

Possible diagnosis types:
- conceptual_misunderstanding
- calculation_error
- incomplete_reasoning
- correct_but_unclear
- fully_correct
"""

    return gemini(prompt)