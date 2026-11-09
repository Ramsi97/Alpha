from pydantic import BaseModel

from app.schemas.user import UserOut


class AuthRequest(BaseModel):
    init_data: str


class AuthResponse(BaseModel):
    access_token: str
    expires_in: int
    user: UserOut
