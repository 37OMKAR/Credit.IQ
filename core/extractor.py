"""Turn located statement pages into the canonical schema.

Two paths:
  * LLM extraction (DeepSeek or any OpenAI-compatible model) - primary
  * Heuristic line-matcher - works offline / without a key, and as a cross-check
The officer always reviews and edits the result in the dashboard before analysis.
"""
import re

from . import schema
from .pdf_reader import detect_unit, pages_text

NUM_RE = re.compile(r"\(?-?\d[\d,.]*\d\)?|\(?-?\d\)?|(?<!\w)[-–—](?!\w)")
DEC_RE = re.compile(r"^\(?-?[\d,.]*\d[.,]\d{1,2}\)?$")
YEAR_RE = re.compile(r"(?:march|mar\.?)\s*31,?\s*(20\d{2})|31(?:st)?[\s\-/.]*(?:march|mar|03)[\s\-/.,]*(20\d{2})|\bfy\s*'?(20\d{2}|\d{2})\b|(20\d{2})\s*-\s*\d{2}\b", re.I)


def parse_number(tok):
    tok = str(tok).strip().replace("（", "(").replace("）", ")")
    if tok in ("-", "–", "—", ""):
        return 0.0
    neg = (tok.startswith("(") and tok.endswith(")")) or tok.startswith("-")
    tok = tok.strip("()-")
    # OCR / Indian formats: "9.726.59" -> 9726.59 ; "1,23,456.78" -> 123456.78 ; "9,726,59" -> 9726.59
    if tok.count(".") > 1:
        head, _, tail = tok.rpartition(".")
        tok = head.replace(".", "") + "." + tail
    if "." not in tok and re.search(r",\d{2}$", tok) and tok.count(",") >= 1 and len(tok.split(",")[-2]) >= 3:
        head, _, tail = tok.rpartition(",")
        tok = head + "." + tail
    tok = tok.replace(",", "")
    try:
        v = float(tok)
    except ValueError:
        return None
    return -v if neg else v


def detect_years(text):
    years = []
    for m in YEAR_RE.finditer(text):
        y = next((x for x in m.groups() if x), None)
        if not y:
            continue
        y = int(y) if len(y) == 4 else 2000 + int(y)
        if 2000 < y < 2100:
            years.append(y)
    uniq = sorted(set(years), reverse=True)
    return [f"FY{y}" for y in uniq[:3]] or ["FY-Current", "FY-Previous"]


# ----------------------------------------------------------------- heuristic
# generic labels whose meaning depends on the section heading above them
_CONTEXT_MAP = {
    "tradereceivable": {"NCA": "other_nc_fin_assets"},
    "tradepayable": {"NCL": "other_nc_fin_liabilities"},
    "borrowings": {"NCL": "long_term_borrowings", "CL": "short_term_borrowings"},
    "leaseliabilities": {"NCL": "lease_liabilities_nc", "CL": "lease_liabilities_c"},
    "otherfinancialliabilities": {"NCL": "other_nc_fin_liabilities", "CL": "other_current_fin_liabilities"},
    "provisions": {"NCL": "long_term_provisions", "CL": "short_term_provisions"},
    "loan": {"NCA": "nc_loans", "CA": "current_loans"},
    "investments": {"NCA": "nc_investments", "CA": "current_investments"},
    "otherfinancialassets": {"NCA": "other_nc_fin_assets", "CA": "other_current_fin_assets"},
    "otherassets": {"NCA": "other_nc_assets", "CA": "other_current_assets"},
    "otherliabilities": {"NCL": "other_nc_liabilities", "CL": "other_current_liabilities"},
    "total": {"CA": "total_current_assets", "CL": "total_current_liabilities"},
}
ABS_KEYS = {"interest_income", "dividend_paid"}
_EXTRA_SYN = {
    "trade_receivables": ["trade receivable"], "trade_payables": ["trade payable"], "deferred_tax_assets": ["deferred tax asset"],
    "purchases_stock": ["purchase of stock in trade", "purchases of stock in trade"],
    "cost_of_materials": ["cost of services", "cost of contract", "cost of sales", "cost of revenue", "cost of goods sold", "subcontracting"],
    "pat": ["profit (loss) for the year", "profit for the period"], "revenue": ["revenue from operation"],
    "finance_cost": ["finance cost"], "ppe": ["property p", "property,p"],
}
ADDITIVE = {"cost_of_materials"}
_LEAD_NOISE = re.compile(r"^(?:[\s\-–•*:.]*(?:\(?[ivxlc]{1,5}\)?[.)]+|\([a-z0-9]{1,3}\)|[a-z0-9][.)])\s*)+")
_PREFIXES = ("financialliabilities", "financialassets", "expenses", "income", "less", "add")


