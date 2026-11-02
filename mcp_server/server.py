"""Настоящий MCP Streamable HTTP на loopback, четыре инструмента чтения."""
import os
from typing import Literal

from mcp.server.fastmcp import FastMCP

from mcp_server import db

mcp = FastMCP("localization-search", host="127.0.0.1", port=int(os.getenv("MCP_PORT", "8000")), json_response=True, stateless_http=True)


@mcp.tool()
def search_russian(query: str, offset: int = 0, limit: int = 5) -> dict:
    """Поиск игрового русского перевода TranslateTextJD; вернуть китайский оригинал и атрибуты. Сначала точное совпадение, иначе подстрока."""
    return db.search(query, "russian", offset, limit)


@mcp.tool()
def search_chinese(query: str, offset: int = 0, limit: int = 5) -> dict:
    """Поиск китайского оригинала NeedTranslateTextJD_CHN; вернуть игровой русский перевод и атрибуты."""
    return db.search(query, "chinese", offset, limit)


@mcp.tool()
def find_item(query: str, mode: Literal["name", "description", ""] = "", offset: int = 0, limit: int = 5) -> dict:
    """Код предмета по тексту. name: только CommonItem.txt/ColName=Name; description: только CommonItemTips.txt/ColName=Tips. Если пользователь не уточнил название или описание, оставь mode пустым. Код = столбец Name / 1000. Ищет русский и китайский текст."""
    if not mode:
        return {"clarification": "Искать код предмета по названию или по описанию?", "query": query}
    return db.search(query, "both", offset, limit, item_mode=mode)


@mcp.tool()
def get_item(item_id: str) -> dict:
    """Найти название и описание предмета по коду для выдачи. Например, код 12 соответствует столбцу Name=12000. Не передавай сюда уже умноженное значение Name."""
    return db.item_by_code(item_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
