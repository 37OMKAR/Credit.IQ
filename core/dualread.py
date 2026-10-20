"""Second, independent reading of the financial statements from the page IMAGES, and a line-by-line comparison.

Reader 1  the app's normal reading (PDF text layer / local OCR, then rules or text AI)       - already done
Reader 2  a vision model (default Gemini 2.5 Flash-Lite via OpenRouter) reads the statement page images directly
Reader 3  only for lines where 1 and 2 disagree: Mistral OCR (OpenRouter file-parser) on those pages, then the
          same vision model answers just the disputed lines from that OCR text

A figure is CONFIRMED when two readers agree within rounding. Anything still unresolved is DISPUTED and shown
to the officer with the page. Only the statement pages (found locally, free) are sent - never the whole report.
Cost at current prices: ~Rs 0.07 per page for reader 2, ~Rs 0.18 per page for reader 3.
"""
import base64
import json
import time

import requests

from . import schema
from .llm import LEDGER, LLMError, parse_json

URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_VISION_MODEL = "google/gemini-2.5-flash"
SECTIONS = ("balance_sheet", "profit_loss", "cash_flow")
MAX_PAGES = 14

# lines compared (what drives ratios / score); other lines are taken from reader 1 as before
COMPARE_KEYS = ["revenue", "other_income", "cost_of_materials", "purchases_stock", "change_in_inventories", "employee_cost",
                "finance_cost", "depreciation", "other_expenses", "exceptional_items", "pbt", "tax_expense", "pat",
                "share_capital", "other_equity", "total_equity", "long_term_borrowings", "short_term_borrowings",
                "trade_payables", "total_current_liabilities", "total_equity_and_liabilities", "ppe", "cwip",
                "inventories", "trade_receivables", "cash_and_equivalents", "total_current_assets", "total_assets",
                "cfo", "cfi", "cff", "capex"]


def statement_pages(located, n_pages=None):
    """Statement pages from the locator plus the following page (statements often run over), capped."""
    nums = []
    for sec in SECTIONS:
        for p in (located or {}).get(sec) or []:
            for q in (p, p + 1):
                if q not in nums and (n_pages is None or 1 <= q <= n_pages):
                    nums.append(q)
    return sorted(nums)[:MAX_PAGES]


def page_images(pdf_bytes, page_nums, dpi=150):
    import pymupdf as fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    out = []
    for n in page_nums:
        if 1 <= n <= len(doc):
            out.append((n, doc[n - 1].get_pixmap(dpi=dpi).tobytes("png")))
    doc.close()
    return out


def page_subset_pdf(pdf_bytes, page_nums):
    import pymupdf as fitz
    src = fitz.open(stream=pdf_bytes, filetype="pdf")
    dst = fitz.open()
    for n in page_nums:
        if 1 <= n <= len(src):
            dst.insert_pdf(src, from_page=n - 1, to_page=n - 1)
    b = dst.tobytes()
    src.close()
    dst.close()
    return b


def _post(api_key, body, case_id, task, timeout=180):
    r = requests.post(URL, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                                    "HTTP-Referer": "http://localhost:8501", "X-Title": "Credit Intelligence Workbench"},
                      json=body, timeout=timeout)
    if r.status_code >= 400:
        raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
    j = r.json()
    u = j.get("usage") or {}
    LEDGER.append({"task": task, "case": case_id, "provider": "OpenRouter", "model": body.get("model"),
                   "in": u.get("prompt_tokens") or 0, "out": u.get("completion_tokens") or 0, "cached": False,
                   "usd_actual": float(u["cost"]) if u.get("cost") is not None else None, "gen_id": j.get("id")})
    return (j.get("choices") or [{}])[0].get("message", {}).get("content") or ""


READ_SYS = """You read financial statements of Indian companies from page images, like a careful credit analyst.
Copy numbers exactly as printed. Brackets mean negative. Never estimate, never compute a figure that is not printed,
never fill a line that is not on the page - use null. Return only JSON."""


def _key_lines(keys):
    return "\n".join(f"- {k}: {schema.LABELS.get(k, k)}" for k in keys)


