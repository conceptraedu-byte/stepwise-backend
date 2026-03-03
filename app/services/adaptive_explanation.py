import json
import re
from typing import Dict, Any

from app.socratic import gemini


# =====================================================
# SAFE JSON EXTRACTION
# =====================================================
def extract_json(text: str) -> Dict[str, Any] | None:
    """
    Extracts the first valid JSON object from LLM output.
    Handles markdown fences and extra text safely.
    """

    if not text:
        return None

    # Remove markdown code fences if present
    text = text.strip()
    text = re.sub(r"```json", "", text)
    text = re.sub(r"```", "", text)

    # Extract first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    json_block = match.group()

    try:
        return json.loads(json_block)
    except Exception:
        return None


# =====================================================
# FALLBACK STRUCTURE
# =====================================================
def fallback_structure() -> Dict[str, Any]:
    return {
        "definition": "Structured explanation could not be generated.",
        "core_concept": "",
        "formula": "",
        "stepwise_logic": [],
        "common_mistakes": [],
        "exam_format_answer": "",
        "reinforcement_question": ""
    }


# =====================================================
# MAIN ADAPTIVE EXPLANATION GENERATOR
# =====================================================
def generate_adaptive_explanation(state: dict) -> dict:

    topic = state.get("last_question") or state.get("last_topic") or "the given topic"
    diagnosis = state.get("diagnosis")
    profile = state.get("diagnostic_profile", {})
    confidence = profile.get("confidence_level", "unknown")
    weakness = profile.get("weakness_type", "general")
    depth = state.get("teaching_depth", "board")

    prompt = f"""
You are a strict CBSE board exam tutor.

Generate a structured teaching explanation for the topic: {topic}

Student weakness type: {weakness}
Confidence score: {confidence}
Diagnosis category: {diagnosis}
Teaching depth: {depth}

If depth is:
- simple → Use easy language, short sentences, basic examples.
- board → Standard CBSE structured explanation.
- advanced → Deeper reasoning, edge cases, conceptual expansion.

Respond ONLY in valid JSON with this exact structure:

{{
  "definition": "...",
  "core_concept": "...",
  "formula": "...",
  "stepwise_logic": ["...", "...", "..."],
  "common_mistakes": ["...", "..."],
  "exam_format_answer": "...",
  "reinforcement_question": "..."
}}

No extra text.
No markdown.
Only valid JSON.
"""

    raw = gemini(prompt)

    if not raw:
        return fallback_structure()

    structured = extract_json(raw)

    if not structured:
        return fallback_structure()

    # Ensure required keys exist (safety validation)
    required_keys = [
        "definition",
        "core_concept",
        "formula",
        "stepwise_logic",
        "common_mistakes",
        "exam_format_answer",
        "reinforcement_question"
    ]

    for key in required_keys:
        if key not in structured:
            structured[key] = "" if key not in ["stepwise_logic", "common_mistakes"] else []

    return structured