"""Logic checker - runs on every analysis before any report is written.

1. Arithmetic: balance sheet tallies, PBT - tax = PAT, no negative assets / revenue.
2. Independent recomputation: key ratios are recomputed here with separate code from the raw figures and must
   agree with the ratio engine (catches formula or mapping errors).
3. Plausibility: year-on-year jumps that usually mean a misread unit (lakh vs crore) or a wrong year.
4. Consistency: grade, red flags and recommendation must not contradict each other.
5. AI text: every figure in an AI-written sentence must trace back to the financial data, ratios or scores.
   Sentences with untraceable figures are removed from the report and listed in the verification log.
6. Web: counts of web facts that were verified on their source page vs rejected.

Result: list of checks {area, check, result PASS|WARN|FAIL, detail} and the cleaned narrative.
"""
import copy
import re

from . import schema

g = schema.g
PASS, WARN, FAIL = "PASS", "WARN", "FAIL"


def _add(out, area, check, result, detail=""):
    out.append({"area": area, "check": check, "result": result, "detail": detail})


def _close(a, b, rel=0.005, absol=0.01):
    if a is None or b is None:
        return True
    return abs(a - b) <= max(abs(b) * rel, absol)


# ------------------------------------------------------------------ 1-3 figures
def check_figures(b, out):
    years, d, r = b["years"], b["data"], b["ratios"]
    der = b.get("derived") or {}
    for y in years:
        c = d[y]
        dy = der.get(y) or {}
        ta, tel = g(c, "total_assets"), g(c, "total_equity_and_liabilities")
        if {"total_assets", "total_equity_and_liabilities"} & set(dy):
            _add(out, "Arithmetic", f"Balance sheet tallies - {y}", WARN, "only one side of the balance sheet was read - the tally cannot be verified")
        elif ta and tel:
            ok = abs(ta - tel) <= max(0.001 * ta, 0.05)  # a printed balance sheet ties to the rupee; allow only rounding
            _add(out, "Arithmetic", f"Balance sheet tallies - {y}", PASS if ok else FAIL, f"assets {ta:,.2f} vs equity & liabilities {tel:,.2f} Cr")
        else:
            _add(out, "Arithmetic", f"Balance sheet tallies - {y}", WARN, "total assets or total equity & liabilities not read")
        pbt, tax, pat = c.get("pbt"), c.get("tax_expense"), c.get("pat")
        if {"pbt", "tax_expense", "pat"} & set(dy):
            _add(out, "Arithmetic", f"PBT - tax = PAT - {y}", WARN,
                 "; ".join(f"{schema.LABELS.get(k, k)} derived: {dy[k]}" for k in ("pbt", "tax_expense", "pat") if k in dy)
                 + " - the tie-out cannot be verified")
        elif None not in (pbt, tax, pat) and pbt > max(0.05, 0.02 * abs(g(c, "revenue"))) and abs(tax) < 1e-9 and abs(pbt - pat) < 1e-9:
            _add(out, "Arithmetic", f"PBT - tax = PAT - {y}", WARN, f"tax nil and PAT equal to PBT ({pbt:,.2f} Cr) on a material profit - confirm "
                 "against the P&L: often the PAT line was not read and was set equal to PBT")
        elif None not in (pbt, tax, pat):
            ok = abs((pbt - tax) - pat) <= max(0.01 * abs(pbt), 0.05)
            _add(out, "Arithmetic", f"PBT - tax = PAT - {y}", PASS if ok else FAIL, f"{pbt:,.2f} - {tax:,.2f} vs PAT {pat:,.2f}"
                 + ("" if ok else " - check total tax (current + deferred) and PAT against the P&L"))
        # lines that cannot be negative (other equity, net worth, minority interest, exceptional items, JV share, change in
        # inventories, PBT / PAT and cash flows legitimately can)
        neg = [schema.LABELS.get(k, k) for k, _l, sec, _s in schema.ALL_ITEMS
               if sec in ("Non-current Assets", "Current Assets", "Non-current Liabilities", "Current Liabilities", "Expenses", "Income")
               and k not in ("change_in_inventories", "other_income") and (c.get(k) or 0) < 0]
        neg += [schema.LABELS.get(k, k) for k in ("total_assets", "total_equity_and_liabilities", "share_capital") if (c.get(k) or 0) < 0]
        _add(out, "Arithmetic", f"No negative assets / revenue - {y}", FAIL if neg else PASS, ", ".join(neg) or "")

    # independent recomputation (written separately from core/ratios.py on purpose)
    y0 = years[0]
    c, rr = d[y0], r[y0]
    rev, tca, tcl = c.get("revenue"), c.get("total_current_assets"), c.get("total_current_liabilities")
    eq = c.get("total_equity")
    debt = sum((c.get(k) or 0) for k in ("long_term_borrowings", "short_term_borrowings", "lease_liabilities_nc", "lease_liabilities_c"))
    pbt = c.get("pbt")
    ebitda = None if pbt is None else (pbt - (c.get("exceptional_items") or 0) - (c.get("share_jv_profit") or 0) + (c.get("finance_cost") or 0)
                                      + (c.get("depreciation") or 0) - (c.get("other_income") or 0))
    mine = {
        "current_ratio": tca / tcl if tca is not None and tcl else None,
        "ebitda_margin": ebitda / rev if ebitda is not None and rev else None,
        "debtor_days": (c.get("trade_receivables") or 0) / rev * 365 if rev else None,
        "pat_margin": c.get("pat") / rev if c.get("pat") is not None and rev else None,
        "de": debt / eq if eq and eq > 0 else None,
    }
    bad = []
    for k, v in mine.items():
        if v is not None and rr.get(k) is not None and not _close(rr[k], v, rel=0.01, absol=0.005):
            bad.append(f"{k}: engine {rr[k]:.4f} vs check {v:.4f}")
    _add(out, "Recomputation", "Key ratios recomputed independently agree with the ratio engine", FAIL if bad else PASS,
         "; ".join(bad) or "current ratio, EBITDA margin, debtor days, PAT margin, debt/equity")

    if len(years) > 1:
        p = d[years[1]]
        jumps = []
        for k in ("revenue", "total_assets", "total_equity"):
            a, b_ = g(c, k), g(p, k)
            if a > 0 and b_ > 0 and (a / b_ > 4 or a / b_ < 0.25):
                jumps.append(f"{schema.LABELS.get(k, k)} {b_:,.2f} -> {a:,.2f} Cr ({a / b_:.1f}x)")
        _add(out, "Plausibility", "No extreme year-on-year jump (possible lakh/crore or wrong-year misread)", WARN if jumps else PASS,
             ("Confirm against the PDF: " + "; ".join(jumps)) if jumps else "")
    ta0 = g(c, "total_assets")
    if ta0:
        odd = ta0 > 2_000_000 or ta0 < 0.005  # > Rs 20 lakh crore (bigger than any Indian company) or < Rs 50,000
        _add(out, "Plausibility", "Size plausible for the unit read (rupees / thousands / lakhs / crore)", FAIL if odd else PASS,
             (f"total assets read as Rs {ta0:,.4f} crore - the document's unit was almost certainly misread; check the 'Amounts in ...' line"
              if odd else f"total assets Rs {ta0:,.2f} crore"))
    if len(years) > 1:
        p_ = d[years[1]]
        mv = []
        for k in ("ppe", "cwip", "long_term_borrowings", "short_term_borrowings", "nc_investments", "current_investments",
                  "trade_receivables", "inventories", "other_current_assets", "nc_loans", "current_loans"):
            if c.get(k) is None or p_.get(k) is None:
                continue  # read for one year only: reported under 'Material lines read for both years', never as a movement
            a_, b0 = g(c, k), g(p_, k)
            ta_ = max(g(c, "total_assets"), 1e-9)
            if max(a_, b0) > 0.02 * ta_ and (b0 == 0 or a_ / b0 > 2.5 or a_ / b0 < 0.4) and abs(a_ - b0) > 0.02 * ta_:
                mv.append(f"{schema.LABELS.get(k, k)} {b0:,.2f} -> {a_:,.2f} Cr")
        _add(out, "Plausibility", "Large balance-sheet movements reconciled", WARN if mv else PASS,
             ("Reconcile opening, additions, transfers (e.g. CWIP capitalised), disposals and closing before relying on them: " + "; ".join(mv[:6]))
             if mv else "no line above 2% of assets moved by more than 2.5x")
    import datetime as _dt
    import re as _re
    m_ = _re.search(r"(20\d\d)", str(y0))
    if m_:
        fy_end = _dt.date(int(m_.group(1)), 3, 31)
        age = (_dt.date.today() - fy_end).days // 30
        _add(out, "Coverage", "Latest statements are recent", WARN if age > 18 else PASS,
             f"latest year {y0} ended about {age} months ago" + (" - request the latest audited (or provisional) statements" if age > 18 else ""))
    nt = b.get("notes") or {}
    op = str(nt.get("auditor_opinion") or "not found")
    _add(out, "Coverage", "Audit opinion read from the auditor's report itself", PASS if nt.get("auditor_report_pages") else WARN,
         f"opinion '{op}' from page(s) {nt.get('auditor_report_pages')}" if nt.get("auditor_report_pages") else
         "auditor's report not in the documents - opinion and going-concern status NOT verified; obtain the signed report")
    dl = [f"{schema.LABELS.get(k, k)} {y}: {how}" for y in years for k, how in (der.get(y) or {}).items() if k != "total_income"]
    _add(out, "Coverage", "Totals read from the statements, not rebuilt", WARN if dl else PASS,
         ("derived, not read - confirm against the PDF: " + "; ".join(dl[:8])) if dl else "")
    if len(years) > 1:
        one = []
        for k, lab, sec, _s in schema.ALL_ITEMS:
            if sec in ("Cash Flow",) or k in ("promoter_pledge_pct", "market_cap", "rpt_sales", "rpt_purchases", "rpt_loans_given",
                                               "contingent_liabilities", "guarantees_given", "dividend_paid"):
                continue
            a_, b_ = c.get(k), d[years[1]].get(k)
            if (a_ is None) != (b_ is None) and abs(a_ if a_ is not None else b_) > 0.005 * max(g(c, "total_assets"), 1):
                one.append(f"{lab} ({years[0] if a_ is not None else years[1]} only)")
        debt_gap = [schema.LABELS[k] for k in ("long_term_borrowings", "short_term_borrowings", "lease_liabilities_nc", "lease_liabilities_c")
                    if c.get(k) is None and d[years[1]].get(k) not in (None, 0) and abs(g(d[years[1]], k)) > 0.005 * max(g(c, "total_assets"), 1)]
        if debt_gap:  # borrowings may be nil, but borrowings that existed last year and were not read this year flatter every leverage ratio
            _add(out, "Arithmetic", "Borrowings read for the latest year", FAIL,
                 f"{', '.join(debt_gap)} read for {years[1]} but not for {years[0]} - confirm against the balance sheet; until then leverage, "
                 "DSCR and security cover would be understated")
        _add(out, "Coverage", "Material lines read for both years", WARN if one else PASS,
             ("read for one year only - possible misread or missed line (comparisons with the other year are not shown): " + "; ".join(one[:8]))
             if one else "")
    core = [k for k in ("revenue", "pat", "total_equity", "total_current_assets", "total_current_liabilities", "total_assets") if c.get(k) is None]
    _add(out, "Coverage", "Core statement lines read", FAIL if core else PASS, ("missing: " + ", ".join(core)) if core else "")