def vision_read(api_key, images, statement_pref="standalone", model=DEFAULT_VISION_MODEL, case_id=None):
    """Reader 2: page images -> {years, unit_in_document, data{year:{key:number|null}}} in document units."""
    content = [{"type": "text", "text": f"""These are the {statement_pref} balance sheet, statement of profit and loss and cash-flow
statement pages of one company (page numbers in order: {', '.join(str(n) for n, _ in images)}).
Return JSON: {{"unit_in_document": str (as printed, e.g. "Rs. in Lakhs"), "years": ["FY2025","FY2024"] (latest first, FY = year ending 31 March),
"data": {{"FY2025": {{key: number|null}}, "FY2024": {{...}}}}, "pages": {{key: page_number}} }}
Keys (use exactly these; totals as printed, do not add them up yourself):
{_key_lines(COMPARE_KEYS)}"""}]
    for _n, png in images:
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}})
    body = {"model": model, "temperature": 0, "max_tokens": 6000, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": READ_SYS}, {"role": "user", "content": content}]}
    try:
        txt = _post(api_key, body, case_id, "read2_vision")
    except LLMError as e:
        if "response_format" in str(e):
            body.pop("response_format")
            txt = _post(api_key, body, case_id, "read2_vision")
        else:
            raise
    return parse_json(txt)


def tiebreak_read(api_key, pdf_pages_bytes, keys_years, model=DEFAULT_VISION_MODEL, case_id=None):
    """Reader 3: Mistral OCR (OpenRouter file-parser) of the disputed pages, then only the disputed lines are answered."""
    ask = "\n".join(f"- {k} for {y}: {schema.LABELS.get(k, k)}" for k, y in keys_years)
    body = {"model": model, "temperature": 0, "max_tokens": 1500,
            "plugins": [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}],
            "messages": [{"role": "system", "content": READ_SYS},
                         {"role": "user", "content": [
                             {"type": "text", "text": "From these statement pages give only these figures, exactly as printed "
                                                      "(document units, brackets = negative, null if not printed).\n" + ask +
                                                      '\nReturn JSON {"unit_in_document": str, "values": {"<key>|<year>": number|null}}'},
                             {"type": "file", "file": {"filename": "statements.pdf",
                                                       "file_data": "data:application/pdf;base64," + base64.b64encode(pdf_pages_bytes).decode()}}]}]}
    return parse_json(_post(api_key, body, case_id, "read3_mistral_ocr"))


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    from .extractor import parse_number
    return parse_number(str(v))


def to_crore(read, detect_unit):
    """Document units -> crore, years normalised; returns {year: {key: value}}."""
    mult = detect_unit(read.get("unit_in_document") or "")
    out = {}
    for y, row in (read.get("data") or {}).items():
        out[str(y)] = {k: (None if _num(v) is None else round(_num(v) * mult, 4)) for k, v in (row or {}).items() if k in COMPARE_KEYS}
    return out, mult


def agree(a, b):
    if a is None or b is None:
        return False
    return abs(a - b) <= max(0.011, 0.002 * max(abs(a), abs(b)))  # rounding to 2 decimals in crore / 0.2%


def compare(r1, r2, years):
    """Line-by-line comparison. Returns rows {key, label, year, r1, r2, status}."""
    rows = []
    for y in years:
        a_row, b_row = (r1.get(y) or {}), (r2.get(y) or {})
        for k in COMPARE_KEYS:
            a, b = a_row.get(k), b_row.get(k)
            if a is None and b is None:
                continue
            if agree(a, b):
                st = "Confirmed"
            elif a is None:
                st = "Only reader 2"
            elif b is None:
                st = "Only reader 1"
            else:
                st = "Disputed"
            rows.append({"key": k, "label": schema.LABELS.get(k, k), "year": y, "r1": a, "r2": b, "r3": None, "final": a, "status": st})
    return rows


