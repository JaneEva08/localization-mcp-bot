"""Потоковый импорт единственного листа RUS+CHN, с атомарной заменой базы."""
import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

from mcp_server.db import INDEXES, SCHEMA
from settings import DB_PATH

REQUIRED = ("Id", "IsClient", "Name", "ColName", "NeedTranslateTextJD", "TranslateTextJD", "NeedTranslateTextJD_CHN")


def text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def import_excel(source: Path, target: Path = DB_PATH, progress=print):
    source, target = source.resolve(), target.resolve()
    if source == target:
        raise ValueError("Исходник и база должны быть разными файлами.")
    with source.open("rb") as stream:
        source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    wb = load_workbook(source, read_only=True, data_only=False)
    temp = None
    try:
        if "RUS+CHN" not in wb.sheetnames:
            raise ValueError("В книге нет листа RUS+CHN.")
        sheet = wb["RUS+CHN"]
        iterator = sheet.iter_rows()
        headers = [text(c.value) for c in next(iterator)]
        if any(headers.count(name) != 1 for name in REQUIRED):
            raise ValueError("Нужны однозначные столбцы: " + ", ".join(REQUIRED))
        positions = [headers.index(name) for name in REQUIRED]
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, filename = tempfile.mkstemp(prefix="import-", suffix=".db", dir=target.parent)
        os.close(fd)
        temp = Path(filename)
        conn = sqlite3.connect(temp)
        count = 0
        try:
            conn.executescript(SCHEMA)
            batch = []
            for row_num, row in enumerate(iterator, 2):
                selected = [row[p] for p in positions]
                if all(c.value is None for c in selected):
                    continue
                if text(selected[0].value).startswith("#"):
                    continue
                if any(c.data_type in ("f", "e") for c in selected):
                    raise ValueError(f"Строка {row_num}: формула или ошибка в импортируемых полях. Нужны значения.")
                table, client, name, attr, jd, ru, zh = map(lambda c: text(c.value), selected)
                if not table or not name or not attr:
                    raise ValueError(f"Строка {row_num}: отсутствует таблица, Name или ColName.")
                batch.append((row_num, table, client, name, attr, jd, ru, zh, ru.casefold(), zh.casefold()))
                count += 1
                if len(batch) >= 5000:
                    conn.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
                    batch.clear()
                    progress(f"Импортировано: {count}")
            conn.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
            if not count:
                raise ValueError("На листе нет записей для импорта.")
            info = {"workbook": source.name, "sheet": "RUS+CHN", "sha256": source_hash,
                    "imported_at": datetime.now(timezone.utc).isoformat(), "rows": count}
            conn.executemany("INSERT INTO metadata VALUES (?,?)", [(k, json.dumps(v, ensure_ascii=False)) for k, v in info.items()])
            conn.commit()
            conn.executescript(INDEXES)
            conn.execute("ANALYZE")
            conn.commit()
        finally:
            conn.close()
        # Защита от редактирования/синхронизации исходника во время импорта.
        with source.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != source_hash:
                raise ValueError("Excel изменился во время импорта. Повторите с сохранённой копией.")
        os.replace(temp, target)
        progress(f"Готово: {count} записей; база: {target}")
        return info
    finally:
        wb.close()
        if temp is not None and temp.exists():
            temp.unlink()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel", type=Path)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()
    import_excel(args.excel, args.db)