# lines that make up each printed total (capital advances is usually inside 'other non-current assets', so it is a memo line)
SUBTOTALS = [
    ("total_equity", ["share_capital", "other_equity"], "Equity"),
    ("total_current_assets", ["inventories", "current_investments", "trade_receivables", "cash_and_equivalents", "other_bank_balances",
                              "current_loans", "other_current_fin_assets", "current_tax_assets", "other_current_assets"], "Current assets"),
    ("total_current_liabilities", ["short_term_borrowings", "lease_liabilities_c", "trade_payables", "other_current_fin_liabilities",
                                   "other_current_liabilities", "short_term_provisions", "current_tax_liabilities"], "Current liabilities"),
    ("total_assets", ["ppe", "cwip", "right_of_use", "investment_property", "goodwill", "intangibles", "nc_investments", "nc_loans",
                      "other_nc_fin_assets", "deferred_tax_assets", "other_nc_assets", "total_current_assets"], "Total assets"),
    ("total_equity_and_liabilities", ["total_equity", "minority_interest", "long_term_borrowings", "lease_liabilities_nc",
                                      "other_nc_fin_liabilities", "long_term_provisions", "deferred_tax_liabilities", "other_nc_liabilities",
                                      "total_current_liabilities"], "Equity & liabilities"),
    ("total_income", ["revenue", "other_income"], "Total income"),
    ("total_expenses", ["cost_of_materials", "purchases_stock", "change_in_inventories", "employee_cost", "finance_cost", "depreciation",
                        "other_expenses"], "Total expenses"),
]


