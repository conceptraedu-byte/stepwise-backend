from fastapi import APIRouter, Request
from app.socratic import socratic_reply
from app import db
import httpx
import os

router = APIRouter()

TELEGRAM_API = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}"
FREE_LIMIT = 200


@router.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return {"ok": True}

    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "").strip()

    if not text:
        return {"ok": True}

    if db.users_collection is None:
        raise RuntimeError("MongoDB users_collection is not initialized")

    async with httpx.AsyncClient() as client:
        user = await db.users_collection.find_one({"chat_id": chat_id})

        if not user:
            await db.users_collection.insert_one({
                "chat_id": chat_id,
                "total_questions_asked": 1,
                "contact_shared": False
            })

        elif user["total_questions_asked"] >= FREE_LIMIT:
            await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": "🚫 You’ve reached the free limit of 10 questions.\n\nShare your contact to continue."
                }
            )
            return {"ok": True}

        else:
            await db.users_collection.update_one(
                {"chat_id": chat_id},
                {"$inc": {"total_questions_asked": 1}}
            )

        reply = socratic_reply(text)

        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": reply}
        )

    return {"ok": True}
