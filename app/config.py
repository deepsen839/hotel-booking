from pathlib import Path

from dotenv import load_dotenv
import os


# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from the project root .env file
load_dotenv(BASE_DIR / ".env")


class Config:
    """
    Application configuration.
    """

    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    GROQ_MODEL = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-20b"
    )

    PORT = int(
        os.getenv("PORT", "5000")
    )

    DEBUG = os.getenv(
        "DEBUG",
        "False"
    ).lower() == "true"

    INVENTORY_PATH = BASE_DIR / "data" / "inventory.json"