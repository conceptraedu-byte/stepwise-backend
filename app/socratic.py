import os
import traceback
from datetime import datetime
from typing import Optional, Dict, Any, List
import google.generativeai as genai
from app.rag.retriever import retrieve
import json

# =====================================================
# Gemini setup
# =====================================================
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_NAME = "models/gemini-flash-latest"
model = genai.GenerativeModel(MODEL_NAME)

# =====================================================
# In-memory chat store
# =====================================================
chat_states: Dict[str, Dict[str, Any]] = {}

def get_state(chat_id: str) -> Dict[str, Any]:
    """Get or create chat state for a given chat ID"""
    if chat_id not in chat_states:
        chat_states[chat_id] = {
            "board": "CBSE",
            "domain": None,
            "subject": None,
            "intent": None,
            "mode": "explain",
            "diagnosis": None,
            "clarification": None,
            "declared_gap": None,
            "micro_history": [],
            "rolling_confidence": 0.5,
            "discipline_score": 0.5,
            "current_training_mode": "guided",
            "verification_answers": None,
            "diagnostic_profile": None,
            "history": [],
            "context_window": [],

            # ==============================
            # SOCRATIC MODE
            # ==============================
            "socratic": {
                "original_question": None,
                "steps": [],
                "current": 0,
                "failures": 0,
                "user_attempts": []
            },

            # ==============================
            # EXAM SIMULATION (SHORT ANSWER)
            # ==============================
            "exam_simulation_active": False,
            "last_expected_keywords": [],
            "last_question_type": None,

            # ==============================
            # 🔥 NEW: FULL MOCK EXAM ENGINE
            # ==============================
            "mock_exam": {
                "active": False,
                "subject": None,
                "current_index": 0,
                "questions": [],
                "answers": [],
                "scores": [],
                "total_score": 0
            },

            "last_question": None,
            "last_topic": None,
            "last_answer": None,

            "mock_active": False,
            "mock_questions": [],
            "mock_current": 0,
            "last_active": datetime.utcnow()
        }

    chat_states[chat_id]["last_active"] = datetime.utcnow()
    return chat_states[chat_id]


def generate_class10_physics_mock():
    """
    Structured 5-question CBSE-style mini mock.
    Each question contains:
    - marks
    - model_answer
    - keywords
    - evaluation_type
    """

    return [

        {
            "type": "definition",
            "marks": 2,
            "evaluation_type": "concept",
            "question": "State Newton's Second Law of Motion.",
            "model_answer": (
                "Newton's Second Law of Motion states that the rate of change "
                "of momentum of an object is directly proportional to the applied "
                "unbalanced force and takes place in the direction of the force. "
                "Mathematically, F = ma."
            ),
            "keywords": [
                "rate of change of momentum",
                "directly proportional",
                "unbalanced force",
                "direction of force",
                "F = ma"
            ]
        },

        {
            "type": "short",
            "marks": 3,
            "evaluation_type": "concept",
            "question": "Define acceleration.",
            "model_answer": (
                "Acceleration is the rate of change of velocity with respect to time. "
                "a = (v - u) / t. "
                "Its SI unit is m/s² and it is a vector quantity."
            ),
            "keywords": [
                "rate of change of velocity",
                "time",
                "a = (v - u) / t",
                "m/s²",
                "vector"
            ]
        },

        {
            "type": "short",
            "marks": 3,
            "evaluation_type": "concept",
            "question": "State Ohm's Law.",
            "model_answer": (
                "Ohm's Law states that at constant temperature, the current "
                "flowing through a conductor is directly proportional to the "
                "potential difference across it. V = IR."
            ),
            "keywords": [
                "constant temperature",
                "directly proportional",
                "current",
                "potential difference",
                "V = IR"
            ]
        },

        {
            "type": "definition",
            "marks": 2,
            "evaluation_type": "concept",
            "question": "What is power in electricity?",
            "model_answer": (
                "Electric power is the rate at which electrical energy is consumed "
                "or work is done in an electric circuit. "
                "P = VI. The SI unit of power is Watt."
            ),
            "keywords": [
                "rate",
                "electrical energy",
                "P = VI",
                "watt"
            ]
        },

        {
            "type": "numerical",
            "marks": 3,
            "evaluation_type": "numerical",
            "question": "A force of 20 N acts on a 5 kg object. Find the acceleration.",
            "model_answer": (
                "Given: F = 20 N, m = 5 kg. "
                "Using Newton's Second Law: F = ma. "
                "a = F/m = 20/5 = 4 m/s²."
            ),
            "keywords": [
                "F = ma",
                "20",
                "5",
                "4",
                "m/s²"
            ]
        }
    ]


