"""Builds a FICTIONAL sample annual report + BRSR (and a scanned copy) so you can try the app
without a real document. 'Deccan Polyfab Industries Ltd' is invented; red flags are planted on purpose."""
import os
import sys

try:
    import pymupdf as fitz
except ImportError:
    import fitz
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples")
os.makedirs(OUT, exist_ok=True)
CO = "DECCAN POLYFAB INDUSTRIES LIMITED"
CIN = "L25209MH2004PLC123456"

BS = [
    ("EQUITY AND LIABILITIES", None, None, None), ("Equity", None, None, None),
    ("Equity share capital", "14", "50.00", "50.00"), ("Other equity", "15", "420.00", "380.00"), ("Total equity", "", "470.00", "430.00"),
    ("Liabilities", None, None, None), ("Non-current liabilities", None, None, None),
    ("Borrowings", "16", "380.00", "260.00"), ("Lease liabilities", "", "10.00", "12.00"), ("Provisions", "17", "8.00", "7.00"),
    ("Deferred tax liabilities (net)", "18", "22.00", "20.00"),
    ("Current liabilities", None, None, None),
    ("Borrowings", "19", "300.00", "169.00"), ("Trade payables", "20", "210.00", "190.00"), ("Other financial liabilities", "21", "40.00", "35.00"),
    ("Other current liabilities", "22", "25.00", "22.00"), ("Provisions", "17", "5.00", "4.00"), ("Current tax liabilities (net)", "", "3.00", "2.00"),
    ("Total current liabilities", "", "583.00", "422.00"),
    ("Total equity and liabilities", "", "1,473.00", "1,151.00"),
    ("ASSETS", None, None, None), ("Non-current assets", None, None, None),
    ("Property, plant and equipment", "3", "420.00", "410.00"), ("Capital work-in-progress", "3", "95.00", "90.00"),
    ("Right-of-use assets", "4", "12.00", "14.00"), ("Other intangible assets", "5", "8.00", "6.00"),
    ("Investments", "6", "110.00", "70.00"), ("Loans", "7", "85.00", "10.00"), ("Other financial assets", "8", "10.00", "9.00"),
    ("Capital advances", "9", "30.00", "8.00"), ("Other non-current assets", "9", "15.00", "12.00"),
    ("Current assets", None, None, None),
    ("Inventories", "10", "210.00", "180.00"), ("Trade receivables", "11", "290.00", "200.00"), ("Cash and cash equivalents", "12", "85.00", "60.00"),
    ("Bank balances other than above", "12", "35.00", "30.00"), ("Loans", "7", "25.00", "15.00"), ("Other financial assets", "8", "18.00", "15.00"),
    ("Other current assets", "13", "25.00", "22.00"), ("Total current assets", "", "688.00", "522.00"),
    ("Total assets", "", "1,473.00", "1,151.00"),
]
PL = [
    ("Revenue from operations", "23", "1,350.00", "1,250.00"), ("Other income", "24", "18.00", "12.00"), ("Total income", "", "1,368.00", "1,262.00"),
    ("Expenses", None, None, None),
    ("Cost of materials consumed", "25", "820.00", "760.00"), ("Purchases of stock-in-trade", "", "40.00", "35.00"),
    ("Changes in inventories of finished goods and work-in-progress", "26", "(20.00)", "(10.00)"),
    ("Employee benefits expense", "27", "95.00", "88.00"), ("Finance costs", "28", "62.00", "45.00"),
    ("Depreciation and amortisation expense", "3", "38.00", "36.00"), ("Other expenses", "29", "185.00", "170.00"),
    ("Total expenses", "", "1,220.00", "1,124.00"), ("Profit before tax", "", "148.00", "138.00"),
    ("Total tax expense", "30", "37.00", "35.00"), ("Profit for the year", "", "111.00", "103.00"),
]
CF = [
    ("A. Cash flow from operating activities", None, None, None), ("Profit before tax", "", "148.00", "138.00"),
    ("Adjustments for depreciation, finance costs and other items", "", "95.00", "76.00"),
    ("Increase in trade receivables", "", "(90.00)", "(15.00)"), ("Increase in inventories", "", "(30.00)", "(12.00)"),
    ("Income taxes paid", "", "(36.00)", "(34.00)"),
    ("Net cash generated from operating activities", "", "35.00", "120.00"),
    ("B. Cash flow from investing activities", None, None, None),
    ("Purchase of property, plant and equipment", "", "(48.00)", "(40.00)"), ("Investment in associate", "", "(40.00)", "(10.00)"),
    ("Loans given to related parties", "", "(85.00)", "(10.00)"), ("Interest received", "", "1.60", "1.20"),
    ("Net cash used in investing activities", "", "(171.40)", "(58.80)"),
    ("C. Cash flow from financing activities", None, None, None),
    ("Proceeds from borrowings (net)", "", "249.00", "(20.00)"), ("Finance costs paid", "", "(62.00)", "(45.00)"), ("Dividend paid", "", "(25.60)", "(26.20)"),
    ("Net cash from financing activities", "", "161.40", "(91.20)"),
    ("Net increase in cash and cash equivalents", "", "25.00", "(30.00)"),
]


