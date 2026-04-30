from pydantic import BaseModel, EmailStr

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

#  .\.venv\Scripts\activate
#  uvicorn app.main:app --reload
