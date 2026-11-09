from motor.motor_asyncio import AsyncIOMotorClient

class UserSettings:
    def __init__(self, uri: str, database_name: str):
        self.client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=10000)
        self.collection = self.client[database_name]["user_settings"]

    async def ensure_user(self, user_id: int):
        await self.collection.update_one({"_id": int(user_id)}, {"$setOnInsert": {}}, upsert=True)

    async def set_value(self, user_id: int, key: str, value):
        if key.startswith("$") or "." in key:
            raise ValueError("Invalid setting key")
        await self.collection.update_one(
            {"_id": int(user_id)}, {"$set": {key: value}}, upsert=True
        )

    async def get_value(self, user_id: int, key: str, default=None):
        user = await self.collection.find_one({"_id": int(user_id)}, {key: 1})
        return user.get(key, default) if user else default

    async def set_template(self, user_id: int, template: str):
        await self.set_value(user_id, "rename_template", template)

    async def get_template(self, user_id: int):
        return await self.get_value(user_id, "rename_template")

    async def reset_template(self, user_id: int):
        await self.set_value(user_id, "rename_template", None)

    async def close(self):
        self.client.close()