# =====================================================
# Gemini helpers
# =====================================================
def gemini(prompt: str, temperature: float = 0.7) -> Optional[str]:
    """Call Gemini API with error handling"""
    try:
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=2048,
        )
        res = model.generate_content(prompt, generation_config=generation_config)
        return res.text.strip() if res and hasattr(res, "text") else None
    except Exception as e:
        traceback.print_exc()
        print(f"Gemini API error: {e}")
        return None


def clean_latex(text: str) -> str:
    """
    Remove LaTeX formatting and convert to readable plain text.
    Converts $$...$$, $...$, and \(...\) to plain text.
    """
    import re
    
    if not text:
        return text
    
    # Remove display math $$...$$
    text = re.sub(r'\$\$([^$]+)\$\$', r'\1', text)
    
    # Remove inline math $...$
    text = re.sub(r'\$([^$]+)\$', r'\1', text)
    
    # Remove \(...\)
    text = re.sub(r'\\$$([^)]+)\\$$', r'\1', text)
    
    # Remove \[...\]
    text = re.sub(r'\\\[([^\]]+)\\\]', r'\1', text)
    
    # Clean up common LaTeX commands
    replacements = {
        r'\\frac{([^}]+)}{([^}]+)}': r'\1/\2',  # \frac{a}{b} -> a/b
        r'\\sqrt{([^}]+)}': r'√\1',             # \sqrt{x} -> √x
        r'\\times': '×',
        r'\\div': '÷',
        r'\\cdot': '·',
        r'\\pi': 'π',
        r'\\alpha': 'α',
        r'\\beta': 'β',
        r'\\gamma': 'γ',
        r'\\theta': 'θ',
        r'\\Delta': 'Δ',
        r'\\sum': 'Σ',
        r'\\int': '∫',
        r'\\le': '≤',
        r'\\ge': '≥',
        r'\\approx': '≈',
        r'\\degree': '°',
        r'\^2': '²',
        r'\^3': '³',
        r'\\\\': '\n',  # Line breaks
        r'\\text{([^}]+)}': r'\1',  # \text{abc} -> abc
        r'\\mathrm{([^}]+)}': r'\1',
        r'\\mathbf{([^}]+)}': r'\1',
    }
    
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    
    # Remove any remaining backslashes before common letters
    text = re.sub(r'\\([a-zA-Z])', r'\1', text)
    
    return text


# =====================================================
# KEYWORD EXTRACTION (SIMPLE BOARD MODE)
# =====================================================
def extract_keywords(answer: str) -> List[str]:
    """
    Extract important keywords from tutor answer.
    Simple frequency-based filtering.
    """

    import re

    # Lowercase and remove punctuation
    text = re.sub(r'[^\w\s]', '', answer.lower())
    words = text.split()

    # Remove common stopwords
    stopwords = {
        "the", "is", "a", "an", "of", "and", "to", "in",
        "that", "it", "as", "for", "on", "with", "this",
        "are", "be", "by", "or", "at", "from"
    }

    filtered = [w for w in words if w not in stopwords and len(w) > 3]

    # Count frequency
    from collections import Counter
    counts = Counter(filtered)

    # Take top 5 meaningful words
    keywords = [word for word, _ in counts.most_common(5)]

    return keywords


# =====================================================
# IMPROVED FOLLOW-UP DETECTION
# =====================================================
def is_followup_question(question: str, history: List[Dict[str, str]]) -> bool:
    """
    Detect if question is a follow-up using multiple signals.
    Returns True if this is likely a follow-up question.
    """
    question_lower = question.lower().strip()
    
    # No history = can't be a follow-up
    if not history:
        return False
    
    # Single word responses (except complete questions)
    if len(question.split()) == 1:
        single_word_exceptions = ["what", "why", "how", "when", "where", "who"]
        if question_lower not in single_word_exceptions:
            return True
    
    # Very short questions without question words
    if len(question.split()) < 4:
        question_words = ["what", "why", "how", "when", "where", "who", "define", "explain", "prove", "derive", "solve"]
        if not any(word in question_lower for word in question_words):
            return True
    
    # Explicit follow-up indicators
    followup_indicators = [
        "example", "examples", "more", "another", "else", "too",
        "elaborate", "clarify", "explain that", "explain this",
        "what about", "how about", "tell me more", "show me",
        "give me", "can you", "could you", "also", "as well"
    ]
    if any(indicator in question_lower for indicator in followup_indicators):
        return True
    
    # Short confirmations/responses
    short_responses = [
        "yes", "no", "ok", "okay", "sure", "fine", "right",
        "continue", "next", "go on", "proceed", "i see", "got it"
    ]
    if question_lower in short_responses:
        return True
    
    # Questions without a "?" but too short to be standalone
    if "?" not in question and len(question.split()) < 6:
        return True
    
    return False