def reading_score(ext):
    """How trustworthy a reading is: printed totals that equal the lines read under them, plus core lines present."""
    sc = 0
    data = (ext or {}).get("data") or {}
    for y in (ext or {}).get("years") or []:
        c = data.get(y) or {}
        for tot, parts, _l in SUBTOTALS:
            read_ = [k for k in parts if isinstance(c.get(k), (int, float))]
            tot_v = c.get(tot)
            if isinstance(tot_v, (int, float)) and len(read_) >= 2 and abs(sum(c[k] for k in read_) - tot_v) <= max(0.005 * abs(tot_v), 0.05):
                sc += 2
        sc += sum(1 for k in ("revenue", "pbt", "pat", "total_assets", "total_equity", "total_current_assets", "total_current_liabilities")
                  if isinstance(c.get(k), (int, float)))
    return sc



def check_subtotals(b, out):
    """Each printed total must equal the lines read under it. Lines adding up to MORE than the total means a line was
    misread (unit, digit) or double counted - FAIL. Lines adding up to LESS means some lines were not captured - WARN,
    with the gap. This is what catches a single line misread by 10x or 100x, which the balance-sheet tally cannot."""
    der = b.get("derived") or {}
    over, gaps = [], []
    for y in b["years"]:
        c, dy = b["data"][y], der.get(y) or {}
        for tot, parts, lab in SUBTOTALS:
            if c.get(tot) is None or tot in dy:
                continue
            read = [k for k in parts if c.get(k) is not None]
            if len(read) < 2:
                continue
            sm, t = sum(g(c, k) for k in read), g(c, tot)
            tol = max(0.005 * abs(t), 0.05)
            if tot == "total_assets" and c.get("capital_advances") and abs(sm + g(c, "capital_advances") - t) <= tol:
                sm += g(c, "capital_advances")  # capital advances shown on the face of this balance sheet, not inside other assets
            if sm - t > tol:
                over.append(f"{lab} {y}: lines add to {sm:,.2f} vs total {t:,.2f} Cr")
            elif t - sm > max(0.25 * abs(t), 0.05):  # a quarter of the total missing: a key line was misread (e.g. read as nil)
                over.append(f"{lab} {y}: lines read cover only {sm:,.2f} of {t:,.2f} Cr - a major line is missing or misread")
            elif t - sm > max(0.02 * abs(t), 0.05):
                gaps.append(f"{lab} {y}: {t - sm:,.2f} Cr of {t:,.2f} not in the lines read")
        # P&L: PBT = total income - total expenses + exceptional items + share of JV / associates
        if None not in (c.get("total_income"), c.get("total_expenses"), c.get("pbt")) and not ({"total_income", "pbt"} & set(dy)):
            calc = g(c, "total_income") - g(c, "total_expenses") + g(c, "exceptional_items") + g(c, "share_jv_profit")
            if abs(calc - g(c, "pbt")) > max(0.005 * abs(g(c, "total_income")), 0.05):
                over.append(f"P&L {y}: total income - total expenses + exceptional + JV share = {calc:,.2f} vs PBT {g(c, 'pbt'):,.2f} Cr "
                            "(check the sign of exceptional items and the PBT line)")
    if len(b["years"]) > 1:
        c, p = b["data"][b["years"][0]], b["data"][b["years"][1]]
        if None not in (c.get("cfo"), c.get("cfi"), c.get("cff"), c.get("cash_and_equivalents"), p.get("cash_and_equivalents")):
            net, dcash = g(c, "cfo") + g(c, "cfi") + g(c, "cff"), g(c, "cash_and_equivalents") - g(p, "cash_and_equivalents")
            gap_ = abs(net - dcash)
            if gap_ > max(0.10 * max(g(c, "total_assets"), 1), 0.05):
                over.append(f"cash flow {b['years'][0]}: CFO + CFI + CFF = {net:,.2f} vs change in cash {dcash:,.2f} Cr - a cash-flow line "
                            "was misread (difference above 10% of total assets)")
            elif gap_ > max(0.02 * max(g(c, "total_assets"), 1), 0.05):
                gaps.append(f"cash flow {b['years'][0]}: CFO + CFI + CFF = {net:,.2f} vs change in cash {dcash:,.2f} Cr (overdrafts and "
                            "other bank balances can explain a difference; a large one means a cash-flow line was misread)")
    c0 = b["data"][b["years"][0]]
    if c0.get("capex") is not None and c0.get("cfi") is not None and abs(g(c0, "capex")) > 3 * abs(g(c0, "cfi")) + 0.05 * max(g(c0, "total_assets"), 1):
        gaps.append(f"capex {abs(g(c0, 'capex')):,.2f} Cr is far larger than net investing cash flow {g(c0, 'cfi'):,.2f} Cr - confirm the capex lines")
    _add(out, "Arithmetic", "Lines add up to their printed totals", FAIL if over else PASS,
         "; ".join(over[:6]) if over else "every total checked against the lines read under it")
    if gaps:
        _add(out, "Coverage", "All lines under each total captured", WARN, "; ".join(gaps[:6]))


