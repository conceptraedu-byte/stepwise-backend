from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone, timedelta
from app.db import users_collection


async def reset_monthly_credits():

    now = datetime.now(timezone.utc)

    cursor = users_collection.find({
        "plan": "pro",
        "subscription_status": "active",
        "subscription_current_period_end": {"$lte": now}
    })

    async for user in cursor:

        next_period = now + timedelta(days=30)

        await users_collection.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "credits_remaining": user.get("monthly_credit_limit", 150),
                    "subscription_current_period_end": next_period,
                    "updated_at": now
                }
            }
        )

    print("✅ Monthly credit reset completed")


def start_scheduler():

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        reset_monthly_credits,
        "interval",
        hours=6
    )

    scheduler.start()