from fastapi import APIRouter, Request, HTTPException
from app.socratic import socratic_reply
from app.db import users_collection
import httpx
import os

router = APIRouter()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

FREE_LIMIT = 10  # free questions per user


@router.post("/webhook")
async def telegram_webhook(request: Request):
    # ---- SAFETY CHECKS ----
    if users_collection is None:
        raise RuntimeError("MongoDB users_collection is not initialized")

    data = await request.json()

    # Telegram sometimes sends non-message updates
    if "message" not in data:
        return {"ok": True}

    message = data["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    if not text:
        return {"ok": True}

    async with httpx.AsyncClient() as client:
        # ---- USER LOOKUP ----
        user = await users_collection.find_one({"chat_id": chat_id})

        # ---- NEW USER ----
        if not user:
            await users_collection.insert_one({
                "chat_id": chat_id,
                "total_questions_asked": 1,
                "contact_shared": False
            })

        # ---- LIMIT REACHED ----
        elif user.get("total_questions_asked", 0) >= FREE_LIMIT:
            await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": (
                        "🚫 You’ve reached the free limit of 10 questions.\n\n"
                        "📩 Share your contact to unlock unlimited access."
                    )
                }
            )
            return {"ok": True}

        # ---- UNDER LIMIT ----
        else:
            await users_collection.update_one(
                {"chat_id": chat_id},
                {"$inc": {"total_questions_asked": 1}}
            )

        # ---- SOCRATIC REPLY ----
        reply = socratic_reply(text)

        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": reply
            }
        )

    return {"ok": True}
