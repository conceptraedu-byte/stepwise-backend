from fastapi import APIRouter, Request
from app.socratic import socratic_reply
import httpx
import os

router = APIRouter()

TELEGRAM_API = f"https://api.telegram.org/bot{os.getenv('TELEGRAM_BOT_TOKEN')}"

@router.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    chat_id = data["message"]["chat"]["id"]
    text = data["message"].get("text", "")

    reply = socratic_reply(text)

    async with httpx.AsyncClient() as client:
        await client.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": reply}
        )

    return {"ok": True}
