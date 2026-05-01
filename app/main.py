
from dotenv import load_dotenv
load_dotenv()
import os
import os
import google.generativeai as genai
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL_NAME = "models/gemini-flash-latest"
model = genai.GenerativeModel(MODEL_NAME)
import json
import re
from fastapi import HTTPException, APIRouter
from app.services.evaluator import evaluate_answer_llm
from app.services.subscription_scheduler import start_scheduler
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import asyncio
from bson import ObjectId
from app.services.razorpay_client import client as razorpay_client
from app.services.credit_manager import check_credits, consume_credits, CHAT_COST, MOCK_COST
from app.mock_explainer import generate_explanation
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials,  OAuth2PasswordBearer
from app.services.adaptive_explanation import generate_adaptive_explanation
from app.services.adaptive_explanation import extract_json
from app.services.learning_steps import get_gravity_steps
from app.services.diagnosis import diagnose_answer
from app.services.step_generator import generate_steps



import time
print("SYSTEM TIME:", int(time.time()))

from app.socratic import chat_reply, cleanup_old_sessions, get_state, analyze_student_profile
from app.telegram import router as telegram_router
from app.db import init_db
import app.db as db

# =========================
# APP INIT
# =========================
app = FastAPI(
    title="StepWise AI",
    description="AI-powered tutoring system with Socratic method",
    version="2.0.0"
)
  



oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

security = HTTPBearer()

async def get_current_user(token: str = Depends(oauth2_scheme)):

    print("Auth header received:", token)

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")

        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

    user = await db.users_collection.find_one({"_id": ObjectId(user_id)})

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    return user


def sanitize_json_string(text: str) -> str:
    # Remove markdown
    text = re.sub(r"```json|```", "", text)

    # Replace problematic quotes inside values
    text = text.replace('\n', ' ')
    text = re.sub(r'(?<!\\)"(?=.*?:)', '"', text)  # keep key quotes safe

    return text.strip()


# =========================
# CORS (REQUIRED FOR ANGULAR)
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://localhost:3000",
        "https://neon-kleicha-d90bd1.netlify.app"
        # Add your production domain here
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# STARTUP & SHUTDOWN
# =========================
@app.on_event("startup")
async def startup_event():
    """Initialize database and start background tasks"""
    print("🚀 Starting StepWise AI...")
    init_db()
    start_scheduler()
    print("✅ Database initialized")
    print("✅ Server ready")

class MockQuestionResponse(BaseModel):
    id: str
    question: str
    options: List[str]

class MockSubmitRequest(BaseModel):
    answers: Dict[str, int]
    session_id: str  # question_id -> selected_index




pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    class_level: int
    board: str

class VerifyPaymentRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class LoginRequest(BaseModel):
    email: str
    password: str


import hashlib

def hash_password(password: str):
    sha = hashlib.sha256(password.encode()).hexdigest()
    return pwd_context.hash(sha)

def verify_password(plain_password, hashed_password):
    sha = hashlib.sha256(plain_password.encode()).hexdigest()
    return pwd_context.verify(sha, hashed_password)


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):

    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")

        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        user = await db.users_collection.find_one({"_id": ObjectId(user_id)})

        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        return user

    except JWTError as e:
        print("JWT decode error:", str(e))
        raise HTTPException(status_code=401, detail="Invalid token")

SECRET_KEY = "your_super_secret_key_here"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@app.post("/billing/verify-payment")
async def verify_payment(
    data: VerifyPaymentRequest,
    current_user: dict = Depends(get_current_user)
):

    try:

        params_dict = {
            "razorpay_order_id": data.razorpay_order_id,
            "razorpay_payment_id": data.razorpay_payment_id,
            "razorpay_signature": data.razorpay_signature
        }

        # Verify signature
        razorpay_client.utility.verify_payment_signature(params_dict)

        user_id = ObjectId(current_user["_id"])

        # Upgrade user to Pro
        await db.users_collection.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "plan_type": "pro",
                    "is_paid": True,
                    "credits_remaining": 150,
                    "monthly_credit_limit": 150
                }
            }
        )

        return {
            "message": "Payment verified. Pro activated.",
            "credits": 150
        }

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Payment verification failed: {str(e)}"
        )

@app.post("/billing/create-extra-credits-order")
async def create_extra_credit_order(
    current_user: dict = Depends(get_current_user)
):

    amount = 4900  # ₹49

    order = razorpay_client.order.create({
        "amount": amount,
        "currency": "INR"
    })

    return {
        "order_id": order["id"],
        "amount": amount,
        "currency": "INR",
        "razorpay_key": os.getenv("RAZORPAY_KEY_ID")
    }

@app.post("/billing/verify-extra-credits")
async def verify_extra_credits(
    data: VerifyPaymentRequest,
    current_user: dict = Depends(get_current_user)
):

    try:
        print("STEP 1: API HIT")

        params_dict = {
            "razorpay_order_id": data.razorpay_order_id,
            "razorpay_payment_id": data.razorpay_payment_id,
            "razorpay_signature": data.razorpay_signature
        }

        print("STEP 2: Params created")

        # ✅ CRITICAL — catch verification errors
        razorpay_client.utility.verify_payment_signature(params_dict)

        print("STEP 3: Signature verified")

        user_id = ObjectId(current_user["_id"])

        result = await db.users_collection.update_one(
            {"_id": user_id},
            {
                "$inc": {
                    "credits_remaining": 30
                }
            }
        )

        print("STEP 4: Credits updated")

        return {
            "message": "30 credits added successfully"
        }

    except Exception as e:
        print("❌ VERIFY EXTRA CREDITS ERROR:", str(e))

        raise HTTPException(
            status_code=400,
            detail=f"Verification failed: {str(e)}"
        )

@app.post("/billing/create-order")
async def create_order(current_user: dict = Depends(get_current_user)):

    user_id = str(current_user["_id"])

    amount = 19900  # ₹199 in paise

    order = razorpay_client.order.create({
        "amount": amount,
        "currency": "INR",
        "payment_capture": 1
    })

    return {
        "order_id": order["id"],
        "amount": amount,
        "currency": "INR",
        "razorpay_key": os.getenv("RAZORPAY_KEY_ID")
    }


