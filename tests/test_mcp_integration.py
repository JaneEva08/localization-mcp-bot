"""Реальный HTTP MCP цикл, без Telegram и без платного OpenAI API."""
import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from import_excel import import_excel
from settings import ROOT
from telegram_bot.formatting import render
from telegram_bot.mcp_client import decode, session
from tests.fixtures import workbook


class McpIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_initialize_discovery_and_all_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            xlsx, database = root / "demo.xlsx", root / "demo.db"
            workbook(xlsx)
            import_excel(xlsx, database, progress=lambda _: None)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            env = {**os.environ, "LOCALIZATION_DB": str(database), "MCP_PORT": str(port)}
            with (root / "server.log").open("w", encoding="utf-8") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "mcp_server.server"], cwd=ROOT, env=env,
                    stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
                try:
                    for _ in range(100):
                        if process.poll() is not None:
                            self.fail("MCP-сервер завершился до подключения")
                        try:
                            reader, writer = await asyncio.open_connection("127.0.0.1", port)
                            writer.close()
                            await writer.wait_closed()
                            break
                        except OSError:
                            await asyncio.sleep(0.1)
                    else:
                        self.fail("MCP-сервер не запустился за 10 секунд")
                    async with session(f"http://127.0.0.1:{port}/mcp") as client:
                        tools = (await client.list_tools()).tools
                        self.assertEqual({t.name for t in tools}, {"search_russian", "search_chinese", "find_item", "get_item"})
                        for name, args in [
                            ("search_russian", {"query": "Лунный ключ"}),
                            ("search_chinese", {"query": "月亮钥匙"}),
                            ("find_item", {"query": "Лунный ключ", "mode": "name"}),
                            ("find_item", {"query": "лунные врата", "mode": "description"}),
                            ("get_item", {"item_id": "12"}),
                        ]:
                            response = await client.call_tool(name, args)
                            self.assertFalse(response.isError, name)
                            self.assertTrue(decode(response)["records"], name)
                            self.assertIn("Русский:", render(decode(response)))
                        clarification = await client.call_tool("find_item", {"query": "ключ"})
                        self.assertIn("clarification", decode(clarification))
                        invalid = await client.call_tool("get_item", {"item_id": "12.5"})
                        self.assertTrue(invalid.isError)
                finally:
                    process.terminate()
                    process.wait(timeout=10)


if __name__ == "__main__":
    unittest.main()
