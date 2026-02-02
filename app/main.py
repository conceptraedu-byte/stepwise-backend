from fastapi import FastAPI

app = FastAPI(title="StepWise AI")

@app.get("/")
async def health_check():
    return {"status": "ok"}