# ------------------------------------------------------------------ 4 consistency
def check_consistency(b, narr, out):
    fz = b["forensics"]
    grade, rec = fz.get("grade", ""), (narr or {}).get("recommendation", "")
    hi = sum(1 for f in fz["flags"] if f["severity"] == "High" and f.get("status") != "Resolved - not a concern")
    problems = []
    if grade.startswith("NR") and rec.startswith("Approve"):
        problems.append("not rated (key figures missing) but recommendation is Approve")
    if hi >= 2 and rec.startswith("Approve"):
        problems.append(f"{hi} open high-severity flags but recommendation is Approve")
    if grade.startswith(("CI-6", "CI-7")) and rec == "Approve":
        problems.append(f"{grade.split(' ')[0]} with an unconditional Approve")
    _add(out, "Consistency", "Rating, red flags and recommendation agree", FAIL if problems else PASS, "; ".join(problems))


# ------------------------------------------------------------------ 5 AI text tracing
_MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
_DATES = re.compile(rf"\b\d{{1,2}}(?:st|nd|rd|th)?\s+{_MON}(?:,?\s+\d{{4}})?|\b{_MON}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?"
                    r"|\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b")
_NUM = re.compile(r"(?<![A-Za-z0-9])[-+]?(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?")


def _allowed_values(b):
    """Pools of figures an honest sentence may quote, by unit: amounts (crore), percentages, multiples (x), days, bps, counts."""
    P = {"cr": set(), "pct": set(), "x": set(), "days": set(), "bps": set(), "lakh": set(), "count": set(), "any": set()}
    years, d, r = b["years"], b["data"], b["ratios"]
    meta = {k: m for k, m in __import__("core.ratios", fromlist=["RATIO_META"]).RATIO_META.items()}

    def num(v):
        return isinstance(v, (int, float)) and v == v and abs(v) < 1e12

    def amt(v):
        if num(v):
            P["cr"].add(abs(v)); P["lakh"].add(abs(v) * 100)

    def ratio(k, v):
        if not num(v):
            return
        f = meta.get(k, [None] * 5)[4]
        if f == "%":
            P["pct"].add(abs(v * 100)); P["bps"].add(abs(v * 1e4))
        elif f == "days":
            P["days"].add(abs(v))
        elif f == "x":
            P["x"].add(abs(v))
        else:
            P["cr"].add(abs(v))
    for y in years:
        for v in d[y].values():
            amt(v)
        for k, v in r[y].items():
            ratio(k, v)
    if len(years) > 1:
        c, p = d[years[0]], d[years[1]]
        for k in set(c) | set(p):
            a_, b_ = c.get(k), p.get(k)
            if num(a_) and num(b_):
                amt(a_ - b_)
                if b_:
                    P["pct"].add(abs((a_ / b_ - 1) * 100)); P["x"].add(abs(a_ / b_))
        for k in r[years[0]]:
            a_, b_ = r[years[0]].get(k), r[years[1]].get(k)
            if num(a_) and num(b_):
                f = meta.get(k, [None] * 5)[4]
                if f == "%":
                    P["pct"].add(abs((a_ - b_) * 100)); P["bps"].add(abs((a_ - b_) * 1e4))
                elif f == "days":
                    P["days"].add(abs(a_ - b_))
                else:
                    P["x"].add(abs(a_ - b_))
    fz = b["forensics"]
    for v in (fz.get("score"), fz.get("beneish"), fz.get("piotroski"), fz.get("altman_z")):
        if num(v):
            P["any"].add(abs(v)); P["x"].add(abs(v))
    for k, v in (fz.get("score_breakdown") or {}).items():
        if num(v):
            P["any"].add(abs(v))
    P["count"].update({len(fz["flags"]), len(b.get("news") or [])} | {sum(1 for f in fz["flags"] if f["severity"] == s_) for s_ in ("High", "Medium", "Low")})
    for v in (b.get("proposal") or {}).values():
        if num(v):
            P["cr"].add(abs(v)); P["pct"].add(abs(v * 100)); P["any"].add(abs(v))
    return P


_UNIT = re.compile(r"\s*(%|per\s*cent|percent|bps|basis\s+points|x\b|times\b|days?\b|d\b|crore|cr\b|lakh|lac\b)", re.I)
_CUR = re.compile(r"(₹|inr|rs\.?)\s*$", re.I)


def _unit_of(scan, m):
    u = _UNIT.match(scan, m.end())
    if u:
        w = u.group(1).lower()
        if w in ("%",) or w.startswith("per") or w == "percent":
            return "pct"
        if w.startswith("bps") or w.startswith("basis"):
            return "bps"
        if w in ("x", "times"):
            return "x"
        if w.startswith("day") or w == "d":
            return "days"
        if w.startswith("lakh") or w == "lac":
            return "lakh"
        return "cr"
    if _CUR.search(scan[max(0, m.start() - 6):m.start()]):
        return "cr"
    return None


def _traceable(txt_num, allowed, unit=None):
    s = txt_num.replace(",", "").lstrip("+-")
    try:
        x = abs(float(s))
    except ValueError:
        return True
    dec = len(s.split(".")[1]) if "." in s else 0
    if unit is None and dec == 0 and (x <= 12 or 1990 <= x <= 2035):  # small counts and years
        return True
    if unit is None and dec == 0 and x in allowed["count"]:
        return True
    tol = 0.5 * 10 ** (-dec) + 1e-9 + 0.002 * x  # what rounding to the printed decimals allows, nothing more
    pool = allowed[unit] if unit else set().union(*[v for k, v in allowed.items() if k != "count"])
    if unit == "x":
        pool = pool | allowed["any"]
    return any(abs(x - a) <= tol for a in pool)


