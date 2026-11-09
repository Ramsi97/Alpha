from fastapi import APIRouter

from app.api.v1 import (
    achievements,
    admin,
    analytics,
    auth,
    challenges,
    checkin,
    games,
    leaderboards,
    me,
    referrals,
    seasons,
    sessions,
    share,
    tasks,
    tournaments,
)
from app.core.rate_limit import rate_limit

# Plan section 16: "Admin routes get stricter rate limits." Applied once
# here (rather than on every individual admin route) to every router that
# is *entirely* admin-only. tasks.router mixes player and admin routes in
# one router and is deliberately excluded — its admin endpoints are still
# gated by require_admin, just not by this additional limit; see
# server/README.md's security section for that scope call.
_ADMIN_RATE_LIMIT = [rate_limit("admin", limit=600, window_seconds=3600)]

api_router = APIRouter()
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(me.router, tags=["profile"])
api_router.include_router(games.router, tags=["games"])
api_router.include_router(sessions.router, tags=["games"])
api_router.include_router(leaderboards.router, tags=["leaderboards"])
api_router.include_router(checkin.router, tags=["checkin"])
api_router.include_router(achievements.router, tags=["achievements"])
api_router.include_router(admin.router, tags=["admin"], dependencies=_ADMIN_RATE_LIMIT)
api_router.include_router(tasks.router, tags=["tasks"])
api_router.include_router(referrals.router, tags=["referrals"])
api_router.include_router(challenges.router, tags=["challenges"])
api_router.include_router(share.router, tags=["share"])
api_router.include_router(seasons.router, tags=["admin"], dependencies=_ADMIN_RATE_LIMIT)
api_router.include_router(tournaments.router, tags=["tournaments"])
api_router.include_router(tournaments.admin_router, tags=["admin"], dependencies=_ADMIN_RATE_LIMIT)
api_router.include_router(analytics.router, tags=["admin"], dependencies=_ADMIN_RATE_LIMIT)
