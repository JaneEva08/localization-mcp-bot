"""Запуск: python -m telegram_bot.bot из папки VPf08."""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from openai import AsyncOpenAI

from settings import ROOT  # загружает .env относительно проекта
from telegram_bot import mcp_client
from telegram_bot.formatting import chunks, render
from telegram_bot.routing import choose_tool, explicit

HELP = """Помощник по игровой локализации. Только поиск, без изменения данных.

/ru текст — русский → китайский
/zh 文本 — китайский → русский
/item_name название — код предмета по названию
/item_desc описание — код предмета по описанию
/item текст — уточнить название или описание
/id 12 — предмет по коду выдачи (Name=12000)
/next — следующая страница
/reset — сбросить контекст
/whoami — узнать свой Telegram ID

Можно писать обычным языком, если настроен OPENAI_API_KEY.
"""


def authorized(user_id, chat_type, owner):
    return chat_type == "private" and user_id == owner


async def main():
    token = os.getenv("TELEGRAM_API_TOKEN", "")
    owner = os.getenv("OWNER_TELEGRAM_ID", "")
    if not token:
        raise SystemExit(f"Укажите TELEGRAM_API_TOKEN в {ROOT / '.env'}")
    if owner and (not owner.isascii() or not owner.isdigit()):
        raise SystemExit("OWNER_TELEGRAM_ID должен быть числом.")
    owner_id = int(owner) if owner else None
    key = os.getenv("OPENAI_API_KEY", "")
    llm = AsyncOpenAI(
        api_key=key, base_url=os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1",
        timeout=40, max_retries=1,
    ) if key else None
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    tools = await mcp_client.list_tools()
    history, state = [], {}
    lock = asyncio.Lock()
    dp = Dispatcher()

    async def send_result(message, result):
        parts = chunks(render(result))
        for i, part in enumerate(parts):
            keyboard = None
            if result.get("has_more") and i == len(parts) - 1:
                keyboard = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="Ещё", callback_data="next")]])
            await message.answer(part, reply_markup=keyboard)

    async def execute(message, tool, args):
        result = await mcp_client.call_tool(tool, args)
        if "clarification" in result:
            state.clear()
            state["pending"] = result["query"]
        else:
            state.clear()
            state.update(tool=tool, args=args.copy(), has_more=result.get("has_more", False))
        await send_result(message, result)
        return result

    async def next_page(message):
        if not state.get("has_more"):
            await message.answer("Следующей страницы нет. Выполните новый поиск.")
            return
        args = {**state["args"], "offset": state["args"].get("offset", 0) + 5}
        await execute(message, state["tool"], args)

    @dp.callback_query(F.data == "next")
    async def on_next(callback: CallbackQuery):
        await callback.answer()
        if not callback.message or not authorized(callback.from_user.id, callback.message.chat.type, owner_id):
            return
        async with lock:
            try:
                await next_page(callback.message)
            except Exception:
                logging.error("Не удалось получить страницу")
                await callback.message.answer("Ошибка поиска. Проверьте локальный MCP-сервер.")

    @dp.message()
    async def on_message(message: Message):
        text = (message.text or "").strip()
        command = text.split(" ", 1)[0].split("@")[0].lower()
        if command == "/whoami" and message.chat.type == "private":
            await message.answer(f"Ваш Telegram ID: {message.from_user.id}")
            return
        if not message.from_user or not authorized(message.from_user.id, message.chat.type, owner_id):
            await message.answer("Доступ не настроен. Укажите свой OWNER_TELEGRAM_ID в локальном .env; ID можно узнать командой /whoami в личном чате.")
            return
        async with lock:
            if command in ("/start", "/help"):
                await message.answer(HELP)
                return
            if command == "/reset":
                history.clear()
                state.clear()
                await message.answer("Контекст очищен.")
                return
            if not text:
                await message.answer("Отправьте текстовый запрос.")
                return
            try:
                if command == "/next":
                    await next_page(message)
                    return
                route = explicit(text)
                mode = {"название": "name", "по названию": "name", "описание": "description", "по описанию": "description"}.get(text.casefold())
                if route is None and state.get("pending") and mode:
                    route = ("find_item", {"query": state["pending"], "mode": mode})
                if route is None:
                    if llm is None:
                        await message.answer("Для свободного текста нужен OPENAI_API_KEY. Пока используйте команды из /help.")
                        return
                    route, question = await choose_tool(llm, model, tools, history, text)
                    if route is None:
                        for part in chunks(question):
                            await message.answer(part)
                        history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": question}])
                        del history[:-6]
                        return
                result = await execute(message, *route)
                summary = result.get("clarification") or f"Выполнен {route[0]} с параметрами {route[1]}; записей на странице: {len(result.get('records', []))}."
                history.extend([{"role": "user", "content": text}, {"role": "assistant", "content": summary}])
                del history[:-6]
            except ValueError as exc:
                # Не отправляем произвольный traceback или локальные пути пользователю.
                for part in chunks(str(exc)):
                    await message.answer(part)
            except Exception:
                logging.error("Ошибка выполнения запроса; проверьте MCP и настройки API")
                await message.answer("Не удалось выполнить запрос. Проверьте MCP-сервер, ключ OpenAI и доступность интернета. Явные команды не требуют OpenAI.")

    bot = Bot(token)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        if llm:
            await llm.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    # Не включаем HTTP debug: в адресе Telegram API находится токен.
    asyncio.run(main())