def is_diagnostic_greeting(question: str) -> bool:
    """Detect if this is a vague diagnostic starter that needs clarification"""
    question_lower = question.lower().strip()
    
    diagnostic_phrases = [
        "i don't understand the idea",
        "i understand the idea, but not the formula",
        "i get stuck when solving questions",
        "i don't know where i'm stuck",
        "i'm confused",
        "i need help",
        "help me understand",
    ]
    
    return any(phrase in question_lower for phrase in diagnostic_phrases)


def extract_topic_from_conversation(history: List[Dict[str, str]]) -> Optional[str]:
    """
    Extract the main topic from recent conversation history using LLM.
    Returns the topic being discussed.
    """
    if not history or len(history) < 2:
        return None
    
    # Get last few exchanges
    recent = history[-4:]  # Last 2 exchanges
    conversation = "\n".join([
        f"{msg['role']}: {msg['content'][:200]}"
        for msg in recent
    ])
    
    prompt = f"""Extract the main topic being discussed in this conversation.
Return ONLY the topic name (2-5 words maximum), nothing else.

Conversation:
{conversation}

Topic:"""
    
    topic = gemini(prompt, temperature=0.3)
    return topic.strip() if topic else None


def build_contextualized_question(
    user_input: str,
    last_question: str,
    last_topic: str,
    last_answer: str,
    history: List[Dict[str, str]]
) -> str:
    """
    Build a complete, context-aware question from a follow-up using LLM.
    This is more intelligent than simple template matching.
    """
    
    # Build conversation context
    recent_history = ""
    if history:
        recent = history[-4:]
        recent_history = "\n".join([
            f"{msg['role']}: {msg['content'][:150]}"
            for msg in recent
        ])
    
    prompt = f"""You are helping reconstruct a complete question from a follow-up.

Recent conversation:
{recent_history}

User's follow-up input: {user_input}

Task: Convert this follow-up into a complete, standalone question that includes the topic context.

Rules:
- If they say "example", ask for an example of the topic
- If they say "more" or "elaborate", ask for more details on the topic
- If they say "how" or "why", complete the question with the topic
- Make it a natural, complete question

Complete question:"""
    
    result = gemini(prompt, temperature=0.5)
    
    # Fallback to simple template if LLM fails
    if not result:
        user_lower = user_input.lower()
        if "example" in user_lower:
            return f"Give me an example of {last_topic or 'that'}"
        elif "more" in user_lower or "elaborate" in user_lower:
            return f"Explain more about {last_topic or 'that'}"
        elif "how" in user_lower:
            return f"How does {last_topic or 'that'} work?"
        elif "why" in user_lower:
            return f"Why is {last_topic or 'that'} important?"
        else:
            return f"{last_question} - {user_input}"
    
    return result.strip()


# =====================================================
# CLASSIFIERS
# =====================================================
def classify_domain(question: str, history: List[Dict[str, str]]) -> tuple[str, Optional[str]]:
    """
    Classify whether question is about maths or science.
    If science, also identify the specific subject.
    
    Returns: (domain, subject)
    """
    
    # Build context from recent history
    context = ""
    if history:
        recent = history[-4:]
        context = "Recent conversation:\n"
        for msg in recent:
            context += f"{msg['role']}: {msg['content'][:100]}...\n"
    
    prompt = f"""Classify this question into domain and subject.

{context}

Current question: {question}

Analyze the question and respond ONLY with this exact format:
domain: [maths OR science]
subject: [physics OR chemistry OR biology OR none]

Rules:
- If question is about mathematics, algebra, geometry, calculus, statistics, etc. → domain: maths, subject: none
- If question is about physics, motion, forces, electricity, etc. → domain: science, subject: physics
- If question is about chemistry, reactions, compounds, elements, etc. → domain: science, subject: chemistry
- If question is about biology, cells, organisms, life processes, etc. → domain: science, subject: biology

Examples:
"What is Pythagorean theorem?" → domain: maths, subject: none
"Explain Newton's laws" → domain: science, subject: physics
"What is photosynthesis?" → domain: science, subject: biology
"Balance this equation: H2 + O2" → domain: science, subject: chemistry
"""
    
    response = gemini(prompt, temperature=0.3)
    if not response:
        return "maths", None
    
    # Parse response
    domain = "maths"
    subject = None
    
    for line in response.lower().split('\n'):
        if 'domain:' in line:
            if 'science' in line:
                domain = "science"
            else:
                domain = "maths"
        if 'subject:' in line:
            if 'physics' in line:
                subject = "physics"
            elif 'chemistry' in line:
                subject = "chemistry"
            elif 'biology' in line:
                subject = "biology"
    
    return domain, subject


