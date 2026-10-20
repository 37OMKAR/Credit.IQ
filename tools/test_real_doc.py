import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from core import pdf_reader as PR, extractor as EX, pipeline as PL, checker as CK, report_word as RW, report_excel as RE

pdf_path = r"C:\Users\LW37\Downloads\Uniq-Facility-Services-Private-Limited.pdf"
if not os.path.exists(pdf_path):
    print("File not found:", pdf_path)
    sys.exit(1)

print(f"Loading real PDF: {pdf_path}")
pages = PR.read_pdf(open(pdf_path, "rb").read())
print(f"Total Pages read: {len(pages)}")

loc = PR.locate_sections(pages)
print("\n--- 1. Located Sections ---")
for k, v in loc.items():
    print(f"  {k:16}: {v}")

ext = EX.heuristic_extract(pages, loc)
years = ext.get("years", [])
print(f"\n--- 2. Extracted Years: {years} ---")
print(f"  Unit: {ext.get('unit_status')} (Multiplier: {ext.get('unit_multiplier')})")

for y in years:
    d = ext["data"][y]
    print(f"\n  Figures for {y} (Rs. Cr):")
    for k in ["revenue", "other_income", "total_income", "cogs", "employee_cost", "finance_cost", "depreciation",
              "pbt", "tax_expense", "pat", "share_capital", "other_equity", "total_equity",
              "long_term_borrowings", "short_term_borrowings", "trade_payables", "trade_receivables",
              "inventories", "cash_and_equivalents", "total_current_assets", "total_current_liabilities",
              "total_assets", "total_equity_and_liabilities", "cfo"]:
        if d.get(k) is not None:
            print(f"    {k:30}: {d[k]:10.2f}")

bundle = PL.analyse(
    ext["data"], years, "Uniq Facility Services Private Limited",
    notes=EX.heuristic_notes_review(pages, loc),
    source_file=os.path.basename(pdf_path),
    cin="U74999KA2016PTC094285",
    meta={"pages": pages, "unit_status": ext.get("unit_status"), "provenance": ext.get("provenance", {})}
)

print("\n--- 3. Credit Assessment & Forensic Score ---")
fz = bundle["forensics"]
print(f"  Credit Score : {fz['score']} / 100")
print(f"  Risk Grade   : {fz['grade']}")
print(f"  Total Flags  : {len(fz['flags'])}")
for fl in fz["flags"]:
    sev = fl.get("severity")
    print(f"    [{sev}] {fl.get('title')}: {fl.get('evidence', '')[:80]}")

print("\n--- 4. ICAI UDIN Audit Authentication ---")
u = bundle.get("udin") or {}
print(f"  UDIN Status  : {u.get('status')}")
prim = u.get("primary_udin") or {}
print(f"  UDIN Number  : {prim.get('udin')}")
matched = prim.get("matched_ca") or {}
print(f"  Signing CA   : {matched.get('ca_name')} (M.No: {matched.get('membership_no')})")
print(f"  Audit Firm   : {matched.get('firm_name')} (FRN: {matched.get('frn')})")
print(f"  Signing Date : {matched.get('date')}")
print(f"  Portal Link  : {u.get('portal_url')}")
print(f"  Audit Detail : {u.get('message')}")

narr = PL.write_narrative(bundle)
cleaned_narr, checks = CK.run(bundle, narr)
print("\n--- 5. Key Logic Checker Audit Tie-Outs ---")
for c in checks:
    if c["result"] in ("WARN", "FAIL") or "UDIN" in c["check"] or "tallies" in c["check"]:
        print(f"    [{c['result']}] {c['check']}: {c['detail'][:85]}")

os.makedirs("reports/test_run", exist_ok=True)
docx_b = RW.build(bundle, cleaned_narr)
xlsx_b = RE.build(bundle)

docx_path = "reports/test_run/Uniq_Facility_Services_Appraisal.docx"
xlsx_path = "reports/test_run/Uniq_Facility_Services_Model.xlsx"

with open(docx_path, "wb") as f:
    f.write(docx_b)
with open(xlsx_path, "wb") as f:
    f.write(xlsx_b)

print("\n--- 6. Generated Production Deliverables ---")
print(f"  Appraisal Memorandum (Word) : {docx_path} ({len(docx_b):,} bytes)")
print(f"  Dynamic Financial Model (Excel): {xlsx_path} ({len(xlsx_b):,} bytes)")
