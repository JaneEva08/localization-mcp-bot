"""Ответы собираются из данных, без перефразирования нейросетью."""


def record_lines(row):
    lines = [f"Русский: {row['russian'] or '(перевод пустой)'}",
             f"Китайский: {row['chinese'] or '(оригинал пустой)'}"]
    if "item_code" in row:
        lines.append(f"Код предмета: {row['item_code'] if row['item_code'] is not None else '(Name не делится на 1000; код не вычислен)'}")
    lines.extend([f"Таблица: {row['source_table']}", f"Name: {row['record_name']}",
                  f"Атрибут: {row['attribute']}", f"IsClient: {row['is_client']}",
                  f"Строка Excel: {row['excel_row']}"])
    return lines


def render(result):
    if "clarification" in result:
        return result["clarification"]
    source = result.get("source", {})
    sections = [f"Файл: {source.get('workbook', '?')}\nЛист: {source.get('sheet', 'RUS+CHN')}"]
    rows = result.get("records", [])
    if not rows:
        sections.append("Совпадений не найдено.")
    for row in rows:
        lines = record_lines(row)
        for related in row.get("related", []):
            if related["excel_row"] != row["excel_row"]:
                lines.extend(["", "Связанная запись:", *record_lines(related)])
        sections.append("\n".join(lines))
    if result.get("match_mode"):
        sections.append("Совпадение: " + {"exact": "точное", "contains": "по части текста"}[result["match_mode"]])
    if result.get("has_more"):
        sections.append("Есть ещё результаты. Нажмите «Ещё» или отправьте /next.")
    return "\n\n".join(sections)


def chunks(text, size=1800):
    # До 3600 UTF-16 units даже для строки целиком из emoji (Telegram limit: 4096).
    return [text[i:i + size] for i in range(0, len(text), size) if text[i:i + size].strip()]