#Diagnstic Analyzer

def fallback_profile(diagnosis: Optional[str]) -> Dict[str, str]:
    """
    Safe fallback if LLM fails.
    """
    return {
        "weakness_type": diagnosis or "conceptual_gap",
        "confidence_level": "low",
        "recommended_teaching_mode": "intuitive",
        "diagnostic_scores": {}
    }


def analyze_student_profile(

    diagnosis: Optional[str],
    verification_answers: Dict[str, str],
    topic: str
) -> Dict[str, str]:

     # 🔒 SAFETY CHECK — ADD THIS
    if verification_answers is None:
        return fallback_profile(diagnosis)
    """
    Advanced diagnostic profiling with:
    - Structured feature extraction (LLM-assisted)
    - Deterministic weakness classification
    - Explainable decision logic
    """

    prompt = f"""
You are a cognitive learning evaluator.

Topic: {topic}

Student answers:
1. {verification_answers.get("q1")}
2. {verification_answers.get("q2")}
3. {verification_answers.get("q3")}

Evaluate the student's understanding using the following metrics (0.0 to 1.0 scale):

Return ONLY valid JSON in this format:

{{
  "conceptual_accuracy": float,
  "procedural_accuracy": float,
  "terminology_precision": float,
  "reasoning_coherence": float,
  "misconception_detected": true/false,
  "uncertainty_detected": true/false
}}
"""

    try:
        raw = gemini(prompt, temperature=0.2)
        features = json.loads(raw)
    except Exception:
        return fallback_profile(diagnosis)

    # -------------------------------
    # Extract feature values safely
    # -------------------------------

    conceptual = float(features.get("conceptual_accuracy", 0))
    procedural = float(features.get("procedural_accuracy", 0))
    terminology = float(features.get("terminology_precision", 0))
    coherence = float(features.get("reasoning_coherence", 0))
    misconception = bool(features.get("misconception_detected", False))
    uncertainty = bool(features.get("uncertainty_detected", False))

    # -------------------------------
    # Weakness Classification Logic
    # -------------------------------

    if misconception:
        weakness = "misconception"

    elif conceptual < 0.4:
        weakness = "conceptual_gap"

    elif procedural < 0.4:
        weakness = "procedural_gap"

    elif terminology < 0.4:
        weakness = "formula_confusion"

    elif uncertainty and avg_score < 0.6:
        weakness = "low_confidence"

    else:
        # If everything looks okay, trust initial diagnosis
        weakness = "no_major_gap"

    # -------------------------------
    # Confidence Level Calculation
    # -------------------------------

    avg_score = (conceptual + procedural + coherence + terminology) / 4

    if avg_score < 0.4:
        confidence = "low"
    elif avg_score < 0.7:
        confidence = "medium"
    else:
        confidence = "high"

    # -------------------------------
    # Teaching Mode Mapping
    # -------------------------------

    if weakness == "conceptual_gap":
        mode = "guided"

    elif weakness == "procedural_gap":
        mode = "structural"

    elif weakness == "misconception":
        mode = "socratic"

    elif weakness == "formula_confusion":
        mode = "structural"

    elif weakness == "low_confidence":
        mode = "guided"

    elif weakness == "no_major_gap":
        mode = "structural"

    else:
        mode = "socratic"

    return {
        "weakness_type": weakness,
        "confidence_level": confidence,
        "confidence_score": round(avg_score, 2),
        "recommended_teaching_mode": mode,
        "diagnostic_scores": {
            "conceptual_accuracy": conceptual,
            "procedural_accuracy": procedural,
            "terminology_precision": terminology,
            "reasoning_coherence": coherence,
            "misconception_detected": misconception,
            "uncertainty_detected": uncertainty
        }
    }


