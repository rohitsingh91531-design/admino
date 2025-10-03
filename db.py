import motor.motor_asyncio
from config import MONGO_URI, DB_NAME
from datetime import datetime, timedelta

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]

# Ensure TTL index on files collection (expireAt field)
async def ensure_indexes():
    await db.files.create_index("expireAt", expireAfterSeconds=0)
    await db.users.create_index("user_id", unique=False)
