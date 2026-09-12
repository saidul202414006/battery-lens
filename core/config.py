from core.database import Database
from core.models import AppSettings

class ConfigManager:
    def __init__(self, db: Database):
        self.db = db

    def get_settings(self) -> AppSettings:
        return self.db.get_settings()

    def update_setting(self, key: str, value: str):
        self.db.update_setting(key, value)