def micro_diagnose_student_response(
    topic: str,
    student_response: str
) -> Dict:

    prompt = f"""
You are a strict cognitive evaluator.

Topic: {topic}

Student response:
{student_response}

Evaluate using 0.0 to 1.0 scale.

Return ONLY JSON:

{{
  "reasoning_depth": float,
  "structural_discipline": float,
  "misconception_detected": true/false,
  "confidence_signal": float
}}
"""

    try:
        raw = gemini(prompt, temperature=0.2)
        features = json.loads(raw)
    except:
        return {
            "reasoning_depth": 0.5,
            "structural_discipline": 0.5,
            "misconception_detected": False,
            "confidence_signal": 0.5
        }

    return features



def classify_intent(question: str, domain: str, history: List[Dict[str, str]]) -> str:
    """
    Classify the intent of the question.
    
    Returns: concept | example | derivation | numerical | followup
    """
    
    # Build context
    context = ""
    if history:
        recent = history[-2:]
        context = "Recent conversation:\n"
        for msg in recent:
            context += f"{msg['role']}: {msg['content'][:150]}...\n"
    
    prompt = f"""Classify the intent of this question.

{context}

Current question: {question}
Domain: {domain}

Respond with ONLY ONE word from these options:
- concept (asking for explanation/definition of a concept)
- example (asking for examples or applications)
- derivation (asking to prove/derive a formula or theory)
- numerical (asking to solve a numerical problem)
- followup (asking for clarification/elaboration on previous topic)

Question: {question}

Intent:"""
    
    response = gemini(prompt, temperature=0.2)
    if not response:
        return "concept"
    
    intent = response.strip().lower()
    
    # Validate response
    valid_intents = ["concept", "example", "derivation", "numerical", "followup"]
    for valid in valid_intents:
        if valid in intent:
            return valid
    
    return "concept"


# =====================================================
# EXAM QUESTION TYPE CLASSIFIER (BOARD MODE)
# =====================================================
def classify_exam_question_type(question: str) -> str:
    """
    Classify question into board exam answer type.
    Returns:
        - definition
        - short
        - derivation
        - numerical
    """

    prompt = f"""
You are analyzing a CBSE board exam question.

Classify the question into one of these types:
- definition (1–2 mark direct theory)
- short (2–3 mark explanation)
- derivation (long theoretical derivation, 4–5 marks)
- numerical (calculation based problem)

Respond with ONLY one word:
definition / short / derivation / numerical

Question:
{question}

Type:
"""

    response = gemini(prompt, temperature=0.2)

    if not response:
        return "short"

    result = response.strip().lower()

    if "definition" in result:
        return "definition"
    if "derivation" in result:
        return "derivation"
    if "numerical" in result:
        return "numerical"

    return "short"



# =====================================================
# SOCRATIC STEP GENERATION
# =====================================================
def generate_steps(domain: str, subject: Optional[str], question: str) -> List[str]:
    """Generate step-by-step questions for Socratic mode"""
    
    subject_info = f" ({subject})" if subject else ""
    
    prompt = f"""You are an expert {domain}{subject_info} tutor.

Break down this problem into 4-6 logical steps that guide the student to solve it themselves.

CRITICAL RULES:
- Each step should be a guiding QUESTION, not a statement
- Steps should be progressive and build on each other
- Use SIMPLE, conversational language
- NEVER use LaTeX, $$, or mathematical markup
- Use plain text: write "I = mr²" not "$$I = mr^2$$"
- Use Unicode: ² ³ √ π α β θ × ÷
- Keep each step SHORT (1 line)
- Number each step (1., 2., 3., etc.)

Problem:
{question}

Generate steps:"""
    
    text = gemini(prompt, temperature=0.7)
    if not text:
        return []
    
    steps = []
    for line in text.split("\n"):
        line = line.strip()
        if line and len(line) > 3 and line[0].isdigit() and '.' in line[:3]:
            step_text = line.split(".", 1)[-1].strip()
            if step_text and len(step_text) > 10:
                steps.append(step_text)
    
    return steps[:6]


def check_student_answer(step_question: str, student_answer: str, domain: str) -> bool:
    """Check if student's answer to a step is correct"""
    
    prompt = f"""You are evaluating a student's answer to a guided question.

Domain: {domain}

Question: {step_question}

Student's answer: {student_answer}

Is the student's understanding correct and on the right track?

Respond with ONLY one word:
- correct (if answer shows understanding and is on right track)
- incorrect (if answer is wrong or shows misunderstanding)

Evaluation:"""
    
    response = gemini(prompt, temperature=0.3)
    return response and "correct" in response.lower()


