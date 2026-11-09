from pydantic import BaseModel, Field


class RatingRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
