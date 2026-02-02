from motor.motor_asyncio import AsyncIOMotorClient
import os

client = None
db = None
users_collection = None

def init_db():
    global client, db, users_collection
    client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
    db = client["stepwise"]
    users_collection = db["users"]
