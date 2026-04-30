from app.utils.json_parser import safe_json_extract


# ================= VALIDATION =================
def is_valid_eval(data):
    if not isinstance(data, dict):
        return False

    if "is_correct" not in data:
        return False

    return True


# ================= MAIN EVALUATION =================
def evaluate_answer_llm(topic, question, expected, user_input, chat_reply):
    prompt = f"""
You are a strict but fair evaluator.

Topic: {topic}

Question: {question}

Expected Answer: {expected}

Student Answer: {user_input}

Return ONLY JSON:

{{
  "is_correct": true/false,
  "reason": "short reason",
  "missing": "what is missing (if wrong)"
}}

Rules:
- Accept semantically correct answers
- DO NOT require exact wording
- Be LENIENT for conceptual answers
- Only mark wrong if concept is clearly incorrect
- Do NOT add explanation outside JSON
"""

    for attempt in range(1):
        response = chat_reply(
            chat_id="eval",
            user_text=prompt
        )

        # 🔥 FIXED LINE
        data = safe_json_extract(response, "object")

        if is_valid_eval(data):
            return data

        print(f"EVAL RETRY {attempt+1} FAILED:", response)

    # ---------- FALLBACK ----------
    print("EVAL FALLBACK TRIGGERED")

    user = user_input.lower()
    expected_lower = expected.lower()

    if any(word in user for word in expected_lower.split()):
        return {
            "is_correct": True,
            "reason": "Close enough answer",
            "missing": ""
        }

    return {
        "is_correct": False,
        "reason": "Answer does not match expected concept",
        "missing": "Revise the core idea"
    }