@app.get("/billing/status")
async def get_billing_status(current_user: dict = Depends(get_current_user)):

    user_id = ObjectId(current_user["_id"])

    user = await db.users_collection.find_one(
        {"_id": user_id},
        {
            "plan_type": 1,
            "credits_remaining": 1,
            "monthly_credit_limit": 1,
            "mock_attempts_used": 1,
            "subscription_status": 1,
            "subscription_current_period_end": 1
        }
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    mock_limit = None

    if user.get("plan_type") == "free":
        mock_limit = 1

    return {
        "plan_type": user.get("plan_type", "free"),
        "credits_remaining": user.get("credits_remaining", 0),
        "monthly_credit_limit": user.get("monthly_credit_limit", 10),
        "mock_attempts_used": user.get("mock_attempts_used", 0),
        "mock_limit": mock_limit,
        "subscription_status": user.get("subscription_status"),
        "subscription_current_period_end": user.get("subscription_current_period_end"),
        "low_credit_warning": user.get("credits_remaining", 0) <= 3

    }


@app.get("/billing/plans")
async def get_billing_plans():

    plans = [
        {
            "name": "Free",
            "price": 0,
            "currency": "INR",
            "credits": 10,
            "mock_limit": 1,
            "features": [
                "10 AI evaluation credits",
                "1 mock test",
                "Practice mode access",
                "Personal dashboard"
            ]
        },
        {
            "name": "Pro",
            "price": 199,
            "currency": "INR",
            "credits": 150,
            "mock_limit": None,
            "features": [
                "150 AI credits per month",
                "Unlimited mock tests (within credits)",
                "Advanced analytics",
                "Detailed feedback reports"
            ]
        }
    ]

    return {
        "plans": plans
    }


@app.get("/billing/can-upgrade")
async def can_upgrade(current_user: dict = Depends(get_current_user)):

    user_id = ObjectId(current_user["_id"])

    user = await db.users_collection.find_one(
        {"_id": user_id},
        {"plan": 1}
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    plan_type = user.get("plan_type", "free")

    return {
        "current_plan": plan,
        "can_upgrade": plan_type == "free"
    }

@app.post("/billing/dev-upgrade")
async def dev_upgrade(current_user: dict = Depends(get_current_user)):

    user_id = ObjectId(current_user["_id"])

    await db.users_collection.update_one(
        {"_id": user_id},
        {
            "$set": {
                "plan": "pro",
                "credits_remaining": 150,
                "monthly_credit_limit": 150,
                "subscription_status": "active",
                "subscription_current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
                "updated_at": datetime.utcnow()
            }
        }
    )

    return {
        "message": "User upgraded to Pro (dev mode)",
        "credits": 150
    }


def clean_reply(reply: str) -> str:
    if not reply:
        return reply

    if "Score:" in reply or "Missing Concepts" in reply:
        return None  # 🚨 signal invalid response

    return reply

@app.post("/auth/register")
async def register_user(data: RegisterRequest):

    email = data.email.lower().strip()

    existing_user = await db.users_collection.find_one({"email": email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pwd = hash_password(data.password)

    user = {
        "name": data.name,
        "email": email,
        "password": hashed_pwd,
        "class_level": data.class_level,
        "board": data.board,

        "role": "user",
        "plan": "free",

        "credits_remaining": 10,
        "monthly_credit_limit": 10,

        "mock_attempts_used": 0,

        "subscription_id": None,
        "subscription_status": None,
        "subscription_current_period_end": None,

        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    result = await db.users_collection.insert_one(user)

    access_token = create_access_token({
        "user_id": str(result.inserted_id)
    })

    return {
        "message": "User registered successfully",
        "access_token": access_token,
        "user": {
            "name": user["name"],
            "email": user["email"],
            "plan_type": user["plan"],
            "credits_remaining": user["credits_remaining"]
        }
    }

@app.post("/auth/login")
async def login_user(data: LoginRequest):

    email = data.email.lower().strip()

    user = await db.users_collection.find_one({"email": email})

    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if not verify_password(data.password, user["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    access_token = create_access_token({
        "user_id": str(user["_id"]),
        "is_paid": user.get("is_paid", False)
    })

    return {
        "access_token": access_token,
        "user": {
            "name": user["name"],
            "email": user["email"],
            "is_paid": user.get("is_paid", False),
            "plan": user.get("plan"),
            "valid_until": user.get("valid_until")
        }
    }

@app.get("/auth/me")
async def get_me(current_user = Depends(get_current_user)):
    return {
        "name": current_user["name"],
        "email": current_user["email"],
        "is_paid": current_user.get("is_paid", False),
        "plan": current_user.get("plan"),
        "valid_until": current_user.get("valid_until")
    }




@app.get("/protected")
async def protected_route(current_user = Depends(get_current_user)):
    return {
        "message": "Access granted",
        "email": current_user["email"]
    }


# if not user.get("is_paid"):
#     raise HTTPException(status_code=403, detail="Upgrade required")

# if user.get("valid_until") and user["valid_until"] < datetime.utcnow():
#     raise HTTPException(status_code=403, detail="Subscription expired")




@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("🛑 Shutting down StepWise AI...")
    cleanup_old_sessions(max_age_hours=0)  # Clean all sessions
    print("✅ Cleanup complete")


# =========================
# BACKGROUND TASKS
# =========================
async def periodic_cleanup():
    """Periodically clean up old sessions"""
    while True:
        await asyncio.sleep(3600)  # Run every hour
        removed = cleanup_old_sessions(max_age_hours=24)
        if removed > 0:
            print(f"🧹 Cleaned up {removed} inactive sessions")


# Start cleanup task on startup
@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(periodic_cleanup())


# =========================
# TELEGRAM ROUTES
# =========================
app.include_router(telegram_router)


# =========================
# HEALTH CHECK
# =========================
@app.get("/")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "StepWise AI",
        "version": "2.0.0"
    }


@app.get("/health")
async def detailed_health():
    """Detailed health check"""
    from app.socratic import chat_states
    
    return {
        "status": "healthy",
        "active_sessions": len(chat_states),
        "endpoints": {
            "chat": "/chat",
            "stream": "/chat/stream",
            "reset": "/chat/reset"
        }
    }



 # question_id -> selected_index


@app.get("/mock/history")
async def get_mock_history(user=Depends(get_current_user)):

    sessions = await db.test_sessions_collection.find(
        {
            "user_id": ObjectId(user["_id"]),
            "status": "completed"
        }
    ).sort("completed_at", -1).to_list(length=50)

    history = []

    for s in sessions:

        topic_stats = {}

        for r in s.get("results", []):
            topic = r.get("topic", "General")

            if topic not in topic_stats:
                topic_stats[topic] = {"correct": 0, "total": 0}

            topic_stats[topic]["total"] += 1

            if r.get("isCorrect"):
                topic_stats[topic]["correct"] += 1

        topic_accuracy = {}

        for t, stats in topic_stats.items():
            topic_accuracy[t] = round(
                (stats["correct"] / stats["total"]) * 100
            )

        history.append({
            "session_id": str(s["_id"]),
            "subject": s.get("subject"),
            "class_level": s.get("class_level"),
            "score": s.get("score"),
            "total": s.get("total"),
            "accuracy": s.get("accuracy"),
            "chapter": s.get("chapter"),
            "weak_topics": s.get("weak_topics", []),
            "topic_accuracy": topic_accuracy,
            "duration": s.get("duration"),
            "completed_at": s.get("completed_at")
        })

    return history


@app.post("/mock-test/submit")
async def submit_mock_test(
    data: MockSubmitRequest,
    current_user: dict = Depends(get_current_user)
):

    user_id = ObjectId(current_user["_id"])

    # ------------------------------------------------
    # 1️⃣ Find Active Session
    # ------------------------------------------------
    session = await db.test_sessions_collection.find_one({
        "_id": ObjectId(data.session_id),
        "user_id": user_id,
        "status": "active"
    })

    if not session:
        raise HTTPException(status_code=400, detail="No active session found")

    score = 0
    total = len(data.answers)
    detailed_results = []

    now_ts = int(datetime.now(timezone.utc).timestamp())

    # ------------------------------------------------
    # 2️⃣ Evaluate Answers
    # ------------------------------------------------
    for question_id, selected_index in data.answers.items():

        q = await db.questions_collection.find_one({
            "_id": ObjectId(question_id)
        })

        if not q:
            continue

        correct_index = q["correctAnswer"]
        correct_option = q["options"][correct_index]

        topic = q.get("topic", "General")
        difficulty = q.get("difficulty", "medium")
        concept = q.get("concept", topic)

        # ----------------------------------------------
        # Selected Answer
        # ----------------------------------------------
        if selected_index == -1:
            selected_option = "Not Attempted"
        elif selected_index < len(q["options"]):
            selected_option = q["options"][selected_index]
        else:
            selected_option = "Invalid Option"

        is_correct = (selected_index == correct_index)

        # ----------------------------------------------
        # Score Calculation
        # ----------------------------------------------
        if is_correct:
            score += 1
            explanation = "Correct. Well done."
        else:
            base_explanation = q.get("explanation", "Explanation not available.")
            explanation = f"Incorrect. The correct answer is '{correct_option}'. {base_explanation}"
        
        # ----------------------------------------------
        # Build Detailed Result
        # ----------------------------------------------
        detailed_results.append({
            "question_id": question_id,
            "question": q["question"],
            "difficulty": q.get("difficulty", "medium"),
            "selectedAnswer": selected_index,
            "selectedOption": selected_option,
            "concept": q.get("topic", "General"),
            "correctAnswer": correct_index,
            "correctOption": correct_option,

            "isCorrect": is_correct,

            "topic": topic,
            "concept": concept,
            "difficulty": difficulty,

            "explanation": explanation,

            "answered_at": now_ts
        })

    # ------------------------------------------------
    # 3️⃣ Accuracy Calculation
    # ------------------------------------------------
    accuracy = round((score / total) * 100) if total > 0 else 0

    # ------------------------------------------------
    # 4️⃣ Weak Topics Detection
    # ------------------------------------------------
    weak_topics = list({
        r["topic"]
        for r in detailed_results
        if not r["isCorrect"]
    })

    # ------------------------------------------------
    # 5️⃣ Credit Deduction
    # ------------------------------------------------
    await consume_credits(str(user_id), MOCK_COST, "mock_test")

    await db.users_collection.update_one(
        {"_id": user_id},
        {
            "$inc": {"mock_attempts_used": 1},
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }
    )

    # ------------------------------------------------
    # 6️⃣ Update Session (Completed)
    # ------------------------------------------------
    await db.test_sessions_collection.update_one(
        {"_id": session["_id"]},
        {
            "$set": {
                "status": "completed",
                "score": score,
                "total": total,
                "accuracy": accuracy,
                "weak_topics": weak_topics,
                "results": detailed_results,
                "completed_at": now_ts
            }
        }
    )

    # ------------------------------------------------
    # 7️⃣ Return Response
    # ------------------------------------------------
    return {
        "score": score,
        "total": total,
        "accuracy": accuracy,
        "weak_topics": weak_topics,
        "results": detailed_results
    }


@app.post("/practice/generate")
async def generate_practice_question(data: dict):

    topic = data.get("topic")
    confidence = data.get("confidence", 50)

    prompt = f"""
You are an expert CBSE tutor.

Generate ONE practice problem.

Topic: {topic}
Student confidence: {confidence}%

Difficulty rules:
- <40% → easy
- 40–70% → medium
- >70% → challenging

Return ONLY JSON:

{{
 "question": "clear exam-style question",
 "correct_answer": "exact final answer",
 "solution_steps": [
   "step 1 explanation",
   "step 2 explanation",
   "step 3 explanation"
 ],
 "concept": "{topic}",
 "difficulty": "easy | medium | hard",
 "common_mistake_patterns": [
   "mistake students often make"
 ]
}}

Rules:
- Application-based
- CBSE exam style
- Avoid trivial questions
- Output ONLY JSON
"""

    response = model.generate_content(prompt)

    raw = response.text.strip()
    raw = re.sub(r"```json|```", "", raw).strip()

    match = re.search(r"\{.*\}", raw, re.S)

    if not match:
        raise HTTPException(status_code=500, detail="Invalid AI output")

    question_data = json.loads(match.group())

    return question_data


@app.post("/practice/evaluate")
async def evaluate_practice(data: dict):

    question = data.get("question")
    correct_answer = data.get("correct_answer")
    student_answer = data.get("student_answer")
    solution_steps = data.get("solution_steps")

    if not question or not correct_answer or not student_answer:
        raise HTTPException(status_code=400, detail="Missing fields")

    is_correct = check_correctness(student_answer, correct_answer)

    prompt = f"""
You are a strict CBSE tutor analyzing a student's answer.

Question:
{question}

Correct Answer:
{correct_answer}

Student Answer:
{student_answer}

Correctness result from system:
{is_correct}

Provide pedagogical feedback.

If correctness is False:
- Explain where the student likely went wrong
- Emphasize conceptual misunderstanding

If correctness is True:
- Reinforce reasoning
- Suggest deeper thinking

Return ONLY JSON:

{{
 "score": number between 0 and 5,
 "strengths": ["point"],
 "mistakes": ["point"],
 "correct_solution": {solution_steps},
 "next_question": "similar practice question"
}}
"""

    response = model.generate_content(prompt)

    raw = response.text.strip()
    raw = re.sub(r"```json|```", "", raw).strip()

    match = re.search(r"\{.*\}", raw, re.S)

    if not match:
        raise HTTPException(status_code=500, detail="Invalid evaluation output")

    evaluation = json.loads(match.group())

    # override score using deterministic correctness
    if not is_correct:
        evaluation["score"] = min(evaluation.get("score", 2), 2)

    return evaluation

def extract_final_answer(text: str):

    if not text:
        return ""

    numbers = re.findall(r"-?\d+\.?\d*", text)

    if numbers:
        return numbers[-1]

    return text.strip().lower()


def check_correctness(student_answer: str, correct_answer: str):

    student = extract_final_answer(student_answer)
    correct = extract_final_answer(correct_answer)

    return student == correct



#===========insights===================

@app.get("/analytics/learning-insights")
async def get_learning_insights(user=Depends(get_current_user)):

    sessions = await db.test_sessions_collection.find(
        {
            "user_id": ObjectId(user["_id"]),
            "status": "completed"
        }
    ).sort("completed_at", -1).to_list(length=20)

    if not sessions:
        return {
            "learning_velocity": 0,
            "difficulty_strength": {},
            "weakest_topic": None,
            "strongest_topic": None,
            "recommended_topic": None
        }

    topic_stats = {}
    difficulty_stats = {}

    accuracies = []

    for s in sessions:

        accuracies.append(s.get("accuracy", 0))

        for r in s.get("results", []):

            topic = r.get("topic", "General")
            difficulty = r.get("difficulty", "medium")

            # Topic stats
            if topic not in topic_stats:
                topic_stats[topic] = {"correct": 0, "total": 0}

            topic_stats[topic]["total"] += 1

            if r.get("isCorrect"):
                topic_stats[topic]["correct"] += 1

            # Difficulty stats
            if difficulty not in difficulty_stats:
                difficulty_stats[difficulty] = {"correct": 0, "total": 0}

            difficulty_stats[difficulty]["total"] += 1

            if r.get("isCorrect"):
                difficulty_stats[difficulty]["correct"] += 1

    # ------------------------------------------------
    # Topic accuracy
    # ------------------------------------------------
    topic_accuracy = {}

    for t, stats in topic_stats.items():
        topic_accuracy[t] = round(
            (stats["correct"] / stats["total"]) * 100
        )

    # ------------------------------------------------
    # Difficulty strength
    # ------------------------------------------------
    difficulty_strength = {}

    for d, stats in difficulty_stats.items():
        difficulty_strength[d] = round(
            (stats["correct"] / stats["total"]) * 100
        )

    # ------------------------------------------------
    # Weakest & strongest topics
    # ------------------------------------------------
    weakest_topic = None
    strongest_topic = None

    if topic_accuracy:
        weakest_topic = min(topic_accuracy, key=topic_accuracy.get)
        strongest_topic = max(topic_accuracy, key=topic_accuracy.get)

    # ------------------------------------------------
    # Learning velocity
    # ------------------------------------------------
    learning_velocity = 0

    if len(accuracies) >= 2:
        learning_velocity = round(
            accuracies[0] - accuracies[-1]
        )

    return {
        "learning_velocity": learning_velocity,
        "difficulty_strength": difficulty_strength,
        "weakest_topic": weakest_topic,
        "strongest_topic": strongest_topic,
        "recommended_topic": weakest_topic
    }
    

@app.get("/progress")
async def get_user_progress(current_user: dict = Depends(get_current_user)):

    user_id = ObjectId(current_user["_id"])

    cursor = db.test_sessions_collection.find(
        {
            "user_id": user_id,
            "status": "completed"
        }
    ).sort("completed_at", 1)

    sessions = await cursor.to_list(length=1000)

    if not sessions:
        return {
            "total_tests": 0,
            "average_accuracy": 0,
            "best_score": 0,
            "last_score": 0,
            "accuracy_history": [],
            "topic_mastery": {},
            "improvement_rate": 0
        }

    total_tests = len(sessions)

    accuracies = [s.get("accuracy", 0) for s in sessions]

    average_accuracy = round(sum(accuracies) / total_tests)
    best_score = max(accuracies)
    last_score = accuracies[-1]

    improvement_rate = last_score - accuracies[0]

    # -------------------------------
    # Topic mastery
    # -------------------------------

    topic_data = {}

    for session in sessions:

        for q in session.get("results", []):

            topic = q.get("topic", "General")

            if topic not in topic_data:
                topic_data[topic] = {"correct": 0, "total": 0}

            topic_data[topic]["total"] += 1

            if q.get("isCorrect"):
                topic_data[topic]["correct"] += 1

    topic_mastery = {}

    for topic, data in topic_data.items():

        mastery = (data["correct"] / data["total"]) * 100

        topic_mastery[topic] = round(mastery)

    return {
        "total_tests": total_tests,
        "average_accuracy": average_accuracy,
        "best_score": best_score,
        "last_score": last_score,
        "accuracy_history": accuracies,
        "topic_mastery": topic_mastery,
        "improvement_rate": improvement_rate
    }

@app.get("/mock-test", response_model=List[MockQuestionResponse])
async def get_mock_test(
    count: int = 5,
    subject: str = "Maths",
    class_level: int = 10,
    chapter: str | None = None
):

    query = {
        "board": "CBSE",
        "subject": subject,
        "class": class_level
    }

    if chapter:
        query["chapter"] = chapter

    cursor = db.questions_collection.aggregate([
        {"$match": query},
        {"$sample": {"size": count}}
    ])

    questions = await cursor.to_list(length=count)

    if not questions:
        raise HTTPException(status_code=404, detail="No matching questions found")

    return [
        {
            "id": str(q["_id"]),
            "question": q["question"],
            "options": q["options"]
        }
        for q in questions
    ]


# =========================
# REQUEST/RESPONSE MODELS
# =========================
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User's question or message")
    board: Optional[str] = Field("CBSE", description="Education board (CBSE, ICSE, etc.)")
    reset: bool = Field(False, description="Reset chat session")
    session_id: Optional[str] = Field(None, description="Optional session ID for web clients")
    diagnosis:Optional[str]=None
    clarification: Optional[str] = None
    verification_answers: Optional[List[str]]=None
    topic: Optional[str] = None
    depth: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "message": "What is Newton's second law?",
                "board": "CBSE",
                "reset": False
            }
        }


class ChatResponse(BaseModel):
    reply: str = Field(..., description="Bot's response")
    session_id: Optional[str] = Field(None, description="Session identifier")
    metadata: Optional[dict] = Field(None, description="Additional metadata")
    structured: Optional[Dict[str, Any]] = None

    class Config:
        schema_extra = {
            "example": {
                "reply": "Newton's second law states that F = ma...",
                "session_id": 12345,
                "metadata": {
                    "domain": "science",
                    "subject": "physics",
                    "intent": "concept",
                    "mode": "explain"
                }
            }
        }


class ResetRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="Session ID to reset")


class ResetResponse(BaseModel):
    message: str
    session_id: Optional[str] = None

 # question_id -> selected index


class MockSubmitResponse(BaseModel):
    score: int
    results: List[dict]



# =========================
# HELPER FUNCTIONS
# =========================
def generate_session_id(req: ChatRequest) -> str:
    """
    Use frontend-provided session_id directly.
    No hashing. No instability.
    """
    if req.session_id:
        return req.session_id
    else:
        # Fallback — should not happen for web
        return str(id(req))

def get_session_metadata(chat_id: int) -> dict:
    """Get session metadata without exposing internal state"""
    from app.socratic import chat_states
    
    if chat_id not in chat_states:
        return {}
    
    state = chat_states[chat_id]

    micro_history = state.get("micro_history", [])

    diagnostic_profile = state.get("diagnostic_profile") or {}


    latest_misconception = any(
        isinstance(m, dict) and m.get("misconception_detected")
        for m in micro_history
    ) if micro_history else False

    
    return {
        "domain": state.get("domain"),
        "subject": state.get("subject"),
        "intent": state.get("intent"),
        "mode": state.get("mode"),
        "board": state.get("board"),

        # 🔥 Adaptive Metrics
        "rolling_confidence": state.get("rolling_confidence", 0.5),
        "discipline_score": state.get("discipline_score", 0.5),
        "training_mode": state.get("current_training_mode", "guided"),
        "misconception_recent": latest_misconception,
        "weakness_type": diagnostic_profile.get("weakness_type"),
        
         # 🔥 NEW
        "mock_active": state.get("mock_active", False),
        "exam_simulation_active": state.get("exam_simulation_active", False),
        "question_type": state.get("question_type"),
        "conversation_length": len(state.get("history", [])),
        "socratic_active": state.get("mode") == "socratic",
        "current_step": state.get("socratic", {}).get("current", 0) if state.get("mode") == "socratic" else None,
        "total_steps": len(state.get("socratic", {}).get("steps", [])) if state.get("mode") == "socratic" else None
    }


@app.post("/mock/start")
async def start_mock_test(
    count: int,
    duration: int,
    subject: str,
    class_level: int,
    chapter: str | None = None,
    user=Depends(get_current_user)
):

    print("===== DEBUG DB INFO =====")
    print("DB NAME:", db.db.name)
    print("CLIENT:", db.client)
    print("=========================")

    # ✅ Allow 1–180 minutes
    if duration < 1 or duration > 180:
        raise HTTPException(
            status_code=400,
            detail="Duration must be between 1 and 180 minutes"
        )

    user_id = ObjectId(user["_id"])
    now = datetime.now(timezone.utc)

    # --------------------------------------------------
    # CREDIT + PLAN CHECK
    # --------------------------------------------------

    user_doc = await db.users_collection.find_one({"_id": user_id})

    # Admin bypass
    if user_doc.get("role") != "admin":

        # Free plan restriction
        if user_doc.get("plan_type") == "free" and user_doc.get("mock_attempts_used", 0) >= 1:
            raise HTTPException(
                status_code=403,
                detail="Free plan allows only 1 mock test"
            )

        # Check if enough credits exist
        await check_credits(str(user_id), MOCK_COST)

    print("===== TIME DEBUG =====")
    print("NOW UTC:", now)
    print("NOW TIMESTAMP:", int(now.timestamp()))
    print("======================")

    # ==================================================
    # 1️⃣ CHECK FOR ACTIVE SESSION
    # ==================================================
    existing_session = await db.test_sessions_collection.find_one({
        "user_id": user_id,
        "status": "active"
    })

    if existing_session:

        started_at = existing_session["started_at"]
        duration_seconds = existing_session["duration"]

        now_ts = int(datetime.now(timezone.utc).timestamp())

        if isinstance(started_at, datetime):
            started_ts = int(started_at.timestamp())
        else:
            started_ts = int(started_at)

        elapsed = now_ts - started_ts

        # Resume session if still valid
        if elapsed < duration_seconds:

            question_ids = existing_session["question_ids"]
            object_ids = [ObjectId(qid) for qid in question_ids]

            cursor = db.questions_collection.find(
                {"_id": {"$in": object_ids}}
            )

            questions = await cursor.to_list(length=len(object_ids))

            question_map = {str(q["_id"]): q for q in questions}

            ordered_questions = []
            for qid in question_ids:
                q = question_map.get(qid)
                if q:
                    ordered_questions.append({
                        "id": qid,
                        "question": q["question"],
                        "options": q["options"]
                    })

            return {
                "session_id": str(existing_session["_id"]),
                "questions": ordered_questions,
                "selected_answers": existing_session["selected_answers"],
                "current_question_index": existing_session["current_question_index"],
                "duration": duration_seconds,
                "started_at": int(started_at if isinstance(started_at, int) else started_at.timestamp())           
                 }

        # Mark expired session
        await db.test_sessions_collection.update_one(
            {"_id": existing_session["_id"]},
            {"$set": {"status": "expired"}}
        )

    # ==================================================
    # 2️⃣ CREATE NEW SESSION
    # ==================================================

    query = {
        "board": "CBSE",
        "subject": subject,
        "class": class_level
    }

    if chapter:
        query["chapter"] = chapter

    cursor = db.questions_collection.aggregate([
        {"$match": query},
        {"$sample": {"size": count}}
    ])

    questions = await cursor.to_list(length=count)

    if not questions:
        raise HTTPException(
            status_code=404,
            detail="No matching questions found"
        )

    question_data = [
        {
            "id": str(q["_id"]),
            "question": q["question"],
            "options": q["options"]
        }
        for q in questions
    ]

    question_ids = [q["id"] for q in question_data]

    duration_seconds = duration * 60

    session_data = {
        "user_id": user_id,
        "question_ids": question_ids,
        "selected_answers": {qid: -1 for qid in question_ids},
        "current_question_index": 0,
        "duration": duration_seconds,
        "started_at": int(now.timestamp()),
        "status": "active",
        "created_at": now
    }

    result = await db.test_sessions_collection.insert_one(session_data)

    return {
        "session_id": str(result.inserted_id),
        "questions": question_data,
        "selected_answers": session_data["selected_answers"],
        "current_question_index": 0,
        "duration": duration_seconds,
        "started_at": int(now.timestamp())
    }



@app.get("/mock/resume")
async def resume_mock(user=Depends(get_current_user)):

    user_id = ObjectId(user["_id"])

    existing_session = await db.test_sessions_collection.find_one({
        "user_id": user_id,
        "status": "active"
    })

    if not existing_session:
        return {"active": False}

    now_ts = int(datetime.now(timezone.utc).timestamp())
    started_ts = int(existing_session["started_at"])
    duration = existing_session["duration"]

    elapsed = now_ts - started_ts

    if elapsed >= duration:
        await db.test_sessions_collection.update_one(
            {"_id": existing_session["_id"]},
            {"$set": {"status": "expired"}}
        )
        return {"active": False}

    question_ids = existing_session["question_ids"]

    object_ids = [ObjectId(qid) for qid in question_ids]
    cursor = db.questions_collection.find({"_id": {"$in": object_ids}})
    questions = await cursor.to_list(length=len(object_ids))

    question_map = {str(q["_id"]): q for q in questions}

    ordered_questions = []
    for qid in question_ids:
        q = question_map.get(qid)
        if q:
            ordered_questions.append({
                "id": qid,
                "question": q["question"],
                "options": q["options"]
            })

    return {
        "active": True,
        "session_id": str(existing_session["_id"]),
        "questions": ordered_questions,
        "selected_answers": existing_session["selected_answers"],
        "current_question_index": existing_session["current_question_index"],
        "duration": duration,
        "started_at": started_ts
    }


from pydantic import BaseModel

class SaveAnswerRequest(BaseModel):
    session_id: str
    question_id: str
    selected_option: int
    current_index: int

@app.post("/mock/save-answer")
async def save_answer(
    payload: SaveAnswerRequest,
    user=Depends(get_current_user)
):
    result = await db.test_sessions_collection.update_one(
        {
            "_id": ObjectId(payload.session_id),
            "user_id": ObjectId(user["_id"]),
            "status": "active"
        },
        {
            "$set": {
                f"selected_answers.{payload.question_id}": payload.selected_option,
                "current_question_index": payload.current_index
            }
        }
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to save answer")

    return {"success": True}



def socratic_guidance(message: str):

    prompt = f"""
You are a Socratic tutor.

Do NOT give the final answer.

Guide the student step-by-step using questions.

Student problem:
{message}

Ask the next question that helps the student think.
"""

    return gemini(prompt)

def simplify_concept(message: str):

    prompt = f"""
A student is confused.

Explain the concept simply with an example.

Student message:
{message}
"""

    return gemini(prompt)


def gemini(prompt: str) -> str:

    try:

        response = model.generate_content(prompt)

        if not response:
            return ""

        text = getattr(response, "text", None)

        if text:
            return text.strip()

        # sometimes Gemini returns parts
        if response.candidates:
            return response.candidates[0].content.parts[0].text.strip()

        return ""

    except Exception as e:

        print("Gemini error:", e)
        return ""

def generate_practice_from_chat(state):

    topic = state.get("last_topic")

    if not topic:
        return ChatResponse(
            reply="Tell me the topic you want to practice.",
            session_id=state["session_id"]
        )

    question = generate_practice_question_internal(topic)

    return ChatResponse(
        reply=f"Try solving this:\n\n{question}",
        session_id=state["session_id"]
    )


# =========================
# HTTP CHAT API (WEB)
# =========================
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user)
):
    try:
        import json

        # ========================= SESSION =========================
        session_id = generate_session_id(req)
        state = get_state(session_id)

        if state is None:
            state = {}

        state["session_id"] = session_id
        user_id = str(current_user["_id"])
        state["user_id"] = user_id

        if req.board:
            state["board"] = req.board

        state.setdefault("mode", "chat")

        state.setdefault("learning_gate", {
            "awaiting_attempt": False,
            "attempt_count": 0,
            "solution_unlocked": False
        })

        # ========================= CONTEXT =========================
        if req.topic:
            state["last_topic"] = req.topic

        if req.diagnosis:
            state["diagnosis"] = req.diagnosis

        message = (req.message or "").strip()
        topic = req.topic or state.get("last_topic")
        diagnosis = state.get("diagnosis", "unknown")

        await check_credits(user_id, CHAT_COST)

        # ========================= BASELINE =========================
        if message == "baseline" and req.topic:

            # topic = req.topic
            depth = req.depth or "board"

            raw = teach_concept(topic, diagnosis=diagnosis, depth=depth)

            try:
                structured = json.loads(raw) if isinstance(raw, str) else raw
            except:
                structured = {}

            await consume_credits(user_id, CHAT_COST, "chat")

            return ChatResponse(
                reply="ok",
                structured=structured,
                session_id=session_id,
                metadata=get_session_metadata(session_id)
            )

        # ========================= VERIFICATION =========================
        if req.verification_answers and message != "regenerate_explanation":

            # topic = state.get("last_topic")
            if not topic:
                raise HTTPException(status_code=400, detail="Topic missing")

            # ✅ FIX: direct dict (no json.loads)
            result = evaluate_understanding(
                topic=topic,
                answers=req.verification_answers,
                diagnosis=diagnosis
            )

            if not result:
                result = {
                    "understanding_level": "unknown",
                    "mistake_type": "unknown",
                    "final_summary": "",
                    "targeted_fix": "",
                    "next_action": "practice",
                    "question_wise_analysis": []
                }

            next_action = result.get("next_action")
            next_action = result.get("next_action","practice")
            mistake = result.get("mistake_type", "unknown")
            fix = result.get("targeted_fix", "")

            # ================= RETEACH =================
            if next_action == "reteach":

                if mistake == "concept_error":
                    reteach_mode = "concept"
                elif mistake == "calculation_error":
                    reteach_mode = "application"
                else:
                    reteach_mode = diagnosis

                raw = teach_concept(topic, diagnosis=reteach_mode, depth="simple")

                try:
                    structured = json.loads(raw) if isinstance(raw, str) else raw
                except:
                    structured = {}

                await consume_credits(user_id, CHAT_COST, "chat")

                return ChatResponse(
                    reply="ok",
                    structured=structured,
                    session_id=session_id,
                    metadata={
                        **get_session_metadata(session_id),

                        "understanding_level": result.get("understanding_level"),
                        "next_action": next_action,
                        "mistake_type": mistake,

                        "reason": result.get("final_summary"),
                        "targeted_fix": fix,

                        # ✅ FIX: send analysis to UI
                        "question_wise_analysis": result.get("question_wise_analysis", []),
                        "final_summary": result.get("final_summary", "")
                    }
                )

            # ================= PRACTICE / ADVANCE =================
            reply_text = ""

            if next_action == "practice":
                practice = generate_practice_question_internal(topic)
                reply_text = f"{result.get('final_summary')}\n\nTry this:\n{practice}"

            elif next_action == "advance":
                reply_text = "Strong understanding. Move to harder problems."

            else:
                reply_text = "Let’s continue practicing."

            await consume_credits(user_id, CHAT_COST, "chat")

            return ChatResponse(
                reply=reply_text,
                session_id=session_id,
                metadata={
                    **get_session_metadata(session_id),

                    "understanding_level": result.get("understanding_level"),
                    "next_action": next_action,
                    "mistake_type": result.get("mistake_type"),

                    "reason": result.get("final_summary"),
                    "targeted_fix": result.get("targeted_fix"),

                    # ✅ FIX: THIS WAS MISSING → UI now works
                    "question_wise_analysis": result.get("question_wise_analysis", []),
                    "final_summary": result.get("final_summary", "")
                }
            )

        # ========================= REGENERATE =========================
        if message == "regenerate_explanation":

            if not topic and message != "baseline":
                raise HTTPException(status_code=400, detail="Topic missing")

            depth = req.depth or "board"

            raw = teach_concept(topic, diagnosis=diagnosis, depth=depth)

            try:
                structured = json.loads(raw) if isinstance(raw, str) else raw
            except:
                structured = {}

            await consume_credits(user_id, CHAT_COST, "chat")

            return ChatResponse(
                reply="ok",
                structured=structured,
                session_id=session_id,
                metadata=get_session_metadata(session_id)
            )

        # ========================= FOLLOWUP =========================
        if message.lower() in ["not sure", "confused", "explain again"]:

            topic = state.get("last_topic")
            if not topic:
                raise HTTPException(status_code=400, detail="Topic missing")

            raw = teach_concept(topic, diagnosis=diagnosis, depth="simple")

            try:
                structured = json.loads(raw) if isinstance(raw, str) else raw
            except:
                structured = {}

            await consume_credits(user_id, CHAT_COST, "chat")

            return ChatResponse(
                reply="ok",
                structured=structured,
                session_id=session_id
            )

        # ========================= DEFAULT =========================
        reply_text = chat_reply(
            chat_id=session_id,
            user_text=message,
            reset=req.reset,
            board=req.board
        )

        await consume_credits(user_id, CHAT_COST, "chat")

        return ChatResponse(
            reply=reply_text,
            session_id=session_id,
            metadata=get_session_metadata(session_id)
        )

    except Exception as e:
        print("Chat error:", e)
        raise HTTPException(status_code=500, detail=str(e))

