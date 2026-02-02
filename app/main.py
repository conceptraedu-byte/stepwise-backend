from fastapi import FastAPI
from app.telegram import router as telegram_router
from app.db import init_db

app = FastAPI(title="StepWise AI")


@app.on_event("startup")
async def startup_event():
    init_db()


app.include_router(telegram_router)


@app.get("/")
async def health_check():
    return {"status": "ok"}
