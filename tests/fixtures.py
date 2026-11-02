"""Минимальный XLSX fixture через стандартный ZIP/XML, без рабочих текстов."""
from xml.sax.saxutils import escape
from zipfile import ZipFile

HEADERS = ["Id", "IsClient", "Name", "ColName", "NeedTranslateTextJD", "TranslateTextJD",
           "NeedTranslateTextHJ", "TranslateTextHJ", "NeedTranslateTextJD_CHN"]
ROWS = [
    ["CommonItem.txt", "1", "12000", "Name", "Старый перевод", "Лунный ключ", "HJ нельзя искать", "HJ перевод", "月亮钥匙"],
    ["CommonItem.txt", "1", "12000", "TipsClassDesc", "", "Не название", "", "", "非名称"],
    ["CommonItemTips.txt", "1", "12000", "Tips", "", "Открывает лунные врата", "", "", "打开月门"],
    ["Other.txt", "1", "12000", "Name", "", "Лунный ключ", "", "", "月亮钥匙"],
    ["CommonItem.txt", "1", "13001", "Name", "", "Сломанный ключ", "", "", "损坏钥匙"],
    ["Other.txt", "1", "2", "Text", "Не использовать как перевод", "", "", "", "空译文"],
    ["Other.txt", "1", "3", "Text", "", "100%_тест", "", "", "百分比"],
    *[["Other.txt", "1", str(i), "Text", "", f"Страница {i}", "", "", f"页{i}"] for i in range(20, 27)],
]


def workbook(path, rows=None, headers=None):
    rows = ROWS if rows is None else rows
    headers = HEADERS if headers is None else headers
    def sheet(data):
        result = []
        for number, row in enumerate(data, 1):
            cells = []
            for col, value in enumerate(row):
                ref = chr(65 + col) + str(number)
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>')
            result.append(f'<row r="{number}">' + "".join(cells) + '</row>')
        return '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + "".join(result) + '</sheetData></worksheet>'
    with ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="RUS+CHN" sheetId="1" r:id="rId1"/><sheet name="CHN_Only" sheetId="2" r:id="rId2"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", sheet([headers, *rows]))
        z.writestr("xl/worksheets/sheet2.xml", sheet([headers, ["Other.txt", "1", "1", "Name", "", "НЕ ИМПОРТИРОВАТЬ", "", "", "禁止"]]))
