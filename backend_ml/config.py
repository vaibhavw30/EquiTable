"""
Centralized configuration for EquiTable backend.

All environment variables are loaded here and exported as a singleton
Settings instance. Import `settings` from this module.
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self):
        self.MONGO_URI = os.getenv("MONGO_URI", "")
        self.DATABASE_NAME = os.getenv("DATABASE_NAME", "equitable")
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
        self.GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "")
        self.DISCOVERY_CACHE_TTL_DAYS = int(
            os.getenv("DISCOVERY_CACHE_TTL_DAYS", "7")
        )


settings = Settings()