def table_page(c, title, rows, sub="(Rs. in Crore)"):
    c.setFont("Helvetica-Bold", 12); c.drawString(40, 800, CO)
    c.setFont("Helvetica-Bold", 11); c.drawString(40, 782, title)
    c.setFont("Helvetica", 8); c.drawString(40, 768, f"CIN: {CIN}"); c.drawRightString(555, 768, sub)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(40, 750, "Particulars"); c.drawString(330, 750, "Note"); c.drawRightString(450, 750, "As at March 31, 2025"); c.drawRightString(555, 750, "As at March 31, 2024")
    y = 734
    for lab, note, a, b in rows:
        if a is None:
            c.setFont("Helvetica-Bold", 8.5); c.drawString(40, y, lab)
        else:
            c.setFont("Helvetica-Bold" if lab.lower().startswith(("total", "net cash", "profit")) else "Helvetica", 8.5)
            c.drawString(52, y, lab); c.drawString(335, y, note); c.drawRightString(450, y, a); c.drawRightString(555, y, b)
        y -= 14.5
    c.showPage()


def text_page(c, title, paras):
    c.setFont("Helvetica-Bold", 12); c.drawString(40, 800, CO)
    c.setFont("Helvetica-Bold", 11); c.drawString(40, 780, title)
    y = 758
    c.setFont("Helvetica", 9)
    for p in paras:
        words, line = p.split(), ""
        for w in words:
            if c.stringWidth(line + " " + w, "Helvetica", 9) > 510:
                c.drawString(40, y, line); y -= 12.5; line = w
            else:
                line = (line + " " + w).strip()
        c.drawString(40, y, line); y -= 20
    c.showPage()


