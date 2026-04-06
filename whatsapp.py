import os
import httpx
from fastapi import FastAPI, Request, Query,APIRouter
from fastapi.responses import PlainTextResponse
from datetime import datetime
import pytz
import db
from dotenv import load_dotenv
from agno.media import Audio,Image
from ai import agent,voice_agent
from tasks import handle_audio,handle_image,handle_text
load_dotenv()

app = APIRouter(prefix="/whatsapp")

VERIFY_TOKEN = "pass@123!@#" #os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")
WHATSAPP_API_URL = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"


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
        msg_id=message["id"]

        if msg_type == "text":
            text = message["text"]["body"]
            await send_reaction(to=from_number,message_id=msg_id,emoji="💬")
            reply = await handle_text.delay(text,from_number)
            # await send_message(from_number, reply)

        elif msg_type == "image":
            image_id = message["image"]["id"]
            caption = message["image"].get("caption", "")
            await send_reaction(to=from_number,message_id=msg_id,emoji="💬")
            reply = await handle_image.delay(image_id, caption, from_number)
            # await send_message(from_number, reply)

        elif msg_type == "audio":
            audio_id = message["audio"]["id"]
            await send_reaction(to=from_number,message_id=msg_id,emoji="💬")
            reply = await handle_audio.delay(audio_id, from_number)
            # await send_message(from_number, reply)

        else:
            await send_message(from_number, f"Sorry, I don't support *{msg_type}* messages yet.")

    except (KeyError, IndexError):
        pass

    return {"status": "ok"}


# --- Text Handler ---
# async def handle_text(text: str,from_number:str) -> str:
#     if "annie are you ok" in text.lower():
#         return """I have been hit by ... I have been struck by
#         .
#         .
#         .
#         A smooth criminal 🕴"""
#     else:
#         user_data=db.query(collection="users",query={"whatsapp_number":from_number})
#         print("user data", user_data)
#         print("from",from_number)
#         time=datetime.now(pytz.timezone('Asia/Kolkata'))
#         response=agent.run(input=f"""<user_name>{user_data[0]['name']}</user_name>
#                         <user_id>{user_data[0]['email']}</user_id>
#                         <plaform>whatsapp</platform>
#                         <message>{text}</message> 
#                         <datetime>{time}</datetime>""",session_id=from_number)
#         tokens=response.metrics.to_dict()
#         db.inc(collection="users",key={"whatsapp_number":from_number},doc={"input_tokens":tokens["input_tokens"],"output_tokens":tokens["output_tokens"]})
#         return response.content

# --- Image Handler ---
# async def handle_image(image_id: str, caption: str, from_number : str) -> str:
#     # Step 1: Get the image download URL from Meta
#     media_url = await get_media_url(image_id)

#     # Step 2: Download the image bytes
#     image_bytes = await download_media(media_url)
#     user_data=db.query(collection="users",query={"whatsapp_number":from_number})
#     print("user data", user_data)
#     print("from",from_number)
#     time=datetime.now(pytz.timezone('Asia/Kolkata'))
#     response=agent.run(input=f"""<user_name>{user_data[0]['name']}</user_name>
#                        <user_id>{user_data[0]['email']}</user_id>
#                        <plaform>whatsapp</platform>
#                       <message>{caption}</message> 
#                      <datetime>{time}</datetime>""",session_id=from_number,images=[Image(content=image_bytes)])
#     return response.content
    # if not image_bytes:
    #     return "❌ Couldn't download your image. Please try again."

    # # Step 3: Do something with image_bytes
    # # e.g., save to S3, run through a vision model, etc.
    # # For now, just acknowledge receipt
    # caption_note = f'\nCaption: "{caption}"' if caption else ""
    # return f"🖼️ Got your image ({len(image_bytes) // 1024} KB)!{caption_note}\n\nYou can plug in a vision model here."


# --- Audio Handler ---
# async def handle_audio(audio_id: str, from_number :str) -> str:
#     # Step 1: Get the audio download URL from Meta
#     media_url = await get_media_url(audio_id)
#     # if not media_url:
#     #     return "❌ Couldn't retrieve your audio. Please try again."

#     # Step 2: Download the audio bytes
#     audio_bytes = await download_media(media_url)
#     user_data=db.query(collection="users",query={"whatsapp_number":from_number})
#     print("user data", user_data)
#     print("from",from_number)
#     text=voice_agent.run(input="transcribe the audio",audio=[Audio(content=audio_bytes, mime_type="audio/ogg")])
#     print(text.content)
#     time=datetime.now(pytz.timezone('Asia/Kolkata'))
#     response=agent.run(input=f"""<user_name>{user_data[0]['name']}</user_name>
#                        <user_id>{user_data[0]['email']}</user_id>
#                        <plaform>whatsapp voice note</platform>
#                       <message>{text.content}</message> 
#                      <datetime>{time}</datetime>""",session_id=from_number)
#     return response.content
    # if not audio_bytes:
    #     return "❌ Couldn't download your audio. Please try again."

    # # Step 3: Do something with audio_bytes
    # # e.g., send to Whisper for transcription, save to S3, etc.
    # return f"🎙️ Got your voice message ({len(audio_bytes) // 1024} KB)!\n\nYou can plug in Whisper transcription here."


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
        "status":"read",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    print(to)
    async with httpx.AsyncClient() as client:
        response = await client.post(WHATSAPP_API_URL, json=payload, headers=headers)
        return response.json()
    
async def send_reaction(to: str, message_id: str, emoji: str):
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "status":"read",
        "to": to,
        "type": "reaction",
        "reaction": {"message_id": message_id, "emoji": emoji},
    }
    async with httpx.AsyncClient() as client:
        await client.post(WHATSAPP_API_URL, json=payload, headers={
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        })