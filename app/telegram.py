from fastapi import APIRouter, Request
from app.socratic import socratic_reply
from app.db import users_collection
import httpx
import os

router = APIRouter()

TELEGRAM_API = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}"
FREE_LIMIT = 10  # <-- THIS IS WHERE 10 IS SET

@router.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")

    # ---- USER LOOKUP ----
    user = await users_collection.find_one({"chat_id": chat_id})

    async with httpx.AsyncClient() as client:

        # ---- NEW USER ----
        if not user:
            await users_collection.insert_one({
                "chat_id": chat_id,
                "total_questions_asked": 1,
                "contact_shared": False
            })

        # ---- LIMIT REACHED ----
        elif user["total_questions_asked"] >= FREE_LIMIT:
            await client.post(
                f"{TELEGRAM_API}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": (
                        "You’ve reached the free limit of 10 questions.\n\n"
                        "Share your contact to unlock more."
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

        # ---- SOCratic REPLY ----
        reply = socratic_reply(text)

        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": reply}
        )

    return {"ok": True}
