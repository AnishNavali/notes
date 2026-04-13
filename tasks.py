# celery_app.py
from celery import Celery
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import db as database
import httpx
import pytz
from func import *

# import db
from agno.media import Audio, Image
from ai import agent, voice_agent
from dotenv import load_dotenv
import os

load_dotenv()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
WHATSAPP_API_URL = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"


celery = Celery(
    "reminder_app",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=["tasks"],
)

# All tasks without an explicit queue= go to "default"
# This ensures beat tasks land on "default" not Celery's built-in "celery" queue
celery.conf.task_default_queue = "default"

# MongoDB
mongo_client = MongoClient(os.getenv("MONGO_URI"))
db = mongo_client["reminders_db"]
reminders_coll = db["reminders"]


@celery.task
def trigger_reminder(message: str, reminder_id: str, user_id: str):
    """Individual reminder trigger (from countdown)"""
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    print(f"🔔 TRIGGERED for {user_id}: {message}")
    print(f"⏰ {now.strftime('%Y-%m-%d %H:%M:%S IST')}")

    # Update status
    # reminders_coll.update_one(
    #     {"_id": ObjectId(reminder_id)},
    #     {"$set": {
    #         "status": "triggered",
    #         "triggered_at": datetime.now()
    #     }}
    # )
    database.save(
        collection="reminders",
        key={"_id": ObjectId(reminder_id)},
        doc={"status": "triggered", "triggered_at": datetime.now()},
    )
    whatsapp_number = database.get_one(collection="users", key={"email": user_id})[
        "whatsapp_number"
    ]
    send_message(to=whatsapp_number, body=f"Reminder : {message}")
    return f"Triggered {reminder_id}"


@celery.task
def heartbeat_check_reminders():
    """Scan all users' due reminders every 5min (for production)"""
    now = datetime.now(pytz.timezone("Asia/Kolkata"))
    # due_reminders = list(reminders_coll.find({
    #     "status": "scheduled",
    #     "due_datetime": {"$lte": now}
    # }))
    coll = database.get_collection("reminders")
    due_reminders = list(
        coll.find({"status": "scheduled", "due_datetime": {"$lte": now}})
    )

    print(due_reminders)
    triggered = 0
    for r in due_reminders:
        trigger_reminder.delay(r["message"], str(r["_id"]), r["user_id"])
        triggered += 1

    print(f"🔍 Heartbeat: Found & queued {triggered} due reminders")
    return f"Scanned {len(due_reminders)} reminders"


@celery.task
def check_grace_periods():
    """
    Hourly task: downgrade users whose subscription grace period has expired.
    Finds all users with status='grace_period' where grace_period_end < now
    and sets their plan to 'free' and status to 'expired'.
    """
    from datetime import timezone

    now = datetime.now(timezone.utc)
    coll = database.get_collection("users")
    expired_users = list(
        coll.find(
            {
                "subscription.status": "grace_period",
                "subscription.grace_period_end": {"$lt": now},
            },
            {"email": 1},
        )
    )

    downgraded = 0
    for user in expired_users:
        email = user.get("email")
        if email:
            database.save(
                collection="users",
                key={"email": email},
                doc={
                    "subscription.status": "expired",
                    "subscription.plan": "free",
                    "subscription.grace_period_end": None,
                },
            )
            downgraded += 1
            print(f"Downgraded {email} to free (grace period expired)")

    print(f"check_grace_periods: downgraded {downgraded} user(s)")
    return f"Downgraded {downgraded} user(s)"


# Beat schedule (run: celery -A tasks beat)
celery.conf.beat_schedule = {
    "scan-reminders-every-1min": {
        "task": "tasks.heartbeat_check_reminders",
        "schedule": 60.0,  # every 1 minute
    },
    "check-grace-periods-hourly": {
        "task": "tasks.check_grace_periods",
        "schedule": 3600.0,  # every 1 hour
    },
}