def normalize_answer(ans: str) -> str:
    return (ans or "").strip().lower()


def is_garbage(ans: str) -> bool:
    ans = normalize_answer(ans)

    if not ans:
        return True

    if ans in ["idk", "dont know", "no idea", "maybe", "skip"]:
        return True

    if len(ans) < 3:
        return True

    return False


def generate_eval_context(topic):
    from app.socratic import gemini
    from app.services.adaptive_explanation import extract_json

    prompt = f"""
Generate 3 CBSE-level conceptual questions for the topic: {topic}

Also provide correct answers.

Return STRICT JSON:

{{
  "questions": ["...", "...", "..."],
  "answers": ["...", "...", "..."]
}}

Only JSON. No explanation.
"""

    response = gemini(prompt)
    structured = extract_json(response)

    if not structured:
        return None

    return structured


def evaluate_understanding(topic, answers, diagnosis):
    import json
    from app.socratic import gemini
    from app.services.adaptive_explanation import extract_json

    # =========================
    # SAFE ANSWER EXTRACTION
    # =========================
    q1 = answers[0] if len(answers) > 0 else ""
    q2 = answers[1] if len(answers) > 1 else ""
    q3 = answers[2] if len(answers) > 2 else ""

    # =========================
    # PROMPT (STRUCTURED + CONTROLLED)
    # =========================
    prompt = f"""
You are a strict CBSE teacher.

Topic: {topic}
Evaluation type: {diagnosis}

The student answered the following:

Q1: {q1}
Q2: {q2}
Q3: {q3}

---

QUESTION CONTEXT:

If evaluation type is:

- concept:
  Q1 → definition understanding
  Q2 → importance of concept
  Q3 → what happens if misunderstood

- formula:
  Q1 → correctness of formula
  Q2 → meaning of each term
  Q3 → limitations of the formula

- application:
  Q1 → first step
  Q2 → reasoning behind step
  Q3 → common mistake

---

INSTRUCTIONS:

- Stay strictly within topic: {topic}
- Do NOT introduce unrelated concepts
- Evaluate each answer separately
- Identify EXACT mistake (not generic)
- If answer is correct, explicitly say it is correct
- If wrong, explain WHY it is wrong
- Keep explanations short but precise

---

OUTPUT STRICT JSON ONLY:

{{
  "understanding_level": "low | partial | strong",
  "mistake_type": "concept_error | calculation_error | misinterpretation | none",

  "question_wise_analysis": [
    {{
      "question": "Q1",
      "mistake": "...",
      "why_wrong": "...",
      "correct_concept": "..."
    }},
    {{
      "question": "Q2",
      "mistake": "...",
      "why_wrong": "...",
      "correct_concept": "..."
    }},
    {{
      "question": "Q3",
      "mistake": "...",
      "why_wrong": "...",
      "correct_concept": "..."
    }}
  ],

  "final_summary": "...",
  "targeted_fix": "...",
  "next_action": "reteach | practice | advance"
}}

IMPORTANT:
- Only JSON
- No markdown
- No extra text
"""

    # =========================
    # CALL LLM (single clean call)
    # =========================
    response = gemini(prompt)

    structured = extract_json(response)

    if not structured:
        print("⚠️ RAW RESPONSE:", response)

        # retry once
        response = gemini(prompt)
        structured = extract_json(response)

    # =========================
    # FALLBACK (SAFE OUTPUT)
    # =========================
    if not structured:
        structured = {
            "understanding_level": "low",
            "mistake_type": "concept_error",
            "question_wise_analysis": [],
            "final_summary": "Evaluation failed to generate properly.",
            "targeted_fix": "Revise the concept and try again.",
            "next_action": "reteach"
        }

    return structured
