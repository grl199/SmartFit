import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from .config import get_settings
from .db import SessionLocal, init_db
from .deps import verify_api_key
from .models import User, UserProfile, UserTarget
from .routers import chat, dashboard, foods, logs, profile, training
from .services.nutrition import today_local

logging.basicConfig(level=logging.INFO)


def _ensure_default_user() -> None:
    uid = get_settings().default_user_id
    with SessionLocal() as db:
        if not db.get(User, uid):
            db.add(User(id=uid, name="Usuario"))
            db.flush()
            db.add_all([UserProfile(user_id=uid), UserTarget(user_id=uid)])
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    _ensure_default_user()
    yield


app = FastAPI(title="HealthApp API", version="0.1.0", lifespan=lifespan,
              dependencies=[Depends(verify_api_key)])
for r in (foods.router, logs.router, dashboard.router, profile.router, training.router, chat.router):
    app.include_router(r)


@app.get("/meta/today")
def meta_today():
    return {"date": today_local().isoformat()}


@app.get("/health")
def health():
    return {"ok": True}