def _squash(s):
    return re.sub(r"[^a-z&]", "", s.lower())


def _clean_label(line):
    s = line.strip().lower()
    s = re.sub(r"^[\s\-–•*]+", "", s)
    s = _LEAD_NOISE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(line):
    """Numeric tokens to the right of the label (label = text before the first number column)."""
    out = []
    for m in NUM_RE.finditer(line):
        t = m.group(0)
        # skip digits glued to letters (e.g. SOCE1, 4(a), Note15)
        before = line[m.start() - 1] if m.start() else " "
        after = line[m.end()] if m.end() < len(line) else " "
        if before.isalpha() or (after.isalpha() and after.lower() not in "x"):
            continue
        if t.startswith("(") and m.end() < len(line) and line[m.end():m.end() + 1].isalpha():
            continue
        out.append(t)
    return out


def _page_profile(lines):
    dec = tot = 0
    counts = []
    for ln in lines:
        toks = _tokens(ln)
        tot += len(toks)
        d = [t for t in toks if DEC_RE.match(t)]
        dec += len(d)
        if len(d) >= 2:
            counts.append(len(d))
    decimal_mode = tot > 0 and dec / tot >= 0.45
    ncols = max(set(counts), key=counts.count) if counts else 2
    return decimal_mode, ncols


def _line_values(line, decimal_mode, ncols, notes=None):
    line = re.sub(r"^[\s\-–•*]+", "", line)  # bullet dashes are not zeros
    toks = _tokens(line)
    if decimal_mode:
        kept = []
        for t in toks:
            if DEC_RE.match(t) or t in ("-", "–", "—"):
                kept.append(parse_number(t))
            elif re.fullmatch(r"\(?\d{3,}\)?", t) and kept:
                # OCR dropped the decimal point (e.g. 33923 -> 339.23); keep the column position
                v = parse_number(t) / 100.0
                kept.append(v)
                if notes is not None:
                    notes.append(f"OCR number '{t}' read as {v:,.2f} - please verify")
        return [v for v in kept if v is not None]
    while len(toks) > ncols and re.fullmatch(r"\(?\d{1,2}\)?", toks[0]):
        toks.pop(0)  # note reference
    vals = [parse_number(t) for t in toks]
    return [v for v in vals if v is not None]


