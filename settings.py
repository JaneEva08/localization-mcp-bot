"""Общие локальные пути. Импорт и поиск не требуют ключей API."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DB_PATH = Path(os.getenv("LOCALIZATION_DB", str(ROOT / "data" / "localization.db")))
if not DB_PATH.is_absolute():
    DB_PATH = ROOT / DB_PATH
MCP_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
