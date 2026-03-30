from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime
from pymongo import MongoClient
from typing import List
import pytz
from bson import ObjectId
from whatsapp import app as whatsapp_api
from api import router as api_router
from auth import router as auth_router
from fastapi.middleware.cors import CORSMiddleware
from dependencies import CurrentUser
import os

# ALLOWED_ORIGINS = [
#     o.strip()
#     for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
#     if o.strip()
# ]


def add_cors(app):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


app = FastAPI(title="Multi-User Reminders API")
add_cors(app)
app.include_router(router=auth_router)
app.include_router(router=whatsapp_api)
app.include_router(router=api_router)

# MongoDB (update MONGO_URI env var for prod)
mongo_client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = mongo_client["reminders_db"]
reminders_coll = db["reminders"]


class ReminderIn(BaseModel):
    message: str
    due_datetime: str  # ISO: "2026-03-17T22:30:00+05:30"


class ReminderOut(BaseModel):
    id: str
    user_id: str
    message: str
    due_datetime: str
    status: str
    delay_seconds: int
    created_at: str


@app.post("/reminders", response_model=ReminderOut)
async def set_reminder(reminder: ReminderIn, current_user: CurrentUser):
    """Create a reminder for the authenticated user."""
    try:
        due_time = datetime.fromisoformat(reminder.due_datetime)
        now = datetime.now(pytz.timezone("Asia/Kolkata"))

        if due_time <= now:
            raise HTTPException(status_code=400, detail="Due time must be in future")

        delay_seconds = int((due_time - now).total_seconds())
        user_id = current_user["_id"]

        reminder_doc = {
            "user_id": user_id,
            "message": reminder.message,
            "due_datetime": due_time,
            "status": "scheduled",
            "created_at": now,
            "delay_seconds": delay_seconds,
            "task_id": None,
        }
        result = reminders_coll.insert_one(reminder_doc)
        rid = str(result.inserted_id)

        print(f"Scheduled reminder {rid} for user {user_id} in {delay_seconds}s")
        return ReminderOut(
            id=rid,
            user_id=user_id,
            message=reminder.message,
            due_datetime=due_time.isoformat(),
            status="scheduled",
            delay_seconds=delay_seconds,
            created_at=now.isoformat(),
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid datetime format")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/users/me/reminders", response_model=List[ReminderOut])
async def list_my_reminders(current_user: CurrentUser):
    """List all reminders for the authenticated user."""
    user_id = current_user["_id"]
    docs = list(reminders_coll.find({"user_id": user_id}).sort("created_at", -1))
    return [
        ReminderOut(
            id=str(d["_id"]),
            user_id=d["user_id"],
            message=d["message"],
            due_datetime=d["due_datetime"].isoformat(),
            status=d["status"],
            delay_seconds=d.get("delay_seconds", 0),
            created_at=d["created_at"].isoformat(),
        )
        for d in docs
    ]


@app.get("/reminders/{reminder_id}", response_model=ReminderOut)
async def get_reminder(reminder_id: str, current_user: CurrentUser):
    """Fetch a single reminder by ID (must belong to the authenticated user)."""
    try:
        reminder = reminders_coll.find_one({"_id": ObjectId(reminder_id)})
        if not reminder:
            raise HTTPException(status_code=404, detail="Reminder not found")
        if reminder["user_id"] != current_user["_id"]:
            raise HTTPException(status_code=403, detail="Access denied")
        return ReminderOut(
            id=str(reminder["_id"]),
            user_id=reminder["user_id"],
            message=reminder["message"],
            due_datetime=reminder["due_datetime"].isoformat(),
            status=reminder["status"],
            delay_seconds=reminder.get("delay_seconds", 0),
            created_at=reminder["created_at"].isoformat(),
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Invalid reminder ID")
