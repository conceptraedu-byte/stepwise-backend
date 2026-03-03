from motor.motor_asyncio import AsyncIOMotorClient
import os

client = None
db = None
users_collection = None
questions_collection = None
mock_results_collection = None
test_sessions_collection = None



def init_db():
    global client, db, users_collection, questions_collection, mock_results_collection, test_sessions_collection

    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise RuntimeError("MONGO_URI is not set")

    client = AsyncIOMotorClient(
        mongo_uri,
        tls=True,
        tlsAllowInvalidCertificates=True,
        serverSelectionTimeoutMS=5000
    )

    db = client["stepwise"]

    users_collection = db["users"]
    questions_collection = db["questions"]
    mock_results_collection = db["mock_results"]
    test_sessions_collection = db["test_sessions"]   # 👈 NEW

    print("✅ MongoDB client initialized")