def heuristic_extract(pages, located, n_years=None):
    nums = []
    for sec in ("balance_sheet", "profit_loss", "cash_flow"):
        nums += [n for n in located.get(sec, []) if n not in nums]
    page_map = {p["page"]: p for p in pages}
    all_text = "\n".join(page_map[n]["text"] for n in nums if n in page_map)
    years = detect_years(all_text)
    if n_years:
        years = years[:n_years]
    ny = max(1, min(len(years), 3))
    years = years[:ny]
    unit = detect_unit(all_text)
    data = {y: schema.empty_year() for y in years}
    syn = []
    for key, _lbl, _sec, synonyms in schema.ALL_ITEMS:
        for s in synonyms + _EXTRA_SYN.get(key, []):
            syn.append((_squash(s), key))
    syn.sort(key=lambda x: -len(x[0]))
    seen_add = set()
    ocr_notes = []
    for n in nums:
        if n not in page_map:
            continue
        lines = page_map[n]["text"].splitlines()
        decimal_mode, ncols = _page_profile(lines)
        ctx = None
        for raw in lines:
            lab = _clean_label(raw)
            sq = _squash(lab)
            if not sq:
                continue
            for pre in _PREFIXES:
                if sq.startswith(pre) and len(sq) > len(pre) + 3:
                    sq = sq[len(pre):]
            head = sq
            if head.startswith("noncurrentassets") and len(head) < 22:
                ctx = "NCA"; continue
            if head.startswith("currentassets") and len(head) < 18:
                ctx = "CA"; continue
            if head.startswith("noncurrentliabilities") and len(head) < 27:
                ctx = "NCL"; continue
            if head.startswith("currentliabilities") and len(head) < 23:
                ctx = "CL"; continue
            syn_key, syn_len = None, 0
            for s, k in syn:
                if sq.startswith(s):
                    syn_key, syn_len = k, len(s)
                    break
            ctx_key, ctx_len = None, 0
            if ctx:
                for generic, mapping in _CONTEXT_MAP.items():
                    if generic != "total" and sq.startswith(generic) and ctx in mapping:
                        ctx_key, ctx_len = mapping[ctx], len(generic)
                        break
            # the section heading decides ambiguous labels unless a clearly more specific synonym matched
            key = ctx_key if (ctx_key and syn_len <= ctx_len + 3) else syn_key
            if key is None and sq.startswith("netcash"):
                key = "cfo" if "operating" in sq else "cfi" if "investing" in sq else "cff" if "financing" in sq else None
            if key is None and ctx and sq.startswith("total") and ctx in _CONTEXT_MAP["total"]:
                key = _CONTEXT_MAP["total"][ctx]
            if key is None:
                continue
            vals = _line_values(raw, decimal_mode, ncols, ocr_notes)
            if not vals:
                continue
            vals = vals[:ny]  # columns run latest -> oldest; extra columns (e.g. Ind AS opening BS) are ignored
            if key in ADDITIVE:
                sig = (key, sq[:30])
                if sig in seen_add:
                    continue
                seen_add.add(sig)
                for y, v in zip(years, vals):
                    data[y][key] = round((data[y].get(key) or 0) + v * unit, 2)
                continue
            for y, v in zip(years, vals):
                if key in ABS_KEYS:
                    v = abs(v)
                if data[y].get(key) is None:
                    data[y][key] = round(v * unit, 2)
    for y in years:
        schema.fill_derived(data[y])
    return {"years": years, "data": data, "unit_multiplier": unit, "method": "rule-based reader",
            "extraction_notes": list(dict.fromkeys(ocr_notes))}


# ----------------------------------------------------------------- LLM
FIN_SYSTEM = """You are a senior chartered accountant extracting financial statements from Indian annual reports
(Ind-AS / Schedule III) for a bank credit appraisal. You are precise and never invent numbers.
If a line item is not present, return null. Negative numbers (shown in brackets) must be negative.
Map each line to the closest canonical key; if a document line combines several canonical keys, put it in the
closest one. Never double count a sub-total and its components.
Conventions: short_term_borrowings must INCLUDE current maturities of long-term debt (report the current maturities
separately in current_maturities_ltd only as a memo figure). exceptional_items: gain positive, loss negative.
capex and dividend_paid: report as positive outflow amounts. interest_income: interest earned (from the other income
note) if disclosed. Disclosure keys (contingent liabilities, related-party amounts, promoter pledge %) only if visible."""


def _key_list():
    return "\n".join(f"- {k}: {lbl} [{schema.STATEMENT_OF[k]}]" for k, lbl, *_ in schema.ALL_ITEMS)