def annual_report(path):
    c = canvas.Canvas(path, pagesize=A4)
    text_page(c, "ANNUAL REPORT 2024-25 (FICTIONAL SAMPLE FOR SOFTWARE TESTING)", [
        "Deccan Polyfab Industries Limited is a FICTIONAL company created to demonstrate the Credit Intelligence Workbench. It manufactures woven polypropylene sacks, FIBC bulk bags and technical textiles at Chakan, Pune and Waluj, Aurangabad.",
        "Any resemblance to a real entity is coincidental. All figures are invented and deliberately contain warning signs for training credit officers."])
    text_page(c, "INDEPENDENT AUDITOR'S REPORT", [
        "To the Members of Deccan Polyfab Industries Limited. Report on the Audit of the Standalone Financial Statements. Opinion: In our opinion the standalone financial statements give a true and fair view.",
        "Emphasis of Matter: We draw attention to Note 7 regarding loans of Rs. 80.00 crore granted to Sahyadri Agro Trading Private Limited, an enterprise in which a promoter director is interested, which are repayable on demand and on which interest of Rs. Nil has been accrued. Management considers the amount fully recoverable. Our opinion is not modified in respect of this matter.",
        "Key Audit Matters: Recoverability of trade receivables (Note 11) - receivables increased by 45% while revenue grew 8%; balances over 180 days amount to Rs. 64.00 crore.",
        "Annexure to the Auditor's Report (Companies (Auditor's Report) Order, 2020): (iii) The Company has granted loans to a related party repayable on demand without specifying any terms or period of repayment aggregating Rs. 80.00 crore. (ix)(d) On an overall examination, funds raised on short-term basis aggregating Rs. 45.00 crore have been used for long-term purposes. (vii) There were delays in deposit of undisputed statutory dues of GST and TDS of Rs. 3.20 crore outstanding for more than six months."])
    table_page(c, "STANDALONE BALANCE SHEET AS AT MARCH 31, 2025", BS)
    table_page(c, "STANDALONE STATEMENT OF PROFIT AND LOSS FOR THE YEAR ENDED MARCH 31, 2025", PL)
    table_page(c, "STANDALONE CASH FLOW STATEMENT FOR THE YEAR ENDED MARCH 31, 2025", CF)
    text_page(c, "NOTES TO STANDALONE FINANCIAL STATEMENTS", [
        "Note 24 Other income: Interest income Rs. 1.60 crore (previous year Rs. 1.20 crore); miscellaneous income Rs. 16.40 crore.",
        "Note 16 Borrowings: Term loans from State Bank of India Rs. 220.00 crore at 9.25% secured by first charge on fixed assets; term loan from Bajaj Finance Rs. 160.00 crore at 13.5%. Short-term borrowings include working capital from Bank of Baroda Rs. 180.00 crore, inter-corporate deposits Rs. 60.00 crore at 15%, and current maturities of long-term debt Rs. 60.00 crore.",
        "Note 35 Related party transactions: Sahyadri Agro Trading Private Limited (enterprise controlled by promoter): loans given Rs. 80.00 crore (closing), purchases Rs. 210.00 crore, sales Rs. 150.00 crore. Deccan Packaging LLP (KMP interested): capital advance Rs. 22.00 crore. Key managerial personnel remuneration Rs. 6.40 crore.",
        "Note 36 Contingent liabilities and commitments: Corporate guarantee given to banks on behalf of Sahyadri Agro Trading Private Limited Rs. 180.00 crore; disputed GST demand Rs. 48.00 crore; income tax demands under appeal Rs. 32.00 crore. Total contingent liabilities Rs. 260.00 crore.",
        "Note 37: The promoters have pledged 38.5% of their shareholding with lenders of group companies."])
    c.save()


def brsr(path):
    c = canvas.Canvas(path, pagesize=A4)
    text_page(c, "BUSINESS RESPONSIBILITY AND SUSTAINABILITY REPORT 2024-25 (FICTIONAL SAMPLE)", [
        f"Section A: General Disclosures. Corporate Identity Number (CIN): {CIN}. Name: Deccan Polyfab Industries Limited. Financial year 2024-25. Turnover Rs. 1,350 crore. Employees: 2,140 permanent (women 11%). Women on board: 1 of 8.",
        "Section C Principle 6: Total energy consumption 1,250,000 GJ of which renewable 12%. Total Scope 1 emissions 85,000 tCO2e (previous year 81,000). Total Scope 2 emissions 42,000 tCO2e (previous year 40,500). Scope 3 not computed.",
        "Total Scope 1 and Scope 2 emission intensity per rupee of turnover: 0.0000094 tCO2e. Independent assessment: limited assurance by an external agency on GHG data was not obtained during the year.",
        "Total volume of water withdrawal 410,000 kL. Total waste generated 6,800 tonnes including hazardous waste 420 tonnes.",
        "Principle 3: LTIFR (employees) 0.62; fatalities 1 (contract worker at Waluj). Principle 1: penalty of Rs. 0.45 crore levied by Maharashtra Pollution Control Board for effluent discharge. CSR obligation Rs. 2.10 crore; amount spent Rs. 1.20 crore; unspent transferred to unspent CSR account.",
        "No net-zero target has been set. Proposed 5 MW rooftop solar at Chakan."])
    c.save()


def scanned_copy(src, dst, dpi=150):
    """Simulate a scanned PDF: every page becomes an image with no text layer."""
    s, d = fitz.open(src), fitz.open()
    for p in s:
        pix = p.get_pixmap(dpi=dpi)
        np_ = d.new_page(width=p.rect.width, height=p.rect.height)
        np_.insert_image(np_.rect, pixmap=pix)
    d.save(dst)


if __name__ == "__main__":
    ar = os.path.join(OUT, "Sample_Annual_Report_DeccanPolyfab_FY25.pdf")
    annual_report(ar)
    brsr(os.path.join(OUT, "Sample_BRSR_DeccanPolyfab_FY25.pdf"))
    scanned_copy(ar, os.path.join(OUT, "Sample_SCANNED_Annual_Report_DeccanPolyfab_FY25.pdf"))
    print("written to", OUT)