def _clean_text(t, allowed, removed, where):
    if not isinstance(t, str) or not t.strip():
        return t
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'])", t)
    keep = []
    for sent in parts:
        scan = _DATES.sub(" ", sent)  # calendar dates are not financial figures
        bad = [m.group(0) for m in _NUM.finditer(scan) if not _traceable(m.group(0), allowed, _unit_of(scan, m))]
        if bad:
            removed.append({"where": where, "sentence": sent.strip(), "untraced": ", ".join(bad[:4])})
        else:
            keep.append(sent)
    return " ".join(keep).strip()


def trace_ai_text(b, narr, out):
    """Remove AI sentences whose figures do not trace to the data. Template (rule-based) text is computed from the data."""
    if not narr or narr.get("_source") != "AI":
        _add(out, "AI text", "Figures in AI-written text trace to the data", PASS, "narrative is rule-based (no AI text)")
        return narr, []
    allowed = _allowed_values(b)
    clean = copy.deepcopy(narr)
    removed = []
    for k, v in list(clean.items()):
        if k.startswith("_") or k == "recommendation":
            continue
        if isinstance(v, str):
            clean[k] = _clean_text(v, allowed, removed, k)
        elif isinstance(v, list):
            nv = []
            for i, it in enumerate(v):
                if isinstance(it, str):
                    t = _clean_text(it, allowed, removed, k)
                    if t:
                        nv.append(t)
                elif isinstance(it, dict):
                    it = {kk: (_clean_text(vv, allowed, removed, k) if isinstance(vv, str) else vv) for kk, vv in it.items()}
                    if any(isinstance(vv, str) and vv for vv in it.values()):
                        nv.append(it)
                else:
                    nv.append(it)
            clean[k] = nv
    _add(out, "AI text", "Figures in AI-written text trace to the data", WARN if removed else PASS,
         f"{len(removed)} sentence(s) removed - figures not found in the statements, ratios or scores" if removed else "all figures traced")
    clean["_removed_sentences"] = removed
    return clean, removed


# ------------------------------------------------------------------ 6 web
def check_web(b, out):
    br = b.get("brief") or {}
    n_ok = sum(1 for n in (b.get("news") or []) if n.get("verification"))
    n_bad = len(br.get("unverified_web") or [])
    if n_ok or n_bad:
        _add(out, "Web", "Web news items verified on their source page", WARN if n_bad else PASS, f"{n_ok} verified, {n_bad} rejected and not used")
    we = (b.get("meta") or {}).get("web_esg") or {}
    if we:
        v = we.get("_verification") or {}
        ok = sum(1 for x in v.values() if x.get("status") == "verified")
        bad = len(we.get("_unverified") or {})
        if "_verification" not in we:
            _add(out, "Web", "BRSR / market figures from the web checked on source pages", WARN, "fetched before source checking existed - re-run the web check")
        else:
            _add(out, "Web", "BRSR / market figures from the web checked on source pages", WARN if bad else PASS,
                 f"{ok} verified, {bad} not found on any source page and not used")
    scr = b.get("screening") or {}
    aw = scr.get("ai_web") or {}
    if aw.get("unverified"):
        _add(out, "Web", "Adverse web findings confirmed on source page", WARN,
             f"{len(aw['unverified'])} unconfirmed lead(s) - shown on the Fraud screening page for manual checking, not used as findings")
    if br.get("credit_rating_unverified"):
        _add(out, "Web", "External credit rating confirmed on source page", WARN, "rating suggested by web search could not be confirmed - not used")


def _indep(c):
    """Second, separate recomputation of the remaining key ratios (all years)."""
    z = lambda k: c.get(k) or 0
    debt = z("long_term_borrowings") + z("short_term_borrowings") + z("lease_liabilities_nc") + z("lease_liabilities_c")
    ebit = z("pbt") - z("exceptional_items") - z("share_jv_profit") + z("finance_cost")
    eq, rev, ta = z("total_equity"), z("revenue"), z("total_assets")
    tnw = eq - z("goodwill") - z("intangibles")
    out = {}
    if tnw:
        out["tol_tnw"] = (ta - eq - z("minority_interest")) / tnw
    if eq + debt:
        out["roce"] = ebit / (eq + debt)
    if ta:
        out["asset_turnover"] = rev / ta
    if abs(z("finance_cost")) >= max(0.005, 0.0001 * abs(rev)):
        out["icr"] = ebit / z("finance_cost")
    if z("total_current_liabilities"):
        out["current_ratio"] = z("total_current_assets") / z("total_current_liabilities")
    return out


