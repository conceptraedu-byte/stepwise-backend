import os
import google.generativeai as genai
from app.rag.retriever import retrieve

print("🚨 APP/SOCRATIC.PY LOADED 🚨")

# =============================
# Gemini client
# =============================
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


MODEL_NAME = "gemini-1.5-flash"
model = genai.GenerativeModel(MODEL_NAME)

# =============================
# Conversation state
# =============================
MAX_HISTORY = 8
chat_states = {}


def get_chat_state(chat_id: int):
    if chat_id not in chat_states:
        chat_states[chat_id] = {
            "messages": [],
            "board": "CBSE",

            # Tutor state
            "mode": None,          # normal | proof | numerical
            "step": 0,
            "active_question": None,
            "hint_level": 0        # NEW
        }
    return chat_states[chat_id]


# =============================
# Question classification
# =============================
def is_definition_question(text: str) -> bool:
    return text.lower().startswith(
        ("define", "state", "what is", "give the definition of")
    )


def is_proof_question(text: str) -> bool:
    t = text.lower()
    return t.startswith("prove") or "prove that" in t


def is_numerical_question(text: str) -> bool:
    return any(k in text.lower() for k in (
        "find", "calculate", "solve", "hcf", "lcm", "using"
    ))


def is_uncertain_answer(text: str) -> bool:
    return text.strip().lower() in (
        "idk", "i don't know", "dont know", "?", "no idea", "skip"
    )


# =============================
# Tutor flows
# =============================
PROOF_STEPS = [
    "What is the definition of a rational number?",
    "Assume the given number is rational. How can you write it in the form a/b?",
    "What condition can we assume about a and b?",
    "Square both sides. What equation do you get?",
    "What can you say about the parity of a?",
    "What does this imply about b?",
    "What contradiction do you observe?",
    "What is the final conclusion?"
]

PROOF_HINTS = [
    ["Think about numbers that can be written as p/q."],
    ["Use integers a and b, with no common factors."],
    ["They should have no common factor other than 1."],
    ["Square √2 = a/b."],
    ["If a² is even, what about a?" ],
    ["If a is even, what about b?" ],
    ["This violates an earlier assumption."],
    ["State clearly what is proved."]
]

NUMERICAL_STEPS = [
    "Which of the given numbers is larger?",
    "Apply Euclid’s division lemma to the larger number.",
    "Is the remainder zero? If not, repeat the process.",
    "Continue until the remainder becomes zero.",
    "Which number is the HCF?"
]

NUMERICAL_HINTS = [
    ["Compare the numbers directly."],
    ["Write it in the form a = bq + r."],
    ["Check whether r = 0."],
    ["Repeat with the divisor and remainder."],
    ["The last non-zero divisor is the answer."]
]


# =============================
# Socratic engine
# =============================
def handle_socratic(state, user_text, steps, hints):
    step = state["step"]

    # Start
    if step == 0:
        state["step"] = 1
        state["hint_level"] = 0
        return (
            "Let us solve this step by step.\n\n"
            f"Step 1:\n{steps[0]}"
        )

    # Handle uncertainty
    if is_uncertain_answer(user_text):
        hint = hints[step - 1][min(state["hint_level"], len(hints[step - 1]) - 1)]
        state["hint_level"] += 1
        return f"Hint:\n{hint}"

    # Advance
    if step < len(steps):
        state["step"] += 1
        state["hint_level"] = 0
        return (
            "Good.\n\n"
            f"Step {state['step']}:\n{steps[step]}"
        )

    # Completion
    state["mode"] = None
    state["step"] = 0
    state["hint_level"] = 0
    state["active_question"] = None

    return (
        "Correct.\n\n"
        "You have completed all the steps.\n"
        "Now state the final answer clearly."
    )


# =============================
# Normal prompt (definitions / theory)
# =============================
def build_prompt(board: str, question: str) -> str:
    return f"""
You are a Class 10 & 12 board exam tutor.
Use strict NCERT wording.
Answer clearly and concisely.

QUESTION:
{question}
"""


def generate_response(prompt: str):
    try:
        return model.generate_content(prompt)
    except Exception:
        return None



def extract_text(response):
    if not response or not response.candidates:
        return None
    parts = []
    for c in response.candidates:
        for p in getattr(c.content, "parts", []):
            if getattr(p, "text", None):
                parts.append(p.text)
    return "".join(parts).strip() if parts else None


# =============================
# Clear chat
# =============================
def clear_chat(chat_id: int) -> str:
    chat_states.pop(chat_id, None)
    return "🆕 New chat started. Ask a fresh question."


# =============================
# Main entry
# =============================
def chat_reply(chat_id: int, user_text: str, reset=False, board=None) -> str:

    if reset:
        return clear_chat(chat_id)

    if not user_text.strip():
        return "Please type your answer or question."

    state = get_chat_state(chat_id)

    if board:
        state["board"] = board

    # Ongoing Socratic modes
    if state["mode"] == "proof":
        reply = handle_socratic(state, user_text, PROOF_STEPS, PROOF_HINTS)

    elif state["mode"] == "numerical":
        reply = handle_socratic(state, user_text, NUMERICAL_STEPS, NUMERICAL_HINTS)

    # New question detection
    elif is_proof_question(user_text):
        state["mode"] = "proof"
        state["step"] = 0
        state["active_question"] = user_text
        reply = handle_socratic(state, user_text, PROOF_STEPS, PROOF_HINTS)

    elif is_numerical_question(user_text):
        state["mode"] = "numerical"
        state["step"] = 0
        state["active_question"] = user_text
        reply = handle_socratic(state, user_text, NUMERICAL_STEPS, NUMERICAL_HINTS)

    else:
        prompt = build_prompt(state["board"], user_text)
        response = generate_response(prompt)
        reply = extract_text(response) or "Please try again."

    state["messages"].append({"role": "user", "content": user_text})
    state["messages"].append({"role": "assistant", "content": reply})
    state["messages"] = state["messages"][-MAX_HISTORY:]

    return reply