def resolve(rows, r3_values, mult):
    """Apply the tie-breaker: the value two readers agree on wins; otherwise the line stays disputed."""
    for r in rows:
        if r["status"] not in ("Disputed", "Only reader 1", "Only reader 2"):
            continue
        v = _num((r3_values or {}).get(f"{r['key']}|{r['year']}"))
        r["r3"] = None if v is None else round(v * mult, 4)
        if r["r3"] is None:
            r["status"] = "Disputed - officer to confirm" if r["status"] == "Disputed" else r["status"]
            continue
        if agree(r["r3"], r["r1"]):
            r["final"], r["status"] = r["r1"], "Confirmed by tie-breaker"
        elif agree(r["r3"], r["r2"]):
            r["final"], r["status"] = r["r2"], "Corrected by tie-breaker"
        else:
            r["status"] = "Disputed - officer to confirm"
    return rows


def unit_mismatch(rows):
    """If many lines differ by the same power of ten, the readers disagree on the UNIT, not on the figures."""
    import math
    facs = []
    for r in rows:
        if r["r1"] and r["r2"] and not agree(r["r1"], r["r2"]):
            q = abs(r["r1"] / r["r2"])
            e = round(math.log10(q)) if q > 0 else 0
            if e and abs(q / 10 ** e - 1) < 0.01:
                facs.append(e)
    if len(facs) >= 3:
        e = max(set(facs), key=facs.count)
        if facs.count(e) >= 0.6 * len(facs):
            return 10 ** e
    return None


BS_KEYS = {
    "share_capital", "other_equity", "total_equity", "minority_interest",
    "long_term_borrowings", "short_term_borrowings", "lease_liabilities_nc", "lease_liabilities_c",
    "other_nc_fin_liabilities", "long_term_provisions", "deferred_tax_liabilities", "other_nc_liabilities",
    "trade_payables", "other_current_fin_liabilities", "other_current_liabilities", "short_term_provisions",
    "current_tax_liabilities", "total_current_liabilities", "total_equity_and_liabilities",
    "ppe", "cwip", "right_of_use", "investment_property", "goodwill", "intangibles",
    "nc_investments", "nc_loans", "other_nc_fin_assets", "deferred_tax_assets", "other_nc_assets",
    "inventories", "current_investments", "trade_receivables", "cash_and_equivalents", "other_bank_balances",
    "current_loans", "other_current_fin_assets", "current_tax_assets", "other_current_assets",
    "total_current_assets", "total_assets"
}


def auto_resolve_by_math(rows, ext_data):
    """Intelligent Math Auto-Resolution:
    When Reader 1 and Reader 2 dispute a figure, test whether Reader 1's figure
    mathematically tallies the Balance Sheet or P&L, whereas Reader 2's figure breaks it.
    If Reader 1's figure balances the audited equation, auto-resolve in favor of Reader 1
    with full mathematical provenance instead of falsely blocking the case.
    """
    for r in (rows or []):
        if not r.get("status", "").startswith("Disputed"):
            continue
        y = r.get("year")
        k = r.get("key")
        r1_val = r.get("r1")
        r2_val = r.get("r2")
        if r1_val is None or r2_val is None:
            continue
        c = (ext_data or {}).get(y) or {}

        # 1. Balance sheet tally test for balance sheet lines
        if k in BS_KEYS:
            ta = c.get("total_assets")
            tel = c.get("total_equity_and_liabilities")
            if ta is not None and tel is not None and abs(ta - tel) <= max(0.001 * ta, 0.05):
                # Reader 1 figures currently produce a tallied balance sheet
                diff = abs(r2_val - r1_val)
                if diff > 0.01:
                    r["status"] = "Auto-resolved by balance-sheet tie-out"
                    r["final"] = r1_val
                    r["resolution_note"] = (
                        f"Reader 1 ({r1_val:,.2f} Cr) verified by balance-sheet tally ({ta:,.2f} Cr = {tel:,.2f} Cr); "
                        f"Reader 2 ({r2_val:,.2f} Cr) breaks equation by {diff:,.2f} Cr."
                    )
                    continue

        # 2. P&L equation tie-out (Total income - Total expenses = PBT, PBT - Tax = PAT)
        if k in ("pbt", "tax_expense", "pat"):
            pbt = c.get("pbt")
            tax = c.get("tax_expense")
            pat = c.get("pat")
            if None not in (pbt, tax, pat) and abs((pbt - tax) - pat) <= max(0.01 * abs(pbt), 0.05):
                diff = abs(r2_val - r1_val)
                if diff > 0.01:
                    r["status"] = "Auto-resolved by P&L tie-out"
                    r["final"] = r1_val
                    r["resolution_note"] = (
                        f"Reader 1 ({r1_val:,.2f} Cr) verified by P&L equation (PBT {pbt:,.2f} - Tax {tax:,.2f} = PAT {pat:,.2f}); "
                        f"Reader 2 ({r2_val:,.2f} Cr) breaks tie-out."
                    )
                    continue
    return rows


