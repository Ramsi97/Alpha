from pydantic import BaseModel


class ReferralsOut(BaseModel):
    referral_code: str
    referral_link: str
    pending_count: int
    rewarded_count: int
