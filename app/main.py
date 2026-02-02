from fastapi import FastAPI
from app.telegram import router as telegram_router

app = FastAPI(title="StepWise AI")

app.include_router(telegram_router)

@app.get("/")
async def health_check():
    return {"status": "ok"}
