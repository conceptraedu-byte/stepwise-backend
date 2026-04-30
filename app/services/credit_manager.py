from fastapi import HTTPException
from datetime import datetime
from bson import ObjectId

import app.db


# -----------------------------------
# Credit Costs
# -----------------------------------

CHAT_COST = 1
MOCK_COST = 3
VERIFICATION_COST = 1

# -----------------------------------
# Fetch User
# -----------------------------------

async def get_user(user_id: str):
    user = await app.db.users_collection.find_one({"_id": ObjectId(user_id)})

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


# -----------------------------------
# Check Credits (no deduction)
# -----------------------------------

async def check_credits(user_id: str, cost: int):
    user = await get_user(user_id)

    # Admin bypass
    if user.get("role") == "admin":
        return True

    credits = user.get("credits_remaining", 0)

    if credits < cost:
        raise HTTPException(
            status_code=402,
            detail=f"Not enough credits. Required: {cost}, Available: {credits}"
        )

    return True


# -----------------------------------
# Atomic Credit Deduction
# -----------------------------------

async def consume_credits(user_id: str, cost: int, action: str):
    """
    Safely deduct credits using atomic Mongo update
    """

    user = await get_user(user_id)

    # Admin bypass
    if user.get("role") == "admin":
        return True

    result = await app.db.users_collection.update_one(
        {
            "_id": ObjectId(user_id),
            "credits_remaining": {"$gte": cost}
        },
        {
            "$inc": {"credits_remaining": -cost},
            "$set": {"updated_at": datetime.utcnow()}
        }
    )

    if result.modified_count == 0:
        raise HTTPException(
            status_code=402,
            detail="Not enough credits"
        )

    return True