def check_rules(b, narr, out):
    years, d, r = b["years"], b["data"], b["ratios"]
    bad = []
    for y in years:
        for k, v in _indep(d[y]).items():
            if r[y].get(k) is not None and not _close(r[y][k], v, rel=0.001, absol=0.0005):
                bad.append(f"{y} {k}: engine {r[y][k]:.4f} vs check {v:.4f}")
    _add(out, "Recomputation", "TOL/TNW, ROCE, asset turnover, interest cover and current ratio recomputed for every year",
         FAIL if bad else PASS, "; ".join(bad))
    c0, r0 = d[years[0]], r[years[0]]
    nm = []
    if abs(g(c0, "finance_cost")) < max(0.005, 0.0001 * abs(g(c0, "revenue"))) and r0.get("icr") is not None:
        nm.append("interest cover shown on nil interest")
    ebitda = g(c0, "pbt") - g(c0, "exceptional_items") - g(c0, "share_jv_profit") + g(c0, "finance_cost") + g(c0, "depreciation") - g(c0, "other_income")
    if c0.get("pbt") is not None and ebitda <= 0 and any(r0.get(k) is not None for k in ("debt_ebitda", "netdebt_ebitda", "cfo_ebitda")):
        nm.append("EBITDA multiples shown with negative EBITDA")
    if c0.get("pbt") is not None and g(c0, "pbt") <= 0 and r0.get("etr") is not None:
        nm.append("tax rate shown for a loss year")
    _add(out, "Recomputation", "Not-meaningful ratios are suppressed (shown as n.a. / n.m.)", FAIL if nm else PASS, "; ".join(nm))
    fz = b["forensics"]
    grade, score = str(fz.get("grade") or ""), fz.get("score")
    if score is not None and not grade.startswith("NR"):
        from .forensics import GRADES
        exp = next(gn for th, gn, _ in GRADES if score >= th)
        _add(out, "Consistency", "Grade matches the score band", PASS if grade.startswith(exp) else FAIL,
             f"score {score:.1f} -> {exp}; report shows {grade.split(' ')[0]}")
    hi = sum(1 for f in fz["flags"] if f["severity"] == "High" and f.get("status") != "Resolved - not a concern")
    rec = (narr or {}).get("recommendation", "")
    if score is not None and not grade.startswith("NR"):
        must = score < 55 or hi >= 2
        _add(out, "Consistency", "Recommendation follows the policy rule (score < 55 or 2+ high flags -> Refer or stricter)",
             FAIL if (must and rec.startswith("Approve")) else PASS, f"score {score:.0f}, {hi} open high flag(s), recommendation '{rec}'")
    no_ev = [f["title"] for f in fz["flags"] if not str(f.get("evidence") or "").strip()]
    _add(out, "Consistency", "Every red flag shows the figures or source behind it", WARN if no_ev else PASS, "; ".join(no_ev[:5]))
    att = (b.get("screening") or {}).get("attest") or {}
    from .watchlist import REQUIRED_SOURCES
    nc = [s_[1] for s_ in REQUIRED_SOURCES if ((att.get(s_[0]) or {}).get("status") or "Not checked") == "Not checked"]
    _add(out, "Coverage", "Mandatory regulatory checks recorded by the officer (CFR, CRILC, wilful defaulters ...)",
         WARN if nc else PASS, f"{len(nc)} of {len(REQUIRED_SOURCES)} not yet recorded" if nc else "all recorded")


def enforce_policy(b, narr, out):
    """The policy rule wins over AI wording: score < 55, 2+ open high flags or 'not rated' never leave the memo saying Approve."""
    if not narr:
        return narr
    fz = b["forensics"]
    grade, score = str(fz.get("grade") or ""), fz.get("score") or 0
    hi = sum(1 for f in fz["flags"] if f["severity"] == "High" and f.get("status") != "Resolved - not a concern")
    rec = narr.get("recommendation") or ""
    if rec.startswith("Approve") and (grade.startswith("NR") or score < 55 or hi >= 2):
        narr = dict(narr)
        narr["recommendation"] = "Refer / further diligence"
        narr["recommendation_rationale"] = (f"Changed from '{rec}' by the policy rule: score {score:.0f}/100, {hi} open high-severity flag(s)"
                                            + (", not rated" if grade.startswith("NR") else "") + ". " + str(narr.get("recommendation_rationale") or ""))
        _add(out, "Consistency", "AI recommendation overridden by the policy rule", WARN, f"'{rec}' -> 'Refer / further diligence'")
    return narr


def check_dual(b, out):
    meta = b.get("meta") or {}
    dual = meta.get("dual") or {}
    if not dual.get("rows"):
        _add(out, "Reading", "Figures confirmed by a second, independent reading", WARN,
             "second reading not run (" + ("it failed - see the activity log" if meta.get("dual_enabled") else
                                           "switched off or no OpenRouter key") + ") - figures rest on one reading; check Spread review against the PDF")
        return
    sm = dual["summary"]
    core = {"revenue", "pat", "pbt", "total_equity", "total_assets", "total_current_assets", "total_current_liabilities", "finance_cost",
            "long_term_borrowings", "short_term_borrowings", "trade_receivables", "inventories", "cfo"}
    disp_core = [r for r in dual["rows"] if r["status"].startswith("Disputed") and r["key"] in core]
    if sm.get("unit_mismatch"):
        res, det = FAIL, sm["text"]
    elif disp_core:
        res, det = FAIL, sm["text"] + " - disputed key lines: " + ", ".join(f"{r['label']} {r['year']}" for r in disp_core[:6])
    elif sm["disputed"]:
        res, det = WARN, sm["text"]
    else:
        res, det = PASS, sm["text"]
    _add(out, "Reading", "Figures confirmed by a second, independent reading", res, det)


def check_projection(b, out):
    try:
        from . import credit_tools as CT
        rows, a = CT.projections(b, CT.proposal(b))
    except Exception as e:  # noqa: BLE001
        _add(out, "Projection", "Projection inputs are known", WARN, f"projection could not be built: {e}")
        return
    import datetime as _dt
    m_ = re.search(r"(20\d\d)", str(b["years"][0]))
    if m_ and a.get("status") != "NOT COMPUTED":
        lag = _dt.date.today().year - int(m_.group(1)) - (1 if _dt.date.today().month < 4 else 0)
        if lag >= 1:
            _add(out, "Projection", "Projection starts from a current base year", WARN,
                 f"Y+1 is the year after {b['years'][0]} - {lag} projected year(s) have already passed; compare them with actual results "
                 "(Proposal › plan vs actual) or obtain newer statements")
    if a.get("status") == "NOT COMPUTED":
        _add(out, "Projection", "Projection inputs are known", WARN, f"projection not computed - {a.get('reason')}")
    elif a.get("approximations"):
        _add(out, "Projection", "Projection inputs are known", WARN,
             "uses approximations / unreviewed defaults: " + ", ".join(a["approximations"]) + " - see the assumption register")
    else:
        _add(out, "Projection", "Projection inputs are known", PASS, "every input from the spread or entered by the officer")


