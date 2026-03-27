import os
import httpx
from fastapi import FastAPI, Request, Query,APIRouter
from fastapi.responses import PlainTextResponse
from datetime import datetime
import pytz
from dotenv import load_dotenv
from ai import agent
load_dotenv()

app = APIRouter()

VERIFY_TOKEN = "pass@123!@#"
WHATSAPP_TOKEN = "EAASZCUKLoOEEBRIZBCl9gZCjZC9XsbwlIVf9ZCXD54Add0SpwlrzdYpThG7ieOzL8kZAUFbOyYwvG4py55wPIrfXTQFkq6FC4vJZBJEnOPNET7ikEdx24258VsIGED0dTwXyUlLnu7ITdmtJ9yrueXHkueW8odMlNEkYttdqbztrnsdfPv5VlRZCizK8uWWKc5l2ibv2jZB9WM2QMKw9ZBqiK6rEjQaLk9WpOZAF6cn"
PHONE_NUMBER_ID = "1104016476118691"
WHATSAPP_API_URL = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"


# --- 1. Webhook Verification (GET) ---
@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return PlainTextResponse(content=hub_challenge, status_code=200)
    return PlainTextResponse(content="Forbidden", status_code=403)


# --- 2. Receive Messages (POST) ---
@app.post("/webhook")
async def receive_message(request: Request):
    data = await request.json()
    print(data)
    try:
        entry = data["entry"][0]
        value = entry["changes"][0]["value"]

        if "messages" not in value:
            return {"status": "ok"}

        message = value["messages"][0]
        from_number = message["from"]
        msg_type = message["type"]

        if msg_type == "text":
            text = message["text"]["body"]
            reply = await handle_text(text,from_number)
            await send_message(from_number, reply)

        elif msg_type == "image":
            image_id = message["image"]["id"]
            caption = message["image"].get("caption", "")
            reply = await handle_image(image_id, caption)
            await send_message(from_number, reply)

        elif msg_type == "audio":
            audio_id = message["audio"]["id"]
            reply = await handle_audio(audio_id)
            await send_message(from_number, reply)

        else:
            await send_message(from_number, f"Sorry, I don't support *{msg_type}* messages yet.")

    except (KeyError, IndexError):
        pass

    return {"status": "ok"}


# --- Text Handler ---
async def handle_text(text: str,from_number:str) -> str:
    # text = text.strip().lower()
    # if text in ["hi", "hello", "hey"]:
    #     return "👋 Hello! I'm your WhatsApp bot. How can I help you?"
    # elif text == "help":
    #     return "Available commands:\n• *hello* - Greet the bot\n• *help* - Show this menu\n• *status* - Check bot status"
    # elif text == "status":
    #     return "✅ Bot is running and healthy!"
    # else:
    #     return f"You said: *{text}*\n\nType *help* to see available commands."
    print("from",from_number)
    time=datetime.now(pytz.timezone('Asia/Kolkata'))
    response=agent.run(input=f"""<user_name>Anish</user_name>
                      <message>{text}</message> 
                     <datetime>{time}</datetime>""",session_id=from_number)
    return response.content

# --- Image Handler ---
async def handle_image(image_id: str, caption: str) -> str:
    # Step 1: Get the image download URL from Meta
    media_url = await get_media_url(image_id)
    if not media_url:
        return "❌ Couldn't retrieve your image. Please try again."

    # Step 2: Download the image bytes
    image_bytes = await download_media(media_url)
    if not image_bytes:
        return "❌ Couldn't download your image. Please try again."

    # Step 3: Do something with image_bytes
    # e.g., save to S3, run through a vision model, etc.
    # For now, just acknowledge receipt
    caption_note = f'\nCaption: "{caption}"' if caption else ""
    return f"🖼️ Got your image ({len(image_bytes) // 1024} KB)!{caption_note}\n\nYou can plug in a vision model here."


# --- Audio Handler ---
async def handle_audio(audio_id: str) -> str:
    # Step 1: Get the audio download URL from Meta
    media_url = await get_media_url(audio_id)
    if not media_url:
        return "❌ Couldn't retrieve your audio. Please try again."

    # Step 2: Download the audio bytes
    audio_bytes = await download_media(media_url)
    if not audio_bytes:
        return "❌ Couldn't download your audio. Please try again."

    # Step 3: Do something with audio_bytes
    # e.g., send to Whisper for transcription, save to S3, etc.
    return f"🎙️ Got your voice message ({len(audio_bytes) // 1024} KB)!\n\nYou can plug in Whisper transcription here."


# --- Media Helpers ---
async def get_media_url(media_id: str) -> str | None:
    """Fetch the temporary download URL for a media object from Meta."""
    url = f"https://graph.facebook.com/v21.0/{media_id}"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        data = response.json()
        return data.get("url")  # Temporary URL, valid for ~5 minutes


async def download_media(media_url: str) -> bytes | None:
    """Download the actual media bytes using the temporary URL."""
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(media_url, headers=headers)
        if response.status_code == 200:
            return response.content
        return None


# --- Send Text Message ---
async def send_message(to: str, body: str):
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
    async with httpx.AsyncClient() as client:
        response = await client.post(WHATSAPP_API_URL, json=payload, headers=headers)
        return response.json()
