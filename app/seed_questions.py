import json
import asyncio
import os
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SEED_FOLDER = os.path.join(BASE_DIR, "..", "seed_data")


REQUIRED_FIELDS = [
    "question",
    "options",
    "correctAnswer",
    "board",
    "subject",
    "class",
    "chapter",
    "difficulty",
    "marks",
    "explanation"
]


async def seed():

    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise RuntimeError("❌ MONGO_URI not set")

    print("🔗 Connecting to Mongo...")
    client = AsyncIOMotorClient(mongo_uri)

    db = client["stepwise"]
    collection = db["questions"]

    existing_count = await collection.count_documents({})
    print(f"📊 Existing questions in DB before insert: {existing_count}")

    total_inserted = 0

    for root, dirs, files in os.walk(SEED_FOLDER):
        for file in files:
            if file.endswith(".json"):

                file_path = os.path.join(root, file)
                print(f"\n📂 Processing file: {file_path}")

                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()

                    if not content:
                        print(f"⚠️ Skipping empty file: {file_path}")
                        continue

                    data = json.loads(content)


                if not isinstance(data, list):
                    print(f"❌ ERROR: {file} is not a JSON array.")
                    continue

                print(f"📦 Loaded {len(data)} questions from file.")

                for idx, question in enumerate(data):

                    missing = [field for field in REQUIRED_FIELDS if field not in question]
                    if missing:
                        print(f"❌ Skipping question {idx} - Missing fields: {missing}")
                        continue

                    question["negative_marks"] = question.get("negative_marks", 0)
                    question["created_at"] = datetime.utcnow()

                    result = await collection.insert_one(question)
                    total_inserted += 1

                    print(f"✅ Inserted: {question['question'][:50]}...")

    final_count = await collection.count_documents({})
    print(f"\n📊 Final question count in DB: {final_count}")
    print(f"🎯 Total inserted this run: {total_inserted}")

    client.close()


if __name__ == "__main__":
    asyncio.run(seed())
