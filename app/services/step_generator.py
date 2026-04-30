import json
import re
from app.utils.json_parser import safe_json_extract

# ================= JSON EXTRACTION =================
def extract_json(text):
    try:
        start = text.find("[")
        end = text.rfind("]")

        if start == -1 or end == -1:
            return []

        json_str = text[start:end + 1]

        try:
            return json.loads(json_str)
        except:
            pass

        # fix broken JSON
        json_str = json_str.replace("\n", " ")
        json_str = re.sub(r'"[^"]*$', '"', json_str)
        json_str = re.sub(r',\s*{[^}]*$', '', json_str)

        return json.loads(json_str)

    except Exception as e:
        print("STEP JSON ERROR:", e)
        return []


# ================= VALIDATION =================
def is_valid_steps(steps):
    if not isinstance(steps, list):
        return []

    valid = []

    for step in steps:
        if not isinstance(step, dict):
            continue

        if not step.get("question") or not step.get("expected_answer"):
            continue

        # enforce MCQ validity
        if step.get("input_mode") == "mcq":
            options = step.get("options", [])
            if len(options) != 4:
                continue

        valid.append(step)

    return valid if len(valid) >= 2 else []


# ================= CLEANING =================
def clean_text(text):
    if not text:
        return ""

    text = text.split("\n")[0]
    text = text.split("Now write")[0]
    return text.strip()


def clean_steps(steps):
    cleaned = []

    for step in steps:
        question = clean_text(step.get("question", ""))
        expected = clean_text(step.get("expected_answer", ""))

        # limit answer length
        if len(expected) > 80:
            expected = expected[:80]

        options = step.get("options", [])

        # normalize MCQ options
        if step.get("input_mode") == "mcq":
            options = [opt.strip() for opt in options if opt]

        cleaned.append({
            "type": step.get("type", "concept"),
            "question": question,
            "expected_answer": expected,
            "input_mode": step.get("input_mode", "short"),
            "options": options,
            "common_mistakes": step.get("common_mistakes", [])
        })

    return cleaned


# ================= QUALITY FILTER =================
def improve_step_quality(steps):
    improved = []

    for step in steps:
        q = step["question"].lower()

        # reject bad questions
        if len(q) < 10:
            continue

        if "write" in q or "explain in detail" in q:
            continue

        if "according to cbse" in q:
            step["question"] = step["question"].replace(
                "according to CBSE standards", ""
            ).strip()

        improved.append(step)

    return improved


# ================= STRUCTURE ENFORCER =================
def enforce_structure(steps):
    if len(steps) < 2:
        return steps

    # force order: concept → formula → application
    steps[0]["type"] = "concept"
    if len(steps) > 1:
        steps[1]["type"] = "formula"
    if len(steps) > 2:
        steps[2]["type"] = "application"

    return steps


# ================= FINAL GENERATOR =================
def generate_steps(topic, chat_reply):
    prompt = f"""
Create a structured learning flow.

Topic: {topic}

Generate EXACTLY 3 steps:

1. Concept (simple definition)
2. Formula (if applicable)
3. Application (MCQ)

Return ONLY JSON:

[
  {{
    "type": "concept",
    "question": "Short simple question",
    "expected_answer": "short answer",
    "input_mode": "short",
    "options": [],
    "common_mistakes": []
  }},
  {{
    "type": "formula",
    "question": "Ask formula",
    "expected_answer": "formula",
    "input_mode": "short",
    "options": [],
    "common_mistakes": []
  }},
  {{
    "type": "application",
    "question": "MCQ question",
    "expected_answer": "correct option text",
    "input_mode": "mcq",
    "options": ["option1", "option2", "option3", "option4"],
    "common_mistakes": []
  }}
]

Rules:
- Keep questions SHORT
- Keep answers SHORT
- No explanation
- Only JSON
"""

    for attempt in range(1):
        response = chat_reply(
            chat_id="step_gen",
            user_text=prompt
        )

        steps = safe_json_extract(response, "array")
        valid = is_valid_steps(steps)

        if valid:
            cleaned = clean_steps(valid[:3])
            improved = improve_step_quality(cleaned)
            structured = enforce_structure(improved)

            if structured:
                return structured

        print(f"STEP GEN RETRY {attempt+1} FAILED")

    # ================= FALLBACK =================
    print("STEP GEN FALLBACK USED")

    return [
        {
            "type": "concept",
            "question": f"What is {topic}?",
            "expected_answer": topic,
            "input_mode": "short",
            "options": [],
            "common_mistakes": []
        },
        {
            "type": "formula",
            "question": f"Give a formula related to {topic}",
            "expected_answer": topic,
            "input_mode": "short",
            "options": [],
            "common_mistakes": []
        },
        {
            "type": "application",
            "question": f"Which is correct about {topic}?",
            "expected_answer": "option1",
            "input_mode": "mcq",
            "options": ["option1", "option2", "option3", "option4"],
            "common_mistakes": []
        }
    ]