def llm_extract_financials(llm, pages, located, statement_pref="standalone"):
    nums = []
    for sec in ("balance_sheet", "profit_loss", "cash_flow"):
        nums += located.get(sec, [])
    text = pages_text(pages, set(nums), max_chars=70000)
    if not text.strip():
        raise ValueError("Could not locate the financial statement pages.")
    user = f"""Extract the {statement_pref} financial statements below into JSON with EXACTLY this shape:
{{
 "company_name": str,
 "statement_type": "standalone" | "consolidated",
 "unit_in_document": str  (e.g. "INR Crore", "Rs. in Lakhs", "INR Million"),
 "years": [ "FY2025", "FY2024" ]   (latest first; FY = financial year ending 31 March of that year),
 "data": {{ "FY2025": {{ <canonical_key>: number|null, ... }}, "FY2024": {{...}} }},
 "extraction_notes": [str]   (any ambiguity, re-classification or missing pages)
}}
Report numbers EXACTLY as printed in the document's unit (do not convert units).
Canonical keys:
{_key_list()}

DOCUMENT PAGES:
{text}"""
    out = llm.chat_json(FIN_SYSTEM, user, max_tokens=8000)
    unit = detect_unit(out.get("unit_in_document", "") or "") if out.get("unit_in_document") else detect_unit(text)
    years = out.get("years") or list((out.get("data") or {}).keys())
    data = {}
    for y in years:
        row = schema.empty_year()
        src = (out.get("data") or {}).get(y, {}) or {}
        for k in schema.KEYS:
            v = src.get(k)
            if isinstance(v, str):
                v = parse_number(v)
            if v is not None and k != "promoter_pledge_pct":
                v = round(float(v) * unit, 2)
            row[k] = v
        data[y] = schema.fill_derived(row)
    return {"years": years, "data": data, "unit_multiplier": unit, "method": f"LLM ({llm.provider})",
            "company_name": out.get("company_name"), "statement_type": out.get("statement_type"),
            "extraction_notes": out.get("extraction_notes", [])}


NOTES_SYSTEM = """You are a forensic accountant and bank credit analyst. You read auditor reports, CARO annexures,
related-party notes, contingent-liability notes and borrowing notes of Indian companies and identify anything
that hides risk or indicates diversion / siphoning of funds. Quote the evidence. Never speculate beyond the text;
if something is not disclosed, say 'not disclosed'."""


def llm_review_notes(llm, pages, located):
    nums = set()
    for sec in ("auditor", "related_party", "contingent", "borrowings_note"):
        nums.update(located.get(sec, []))
    text = pages_text(pages, nums, max_chars=60000)
    if not text.strip():
        return {"available": False}
    user = f"""From the pages below return JSON:
{{
 "auditor_name": str|null,
 "auditor_opinion": "unmodified"|"qualified"|"adverse"|"disclaimer"|"not found",
 "qualification_text": str|null,
 "going_concern_uncertainty": bool,
 "emphasis_of_matter": [str],
 "key_audit_matters": [str],
 "caro_adverse_remarks": [str]   (defaults in repayment, funds raised short-term used long-term, fraud reported, undisputed dues unpaid, loans to related parties without terms etc.),
 "related_parties": [{{"name": str, "relationship": str, "transaction": str, "amount": number|null, "page": int|null}}],
 "loans_advances_to_related_parties": number|null,
 "guarantees_given_for_related_parties": number|null,
 "contingent_liabilities_total": number|null,
 "contingent_items": [str],
 "borrowing_details": [{{"lender": str|null, "facility": str, "amount": number|null, "security": str|null, "rate": str|null}}],
 "defaults_or_delays": [str],
 "unit_in_document": str,
 "red_flags": [{{"title": str, "severity": "High"|"Medium"|"Low", "evidence": str, "page": int|null}}]
}}
Red flags to look for: round-tripping via related parties, loans/advances/investments to group or shell entities,
large unexplained 'other' assets, capital advances to related parties, guarantees for group companies,
qualified/adverse opinions, going concern doubt, auditor resignation, delayed statutory dues, defaults to banks,
fraud reporting, diversion of term loans, unusual year-end transactions, frequent change of auditor/CFO,
material write-offs, inventory/receivable verification issues, pending litigations or tax demands.

PAGES:
{text}"""
    out = llm.chat_json(NOTES_SYSTEM, user, max_tokens=6000)
    unit = detect_unit(out.get("unit_in_document") or text)
    for k in ("loans_advances_to_related_parties", "guarantees_given_for_related_parties", "contingent_liabilities_total"):
        if isinstance(out.get(k), (int, float)):
            out[k] = round(out[k] * unit, 2)
    for rp in out.get("related_parties", []) or []:
        if isinstance(rp.get("amount"), (int, float)):
            rp["amount"] = round(rp["amount"] * unit, 2)
    out["available"] = True
    return out


