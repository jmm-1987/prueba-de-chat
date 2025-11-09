import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "cambia-esto-en-produccion")
    GREEN_API_URL = os.environ.get("GREEN_API_URL", "https://7107.api.green-api.com")
    GREEN_INSTANCE_ID = os.environ.get("GREEN_INSTANCE_ID", "7107349111")
    GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'app.db'}"
    )
    SQLALCHEMY_ECHO = os.environ.get("SQLALCHEMY_ECHO", "false").lower() == "true"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    GREEN_API_TIMEOUT = tuple(
        int(part)
        for part in os.environ.get("GREEN_API_TIMEOUT", "5,10").split(",")
        if part.strip()
    )
    GREEN_API_MAX_PULL = int(os.environ.get("GREEN_API_MAX_PULL", "10"))
    GREEN_API_MAX_PULL = int(os.environ.get("GREEN_API_MAX_PULL", "10"))


