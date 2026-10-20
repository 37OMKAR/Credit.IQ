"""Builds a small test PDF with the features that broke the SECI reading (fictional company, figures in Rs lakh):
consolidated statements only, balance sheet running onto a second page with current borrowings there, P&L with finance
costs and a joint-venture share, cash flow with 'interest on loan' and investment in CWIP, and a notes page that says
'standalone'. Used by tools/selftest.py."""
import pymupdf as fitz

CO = "Surya Grid Energy Corporation Limited"


def _page(doc, title, rows, unit="(All amounts in Rs. lakhs)"):
    pg = doc.new_page(width=595, height=842)
    y = 50
    pg.insert_text((50, y), CO, fontsize=11); y += 16
    pg.insert_text((50, y), title, fontsize=11); y += 14
    pg.insert_text((50, y), unit, fontsize=8); y += 18
    pg.insert_text((330, y), "Note", fontsize=8); pg.insert_text((400, y), "31.03.2024", fontsize=8); pg.insert_text((490, y), "31.03.2023", fontsize=8)
    y += 16
    for lab, a, b in rows:
        pg.insert_text((50, y), lab, fontsize=8)
        if a is not None:
            pg.insert_text((400, y), a, fontsize=8)
        if b is not None:
            pg.insert_text((490, y), b, fontsize=8)
        y += 13
    return pg


def build(path):
    d = fitz.open()
    _page(d, "Consolidated Balance Sheet as at 31st March 2024", [
        ("ASSETS", None, None), ("Non-current assets", None, None),
        ("Property, plant and equipment", "96,732.00", "8,014.00"), ("Capital work-in-progress", "1,989.00", "25,345.00"),
        ("Investments accounted for using equity method", "41,200.00", "36,900.00"), ("Other non-current assets", "62,515.06", "40,256.89"),
        ("Total non-current assets", "2,02,436.06", "1,10,515.89"),
        ("Current assets", None, None), ("Trade receivables", "1,75,825.53", "1,73,944.27"), ("Cash and cash equivalents", "1,82,000.00", "1,61,000.00"),
        ("Other current assets", "1,61,705.47", "1,73,863.73"), ("Total current assets", "5,19,531.00", "5,08,808.00"),
        ("Total Assets", "7,21,967.06", "6,19,323.89")])
    _page(d, "Consolidated Balance Sheet as at 31st March 2024 (continued)", [
        ("EQUITY AND LIABILITIES", None, None), ("Equity", None, None), ("Equity share capital", "1,50,000.00", "1,50,000.00"),
        ("Other equity", "1,73,603.56", "1,22,475.25"), ("Total equity", "3,23,603.56", "2,72,475.25"),
        ("Non-current liabilities", None, None), ("Borrowings", "24,825.00", "302.00"), ("Lease liabilities", "100.00", "120.00"),
        ("Other non-current liabilities", "1,01,035.50", "48,594.64"), ("Total non-current liabilities", "1,25,960.50", "49,016.64"),
        ("Current liabilities", None, None), ("Borrowings", "5,075.00", "0.00"), ("Lease liabilities", "80.00", "57.00"),
        ("Trade payables", "3,20,000.00", "2,60,000.00"), ("Other current liabilities", "1,47,248.00", "1,29,775.00"),
        ("Total current liabilities", "4,72,403.00", "3,89,832.00"), ("Total Equity and Liabilities", "7,21,967.06", "6,19,323.89")])
    _page(d, "Consolidated Statement of Profit and Loss for the year ended 31st March 2024", [
        ("Revenue from operations", "13,03,507.00", "10,79,507.00"), ("Other income", "8,361.00", "7,422.00"),
        ("Total income", "13,11,868.00", "10,86,929.00"), ("Expenses", None, None), ("Purchase of solar power", "12,13,214.00", "10,22,153.00"),
        ("Employee benefits expense", "3,950.00", "3,412.00"), ("Finance costs", "1,093.40", "815.16"),
        ("Depreciation and amortisation expense", "2,449.57", "1,750.27"), ("Other expenses", "34,427.00", "15,952.00"),
        ("Total expenses", "12,55,134.00", "10,44,082.00"), ("Share of profit of joint ventures", "9,050.00", "6,200.00"),
        ("Profit before tax", "65,784.00", "49,047.00"), ("Total tax expense", "-150.90", "375.30"),
        ("Profit for the year", "65,934.90", "48,671.70")])
    _page(d, "Consolidated Statement of Cash Flows for the year ended 31st March 2024", [
        ("Cash flow from operating activities", None, None), ("Profit before tax", "65,784.00", "49,047.00"),
        ("Interest on loan", "302.00", "359.00"), ("Net cash generated from operating activities", "1,87,397.00", "60,120.00"),
        ("Cash flow from investing activities", None, None), ("Purchase of property, plant and equipment", "(656.00)", "(410.00)"),
        ("Investment in capital work-in-progress", "(66,174.00)", "(22,050.00)"), ("Capital advances", "(2,175.00)", "(1,100.00)"),
        ("Net cash used in investing activities", "(1,40,000.00)", "(40,000.00)"),
        ("Cash flow from financing activities", None, None), ("Interest paid", "(1,093.40)", "(815.16)"),
        ("Net cash from financing activities", "(26,397.00)", "(19,000.00)")])
    pg = d.new_page(width=595, height=842)
    pg.insert_text((50, 60), "Notes to the consolidated financial statements", fontsize=10)
    pg.insert_text((50, 80), "The standalone financial statements of the parent are presented separately. Revenue recognition ...", fontsize=8)
    d.save(path)
    return path


EXPECTED = {"FY2024": {"revenue": 13035.07, "total_current_liabilities": 4724.03, "total_current_assets": 5195.31,
                       "finance_cost": 10.934, "short_term_borrowings": 50.75, "long_term_borrowings": 248.25, "share_jv_profit": 90.5,
                       "other_income": 83.61, "capex": 690.05, "pat": 659.349},
            "FY2023": {"revenue": 10795.07, "total_current_liabilities": 3898.32, "finance_cost": 8.1516, "short_term_borrowings": 0.0}}