# ----------------------------------------------------------------- offline notes scan
_NOTE_RULES = [
    (r"qualified\s+opinion|basis\s+for\s+qualified", "Auditor qualified opinion", "High"),
    (r"adverse\s+opinion", "Auditor adverse opinion", "High"),
    (r"disclaimer\s+of\s+opinion", "Auditor disclaimer of opinion", "High"),
    (r"material\s+uncertainty\s+related\s+to\s+going\s+concern", "Going-concern uncertainty", "High"),
    (r"emphasis\s+of\s+matter", "Emphasis of matter in audit report", "Medium"),
    (r"short[\s-]term\s+basis.{0,120}used\s+for\s+long[\s-]term", "CARO: short-term funds used for long-term purposes", "High"),
    (r"repayable\s+on\s+demand.{0,80}without\s+specifying|without\s+specifying\s+any\s+terms", "CARO: loans without repayment terms", "High"),
    (r"delays?\s+in\s+(deposit|depositing)\s+of\s+undisputed|undisputed\s+statutory\s+dues.{0,60}outstanding", "CARO: delay in statutory dues", "Medium"),
    (r"default(ed)?\s+in\s+(the\s+)?repayment", "Default in repayment to lenders", "High"),
    (r"fraud\s+(by|on)\s+the\s+company|fraud\s+has\s+been\s+(noticed|reported)", "Fraud reported", "High"),
    (r"wilful\s+defaulter", "Wilful defaulter reference", "High"),
    (r"inter[\s-]corporate\s+deposits?", "Inter-corporate deposits in borrowing mix", "Medium"),
    (r"corporate\s+guarantee", "Corporate guarantees given", "Medium"),
    (r"pledged", "Promoter pledge disclosed", "Medium"),
    (r"resign(ed|ation)\s+of\s+(the\s+)?(statutory\s+)?auditor", "Auditor resignation", "High"),
    (r"subject\s+to\s+(reconciliation\s+and\s+)?confirmation", "Debtor / creditor balances not confirmed", "Medium"),
    (r"bank\s+guarantees?\s+(given|issued|through|worth)|given\s+bank\s+guarantees?", "Bank guarantees outstanding (non-fund exposure)", "Low"),
    (r"letters?\s+of\s+comfort", "Letter of comfort given", "Medium"),
    (r"(sanctioned|working\s+capital)\s+limits?.{0,80}(quarterly\s+)?(returns|statements).{0,60}(not\s+in\s+agreement|discrepanc|differ)", "Stock statements to bank differ from books", "High"),
    (r"(material|significant)\s+weakness", "Internal financial control weakness", "High"),
    (r"(proceedings|cases?)\s+.{0,40}(insolvency|ibc|nclt)", "Insolvency proceedings referenced", "High"),
]


