from motor.motor_asyncio import AsyncIOMotorClient

class UserSettings:
    def __init__(self, uri: str, database_name: str):
        self.client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=10000)
        self.collection = self.client[database_name]["user_settings"]

    async def set_template(self, user_id: int, template: str):
        result = await self.collection.update_one(
            {"_id": int(user_id)}, {"$set": {"rename_template": template}}, upsert=True
        )
        if result.matched_count == 0 and result.upserted_id is None:
            raise RuntimeError("MongoDB did not persist the rename template")

    async def get_template(self, user_id: int):
        user = await self.collection.find_one({"_id": int(user_id)}, {"rename_template": 1})
        return user.get("rename_template") if user else None

    async def reset_template(self, user_id: int):
        await self.collection.update_one(
            {"_id": int(user_id)}, {"$unset": {"rename_template": ""}}, upsert=True
        )

    async def close(self):
        self.client.close()