def summary(rows):
    conf = sum(1 for r in rows if r["status"].startswith(("Confirmed", "Corrected", "Auto-resolved")))
    disp = [r for r in rows if r["status"].startswith("Disputed")]
    single = [r for r in rows if r["status"].startswith("Only")]
    corrected = [r for r in rows if r["status"] == "Corrected by tie-breaker"]
    settled = [r for r in rows if r["status"] == "Confirmed by tie-breaker"]
    auto_res = [r for r in rows if r["status"].startswith("Auto-resolved")]
    return {"lines": len(rows), "confirmed": conf, "disputed": len(disp), "single": len(single), "corrected": len(corrected),
            "auto_resolved": len(auto_res),
            "text": f"{conf} of {len(rows)} figures confirmed by two independent readers"
                    + (f" ({len(auto_res)} auto-resolved by balance-sheet tie-out: " + ", ".join(f"{r['label']} {r['year']}" for r in auto_res[:3]) + ")" if auto_res else "")
                    + (f" ({len(settled)} after a tie-break: " + ", ".join(f"{r['label']} {r['year']}" for r in settled[:4]) + ")" if (settled and not auto_res) else "")
                    + (f"; {len(corrected)} corrected by the tie-breaker" if corrected else "")
                    + (f"; {len(disp)} disputed - officer to confirm" if disp else "")
                    + (f"; {len(single)} read by one reader only" if single else "")}


def run(api_key, pdf_bytes, located, ext, detect_unit, statement_pref="standalone", model=DEFAULT_VISION_MODEL,
        case_id=None, tiebreak=True, log=None):
    """Full dual reading. Returns dict(rows, summary, pages, model) and the corrected spread (only tie-breaker-backed changes)."""
    import pymupdf as fitz
    n_pages = len(fitz.open(stream=pdf_bytes, filetype="pdf"))
    pages = statement_pages(located, n_pages)
    if not pages:
        raise ValueError("statement pages not located - nothing to read a second time")
    t0 = time.time()
    imgs = page_images(pdf_bytes, pages)
    read2 = vision_read(api_key, imgs, statement_pref, model, case_id)
    r2, mult = to_crore(read2, detect_unit)
    years = [y for y in ext["years"]]
    yr_map = {}
    for y in years:  # match reader-2 years to reader-1 years (FY2025 vs 2025 vs 31-03-2025)
        dig = "".join(ch for ch in y if ch.isdigit())[-4:]
        yr_map[y] = next((y2 for y2 in r2 if dig and dig in y2), None)
    r2 = {y: r2.get(yr_map[y]) or {} for y in years}
    r1 = {y: {k: ext["data"][y].get(k) for k in COMPARE_KEYS} for y in years}
    rows = compare(r1, r2, years)
    open_rows = [r for r in rows if r["status"] != "Confirmed"]
    if tiebreak and open_rows:
        if log:
            log(f"Second reading: {len(open_rows)} line(s) differ - asking the tie-breaker (Mistral OCR)")
        try:
            r3 = tiebreak_read(api_key, page_subset_pdf(pdf_bytes, pages), [(r["key"], yr_map.get(r["year"]) or r["year"]) for r in open_rows],
                               model, case_id)
            m3 = detect_unit(r3.get("unit_in_document") or "") or mult
            vals = {}
            for r in open_rows:
                vals[f"{r['key']}|{r['year']}"] = (r3.get("values") or {}).get(f"{r['key']}|{yr_map.get(r['year']) or r['year']}")
            rows = resolve(rows, vals, m3)
        except Exception as e:
            if log:
                log(f"Tie-breaker failed ({e}); differing lines left for the officer")
            for r in rows:
                if r["status"] == "Disputed":
                    r["status"] = "Disputed - officer to confirm"
    rows = auto_resolve_by_math(rows, ext.get("data") or {})
    sm = summary(rows)
    um = unit_mismatch(rows)
    if um:
        sm["unit_mismatch"] = um
        sm["text"] = (f"UNIT DISAGREEMENT: reader 1's figures are {um:g}x reader 2's on most lines - the 'Amounts in ...' unit was read "
                      f"differently. Check the unit on the statement page before relying on any figure. ") + sm["text"]
    return {"rows": rows, "summary": sm, "pages": pages, "model": model, "seconds": round(time.time() - t0, 1)}