def explain_step(domain: str, subject: Optional[str], step: str, context: str) -> str:
    """Explain a step when student struggles"""
    
    subject_info = f" ({subject})" if subject else ""
    
    prompt = f"""You are a patient {domain}{subject_info} tutor.

The student is struggling with this step:
{step}

Problem context:
{context}

Provide a clear, simple explanation with an example.

CRITICAL RULES:
- Keep it VERY SHORT (2-3 lines maximum)
- Include ONE brief example (1 line)
- Use plain text only - NO LaTeX, NO $$
- Use Unicode: ² ³ √ π × ÷
- Be encouraging
- Write "F = ma" not "$$F = ma$$"

Explanation:"""
    
    return gemini(prompt, temperature=0.7) or "Let me rephrase: " + step


# =====================================================
# PROMPT BUILDERS
# =====================================================
def build_explanation_prompt(
    board: str,
    domain: str,
    subject: Optional[str],
    intent: str,
    question: str,
    history: List[Dict[str, str]],
    teaching_mode: Optional[str] = None,
    question_type: Optional[str] = None,
    clarification: Optional[str] = None,
    declared_gap: Optional[str] = None
) -> str:
    """Build prompt for board-exam optimized explanation mode"""

    # Retrieve relevant context from RAG
    context_docs = retrieve(question)
    context = "\n".join(d["text"] for d in context_docs[:3]) if context_docs else ""

    # Build conversation history
    history_text = ""
    if history:
        recent = history[-6:]
        history_text = "Previous conversation:\n"
        for msg in recent:
            role = msg['role'].capitalize()
            content = msg['content'][:250]
            history_text += f"{role}: {content}\n"

    subject_info = f" - {subject}" if subject else ""

    # =========================
    # BOARD STRUCTURE INSTRUCTION
    # =========================
    exam_instruction = ""

    if question_type == "definition":
        exam_instruction = (
            "Answer strictly in 1–2 mark board format. "
            "Start with a clear definition sentence. "
            "Add formula if applicable."
        )

    elif question_type == "short":
        exam_instruction = (
            "Answer in proper 2–3 mark format. "
            "Use 2–3 structured key points. "
            "Keep it concise and keyword-rich."
        )

    elif question_type == "derivation":
        exam_instruction = (
            "Answer in proper 5 mark derivation format. "
            "Show logical step-by-step progression clearly."
        )

    elif question_type == "numerical":
        exam_instruction = (
            "Solve step-by-step. "
            "Write formula first, then substitute values, "
            "then give final answer with correct units."
        )

    # =========================
    # TEACHING MODE INSTRUCTION
    # =========================
    if teaching_mode == "intuitive":
        teaching_instruction = "Start with intuition and a simple real-world analogy before formal explanation."

    elif teaching_mode == "structural":
        teaching_instruction = "Break down the formula term-by-term and explain each variable clearly."

    elif teaching_mode == "guided":
        teaching_instruction = "Explain briefly, then end with one reflective question to test understanding."

    elif teaching_mode == "socratic":
        teaching_instruction = "Do not explain directly. Start with a probing question."

    else:
        teaching_instruction = "Keep explanation clear, direct, and exam-focused."

    focus_instruction = ""

    if clarification:
        focus_instruction += f"""
    Student previously clarified confusion:
    "{clarification}"

    Focus STRICTLY on resolving this confusion.
    Avoid re-explaining what is already understood.
    """

    if declared_gap:
        focus_instruction += f"""
    Declared weakness type: {declared_gap}.
    Adjust explanation emphasis accordingly.
    """

    # =========================
    # FINAL PROMPT
    # =========================
    prompt = f"""
You are a strict {board} board exam {domain}{subject_info} tutor.

Board Answer Style Instruction:
{exam_instruction}

Teaching Mode Adjustment:
{teaching_instruction}

{history_text}

Reference material:
{context}

{focus_instruction}

Current question:
{question}

CRITICAL RULES:
- Follow the board answer style strictly.
- Use clear structured sentences.
- Avoid storytelling.
- Avoid unnecessary extra information.
- NEVER use LaTeX or $$.
- Use plain text only (F = ma, m/s², etc.).
- Keep it exam-ready and evaluator-friendly.
- No bullet points unless absolutely required by structure.

Response:
"""

    return prompt


