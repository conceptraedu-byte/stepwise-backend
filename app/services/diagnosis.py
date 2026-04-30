import json
import re
from app.utils.json_parser import safe_json_extract

# ================= JSON EXTRACTION =================
def extract_json(text):
    try:
        start = text.find("{")
        end = text.rfind("}")

        if start == -1 or end == -1:
            return {}

        json_str = text[start:end + 1]

        try:
            return json.loads(json_str)
        except:
            pass

        # fix broken JSON
        json_str = json_str.replace("\n", " ")
        json_str = re.sub(r'"[^"]*$', '"', json_str)

        return json.loads(json_str)

    except Exception as e:
        print("DIAGNOSIS JSON ERROR:", e)
        return {}


# ================= VALIDATION =================
def is_valid_diag(data):
    if not isinstance(data, dict):
        return False

    if "reason" not in data:
        return False

    return True


# ================= MAIN FUNCTION =================
def diagnose_answer(topic, step, user_input, chat_reply):
    prompt = f"""
You are diagnosing a student's mistake.

Topic: {topic}

Question: {step["question"]}

Expected Answer: {step["expected_answer"]}

Student Answer: {user_input}

Return ONLY JSON:

{{
  "mistake_type": "conceptual_error | formula_error | incomplete | wrong_logic",
  "reason": "what exactly is wrong",
  "missing_concept": "what they missed",
  "hint": "short hint (no answer)"
}}

Rules:
- Be VERY specific
- Do NOT give full answer
- Do NOT be generic
- Keep hint short and guiding
"""

    # 🔥 retry for reliability
    for attempt in range(1):
        response = chat_reply(
            chat_id="diagnosis",
            user_text=prompt
        )

        data = safe_json_extract(response, "object")

        if is_valid_diag(data):
            return data

        print(f"DIAGNOSIS RETRY {attempt+1} FAILED:", response)

    # ================= FALLBACK =================
    print("DIAGNOSIS FALLBACK USED")

    user = user_input.lower()

    # simple heuristic fallback
    if "speed" in user and "velocity" in step["question"].lower():
        return {
            "mistake_type": "conceptual_error",
            "reason": "You are confusing speed with velocity",
            "missing_concept": "Velocity includes direction",
            "hint": "Think about displacement, not just speed"
        }

    return {
        "mistake_type": "unknown",
        "reason": "Your answer does not match the expected concept",
        "missing_concept": "Core idea is missing",
        "hint": "Focus on the definition and key idea"
    }