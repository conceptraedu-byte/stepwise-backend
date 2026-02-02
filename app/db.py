from motor.motor_asyncio import AsyncIOMotorClient
import os

client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = client["stepwise"]

users_collection = db["users"]