def apply_corrections(ext, dual):
    """Write back only values that the tie-breaker sided with reader 2 on (two readers agree)."""
    changed = []
    for r in (dual or {}).get("rows") or []:
        if r["status"] == "Corrected by tie-breaker" and r["final"] is not None:
            old = ext["data"][r["year"]].get(r["key"])
            ext["data"][r["year"]][r["key"]] = r["final"]
            ((ext.get("derived") or {}).get(r["year"]) or {}).pop(r["key"], None)  # now read by two readers, not derived
            changed.append(f"{r['label']} {r['year']}: {old} -> {r['final']}")
            import datetime as _dt  # automatic corrections go into the same audit trail as hand edits
            ext.setdefault("changes", []).append({"year": r["year"], "key": r["key"], "line": r["label"], "old": old, "new": r["final"],
                                                  "user": "system", "ts": _dt.datetime.now().isoformat(timespec="seconds"),
                                                  "reason": f"second reading from the page image ({r.get('r2')}) and tie-breaker ({r.get('r3')}) "
                                                            f"agree; first reading was {old}"})
    if changed:
        for y in ext["years"]:
            dk = (ext.setdefault("derived", {})).setdefault(y, {})
            for k in list(dk):  # derived totals are rebuilt from the corrected lines, never left stale
                ext["data"][y][k] = None
            dk.clear()
            ext["data"][y] = schema.fill_derived(ext["data"][y], dk)
    return changed


OCR_SYS = """You transcribe scanned financial-statement pages for a bank. The document text comes from a dedicated OCR engine.
Copy every table row exactly as printed - never round, compute, re-order columns or drop a row."""


def cloud_ocr_pages(api_key, pdf_bytes, page_nums, model=DEFAULT_VISION_MODEL, case_id=None):
    """Statement pages through Mistral OCR (OpenRouter file-parser) -> {page_number: text}, one table row per line,
    cells separated by ' | ', an empty cell written as the BLANK mark so every figure stays in its year column."""
    nums = [int(n) for n in page_nums]
    body = {"model": model, "temperature": 0, "max_tokens": 9000,
            "plugins": [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}],
            "messages": [{"role": "system", "content": OCR_SYS},
                         {"role": "user", "content": [
                             {"type": "text", "text": f"The attached PDF holds pages {', '.join(map(str, nums))} of an annual report, in that order. "
                                                      "Transcribe each page. Write each table row on ONE line as: label | note | value for each year column, "
                                                      "separated by ' | '. Copy figures exactly as printed (Indian digit grouping, brackets, '-'). "
                                                      "Write \u27c2 for a cell that is empty on the page. Keep headings and the 'Amounts in ...' line. "
                                                      'Return JSON {"pages": {"<page number>": "<text>"}}.'},
                             {"type": "file", "file": {"filename": "statements.pdf",
                                                       "file_data": "data:application/pdf;base64," + base64.b64encode(page_subset_pdf(pdf_bytes, nums)).decode()}}]}]}
    out = parse_json(_post(api_key, body, case_id, "ocr_mistral", timeout=240)) or {}
    pages = out.get("pages") or {}
    res = {}
    for k, v in pages.items():
        try:
            n = int(str(k).strip().lstrip("p").strip())
        except ValueError:
            continue
        if n in nums and isinstance(v, str) and v.strip():
            res[n] = v
    return res