def evaluate_exam_answer(
    question: str,
    model_answer: str,
    student_answer: str,
    board: str,
    question_type: str
) -> dict:
    """
    Evaluate student's board-style answer using LLM grading.
    Returns structured JSON result.
    """

    # Define mark scheme
    mark_scheme = {
        "definition": 2,
        "short": 3,
        "long": 5,
        "derivation": 5,
        "numerical": 5
    }

    max_score = mark_scheme.get(question_type, 3)

    prompt = f"""
You are a strict {board} board examiner.

QUESTION:
{question}

MODEL ANSWER:
{model_answer}

STUDENT ANSWER:
{student_answer}

Your task:
1. Compare student answer with model answer.
2. Identify correctness, missing concepts, and clarity.
3. Award marks out of {max_score}.
4. Be fair but strict like a real board evaluator.

IMPORTANT:
- Respond ONLY in valid JSON.
- Do NOT add explanation outside JSON.
- Use this exact format:

{{
  "score": integer,
  "max_score": {max_score},
  "strengths": ["point1", "point2"],
  "missing_concepts": ["point1", "point2"],
  "improvement_advice": "text",
  "model_improved_answer": "ideal full-mark answer"
}}
"""

    try:
        response = gemini(prompt)

        if not response:
            raise ValueError("Empty LLM response")

        result = json.loads(response)

        # Safety validation
        if "score" not in result:
            raise ValueError("Invalid JSON format")

        return result

    except Exception as e:
        print("Evaluation error:", e)

        # Fallback safe response
        return {
            "score": 0,
            "max_score": max_score,
            "strengths": [],
            "missing_concepts": ["Evaluation failed"],
            "improvement_advice": "Try writing answer clearly using board terminology.",
            "model_improved_answer": model_answer
        }


