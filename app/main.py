from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Any
import asyncio
from bson import ObjectId
from app.mock_explainer import generate_explanation
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials,  OAuth2PasswordBearer
from app.services.adaptive_explanation import generate_adaptive_explanation

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


# =========================
# CORS (REQUIRED FOR ANGULAR)
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4200",
        "http://localhost:3000",
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
    print("✅ Database initialized")
    print("✅ Server ready")

class MockQuestionResponse(BaseModel):
    id: str
    question: str
    options: List[str]

class MockSubmitRequest(BaseModel):
    answers: Dict[str, int]
    session_id: str  # question_id -> selected_index



SECRET_KEY = "your_super_secret_key_change_this"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day

security = HTTPBearer()


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    class_level: int
    board: str


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



def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


@app.post("/auth/register")
async def register_user(data: RegisterRequest):

    existing_user = await db.users_collection.find_one({"email": data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pwd = hash_password(data.password)

    user = {
        "name": data.name,
        "email": data.email,
        "password": hashed_pwd,
        "class_level": data.class_level,
        "board": data.board,
        "created_at": datetime.utcnow(),
        "is_paid": False,
        "plan": None,
        "valid_until": None,
    }

    result = await db.users_collection.insert_one(user)

    access_token = create_access_token({"user_id": str(result.inserted_id)})

    return {
        "message": "User registered successfully",
        "access_token": access_token,
        "user": {
            "name": user["name"],
            "email": user["email"],
            "is_paid": user.get("is_paid", False)
        }
    }


@app.post("/auth/login")
async def login_user(data: LoginRequest):

    user = await db.users_collection.find_one({"email": data.email})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")

    if not verify_password(data.password, user["password"]):
        raise HTTPException(status_code=400, detail="Invalid credentials")

    access_token = create_access_token({"user_id": str(user["_id"]), "is_paid": user.get("is_paid", False)})

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
        history.append({
            "session_id": str(s["_id"]),
            "subject": s.get("subject"),
            "class_level": s.get("class_level"),
            "score": s.get("score"),
            "total": s.get("total"),
            "accuracy": s.get("accuracy"),
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
    session = await db.test_sessions_collection.find_one(
        {
            "_id": ObjectId(data.session_id),
            "user_id": user_id,
            "status": "active"
        }
    )

    if not session:
        raise HTTPException(status_code=400, detail="No active session found")

    score = 0
    total = len(data.answers)
    detailed_results = []

    # ------------------------------------------------
    # 2️⃣ Evaluate Answers
    # ------------------------------------------------
    for question_id, selected_index in data.answers.items():

        q = await db.questions_collection.find_one(
            {"_id": ObjectId(question_id)}
        )

        if not q:
            continue

        correct_index = q["correctAnswer"]
        correct_option = q["options"][correct_index]

        # Safe selected option handling
        if selected_index == -1:
            selected_option = "Not Attempted"
        elif selected_index < len(q["options"]):
            selected_option = q["options"][selected_index]
        else:
            selected_option = "Invalid Option"

        is_correct = (selected_index == correct_index)

        if is_correct:
            score += 1
            explanation = "Correct. Well done."
        else:
            explanation = generate_explanation(
                q["question"],
                correct_option,
                selected_option,
                q.get("subject", "Maths"),
                q.get("class", 10)
            )

        detailed_results.append({
            "question_id": question_id,
            "question": q["question"],
            "selectedAnswer": selected_index,
            "correctAnswer": correct_index,
            "correctOption": correct_option,
            "explanation": explanation,
            "isCorrect": is_correct,
            "topic": q.get("topic", "General")
        })

    accuracy = round((score / total) * 100) if total > 0 else 0

    # ------------------------------------------------
    # 3️⃣ Extract Weak Topics
    # ------------------------------------------------
    weak_topics = list({
        r.get("topic", "General")
        for r in detailed_results
        if not r["isCorrect"]
    })

    now_ts = int(datetime.now(timezone.utc).timestamp())

    # ------------------------------------------------
    # 4️⃣ Update Session (MARK COMPLETED)
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
    # 5️⃣ Return Response
    # ------------------------------------------------
    return {
        "score": score,
        "total": total,
        "accuracy": accuracy,
        "results": detailed_results
    }


@app.get("/progress")
async def get_user_progress(current_user: dict = Depends(get_current_user)):

    user_id = current_user["_id"]

    cursor = db.mock_results_collection.find({"user_id": user_id}).sort("submitted_at", 1)

    results = await cursor.to_list(length=1000)

    if not results:
        return {
            "total_tests": 0,
            "average_accuracy": 0,
            "best_score": 0,
            "last_score": 0,
            "accuracy_history": [],
            "topic_mastery": {},
            "improvement_rate": 0
        }

    total_tests = len(results)

    accuracies = [r["accuracy"] for r in results]

    average_accuracy = round(sum(accuracies) / total_tests)
    best_score = max(accuracies)
    last_score = accuracies[-1]

    improvement_rate = last_score - accuracies[0]

    # Topic mastery calculation
    topic_data = {}

    for test in results:
        for q in test["results"]:
            topic = q.get("topic", "General")

            if topic not in topic_data:
                topic_data[topic] = {"correct": 0, "total": 0}

            topic_data[topic]["total"] += 1

            if q["isCorrect"]:
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
    verification_answers: Optional[Dict[str,str]]=None
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

    # ✅ Allow 1–180 minutes (for testing flexibility)
    if duration < 1 or duration > 180:
        raise HTTPException(
            status_code=400,
            detail="Duration must be between 1 and 180 minutes"
        )

    user_id = ObjectId(user["_id"])
    now = datetime.now(timezone.utc)

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


        # 🔥 If still valid → resume session
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
                "started_at": int(started_at.timestamp())
            }

        # 🔥 If expired → mark as expired
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

    duration_seconds = duration * 60  # 🔥 dynamic

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






# =========================
# HTTP CHAT API (WEB)
# =========================
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest, background_tasks: BackgroundTasks,current_user: dict = Depends(get_current_user)
):
    """
    Main chat endpoint for web clients (Angular frontend).
    
    Features:
    - Persistent chat sessions
    - Follow-up question handling
    - Domain classification (maths/science)
    - Socratic mode for derivations/problems
    - Automatic example inclusion for concepts
    
    Example request:
    ```json
    {
        "message": "What is photosynthesis?",
        "board": "CBSE",
        "session_id": "user123"
    }
    ```
    """
    
    try:
        # Generate session ID
        session_id = generate_session_id(req)

        # Get state
        state = get_state(session_id)
        state["session_id"] = session_id
        print("STATE:", state)

        user_id = str(current_user["_id"])
        state["user_id"] = user_id

        # Store board
        if req.board:
            state["board"] = req.board

        # -------------------------------------------------
        # 1️⃣ HANDLE DIAGNOSIS SELECTION
        # -------------------------------------------------
        if req.diagnosis:
            state["diagnosis"] = req.diagnosis

        if req.clarification:
            state["clarification"] = req.clarification

        if req.topic:
            state["last_topic"] = req.topic

        # -------------------------------------------------
# 🔄 HANDLE EXPLANATION REGENERATION
# -------------------------------------------------

        if req.message == "regenerate_explanation":

            if req.topic:
                state["last_topic"] = req.topic

            if req.depth:
                state["teaching_depth"] = req.depth

            structured_data = generate_adaptive_explanation(state)

            profile = state.get("diagnostic_profile")

            return ChatResponse(
                session_id=session_id,
                reply="Explanation regenerated.",
                metadata={
                    "diagnostic_profile": profile
                },
                structured=structured_data
            )

        # 🔥 HANDLE CLARIFICATION CALIBRATION (NO TUTOR RESPONSE)
        if req.clarification and req.message == "baseline":
            return ChatResponse(
                reply="Clarification recorded.",
                session_id=session_id,
                metadata={"status": "clarification_saved"}
            )

        # -------------------------------------------------
# 2️⃣ HANDLE VERIFICATION SUBMISSION

        if req.verification_answers is not None:

    # 🔥 Debug (temporary)
            print("Verification received:", req.verification_answers)
            print("Type:", type(req.verification_answers))

    # 🔒 Safety check
            if not isinstance(req.verification_answers, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid verification_answers format"
                )

            state["verification_answers"] = req.verification_answers

            profile = analyze_student_profile(
                diagnosis=state.get("diagnosis"),
                verification_answers=req.verification_answers,
                topic="baseline"
            )

            print("=== DIAGNOSTIC PROFILE ===")
            print(profile)

            state["diagnostic_profile"] = profile
            state["current_training_mode"] = profile.get("recommended_teaching_mode")
            state["teaching_depth"] = "board"
            

            structured_data = generate_adaptive_explanation(state)

            return ChatResponse(
                session_id=session_id,
                reply="Structured explanation generated.",
                metadata={
                    "diagnostic_profile": profile
                },
                structured=structured_data
            )
        
        # Get response from chat engine
        print("Calling chat_reply...")
        reply_text = chat_reply(
            chat_id=session_id,
            user_text=req.message,
            reset=req.reset,
            board=req.board,
        )
        print("Reply returned:", reply_text)
        
        # Get session metadata
        metadata = get_session_metadata(session_id)
        
        return ChatResponse(
            reply=reply_text,
            session_id=session_id,
            metadata=metadata
        )
    
    except Exception as e:
        print(f"❌ Error in chat endpoint: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while processing your request: {str(e)}"
        )


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
async def chat_stream(req: ChatRequest):
    """
    Token streaming endpoint for real-time responses.
    
    Note: This is a placeholder for future streaming implementation.
    Currently returns the same response as /chat but as a stream.
    """
    
    try:
        session_id = generate_session_id(req)
        
        # Get response
        reply_text = chat_reply(
            chat_id=session_id,
            user_text=req.message,
            reset=req.reset,
            board=req.board
        )
        
        # Simulate streaming by yielding chunks
        async def generate():
            words = reply_text.split()
            for i, word in enumerate(words):
                yield word + (" " if i < len(words) - 1 else "")
                await asyncio.sleep(0.05)  # Simulate typing delay
        
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