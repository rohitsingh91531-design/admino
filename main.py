import asyncio
import logging
import os
from datetime import datetime, timedelta
from bson import ObjectId

from pyrogram import Client, filters
from pyrogram.types import Message
from motor.motor_asyncio import AsyncIOMotorClient

import config
from script import script  # your text/templates

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("admino")

# Pyrogram client
app = Client(
    "admino_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    workdir="."
)

# Mongo
mongo = AsyncIOMotorClient(config.MONGO_URI)
db = mongo[config.DB_NAME]

# Helper: create deep link
def make_deep_link(file_id_str: str):
    # file_id_str expected to be the DB _id string
    return f"https://t.me/{config.BOT_USERNAME}?start=file_{file_id_str}"

# Optionally shorten link (simple tinyurl fallback)
import aiohttp
async def shorten_url(url: str):
    if config.SHORTENER_API:
        # If you have custom shortener API, adapt here (example placeholder)
        # e.g., POST to YOUR_SHORTENER with key and long url
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"api_key": config.SHORTENER_API, "url": url}
                # NOTE: user must set the API endpoint and format - placeholder:
                async with session.post("https://your-shortener.example/api/shorten", json=payload, timeout=15) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("short_url", url)
        except Exception:
            pass
    # fallback to tinyurl (no api key needed)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://tinyurl.com/api-create.php?url={url}") as r:
                if r.status == 200:
                    text = await r.text()
                    return text.strip()
    except Exception:
        pass
    return url

# Ensure indexes
async def ensure_indexes():
    await db.files.create_index("expireAt", expireAfterSeconds=0)
    await db.users.create_index("user_id", unique=False)

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client: Client, message: Message):
    text = message.text or ""
    if " " in text:
        # sometimes /start <param> comes separated - handle both
        parts = text.split(" ", 1)
        param = parts[1].strip()
    else:
        parts = text.split("?", 1)
        param = ""
        if parts and parts[0].startswith("/start"):
            # nothing
            param = message.text.replace("/start", "").strip()
        # but Pyrogram gives full message; safer to parse deep-link from entities or via message.text
        if not param and message.text and message.text.startswith("/start "):
            param = message.text.split(" ", 1)[1].strip()

    # Another way: check start payload in message.entities — some clients pass as one token: /start=payload
    if not param:
        # try to get from message.text with = e.g., /start=file_...
        if "=" in message.text:
            param = message.text.split("=", 1)[1].strip()

    if param.startswith("file_"):
        fid = param.split("file_", 1)[1]
        try:
            doc = await db.files.find_one({"_id": ObjectId(fid)})
        except Exception:
            doc = None
        if not doc:
            await message.reply_text("Sorry, this file link is invalid or expired.")
            return
        # send file by copying from log channel (we stored log_channel_msg_id and the message type)
        try:
            # use copy to preserve original file
            await client.copy_message(
                chat_id=message.chat.id,
                from_chat_id=doc["log_chat_id"],
                message_id=doc["log_message_id"],
                caption=script.CAPTION.format(file_name=doc.get("file_name","unknown"), file_size=doc.get("file_size","unknown"))
            )
        except Exception as e:
            logger.exception("Failed to send file for deep link")
            await message.reply_text("Failed to deliver file. It might have been deleted.")
        return

    # default start
    await message.reply_text(script.START_TXT.format(message.from_user.first_name or "User", config.BOT_USERNAME),
                             disable_web_page_preview=True)

@app.on_message(filters.command("help") & filters.private)
async def help_cmd(client, message):
    await message.reply_text(script.HELP_TXT, disable_web_page_preview=True)