def check_unit_currency(b, out):
    """The unit and the currency must be STATED in the document. A missing unit statement is never assumed to be crore,
    and statements in another currency are never treated as rupees."""
    meta = b.get("meta") or {}
    cur = (meta.get("currency") or {})
    if cur.get("code") and cur["code"] != "INR":
        _add(out, "Reading", "Statements are in Indian rupees", FAIL,
             f"the statements appear to be in {cur['code']} ({cur.get('evidence', '')}) - every ratio, norm, limit and report here assumes INR; "
             "do not use this analysis until the figures are converted and the currency confirmed")
    us = meta.get("unit_status")
    if us == "NOT STATED":
        _add(out, "Reading", "Unit of the statements read from the document", FAIL,
             "no 'Amounts in ...' statement was found - the figures were provisionally taken as crore; set the unit on Spread review")
    elif us:
        _add(out, "Reading", "Unit of the statements read from the document", PASS, f"read from: \"{str(us)[:80]}\"")


def check_read_quality(b, out):
    """Unknown is never zero: report every cell that was a dash, unreadable or repaired, and every optional line whose
    absence is not credible (ratios.NIL_POLICY) - those lines block the figures built on them until the officer confirms them."""
    from . import ratios as R_
    prov = (b.get("meta") or {}).get("provenance") or {}
    odd = []
    for y, pk in prov.items():
        for k, lst in (pk or {}).items():
            for e in lst or []:
                kd = str(e.get("kind") or "")
                if kd.startswith(("UNRESOLVED", "unreadable", "ocr-repaired", "not applicable")):
                    odd.append(f"{schema.LABELS.get(k, k)} {y}: printed '{e.get('token')}' -> {kd}")
    _add(out, "Reading", "Every cell read as printed (no dash, unreadable or repaired figure left unconfirmed)", WARN if odd else PASS,
         ("confirm on Spread review: " + "; ".join(odd[:8]) + (f" and {len(odd) - 8} more" if len(odd) > 8 else "")) if odd else "")
    unc = []
    for y in b["years"]:
        for k in sorted(R_.unconfirmed_nil(b["data"][y])):
            unc.append(f"{schema.LABELS.get(k, k)} {y} (nil only if {R_.NIL_POLICY[k][0]})")
    if str(b.get("statement_type") or "").startswith("consol"):
        c0 = b["data"][b["years"][0]]
        unc += [f"{schema.LABELS.get(k, k)} (consolidated statements - confirm nil)" for k in ("minority_interest", "share_jv_profit") if c0.get(k) is None]
    _add(out, "Coverage", "Lines treated as nil are credibly nil", WARN if unc else PASS,
         ("not read and not credibly nil - figures built on them are withheld until you enter the figure (or 0): " + "; ".join(unc[:8]))
         if unc else "every optional line left blank is consistent with the rest of the statements")


def check_debt_presence(b, out):
    """Borrowings are allowed to be nil, so a missed borrowings line would silently give D/E 0. Interest cost exposes it."""
    y0 = b["years"][0]
    c = b["data"][y0]
    fc, rev = c.get("finance_cost"), c.get("revenue")
    keys = ("long_term_borrowings", "short_term_borrowings", "current_maturities_ltd", "lease_liabilities_nc", "lease_liabilities_c")
    debt = sum((c.get(k) or 0) for k in keys)
    if fc is None:
        _add(out, "Coverage", "Borrowings consistent with finance cost", WARN, "finance cost not read - cannot confirm that all borrowings were captured")
        return
    material = fc > max(0.01, 0.002 * abs(rev or 0))
    if material and debt < 0.01:
        _add(out, "Coverage", "Borrowings consistent with finance cost", WARN,
             f"finance cost ₹{fc:,.2f} Cr but no borrowings read - check the spread; if borrowings were missed, D/E, TOL/TNW and DSCR are overstated in the borrower's favour")
    elif material and fc / debt > 0.30:
        _add(out, "Coverage", "Borrowings consistent with finance cost", WARN,
             f"finance cost ₹{fc:,.2f} Cr is {fc / debt:.0%} of year-end borrowings ₹{debt:,.2f} Cr - borrowings may be incomplete or repaid before year-end")
    else:
        _add(out, "Coverage", "Borrowings consistent with finance cost", PASS, "")


def check_forensic_coverage(b, out):
    fz = b.get("forensics") or {}
    na = fz.get("not_assessed") or []
    _add(out, "Coverage", "Every forensic test had the figures it needs", WARN if na else PASS,
         ("not assessed (inputs not read): " + "; ".join(f"{t['test']} [{', '.join(t['missing'][:3])}]" for t in na[:8])
          + (f" and {len(na) - 8} more" if len(na) > 8 else "")) if na else "all rule-based tests ran on read figures")
    models = fz.get("models") or {}
    bad = [f"{m}: {v['status']}" + (f" ({', '.join(v['missing'][:4])})" if v.get("missing") else "") for m, v in models.items() if v["status"] != "CALCULATED"]
    if models:
        _add(out, "Coverage", "Statistical models (Beneish, Piotroski, Altman) computed on complete inputs", WARN if bad else PASS, "; ".join(bad))


# metrics a credit decision rests on; blank in the latest year -> BLOCKED
DECISION_METRICS = {"current_ratio": "Current ratio", "tol_tnw": "TOL / TNW", "icr": "Interest cover", "dscr": "DSCR",
                    "ebitda_margin": "EBITDA margin", "roce": "ROCE", "debt_ebitda": "Debt / EBITDA"}