# =====================================================
# MAIN CHAT ENGINE
# =====================================================
def chat_reply(
    chat_id: int,
    user_text: str,
    reset: bool = False,
    board: Optional[str] = None,
) -> str:

    # =====================================================
    # RESET
    # =====================================================
    if reset:
        chat_states.pop(chat_id, None)
        return "Session reset. Ask me any question!"

    state = get_state(chat_id)

    if board:
        state["board"] = board

    user_text = user_text.strip()
    if not user_text:
        return "Please ask a question."

    # =====================================================
    # MICRO-DIAGNOSIS (CONTROLLED TRIGGER)
    # Only when:
    # - Diagnostic profile exists
    # - User message length meaningful
    # - Not in mock mode
    # =====================================================
    if (
        state.get("diagnostic_profile")
        and not state.get("mock_active")
        and len(user_text.split()) > 12
    ):

        topic = state.get("last_topic", "") or state.get("last_question", "")

        micro = micro_diagnose_student_response(
            topic=topic,
            student_response=user_text
        )

        state["micro_history"].append(micro)
        state["micro_history"] = state["micro_history"][-5:]

        # Update rolling confidence
        avg_conf = sum(
            m.get("confidence_signal", 0.5)
            for m in state["micro_history"]
        ) / len(state["micro_history"])

        state["rolling_confidence"] = round(avg_conf, 2)

        # Update discipline score
        avg_disc = sum(
            m.get("structural_discipline", 0.5)
            for m in state["micro_history"]
        ) / len(state["micro_history"])

        state["discipline_score"] = round(avg_disc, 2)

        # Dynamic training mode
        if any(m.get("misconception_detected") for m in state["micro_history"]):
            state["current_training_mode"] = "socratic"

        elif state["discipline_score"] < 0.4:
            state["current_training_mode"] = "structural"

        elif state["rolling_confidence"] < 0.4:
            state["current_training_mode"] = "guided"

        elif any(m["misconception_detected"] for m in state["micro_history"]):
            state["current_training_mode"] = "socratic"

        else:
            state["current_training_mode"] = "socratic"

    # =====================================================
    # START CLASS 10 PHYSICS MOCK
    # =====================================================
    if user_text.lower() in ["start class 10 physics mock", "start physics mock"]:

        state["mock_questions"] = generate_class10_physics_mock()
        state["mock_current"] = 0
        state["mock_active"] = True

        first_q = state["mock_questions"][0]["question"]
        return f"Class 10 Physics Mini Mock Started.\n\nQuestion 1:\n{first_q}"

    # =====================================================
    # HANDLE MOCK ANSWERS
    # =====================================================
    if state.get("mock_active"):

        current_q = state["mock_questions"][state["mock_current"]]
        keywords = current_q["keywords"]
        max_marks = current_q["marks"]

        score = 0
        for word in keywords:
            if word.lower() in user_text.lower():
                score += 1

        final_score = min(max_marks, round((score / len(keywords)) * max_marks))

        feedback = f"Score: {final_score}/{max_marks}\n"

        matched = [k for k in keywords if k.lower() in user_text.lower()]
        missing = [k for k in keywords if k.lower() not in user_text.lower()]

        if matched:
            feedback += "\nStrengths:\n"
            for m in matched:
                feedback += f"- {m}\n"

        if missing:
            feedback += "\nMissing Concepts:\n"
            for m in missing:
                feedback += f"- {m}\n"

        state["mock_current"] += 1

        if state["mock_current"] < len(state["mock_questions"]):
            next_q = state["mock_questions"][state["mock_current"]]["question"]
            feedback += f"\nNext Question:\n{next_q}"
        else:
            feedback += "\nMock Completed."
            state["mock_active"] = False

        return feedback

    # =====================================================
    # EXAM SIMULATION
    # =====================================================
    if state.get("exam_simulation_active"):

        evaluation = evaluate_exam_answer(
            question=state.get("last_question"),
            model_answer=state.get("last_answer"),
            student_answer=user_text,
            board=state.get("board"),
            question_type=state.get("last_question_type", "short")
        )

        feedback = f"Score: {evaluation['score']}/{evaluation['max_score']}\n\n"

        if evaluation.get("strengths"):
            feedback += "Strengths:\n"
            for s in evaluation["strengths"]:
                feedback += f"- {s}\n"

        if evaluation.get("missing_concepts"):
            feedback += "\nMissing Concepts:\n"
            for m in evaluation["missing_concepts"]:
                feedback += f"- {m}\n"

        feedback += f"\nImprovement Advice:\n{evaluation['improvement_advice']}\n\n"
        feedback += f"Ideal Full-Mark Answer:\n{evaluation['model_improved_answer']}"

        state["exam_simulation_active"] = False
        state["history"].append({"role": "user", "content": user_text})
        state["history"].append({"role": "assistant", "content": feedback})
        state["last_answer"] = feedback

        return feedback

    # =====================================================
    # FOLLOW-UP + CLASSIFICATION
    # =====================================================
    original_question = user_text

    if is_followup_question(user_text, state["history"]):
        user_text = build_contextualized_question(
            user_text,
            state.get("last_question", ""),
            state.get("last_topic", ""),
            state.get("last_answer", ""),
            state["history"]
        )

    domain, subject = classify_domain(user_text, state["history"])
    intent = classify_intent(user_text, domain, state["history"])
    question_type = classify_exam_question_type(user_text)

    state["domain"] = domain
    state["subject"] = subject
    state["intent"] = intent
    state["question_type"] = question_type
    state["last_question"] = user_text

    # =====================================================
    # DERIVATION / NUMERICAL → SOCRATIC
    # =====================================================
    if question_type in ("derivation", "numerical"):

        steps = generate_steps(domain, subject, user_text)

        if steps:
            state["socratic"] = {
                "original_question": user_text,
                "steps": steps,
                "current": 0,
                "failures": 0,
                "user_attempts": []
            }
            state["mode"] = "socratic"

            return f"Let's solve step by step.\n\nStep 1: {steps[0]}"

    # =====================================================
    # EXPLANATION MODE (ADAPTIVE)
    # =====================================================
    teaching_mode = state.get("current_training_mode")

    prompt = build_explanation_prompt(
        state["board"],
        domain,
        subject,
        intent,
        user_text,
        state["history"],
        teaching_mode=teaching_mode,
        question_type=question_type,
        clarification=state.get("clarification"),
        declared_gap=state.get("diagnosis")
    )

    answer = clean_latex(gemini(prompt) or "Please rephrase your question.")

    state["history"].append({"role": "user", "content": original_question})
    state["history"].append({"role": "assistant", "content": answer})
    state["last_answer"] = answer

    if question_type in ("definition", "short"):
        state["exam_simulation_active"] = True
        state["last_question_type"] = question_type
        answer += "\n\nNow write this answer in proper board exam format (2-mark style)."

    if len(state["history"]) > 20:
        state["history"] = state["history"][-20:]

    return answer

# =====================================================
# SESSION CLEANUP
# =====================================================
def cleanup_old_sessions(max_age_hours: int = 24):
    """Remove inactive chat sessions"""
    now = datetime.utcnow()
    to_remove = []
    
    for chat_id, state in chat_states.items():
        age = (now - state["last_active"]).total_seconds() / 3600
        if age > max_age_hours:
            to_remove.append(chat_id)
    
    for chat_id in to_remove:
        chat_states.pop(chat_id, None)
    
    return len(to_remove)