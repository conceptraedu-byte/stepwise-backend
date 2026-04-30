import json
import asyncio
import os
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
from pymongo.errors import DuplicateKeyError

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

    print("🔗 Connecting to MongoDB...")
    client = AsyncIOMotorClient(mongo_uri)

    db = client["stepwise"]
    collection = db["questions"]

    # Create unique index to prevent duplicate questions
    await collection.create_index("question", unique=True)

    existing_count = await collection.count_documents({})
    print(f"📊 Existing questions before insert: {existing_count}")

    total_inserted = 0

    for root, dirs, files in os.walk(SEED_FOLDER):
        for file in files:

            if not file.endswith(".json"):
                continue

            file_path = os.path.join(root, file)
            print(f"\n📂 Processing file: {file_path}")

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()

                if not content:
                    print(f"⚠️ Skipping empty file: {file}")
                    continue

                data = json.loads(content)

            except Exception as e:
                print(f"❌ Failed to read JSON: {file} | {e}")
                continue

            if not isinstance(data, list):
                print(f"❌ ERROR: {file} must contain a JSON array")
                continue

            print(f"📦 Loaded {len(data)} questions")

            for idx, question in enumerate(data):

                # Validate required fields
                missing = [field for field in REQUIRED_FIELDS if field not in question]
                if missing:
                    print(f"❌ Skipping question {idx} - Missing fields: {missing}")
                    continue

                # Validate options
                if not isinstance(question["options"], list) or len(question["options"]) < 2:
                    print(f"❌ Skipping question {idx} - Invalid options")
                    continue

                # Ensure correctAnswer index is valid
                if question["correctAnswer"] >= len(question["options"]):
                    print(f"❌ Skipping question {idx} - correctAnswer out of range")
                    continue

                # Add default fields
                question["negative_marks"] = question.get("negative_marks", 0)
                question["created_at"] = datetime.now(timezone.utc)

                try:
                    await collection.insert_one(question)
                    total_inserted += 1
                    print(f"✅ Inserted: {question['question'][:60]}...")

                except DuplicateKeyError:
                    print("⚠️ Duplicate skipped")

                except Exception as e:
                    print(f"❌ Insert failed: {e}")

    final_count = await collection.count_documents({})
    print("\n================================")
    print(f"📊 Final question count: {final_count}")
    print(f"🎯 Inserted in this run: {total_inserted}")
    print("================================")

    client.close()


if __name__ == "__main__":
    asyncio.run(seed())