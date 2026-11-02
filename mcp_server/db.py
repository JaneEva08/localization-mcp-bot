"""Поиск только для чтения. Значения локализации не изменяются."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from settings import DB_PATH

SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE records (
 excel_row INTEGER PRIMARY KEY, source_table TEXT NOT NULL, is_client TEXT NOT NULL,
 record_name TEXT NOT NULL, attribute TEXT NOT NULL, source_jd TEXT NOT NULL,
 russian TEXT NOT NULL, chinese TEXT NOT NULL, ru_fold TEXT NOT NULL, zh_fold TEXT NOT NULL
);
"""
INDEXES = """
CREATE INDEX by_record ON records(source_table, record_name, attribute);
CREATE INDEX by_ru ON records(ru_fold);
CREATE INDEX by_zh ON records(zh_fold);
"""


@contextmanager
def connect(path: Path = DB_PATH):
    if not path.is_file():
        raise ValueError("База не найдена. Сначала выполните импорт Excel.")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def metadata(conn):
    return {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT * FROM metadata")}


def code_from_name(value: str):
    if value.isascii() and value.isdigit():
        number = int(value)
        if number % 1000 == 0:
            return str(number // 1000)
    return None


def record(row):
    result = {k: row[k] for k in (
        "excel_row", "source_table", "is_client", "record_name", "attribute", "russian", "chinese"
    )}
    if row["source_table"] in ("CommonItem.txt", "CommonItemTips.txt"):
        result["item_code"] = code_from_name(row["record_name"])
    return result


def check_page(offset, limit):
    if type(offset) is not int or offset < 0 or offset > 1_000_000:
        raise ValueError("Смещение должно быть целым числом от 0 до 1000000.")
    if type(limit) is not int or not 1 <= limit <= 5:
        raise ValueError("Размер страницы должен быть от 1 до 5.")


def search(query: str, language: str, offset=0, limit=5, item_mode=None, path=DB_PATH):
    check_page(offset, limit)
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        raise ValueError("Укажите текст длиной от 1 до 500 символов.")
    if language not in ("russian", "chinese", "both"):
        raise ValueError("Неизвестный язык поиска.")
    columns = {"russian": ["ru_fold"], "chinese": ["zh_fold"], "both": ["ru_fold", "zh_fold"]}[language]
    filters, base_args = [], []
    if item_mode is not None:
        table, attribute = {"name": ("CommonItem.txt", "Name"), "description": ("CommonItemTips.txt", "Tips")}[item_mode]
        filters.append("source_table = ? AND attribute = ?")
        base_args.extend([table, attribute])
    folded = query.strip().casefold()
    with connect(path) as conn:
        exact = "(" + " OR ".join(f"{c} = ?" for c in columns) + ")"
        where = " AND ".join([*filters, exact])
        exact_args = [*base_args, *([folded] * len(columns))]
        has_exact = conn.execute(f"SELECT 1 FROM records WHERE {where} LIMIT 1", exact_args).fetchone()
        match_mode = "exact" if has_exact else "contains"
        if not has_exact:
            contains = "(" + " OR ".join(f"instr({c}, ?) > 0" for c in columns) + ")"
            where = " AND ".join([*filters, contains])
        rows = conn.execute(
            f"SELECT * FROM records WHERE {where} ORDER BY excel_row LIMIT ? OFFSET ?",
            [*exact_args, limit + 1, offset],
        ).fetchall()
        result = {"source": metadata(conn), "match_mode": match_mode, "offset": offset,
                  "has_more": len(rows) > limit, "records": [record(r) for r in rows[:limit]]}
        if item_mode:
            for entry in result["records"]:
                entry["related"] = item_rows(conn, entry["record_name"])
        return result


def item_rows(conn, name):
    rows = conn.execute(
        "SELECT * FROM records WHERE record_name = ? AND "
        "((source_table = 'CommonItem.txt' AND attribute = 'Name') OR "
        "(source_table = 'CommonItemTips.txt' AND attribute = 'Tips')) ORDER BY excel_row", (name,)
    ).fetchall()
    return [record(r) for r in rows]


def item_by_code(item_id: str, path=DB_PATH):
    if not isinstance(item_id, str) or not item_id.isascii() or not item_id.isdigit() or len(item_id) > 15:
        raise ValueError("Код предмета должен содержать от 1 до 15 цифр, без дробной части.")
    name = str(int(item_id) * 1000)
    with connect(path) as conn:
        return {"source": metadata(conn), "item_code": str(int(item_id)), "record_name": name,
                "records": item_rows(conn, name), "has_more": False}