# /link - reply to a file to generate sharable link
@app.on_message(filters.command("link") & filters.private)
async def link_cmd(client: Client, message: Message):
    if not message.reply_to_message:
        await message.reply_text("Reply to the file (video/document/photo) with /link to get a sharable link.")
        return

    rm = message.reply_to_message

    # detect file type and file_id
    file_field = None
    file_name = None
    file_size = None

    if rm.document:
        file_field = rm.document.file_id
        file_name = rm.document.file_name
        file_size = str(round(rm.document.file_size / (1024*1024), 2)) + " MB" if rm.document.file_size else "Unknown"
    elif rm.video:
        file_field = rm.video.file_id
        file_name = getattr(rm.video, "file_name", f"video_{rm.message_id}.mp4")
        file_size = str(round(rm.video.file_size / (1024*1024), 2)) + " MB" if rm.video.file_size else "Unknown"
    elif rm.audio:
        file_field = rm.audio.file_id
        file_name = rm.audio.file_name or f"audio_{rm.message_id}"
        file_size = str(round(rm.audio.file_size / (1024*1024), 2)) + " MB" if rm.audio.file_size else "Unknown"
    elif rm.photo:
        # photo has array, use largest
        file_field = rm.photo.file_id
        file_name = f"photo_{rm.message_id}.jpg"
        file_size = "unknown"
    else:
        await message.reply_text("Unsupported media type. Reply to a document/video/photo/audio.")
        return

    # Copy message to log channel (bot must be admin)
    try:
        copied = await client.copy_message(chat_id=config.LOG_CHANNEL, from_chat_id=rm.chat.id, message_id=rm.message_id)
    except Exception as e:
        logger.exception("Failed to copy message to log channel")
        await message.reply_text("Bot couldn't save file to log channel. Make sure bot is admin of the log channel.")
        return

    # Store to DB
    now = datetime.utcnow()
    expire_at = now + timedelta(hours=config.AUTO_DELETE_HOURS)
    doc = {
        "owner_id": message.from_user.id,
        "owner_name": message.from_user.username or message.from_user.first_name,
        "file_name": file_name,
        "file_size": file_size,
        "tg_file_id": file_field,
        "log_chat_id": copied.chat.id,
        "log_message_id": copied.message_id,
        "created_at": now,
        "expireAt": expire_at
    }
    res = await db.files.insert_one(doc)
    file_db_id = str(res.inserted_id)
    deep_link = make_deep_link(file_db_id)
    short = await shorten_url(deep_link)

    # Reply with the link
    reply_text = f"<b>Link generated ✅</b>\n\nDirect: {deep_link}\n\nShort: {short}\n\nNote: File will auto-delete after {config.AUTO_DELETE_HOURS} hours."
    await message.reply_text(reply_text, disable_web_page_preview=True)

# /search <term> - search files by name (private)
@app.on_message(filters.command("search") & filters.private)
async def search_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("Usage: /search <filename or keyword>")
        return
    q = args[1].strip()
    cursor = db.files.find({"file_name": {"$regex": q, "$options": "i"}}).sort("created_at", -1).limit(10)
    items = await cursor.to_list(length=10)
    if not items:
        await message.reply_text("No files found for that query.")
        return
    out = []
    for it in items:
        fid = str(it["_id"])
        out.append(f"{it.get('file_name','-')} — /start file_{fid} → https://t.me/{config.BOT_USERNAME}?start=file_{fid}")
    await message.reply_text("\n\n".join(out), disable_web_page_preview=True)

# Admin-only: /broadcast (reply to message) -> forward to update channel
@app.on_message(filters.command("broadcast") & filters.user(config.ADMIN_ID))
async def broadcast_cmd(client, message):
    if not message.reply_to_message:
        await message.reply_text("Reply to a message with /broadcast to send it to the update channel.")
        return
    try:
        await client.copy_message(chat_id=config.UPDATE_CHANNEL, from_chat_id=message.reply_to_message.chat.id, message_id=message.reply_to_message.message_id)
        await message.reply_text("Broadcast sent to update channel.")
    except Exception as e:
        logger.exception("Broadcast failed")
        await message.reply_text("Broadcast failed. Make sure bot has rights in the update channel.")

# Admin-only delete file by DB id: /delfile <id>
@app.on_message(filters.command("delfile") & filters.user(config.ADMIN_ID))
async def delfile_cmd(client, message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply_text("Usage: /delfile <db_id>")
        return
    fid = args[1].strip()
    try:
        doc = await db.files.find_one({"_id": ObjectId(fid)})
    except Exception:
        await message.reply_text("Invalid id.")
        return
    if not doc:
        await message.reply_text("File not found.")
        return
    # delete copied message in log channel
    try:
        await client.delete_messages(chat_id=doc["log_chat_id"], message_ids=doc["log_message_id"])
    except Exception as e:
        logger.warning("Failed to delete message in log channel (maybe already deleted)")
    await db.files.delete_one({"_id": ObjectId(fid)})
    await message.reply_text("Deleted file record and removed file from log channel (if possible).")

# Background sweeper: deletes old files from log channel and DB
async def sweeper():
    while True:
        try:
            now = datetime.utcnow()
            expired = db.files.find({"expireAt": {"$lte": now}})
            async for doc in expired:
                try:
                    await app.delete_messages(chat_id=doc["log_chat_id"], message_ids=doc["log_message_id"])
                except Exception:
                    pass
                try:
                    await db.files.delete_one({"_id": doc["_id"]})
                except Exception:
                    pass
        except Exception:
            logger.exception("Error in sweeper loop")
        await asyncio.sleep(config.SWEEPER_INTERVAL)

# On startup
@app.on_message(filters.command("ping") & filters.user(config.ADMIN_ID))
async def ping_cmd(client, message):
    await message.reply_text("Pong!")

async def main():
    await ensure_indexes()
    # also ensure indexes for motor client
    await db.files.create_index("expireAt", expireAfterSeconds=0)
    # start sweeper task
    app.loop.create_task(sweeper())
    await app.start()
    logger.info("Admino bot started.")
    await idle()

if __name__ == "__main__":
    from pyrogram import idle
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        loop.run_until_complete(app.stop())
