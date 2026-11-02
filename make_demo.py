"""Создать вымышленный Excel и базу для демонстрации без рабочих данных."""
from import_excel import import_excel
from settings import ROOT
from tests.fixtures import workbook

if __name__ == "__main__":
    path = ROOT / "data" / "demo.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook(path)
    import_excel(path, ROOT / "data" / "demo.db")
    print("Для запуска с демобазой задайте LOCALIZATION_DB=data/demo.db в .env.")
