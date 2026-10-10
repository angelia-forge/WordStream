from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    authenticated: bool
    csrf_token: str


class SessionResponse(BaseModel):
    authenticated: bool
