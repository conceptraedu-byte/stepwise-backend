from motor.motor_asyncio import AsyncIOMotorClient
import os

client = None
db = None
users_collection = None


def init_db():
    global client, db, users_collection

    mongo_uri = os.getenv("MONGO_URI")

    if not mongo_uri:
        raise RuntimeError("MONGO_URI is not set in environment variables")

    client = AsyncIOMotorClient(mongo_uri)
    db = client["stepwise"]
    users_collection = db["users"]

    print("✅ MongoDB connected successfully")