def integrity(b, narr, out):
    """One authoritative status for the case: READY / READY_WITH_WARNINGS / BLOCKED."""
    from . import credit_tools as CT
    y0 = b["years"][0]
    core = ("revenue", "pbt", "pat", "total_equity", "total_assets", "total_current_assets", "total_current_liabilities", "cfo")
    missing = CT.core_missing(b, core) if hasattr(CT, "core_missing") else [k for k in core if b["data"][y0].get(k) in (None, "")]
    r0 = b["ratios"][y0]
    from . import ratios as _R
    prev = b["data"][b["years"][1]] if len(b["years"]) > 1 else None
    blocked = [f"{lab} ({', '.join(m)})" for k, lab in DECISION_METRICS.items()
               if r0.get(k) is None and k in _R.RATIO_META
               for m in [_R.missing_inputs(_R.RATIO_META[k][3], b["data"][y0], prev)] if m]  # not n.m. ratios - only blanks from missing inputs
    failed = [c_["check"] for c_ in out if c_["result"] == FAIL]
    warns = [c_["check"] for c_ in out if c_["result"] == WARN]
    if failed or missing:
        st_ = "BLOCKED"
    elif warns or blocked:
        st_ = "READY_WITH_WARNINGS"
    else:
        st_ = "READY"
    rec = (narr or {}).get("recommendation") or ""
    res = {"status": st_, "missing_required_fields": missing, "blocked_metrics": blocked, "failed_checks": failed,
           "warnings": len(warns), "final_recommendation_allowed": st_ != "BLOCKED", "recommendation": rec,
           "forensic_not_assessed": [t["test"] for t in (b.get("forensics") or {}).get("not_assessed") or []]}
    res["detail"] = "; ".join(x for x in [("required lines not read: " + ", ".join(missing)) if missing else "",
                                          ("failed checks: " + "; ".join(failed[:5])) if failed else "",
                                          ("metrics not computed: " + ", ".join(blocked)) if blocked else "",
                                          (f"{len(res['forensic_not_assessed'])} forensic test(s) not assessed") if res["forensic_not_assessed"] else "",
                                          f"{len(warns)} warning(s)" if warns else ""] if x) or "all checks passed"
    return res


def run(b, narr):
    out = []
    check_figures(b, out)
    check_subtotals(b, out)
    check_dual(b, out)
    narr2, _ = trace_ai_text(b, narr, out)
    narr2 = enforce_policy(b, narr2, out)
    check_consistency(b, narr2, out)
    check_rules(b, narr2, out)
    check_projection(b, out)
    check_forensic_coverage(b, out)
    check_unit_currency(b, out)
    check_read_quality(b, out)
    check_debt_presence(b, out)
    check_web(b, out)
    narr2 = fail_closed(b, narr2, out)
    b["integrity"] = integrity(b, narr2, out)
    return narr2, out


_APPROVE_TXT = re.compile(r"\b(recommend(ed|s|ation)?\b[^.]{0,60}\b(approv|sanction)|approval\s+is\s+recommended|"
                          r"(may|can|could|should)\s+be\s+(approved|sanctioned)|we\s+recommend\s+approv)", re.I)


def fail_closed(b, narr, out):
    """One authoritative recommendation. Any FAILED check -> 'Not ready for decision'. AI sentences that recommend
    approval when the authoritative recommendation is not an approval are removed (the memo must not contradict itself)."""
    if not narr:
        return narr
    narr = dict(narr)
    fails = [c_["check"] for c_ in out if c_["result"] == FAIL]
    if fails:
        prev = narr.get("recommendation") or ""
        narr["recommendation"] = "Not ready for decision - analysis incomplete"
        narr["recommendation_rationale"] = ("No credit recommendation can be given until these checks pass: " + "; ".join(fails[:6]) +
                                            ". Correct the figures (Spread review) or obtain the missing documents, then regenerate.")
        _add(out, "Consistency", "Recommendation withheld because checks failed", WARN, f"'{prev}' -> 'Not ready for decision'")
    rec = narr.get("recommendation") or ""
    if rec.startswith("Approve"):  # approval also needs the evidence an approval rests on
        blockers = [c_["check"] for c_ in out
                    if c_["result"] == WARN and c_["check"] in ("Audit opinion read from the auditor's report itself", "Latest statements are recent",
                                                              "Mandatory regulatory checks recorded by the officer (CFR, CRILC, wilful defaulters ...)")]
        if blockers:
            narr["recommendation"] = "Refer / further diligence"
            narr["recommendation_rationale"] = ("An approval cannot be recommended until: " + "; ".join(blockers) +
                                                ". " + str(narr.get("recommendation_rationale") or ""))
            _add(out, "Consistency", "Approval requires a verified audit opinion, recent statements and recorded regulatory checks", WARN,
                 f"'{rec}' -> 'Refer / further diligence' (" + "; ".join(blockers) + ")")
            rec = narr["recommendation"]
    if not rec.startswith("Approve"):
        removed = []
        for k, v in list(narr.items()):
            if k.startswith("_") or k in ("recommendation", "recommendation_rationale") or not isinstance(v, str):
                continue
            parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\"'])", v)
            keep = [p_ for p_ in parts if not _APPROVE_TXT.search(p_)]
            if len(keep) != len(parts):
                removed += [p_ for p_ in parts if _APPROVE_TXT.search(p_)]
                narr[k] = " ".join(keep)
        if removed:
            narr.setdefault("_removed_sentences", []).extend({"where": "recommendation conflict", "sentence": r_, "untraced": "-"} for r_ in removed)
        _add(out, "Consistency", "No passage contradicts the recommendation", WARN if removed else PASS,
             f"{len(removed)} AI sentence(s) recommending approval removed" if removed else f"memo consistently says '{rec}'")
    # the log must show the FINAL recommendation, not the draft one the earlier checks saw
    for c_ in out:
        if c_["check"].startswith(("Recommendation follows the policy rule", "Rating, red flags and recommendation agree")):
            c_["detail"] = re.sub(r"recommendation '[^']*'", f"recommendation '{rec}'", c_["detail"]) if "recommendation '" in c_["detail"] \
                else (c_["detail"] + ("; " if c_["detail"] else "") + f"final recommendation '{rec}'")
    return narr


def summary(checks):
    n = {PASS: 0, WARN: 0, FAIL: 0}
    for c in checks:
        n[c["result"]] = n.get(c["result"], 0) + 1
    return n