#================learn and chat =================

def detect_intent(message: str) -> str:
    m = message.lower().strip()

    # ---------- DIRECT ANSWER ----------
    if any(x in m for x in [
        "final answer", "just answer", "give answer", "solution only"
    ]):
        return "direct"

    # ---------- NEXT STEP ----------
    if any(x in m for x in [
        "next step", "what next", "continue", "go ahead"
    ]):
        return "step"

    # ---------- HINT ----------
    if any(x in m for x in [
        "hint", "help", "clue"
    ]):
        return "hint"

    # ---------- EXPLANATION ----------
    if any(x in m for x in [
        "why", "how", "explain", "clarify"
    ]):
        return "explain"

    # ---------- SIMPLIFY ----------
    if any(x in m for x in [
        "simple", "easy", "confusing", "don't understand", "hard"
    ]):
        return "simplify"

    # ---------- EXAMPLE ----------
    if "example" in m:
        return "example"

    # ---------- REPEAT ----------
    if any(x in m for x in [
        "again", "repeat"
    ]):
        return "repeat"

    # ---------- THEORY ----------
    if any(x in m for x in [
        "what is", "define", "meaning"
    ]):
        return "theory"

    # ---------- USER ATTEMPT ----------
    if any(x in m for x in ["=", "x", "answer is", "i think"]):
        return "attempt"

    # ---------- DEFAULT ----------
    return "followup"


