import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from import_excel import import_excel
from mcp_server import db
from mcp_server.server import find_item
from telegram_bot.bot import authorized
from telegram_bot.formatting import chunks, render
from telegram_bot.routing import choose_tool, explicit
from tests.fixtures import HEADERS, ROWS, workbook


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.xlsx, self.path = self.root / "demo.xlsx", self.root / "demo.db"
        workbook(self.xlsx)
        self.info = import_excel(self.xlsx, self.path, progress=lambda _: None)

    def tearDown(self):
        self.temp.cleanup()

    def search(self, query, language="russian", **kw):
        return db.search(query, language, path=self.path, **kw)

    def test_only_selected_sheet_and_columns(self):
        self.assertEqual(self.info["rows"], len(ROWS))
        for query in ["НЕ ИМПОРТИРОВАТЬ", "HJ нельзя искать", "HJ перевод", "Старый перевод"]:
            self.assertFalse(self.search(query)["records"])

    def test_russian_to_chinese_casefold_and_duplicates(self):
        result = self.search("ЛУННЫЙ КЛЮЧ")
        self.assertEqual(result["match_mode"], "exact")
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["records"][0]["chinese"], "月亮钥匙")
        self.assertEqual(result["records"][0]["excel_row"], 2)

    def test_chinese_to_russian(self):
        self.assertEqual(self.search("月亮钥匙", "chinese")["records"][0]["russian"], "Лунный ключ")

    def test_contains(self):
        self.assertEqual(self.search("лунный")["match_mode"], "contains")

    def test_wildcards_are_literal(self):
        self.assertEqual(len(self.search("%_")["records"]), 1)
        self.assertFalse(self.search("' OR 1=1 --")["records"])

    def test_name_scope_and_pair(self):
        result = self.search("Лунный ключ", "both", item_mode="name")
        self.assertEqual(len(result["records"]), 1)
        row = result["records"][0]
        self.assertEqual(row["item_code"], "12")
        self.assertEqual(len(row["related"]), 2)
        self.assertFalse(self.search("Не название", "both", item_mode="name")["records"])

    def test_description_scope(self):
        result = self.search("лунные врата", "both", item_mode="description")
        self.assertEqual(result["records"][0]["item_code"], "12")

    def test_reverse_item_lookup(self):
        result = db.item_by_code("12", self.path)
        self.assertEqual(result["record_name"], "12000")
        self.assertEqual(len(result["records"]), 2)
        self.assertFalse(db.item_by_code("999", self.path)["records"])

    def test_no_rounding(self):
        self.assertIsNone(self.search("Сломанный ключ", "both", item_mode="name")["records"][0]["item_code"])

    def test_empty_translation_not_replaced(self):
        result = self.search("空译文", "chinese")
        self.assertEqual(result["records"][0]["russian"], "")
        self.assertIn("перевод пустой", render(result))

    def test_pagination(self):
        first = self.search("Страница")
        second = self.search("Страница", offset=5)
        self.assertEqual(len(first["records"]), 5)
        self.assertTrue(first["has_more"])
        self.assertEqual(len(second["records"]), 2)
        self.assertFalse(second["has_more"])

    def test_validation(self):
        for query in ["", " ", "x" * 501]:
            with self.assertRaises(ValueError): self.search(query)
        for kw in [{"offset": -1}, {"offset": True}, {"limit": 0}, {"limit": 6}]:
            with self.assertRaises(ValueError): self.search("x", **kw)
        for code in ["12.5", "-1", "１２", "1" * 16]:
            with self.assertRaises(ValueError): db.item_by_code(code, self.path)

    def test_failed_import_keeps_previous_db_and_source(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        source_before = hashlib.sha256(self.xlsx.read_bytes()).hexdigest()
        import_excel(self.xlsx, self.path, progress=lambda _: None)
        self.assertEqual(hashlib.sha256(self.xlsx.read_bytes()).hexdigest(), source_before)
        bad = self.root / "bad.xlsx"
        workbook(bad, headers=[h for h in HEADERS if h != "TranslateTextJD"])
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaises(ValueError): import_excel(bad, self.path)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)

    def test_duplicate_records_preserved_not_overwritten(self):
        workbook(self.xlsx, rows=[ROWS[0], ROWS[0]])
        import_excel(self.xlsx, self.path, progress=lambda _: None)
        self.assertEqual(len(self.search("Лунный ключ")["records"]), 2)

    def test_item_clarification(self):
        self.assertIn("clarification", find_item("ключ"))

    def test_command_routing(self):
        self.assertEqual(explicit("/id 12"), ("get_item", {"item_id": "12"}))
        self.assertEqual(explicit("/item_desc лунные врата")[1]["mode"], "description")
        with self.assertRaises(ValueError): explicit("/ru")

    def test_long_response_chunks(self):
        value = "😀" * 5000
        parts = chunks(value)
        self.assertEqual("".join(parts), value)
        self.assertTrue(all(0 < len(p.encode("utf-16-le")) // 2 <= 4096 for p in parts))

    def test_owner_only(self):
        self.assertTrue(authorized(1, "private", 1))
        self.assertFalse(authorized(2, "private", 1))
        self.assertFalse(authorized(1, "group", 1))
        self.assertFalse(authorized(1, "private", None))


class LlmRoutingTests(unittest.IsolatedAsyncioTestCase):
    async def test_function_call_without_live_api(self):
        message = SimpleNamespace(tool_calls=[SimpleNamespace(function=SimpleNamespace(
            name="search_russian", arguments='{"query":"ключ","offset":100,"limit":100}'))])
        llm = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(
            return_value=SimpleNamespace(choices=[SimpleNamespace(message=message)])))))
        tools = [{"function": {"name": "search_russian"}}]
        route, question = await choose_tool(llm, "test-model", tools, [], "найди ключ")
        self.assertIsNone(question)
        self.assertEqual(route[1], {"query": "ключ", "offset": 0, "limit": 5})


if __name__ == "__main__":
    unittest.main()