@celery.task(bind=True, queue="messages")
def handle_text(self, text: str, from_number: str) -> str:
    if "annie are you ok" in text.lower():
        return """I have been hit by ... I have been struck by
        .
        .
        .
        A smooth criminal 🕴"""
    else:
        allow = check_sub_status(filter={"whatsapp_number": from_number})
        if allow[0]:
            user_data = allow[1]
            # user_data = database.query(
            #     collection="users", query={"whatsapp_number": from_number}
            # )
            print("user data", user_data)
            print("from", from_number)
            time = datetime.now(pytz.timezone(user_data[0]["timezone"]))
            response = agent.run(
                input=f"""<user_name>{user_data[0]["name"]}</user_name>
                            <user_id>{user_data[0]["email"]}</user_id>
                            <password>{user_data[0]["password"]}</password>
                            <plaform>whatsapp</platform>
                            <message>{text}</message> 
                            <datetime>{time}</datetime>""",
                session_id=from_number,
            )
            tokens = response.metrics.to_dict()
            database.inc(
                collection="users",
                key={"whatsapp_number": from_number},
                doc={
                    "input_tokens": tokens["input_tokens"],
                    "output_tokens": tokens["output_tokens"],
                },
            )
            send_message(to=from_number, body=response.content)

        else:
            body = "You have reached your chat limit for the current billing cycle."
            send_message(to=from_number, body=body)
        # return response.content


@celery.task(bind=True, queue="messages")
def handle_image(self, image_id: str, caption: str, from_number: str) -> str:
    # Step 1: Get the image download URL from Meta
    media_url = get_media_url(image_id)

    # Step 2: Download the image bytes
    image_bytes = download_media(media_url)
    allow = check_sub_status(filter={"whatsapp_number": from_number})

    if allow[0]:
        user_data = allow[1]
        # user_data = database.query(
        #     collection="users", query={"whatsapp_number": from_number}
        # )
        print("user data", user_data)
        print("from", from_number)
        time = datetime.now(pytz.timezone(user_data[0]["timezone"]))
        response = agent.run(
            input=f"""<user_name>{user_data[0]["name"]}</user_name>
                        <user_id>{user_data[0]["email"]}</user_id>
                        <password>{user_data[0]["password"]}</password>
                        <plaform>whatsapp</platform>
                        <message>{caption}</message> 
                        <datetime>{time}</datetime>""",
            session_id=from_number,
            images=[Image(content=image_bytes)],
        )
        send_message(to=from_number, body=response.content)
    else:
        send_message(
            to=from_number,
            body="You have reached your chat limit for the current billing cycle.",
        )


@celery.task(bind=True, queue="messages")
def handle_audio(self, audio_id: str, from_number: str) -> str:
    # Step 1: Get the audio download URL from Meta
    media_url = get_media_url(audio_id)
    # if not media_url:
    #     return "❌ Couldn't retrieve your audio. Please try again."

    # Step 2: Download the audio bytes
    audio_bytes = download_media(media_url)
    # user_data = database.query(
    #     collection="users", query={"whatsapp_number": from_number}
    # )
    allow = check_sub_status(filter={"whatsapp_number": from_number})
    if allow[0]:
        user_data = allow[1]
        print("user data", user_data)
        print("from", from_number)
        text = voice_agent.run(
            input="transcribe the audio",
            audio=[Audio(content=audio_bytes, mime_type="audio/ogg")],
        )
        print(text.content)
        time = datetime.now(pytz.timezone(user_data[0]["timezone"]))
        response = agent.run(
            input=f"""<user_name>{user_data[0]["name"]}</user_name>
                        <user_id>{user_data[0]["email"]}</user_id>
                        <password>{user_data[0]["password"]}</password>
                        <plaform>whatsapp voice note</platform>
                        <message>{text.content}</message> 
                        <datetime>{time}</datetime>""",
            session_id=from_number,
        )
        send_message(to=from_number, body=response.content)
    else:
        send_message(
            to=from_number,
            body="You have reached your chat limit for the current billing cycle.",
        )


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
        response = client.post(WHATSAPP_API_URL, json=payload, headers=headers)
        return response.json()


def get_media_url(media_id: str) -> str | None:
    """Fetch the temporary download URL for a media object from Meta."""
    url = f"https://graph.facebook.com/v21.0/{media_id}"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    with httpx.Client() as client:
        response = client.get(url, headers=headers)
        data = response.json()
        return data.get("url")  # Temporary URL, valid for ~5 minutes


def download_media(media_url: str) -> bytes | None:
    """Download the actual media bytes using the temporary URL."""
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    with httpx.Client() as client:
        response = client.get(media_url, headers=headers)
        if response.status_code == 200:
            return response.content
        return None