# ----------problems ------------

def is_attempt(message: str):
    m = message.lower()
    return any(x in m for x in [
        "=", "subtract", "add", "multiply", "divide",
        "i think", "answer is", "gives", "equals"
    ])


@app.post("/problems", response_model=ChatResponse)
async def problems_endpoint(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        user_id = str(current_user["_id"])
        await check_credits(user_id, CHAT_COST)

        session_id = generate_session_id(req)
        state = get_state(session_id)

        # ---------- INIT ----------
        state.setdefault("mode", "problems")
        state.setdefault("problem", None)
        state.setdefault("ptype", None)
        state.setdefault("solved", False)
        state.setdefault("interaction_count", 0)
        state.setdefault("last_response", "")

        message = (req.message or "").strip()

        # ---------- VALIDATION ----------
        if not message.strip():
            return ChatResponse(
                reply="⚠️ Enter a valid input.",
                session_id=session_id
            )

        # ---------- INTENT ----------
        intent = "attempt" if is_attempt(message) else detect_intent(message)

        # ---------- NEW PROBLEM ----------
        def is_new_problem(msg: str, current_problem: str | None):
            if current_problem is None:
                return True
            if any(x in msg.lower() for x in ["solve", "find"]) and "=" in msg:
                return True
            return False

        if is_new_problem(message, state["problem"]):
            state["problem"] = message
            state["ptype"] = classify_problem(message)
            state["interaction_count"] = 0
            state["solved"] = False

            # INVALID
            if state["ptype"] == "invalid":
                return ChatResponse(
                    reply="⚠️ Invalid equation. Only one '=' is allowed.",
                    session_id=session_id
                )

            # ARITHMETIC
            if state["ptype"] == "arithmetic":
                result = evaluate_arithmetic(message)
                if result:
                    await consume_credits(user_id, CHAT_COST, "chat")
                    return ChatResponse(reply=result, session_id=session_id)

            # FIRST STEP PROMPT
            reply = chat_reply(
                chat_id=session_id,
                user_text=f"""
Solve this step by step:

{message}

Start by asking the FIRST step.

IMPORTANT:
- If user gives correct step → confirm and move forward
- If wrong → correct them
- Do NOT solve fully
"""
            )

            state["last_response"] = reply
            state["interaction_count"] += 1

            await consume_credits(user_id, CHAT_COST, "chat")
            return ChatResponse(reply=reply, session_id=session_id)

        # ---------- CONTEXT ----------
        step_num = state["interaction_count"]

        CONTEXT = f"""
Problem:
{state['problem']}

Current step: {step_num}

You are CONTINUING this problem.

RULES:
- Never restart
- Never repeat same question
- Always move forward
- Stay within this problem only
"""

        # ---------- INTENTS ----------

        if intent == "attempt":
            if state["ptype"] == "arithmetic":
                reply = evaluate_arithmetic(state["problem"]) or "⚠️ Couldn't evaluate."
            else:
                reply = chat_reply(
                    chat_id=session_id,
                    user_text=f"""
{CONTEXT}

User step: {message}

Evaluate:

IF CORRECT:
- Say "Correct"
- Show updated equation
- Ask next step

IF WRONG:
- Explain mistake
- Show correct step

DO NOT restart.
"""
                )

        elif intent == "step":
            reply = chat_reply(
                chat_id=session_id,
                user_text=f"""
{CONTEXT}

Give next step only.
"""
            )

        elif intent == "direct":
            reply = chat_reply(
                chat_id=session_id,
                user_text=f"""
{CONTEXT}

Solve fully and give final answer.
"""
            )
            state["solved"] = True

        elif intent == "hint":
            reply = chat_reply(
                chat_id=session_id,
                user_text=f"""
{CONTEXT}

Give a small hint only.
"""
            )

        elif intent == "explain":
            reply = chat_reply(
                chat_id=session_id,
                user_text=f"""
{CONTEXT}

Explain briefly.
"""
            )

        elif intent == "simplify":
            reply = chat_reply(
                chat_id=session_id,
                user_text=f"""
{CONTEXT}

Explain in simple terms and continue solving.
"""
            )

        elif intent == "repeat":
            reply = state.get("last_response", "Let's continue.")

        else:
            reply = chat_reply(
                chat_id=session_id,
                user_text=f"""
{CONTEXT}

User input: {message}

If step → evaluate
If doubt → explain
Else → guide next step

Never restart.
"""
            )

        # ---------- SAFETY ----------
        if not reply or len(reply.strip()) < 5:
            reply = "⚠️ Try rephrasing."

        state["last_response"] = reply
        state["interaction_count"] += 1

        await consume_credits(user_id, CHAT_COST, "chat")

        return ChatResponse(reply=reply, session_id=session_id)

    except Exception as e:
        print("Problems endpoint error:", e)
        raise HTTPException(status_code=500, detail=str(e))

def validate_answer(topic: str, question: str, answer: str, session_id: str):
    result = chat_reply(
        chat_id=session_id,
        user_text=f"""
You are a strict CBSE evaluator.

Question: {question}
Student Answer: {answer}

Evaluate:

1. Is the answer conceptually correct? (yes/no)
2. If correct → say "correct"
3. If wrong → give a small hint

STRICT:
- No long explanation
- No teaching
- Only evaluation

Return JSON:
{{
  "correct": true/false,
  "feedback": "text"
}}
"""
    )

    try:
        import json
        parsed = json.loads(result)
        return parsed.get("correct", False), parsed.get("feedback", "")
    except:
        return False, "Try again."



@app.post("/learn", response_model=ChatResponse)
async def learn_endpoint(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        user_id = str(current_user["_id"])

        # 🔥 ALWAYS CHECK CREDIT FIRST
        await check_credits(user_id, CHAT_COST)

        session_id = generate_session_id(req)
        state = get_state(session_id)

        # ---------- INIT ----------
        state.setdefault("mode", "idle")
        state.setdefault("step_index", 0)
        state.setdefault("steps", [])
        state.setdefault("attempts", {})
        state.setdefault("concept_check", False)

        message = (req.message or "").strip()
        user_input = message.lower()

        # ---------- START LEARNING ----------
        if "teach me" in user_input:
            topic = user_input.replace("teach me", "").strip()

            steps = generate_steps(topic, chat_reply)

            for s in steps:
                if s.get("input_mode") == "mcq":
                    if not s.get("options") or len(s["options"]) < 2:
                        s["input_mode"] = "short"
                        s["options"] = []

            state["mode"] = "learn"
            state["step_index"] = 0
            state["steps"] = steps
            state["attempts"] = {}
            state["concept_check"] = False

            step = steps[0]

            await consume_credits(user_id, CHAT_COST, "chat")

            return ChatResponse(
                reply=step["question"],
                session_id=session_id,
                metadata={
                    "input_mode": step.get("input_mode", "short"),
                    "options": step.get("options", [])
                }
            )

        # ---------- NORMAL CHAT MODE ----------
        if state["mode"] != "learn":
            reply = chat_reply(
                chat_id=session_id,
                user_text=message
            )

            await consume_credits(user_id, CHAT_COST, "chat")

            return ChatResponse(reply=reply, session_id=session_id)

        steps = state["steps"]
        step_index = state["step_index"]

        # ---------- COMPLETED ----------
        if step_index >= len(steps):
            state["mode"] = "idle"

            reply = chat_reply(
                chat_id=session_id,
                user_text=message
            )

            await consume_credits(user_id, CHAT_COST, "chat")

            return ChatResponse(
                reply=reply or "✅ Completed! Ask anything.",
                session_id=session_id
            )

        step = steps[step_index]
        expected = step.get("expected_answer", "").lower()
        options = step.get("options", [])

        # ---------- INPUT FILTER ----------
        confused = ["not sure", "idk", "dont know", "no idea", "skip"]
        garbage = ["asdf", "???", "...", "123"]

        if any(x in user_input for x in confused):
            teaching = chat_reply(
                chat_id="teach",
                user_text=f"Explain simply: {step['question']}"
            )

            await consume_credits(user_id, CHAT_COST, "chat")

            return ChatResponse(
                reply=f"🤝 No problem:\n\n{teaching.strip()}\n\nNow try:",
                session_id=session_id
            )

        if user_input.strip() in garbage or len(user_input) < 2:
            await consume_credits(user_id, CHAT_COST, "chat")

            return ChatResponse(
                reply="⚠️ Give a proper attempt.",
                session_id=session_id
            )

        # ---------- ATTEMPTS ----------
        key = f"step_{step_index}"
        state["attempts"][key] = state["attempts"].get(key, 0) + 1
        attempts = state["attempts"][key]

        # ---------- MCQ ----------
        is_mcq = (
            step.get("input_mode") == "mcq"
            and isinstance(options, list)
            and len(options) >= 2
        )

        if is_mcq:
            options_lower = [o.lower() for o in options]

            if user_input not in options_lower:
                await consume_credits(user_id, CHAT_COST, "chat")
                return ChatResponse(
                    reply="❌ Choose from options",
                    session_id=session_id,
                    metadata={"input_mode": "mcq", "options": options}
                )

            if user_input == expected:
                state["step_index"] += 1
                state["attempts"] = {}

                if state["step_index"] >= len(steps):
                    state["mode"] = "idle"
                    await consume_credits(user_id, CHAT_COST, "chat")
                    return ChatResponse(reply="✅ Completed!", session_id=session_id)

                next_step = steps[state["step_index"]]

                await consume_credits(user_id, CHAT_COST, "chat")

                return ChatResponse(
                    reply=f"✅ Correct\n\nNext:\n{next_step['question']}",
                    session_id=session_id,
                    metadata={
                        "input_mode": next_step.get("input_mode", "short"),
                        "options": next_step.get("options", [])
                    }
                )

            await consume_credits(user_id, CHAT_COST, "chat")

            return ChatResponse(
                reply="❌ Incorrect. Try again.",
                session_id=session_id,
                metadata={"input_mode": "mcq", "options": options}
            )

        # ---------- SIMPLE MATCH ----------
        is_correct = any(word in user_input for word in expected.split())

        if is_correct:
            state["step_index"] += 1
            state["attempts"] = {}

            if state["step_index"] >= len(steps):
                state["mode"] = "idle"
                await consume_credits(user_id, CHAT_COST, "chat")
                return ChatResponse(reply="✅ Completed!", session_id=session_id)

            next_step = steps[state["step_index"]]

            await consume_credits(user_id, CHAT_COST, "chat")

            return ChatResponse(
                reply=f"✅ Correct\n\nNext:\n{next_step['question']}",
                session_id=session_id
            )

        # ---------- WRONG FLOW ----------
        if attempts == 1:
            reply = "❌ Not correct\nHint: Think about the core idea."
        elif attempts == 2:
            reply = "⚠️ You're close\nHint: Focus on key parts."
        elif attempts == 3:
            reply = f"📘 Learn this:\n\n{step['expected_answer']}\n\nTry again:"
        else:
            state["step_index"] += 1
            reply = "➡️ Moving ahead. We'll revisit."

        await consume_credits(user_id, CHAT_COST, "chat")

        return ChatResponse(reply=reply, session_id=session_id)

    except Exception as e:
        print("Learn error:", e)
        raise HTTPException(status_code=500, detail=str(e))
    


def is_invalid_equation(problem: str):
    return problem.count("=") > 1


def is_arithmetic(problem: str):
    return all(c.isdigit() or c in "+-*/=(). " for c in problem)


def evaluate_arithmetic(problem: str):
    try:
        lhs, rhs = problem.split("=")
        lhs_val = eval(lhs.strip())
        rhs_val = eval(rhs.strip())

        if lhs_val == rhs_val:
            return f"✅ Correct.\nLHS = RHS = {lhs_val}"
        else:
            return f"❌ Incorrect.\nLHS = {lhs_val}, RHS = {rhs_val}"
    except:
        return None


def classify_problem(problem: str):
    p = problem.lower()

    if is_invalid_equation(problem):
        return "invalid"

    if is_arithmetic(problem) and "=" in problem:
        return "arithmetic"

    if any(c.isalpha() for c in problem) and "=" in problem:
        return "algebra"

    if any(word in p for word in ["train", "speed", "distance", "time", "profit", "loss"]):
        return "word"

    if any(word in p for word in ["define", "what is", "explain"]):
        return "theory"

    return "general"
#============helper===================

import json

def teach_concept(question: str, diagnosis: str, depth="board"):

    # ================================
    # DIAGNOSIS MODE
    # ================================
    if diagnosis == "concept":
        diagnosis_instruction = """
FOCUS MODE: CONCEPT

- Start with intuition
- Avoid formulas
- Keep it simple
"""

    elif diagnosis == "formula":
        diagnosis_instruction = """
FOCUS MODE: FORMULA

- Focus on formulas
- Minimal theory
- Show how to use formulas
"""

    elif diagnosis == "application":
        diagnosis_instruction = """
FOCUS MODE: APPLICATION

- Focus on solving problems
- Step-by-step logic
"""

    else:
        diagnosis_instruction = "General explanation"

    # ================================
    # FINAL PROMPT
    # ================================
    prompt = f"""
You are an expert CBSE tutor.

Follow the instructions strictly.

TOPIC: {question}
DIAGNOSIS: {diagnosis}
DEPTH: {depth}

{diagnosis_instruction}

----------------------------------------

OUTPUT STRICT JSON ONLY:

{{
"title": "",
"intro": "",
"definition": "",
"key_points": [],

"formula": {{
  "items": [
    {{
      "name": "",
      "meaning": "",
      "simple": "",
      "symbolic": ""
    }}
  ]
}},

"derivation": {{
  "steps": [],
  "intuition": "",
  "when_to_use": ""
}},

"step_by_step_logic": [],

"example": {{
  "problem": "",
  "solution_steps": []
}},

"diagram_hint": "",
"exam_tip": "",
"common_mistakes": [],
"reflective_question": ""
}}



IMPORTANT DERIVATION RULES (CRITICAL):

If diagnosis = "formula" AND depth != "simple":

You MUST generate a REAL derivation using domain knowledge.

STRICT REQUIREMENTS:

• Steps must be logically connected (no generic statements)
• Each step must follow from the previous step
• Use correct laws/theorems (e.g., Newton's laws, algebra rules)
• Show substitution and transformation clearly
• Show cancellation/simplification steps explicitly
• Final step MUST give the derived formula

FORBIDDEN:
❌ No generic phrases like "observe relationship"
❌ No vague reasoning
❌ No skipped steps

STRUCTURE:

steps:
1. Start from known law / definition
2. Substitute values / expressions
3. Transform step-by-step
4. Simplify carefully
5. Reach final formula

intuition:
• Explain WHY the derivation works (not steps)

when_to_use:
• Where this derivation is applied in exams
"""

    # ================================
    # CALL MODEL
    # ================================
    response = gemini(prompt)

    try:
        data = extract_json(response)
    except:
        print("⚠️ JSON parsing failed, fallback triggered")
        data = {}

    # ================================
    # 🔥 HARD ENFORCEMENT (CRITICAL)
    # ================================

    if diagnosis == "formula" and depth != "simple":

        derivation = data.get("derivation", {})

        if not derivation or not derivation.get("steps"):

            data["derivation"] = {
                "steps": [
                    "Start from the fundamental definition or known law related to the formula",
                    "Express the quantities in mathematical form",
                    "Substitute related expressions into the equation",
                    "Rearrange the equation step-by-step to isolate the required variable",
                    "Simplify the expression carefully to obtain the final formula"
                ],
                "intuition": "The formula is derived by systematically transforming known relationships into a usable mathematical form",
                "when_to_use": "Use this derivation when you need to justify the formula in exams or understand its origin"
            }

    # ================================
    # 🔥 FORMULA STRUCTURE FIX
    # ================================

    formula = data.get("formula", {})

    if not formula or not isinstance(formula.get("items"), list):

        data["formula"] = {
            "items": [
                {
                    "name": "Main Formula",
                    "meaning": "Represents relationship between variables",
                    "simple": "Basic relation",
                    "symbolic": "Standard form"
                }
            ]
        }

    # ================================
    # FINAL RETURN
    # ================================
    return data   
#=================detecxtion==================

def detect_student_intent(message: str):

    if not message:
        return "general_chat"

    msg = message.lower().strip()

    practice_keywords = [
        "practice",
        "quiz",
        "test me",
        "give question",
        "practice question",
        "try problem"
    ]

    solve_keywords = [
        "solve",
        "calculate",
        "find",
        "compute",
        "evaluate",
        "determine"
    ]

    confusion_keywords = [
        "i don't understand",
        "confused",
        "not clear",
        "explain again",
        "not sure",
        "explain me clearly again",
        "cant understand",
        "can you explain that",
        "clarify",
        "what do you mean",
        "explain your question"
    ]

    concept_keywords = [
        "what is",
        "define",
        "explain",
        "meaning of",
        "what are",
        "how does",
        "why does",
        "what happens",
        "tell me about"
    ]

    # Practice request
    for k in practice_keywords:
        if k in msg:
            return "practice_request"

    # Problem solving
    for k in solve_keywords:
        if k in msg:
            return "solve_problem"

    # Confusion / clarification
    for k in confusion_keywords:
        if k in msg:
            return "confusion"

    # Concept learning
    for k in concept_keywords:
        if msg.startswith(k):
            return "concept_question"

    return "general_chat"

#==========analyze=====================

def analyze_student_attempt(question: str, answer: str):

    prompt = f"""
You are an expert CBSE Maths and Science tutor.

A student answered a question. Your job is to:
1. Evaluate their answer
2. Teach the concept properly
3. Explain the answer with a real world example for better understanding

Question:
{question}

Student Answer:
{answer}

First identify the main concept in the question.
Then explain that concept clearly before evaluating.

Your response MUST follow this structure exactly.

Verdict:
Correct / Partially Correct / Incorrect

Concept Explanation

Concept Title

Short Intro

📘 Definition
Clear definition of the concept.

Key Points
• Important bullet points

📐 Formula
Formula if applicable.

🔬 Example
Simple real-life example.

Correct Answer
Write the full correct CBSE exam answer.

Exam Tip
Give a short exam tip to score full marks.

🎯 Think About This
Ask a reflective question that checks understanding.

Do NOT use markdown symbols like ** or ###.
Use clean readable formatting.
"""

    return gemini(prompt)


def generate_practice_question_internal(topic: str):

    prompt = f"""
Generate a CBSE exam-style question.

Return ONLY JSON.

Format:

{{
"question": "",
"difficulty": "",
"topic": ""
}}

Topic:
{topic}
"""

    return gemini(prompt)


def reveal_solution(problem: str):

    prompt = f"""
Provide the step-by-step solution.

Problem:
{problem}

Explain clearly.
"""

    return gemini(prompt)


def simplify_concept(message: str):

    prompt = f"""
Explain this concept simply with an example.

Student message:
{message}
"""

    return gemini(prompt)

#===========reset====================

@app.post("/chat/reset", response_model=ResetResponse)
async def reset_session(req: ResetRequest):
    """
    Reset a chat session.
    
    Example request:
    ```json
    {
        "session_id": "user123"
    }
    ```
    """
    try:
        from app.socratic import chat_states
        
        if req.session_id:
            session_id = req.session_id
            if session_id in chat_states:
                chat_states.pop(session_id)
                return ResetResponse(
                    message="Session reset successfully",
                    session_id=session_id
                )
            else:
                return ResetResponse(
                    message="Session not found or already reset",
                    session_id=session_id
                )
        else:
            # Reset all sessions (use with caution)
            count = len(chat_states)
            chat_states.clear()
            return ResetResponse(
                message=f"All {count} sessions reset successfully"
            )
    
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error resetting session: {str(e)}"
        )


# =========================
# SESSION MANAGEMENT
# =========================
@app.get("/sessions")
async def list_sessions():
    """List active sessions (for debugging/admin)"""
    from app.socratic import chat_states
    
    sessions = []
    for chat_id, state in chat_states.items():
        sessions.append({
            "session_id": chat_id,
            "board": state.get("board"),
            "diagnosis":state.get("diagnosis"),
            "domain": state.get("domain"),
            "subject": state.get("subject"),
            "mode": state.get("mode"),
            "messages": len(state.get("history", [])),
            "last_active": state.get("last_active").isoformat() if state.get("last_active") else None
        })
    
    return {
        "total_sessions": len(sessions),
        "sessions": sessions
    }


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: int):
    """Delete a specific session"""
    from app.socratic import chat_states
    
    if session_id in chat_states:
        chat_states.pop(session_id)
        return {"message": "Session deleted", "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail="Session not found")


# =========================
# STREAMING CHAT (FUTURE)
# =========================

@app.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user)
):

    try:
        session_id = generate_session_id(req)
        user_id = str(current_user["_id"])

        # Check credits before generating response
        await check_credits(user_id, CHAT_COST)

        intent = detect_student_intent(req.message)

        if intent == "concept_question":
            state["last_topic"] = (req.message)
        
        else:
            reply_text = chat_reply(
                chat_id=session_id,
                user_text=req.message,
                reset=req.reset,
                board=req.board
            )



        # Deduct credits AFTER response generation
        await consume_credits(user_id, CHAT_COST, "chat_stream")

        async def generate():
            words = reply_text.split()
            for i, word in enumerate(words):
                yield word + (" " if i < len(words) - 1 else "")
                await asyncio.sleep(0.05)

        return StreamingResponse(
            generate(),
            media_type="text/plain"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Streaming error: {str(e)}"
        )

# =========================
# ERROR HANDLERS
# =========================
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Catch-all exception handler"""
    print(f"❌ Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "An internal error occurred",
            "detail": str(exc) if app.debug else "Please try again later"
        }
    )


# =========================
# ADMIN/DEBUG ENDPOINTS
# =========================
@app.get("/debug/session/{session_id}")
async def debug_session(session_id: int):
    """Get detailed session information for debugging"""
    from app.socratic import chat_states
    
    if session_id not in chat_states:
        raise HTTPException(status_code=404, detail="Session not found")
    
    state = chat_states[session_id]
    
    return {
        "session_id": session_id,
        "state": {
            "board": state.get("board"),
            "domain": state.get("domain"),
            "subject": state.get("subject"),
            "intent": state.get("intent"),
            "mode": state.get("mode"),
            "last_question": state.get("last_question"),
            "last_topic": state.get("last_topic"),
            "history_length": len(state.get("history", [])),
            "socratic": state.get("socratic") if state.get("mode") == "socratic" else None,
            "last_active": state.get("last_active").isoformat()
        },
        "history": state.get("history", [])[-5:]  # Last 5 messages
    }


# =========================
# RUN (for development)
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )