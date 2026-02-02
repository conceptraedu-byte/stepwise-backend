from motor.motor_asyncio import AsyncIOMotorClient
import os

mongo_uri = os.getenv("MONGO_URI")
print("MONGO_URI FROM ENV:", mongo_uri)

client = AsyncIOMotorClient(mongo_uri)
db = client["stepwise"]

users_collection = db["users"]