NOTE_WHY = {
    "Auditor qualified opinion": "The auditor could not fully agree with the accounts - some figures may be wrong.",
    "Auditor adverse opinion": "The auditor says the accounts do not give a true picture.",
    "Auditor disclaimer of opinion": "The auditor could not form any opinion - the accounts cannot be relied on.",
    "Going-concern uncertainty": "The auditor doubts the company can keep operating for the next year.",
    "Emphasis of matter in audit report": "The auditor is drawing attention to a significant uncertainty the reader must not miss.",
    "CARO: short-term funds used for long-term purposes": "Working-capital money was used for long-term assets - a classic sign of diversion and liquidity stress.",
    "CARO: loans without repayment terms": "Loans given without repayment schedule are often a route to move money to group firms.",
    "CARO: delay in statutory dues": "Delays in paying taxes / PF signal cash shortage.",
    "Default in repayment to lenders": "The company has defaulted on loans - direct evidence of repayment stress.",
    "Fraud reported": "A fraud has been reported in the company.",
    "Wilful defaulter reference": "A wilful-defaulter reference is a serious integrity concern.",
    "Inter-corporate deposits in borrowing mix": "Costly ICDs usually mean bank finance was not available.",
    "Corporate guarantees given": "Guarantees for others can become the company's own liability.",
    "Promoter pledge disclosed": "Pledged promoter shares signal promoter cash stress and control risk.",
    "Auditor resignation": "Auditors rarely resign mid-term without a reason - often disagreements over accounts.",
    "Debtor / creditor balances not confirmed": "Unconfirmed balances may hide fictitious debtors or unrecorded liabilities.",
    "Bank guarantees outstanding (non-fund exposure)": "Bank guarantees are non-fund exposure that can turn into debt if invoked.",
    "Letter of comfort given": "A comfort letter can create an obligation for another entity's debt.",
    "Stock statements to bank differ from books": "Stock statements to bank differ from books - drawing power may be inflated.",
    "Internal financial control weakness": "Weak internal controls make errors and fraud more likely.",
    "Insolvency proceedings referenced": "Insolvency proceedings can lead to loss of control of the company or its debtors.",
}


def heuristic_notes_review(pages, located):
    nums = set()
    for sec in ("auditor", "related_party", "contingent", "borrowings_note"):
        nums.update(located.get(sec, []))
    flags, eom = [], []
    for p in pages:  # keyword scan is cheap, so read every page (notes often sit outside the located ones)
        flat = re.sub(r"\s+", " ", p["text"])
        for pat, title, sev in _NOTE_RULES:
            m = None
            for cand in re.finditer(pat, flat, re.I):
                # CARO is mostly written as negatives ("has not defaulted", "no fraud ... noticed") - skip those
                before = flat[max(0, cand.start() - 70):cand.start()].lower()
                after = flat[cand.end():cand.end() + 60].lower()
                if re.search(r"\b(not|no|nil|neither|nor|never|without any)\b", before[-45:]) or \
                        re.search(r"^\W*(is|are|has been|have been)?\s*(not|nil)\b", after):
                    continue
                m = cand
                break
            if m:
                s0 = max(0, m.start() - 140)
                s0 = flat.find(" ", s0) + 1 if s0 else 0
                snippet = ("..." if s0 else "") + flat[s0: m.end() + 260].strip() + "..."
                flags.append({"title": title, "severity": sev, "evidence": snippet, "page": p["page"], "why": NOTE_WHY.get(title, "")})
                if title.startswith("Emphasis"):
                    eom.append(snippet)
    seen, uniq = set(), []
    for f in flags:
        if f["title"] not in seen:
            seen.add(f["title"]); uniq.append(f)
    op = "unmodified"
    if any("qualified" in f["title"] for f in uniq): op = "qualified"
    if any("adverse" in f["title"] for f in uniq): op = "adverse"
    if any("disclaimer" in f["title"] for f in uniq): op = "disclaimer"
    return {"available": True, "method": "keyword scan", "auditor_opinion": op if nums else "not found",
            "going_concern_uncertainty": any(f["title"].startswith("Going") for f in uniq),
            "emphasis_of_matter": [], "key_audit_matters": [], "caro_adverse_remarks": [], "defaults_or_delays": [],
            "related_parties": [], "borrowing_details": [], "contingent_items": [], "red_flags": uniq}
