# celery_app.py
from celery import Celery
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import db as database
import httpx
import pytz
from dotenv import load_dotenv
import os
load_dotenv()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
WHATSAPP_API_URL = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"


celery = Celery(
    "reminder_app",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=['tasks']
)

# MongoDB
mongo_client = MongoClient("mongodb://localhost:27017")
db = mongo_client["reminders_db"]
reminders_coll = db["reminders"]

@celery.task
def trigger_reminder(message: str, reminder_id: str, user_id: str):
    """Individual reminder trigger (from countdown)"""
    now = datetime.now(pytz.timezone('Asia/Kolkata'))
    print(f"🔔 TRIGGERED for {user_id}: {message}")
    print(f"⏰ {now.strftime('%Y-%m-%d %H:%M:%S IST')}")
    
    # Update status
    reminders_coll.update_one(
        {"_id": ObjectId(reminder_id)},
        {"$set": {
            "status": "triggered",
            "triggered_at": datetime.now()
        }}
    )
    whatsapp_number=database.get_one(collection="users",key={"email":user_id})["whatsapp_number"]
    send_message(to=whatsapp_number,body=f"Reminder : {message}")
    return f"Triggered {reminder_id}"

@celery.task
def heartbeat_check_reminders():
    """Scan all users' due reminders every 5min (for production)"""
    now = datetime.now(pytz.timezone('Asia/Kolkata'))
    due_reminders = list(reminders_coll.find({
        "status": "scheduled",
        "due_datetime": {"$lte": now}
    }))
    
    triggered = 0
    for r in due_reminders:
        trigger_reminder.delay(r["message"], str(r["_id"]), r["user_id"])
        triggered += 1
    
    print(f"🔍 Heartbeat: Found & queued {triggered} due reminders")
    return f"Scanned {len(due_reminders)} reminders"

# Beat schedule (run: celery -A celery_app beat)
celery.conf.beat_schedule = {
    'scan-reminders-every-1min': {
        'task': 'tasks.heartbeat_check_reminders',
        'schedule': 60.0,  # 1 minute
    },
}
def send_message(to: str, body: str):
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    print(to)
    with httpx.Client() as client:
        response =  client.post(WHATSAPP_API_URL, json=payload, headers=headers)
        return response.json()