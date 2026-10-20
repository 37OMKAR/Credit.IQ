"""Data for the Dashboard page: the key-figures table and the list of items open before a credit decision.

Pure functions (no Streamlit) so they can be tested. Nothing here defaults a missing figure to zero: a value that was not
read is reported as not read, and a ratio that is not meaningful says why.
"""
from . import ratios as R

# (group, label, key, source) - source "d" = statement line (Rs crore), "r" = ratio
METRICS = [
    ("Scale", "Revenue from operations", "revenue", "d"),
    ("Scale", "EBITDA", "ebitda", "d"),
    ("Scale", "Profit after tax", "pat", "d"),
    ("Scale", "Cash from operations", "cfo", "d"),
    ("Scale", "Net worth", "total_equity", "d"),
    ("Scale", "Total debt", "total_debt", "d"),
    ("Profitability", "EBITDA margin", "ebitda_margin", "r"),
    ("Profitability", "ROCE", "roce", "r"),
    ("Liquidity", "Current ratio", "current_ratio", "r"),
    ("Leverage", "TOL / TNW", "tol_tnw", "r"),
    ("Leverage", "Debt / equity", "de", "r"),
    ("Leverage", "Debt / EBITDA", "debt_ebitda", "r"),
    ("Coverage", "Interest cover (EBIT / interest)", "icr", "r"),
    ("Working capital", "Debtor days", "debtor_days", "r"),
    ("Cash quality", "CFO / EBITDA", "cfo_ebitda", "r"),
]
DERIVED_INPUTS = {"ebitda": "PBT, finance cost or depreciation", "total_debt": "borrowings"}
ASSESS = {"good": "Within norm", "watch": "Watch", "bad": "Outside norm"}


def _amount(v, dp=1):
    return None if v is None else f"{v:,.{dp}f}"


def _dp(values):
    """One number format per row, chosen from the row's largest value (so 35.0 and 120.0 line up)."""
    big = max((abs(v) for v in values if v is not None), default=0)
    return 2 if big < 10 else 1 if big < 10000 else 0


def na_reason(b, key, y, src):
    """Why a figure is blank: an input that was not read, or a ratio that is not meaningful."""
    years, d = b["years"], b["data"]
    i = years.index(y)
    cur, prev = d[y], (d[years[i + 1]] if i + 1 < len(years) else None)
    if src == "d":
        return f"not read ({DERIVED_INPUTS[key]} missing)" if key in DERIVED_INPUTS else "not read from the statements"
    meta = R.RATIO_META.get(key)
    miss = R.missing_inputs(meta[3], cur, prev) if meta else []
    if miss:
        return "input not read: " + ", ".join(m.replace("_", " ") for m in miss[:3])
    rev = abs(cur.get("revenue") or 0)
    if key in ("icr", "ebitda_int") and abs(cur.get("finance_cost") or 0) < max(0.005, 0.0001 * rev):
        return "not meaningful: nil or negligible interest"
    if key in ("debt_ebitda", "cfo_ebitda") and (cur.get("ebitda") is not None and cur["ebitda"] <= 0):
        return "not meaningful: EBITDA is negative"
    if key == "de" and (cur.get("total_equity") or 0) <= 0:
        return "not meaningful: net worth is negative"
    return "not computed"


def metric_rows(b):
    """One row per key figure: values oldest -> latest, change on the year, norm and assessment of the latest year."""
    years = b["years"]
    cols = list(reversed(years))
    rows = []
    for group, label, key, src in METRICS:
        vals = []
        dp = _dp([b["data"][y].get(key) for y in cols]) if src == "d" else 0
        for y in cols:
            v = b["data"][y].get(key) if src == "d" else b["ratios"][y].get(key)
            if v is None:
                vals.append({"text": "n.a.", "raw": None, "note": na_reason(b, key, y, src)})
            else:
                vals.append({"text": _amount(v, dp) if src == "d" else R.fmt(key, v), "raw": v, "note": ""})
        change = ""
        if len(cols) > 1 and vals[-1]["raw"] is not None and vals[-2]["raw"] is not None:
            a, p = vals[-1]["raw"], vals[-2]["raw"]
            unit = "cr" if src == "d" else R.RATIO_META[key][4]
            if unit == "cr":
                change = f"{(a - p) / abs(p):+.1%}" if p else ""
            elif unit == "%":
                change = f"{(a - p) * 100:+.1f} pp"
            elif unit == "days":
                change = f"{a - p:+.0f} d"
            else:
                change = f"{a - p:+.2f}x"
        norm, assess = "", ""
        if src == "r":
            meta = R.RATIO_META[key]
            if meta[5] in ("high", "low") and meta[6] is not None:
                norm = ("≥ " if meta[5] == "high" else "≤ ") + R.fmt(key, meta[6])
            assess = ASSESS.get(R.status(key, vals[-1]["raw"]), "")
        rows.append({"group": group, "label": label, "key": key, "src": src, "values": vals, "change": change,
                     "norm": norm, "assess": assess})
    return cols, rows


# where each kind of check is fixed
AREA_PAGE = {"Arithmetic": "spread", "Plausibility": "spread", "Reading": "spread", "Coverage": "spread", "Recomputation": "ratios",
             "Consistency": "reports", "AI text": "reports", "Web": "market", "Projection": "proposal"}
CHECK_PAGE = {"Mandatory regulatory checks recorded by the officer (CFR, CRILC, wilful defaulters ...)": "fraud",
              "Audit opinion read from the auditor's report itself": "desk", "Latest statements are recent": "desk",
              "Large balance-sheet movements reconciled": "forensic"}
SKIP = {"Core statement lines read"}  # reported once, as the required-lines item


def open_items(b, checks, narr=None):
    """Everything that stands between this case and a credit decision, most serious first.
    level: 'block' (no decision possible), 'warn' (resolve or explain before deciding), 'todo' (officer input missing)."""
    items = []
    ig = b.get("integrity") or {}
    if ig.get("missing_required_fields"):
        items.append({"level": "block", "page": "spread", "title": "Required lines not read",
                      "detail": ", ".join(ig["missing_required_fields"]) + " - enter them from the statements"})
    for c in checks or []:
        if c["result"] == "PASS" or c["check"] in SKIP or c["area"] == "Integrity":
            continue
        if c["check"].startswith(("Recommendation withheld", "AI recommendation overridden", "Approval requires", "No passage contradicts")):
            continue  # consequences of other items, not separate work
        items.append({"level": "block" if c["result"] == "FAIL" else "warn",
                      "page": CHECK_PAGE.get(c["check"], AREA_PAGE.get(c["area"], "reports")),
                      "title": c["check"], "detail": c["detail"]})
    fz = b.get("forensics") or {}
    undisposed = [f for f in fz.get("flags") or [] if f["severity"] in ("High", "Medium") and (f.get("status") or "Open") == "Open"]
    if undisposed:
        nh = sum(1 for f in undisposed if f["severity"] == "High")
        items.append({"level": "warn" if nh else "todo", "page": "forensic", "title": "Red flags without your disposition",
                      "detail": f"{len(undisposed)} open ({nh} high) - record a disposition and remark for each"})
    prop = b.get("proposal") or {}
    if not (prop.get("amount") or prop.get("tl_amount") or prop.get("cc_amount")):
        items.append({"level": "todo", "page": "proposal", "title": "Facility not entered",
                      "detail": "enter the proposed facilities so repayment capacity, security and pricing can be assessed"})
    order = {"block": 0, "warn": 1, "todo": 2}
    return sorted(items, key=lambda x: order[x["level"]])


def check_counts(checks):
    n = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for c in checks or []:
        if c["area"] != "Integrity":
            n[c["result"]] = n.get(c["result"], 0) + 1
    return n


SHORT = {"Figures confirmed by a second, independent reading": "Figures not confirmed by a second reading",
         "Mandatory regulatory checks recorded by the officer (CFR, CRILC, wilful defaulters ...)": "Regulatory checks not recorded (CFR, CRILC, wilful defaulters)",
         "Projection inputs are known": "Projection uses unreviewed assumptions",
         "Every forensic test had the figures it needs": "Forensic tests not assessed",
         "Statistical models (Beneish, Piotroski, Altman) computed on complete inputs": "Statistical models incomplete",
         "Large balance-sheet movements reconciled": "Large balance-sheet movements to reconcile",
         "Audit opinion read from the auditor's report itself": "Audit opinion not verified",
         "Latest statements are recent": "Statements are old",
         "Borrowings consistent with finance cost": "Borrowings may be incomplete",
         "Size plausible for the unit read (rupees / thousands / lakhs / crore)": "Unit looks wrong (rupees / lakhs / crore)",
         "No extreme year-on-year jump (possible lakh/crore or wrong-year misread)": "Extreme year-on-year jump",
         "Key ratios recomputed independently agree with the ratio engine": "Ratio recomputation disagrees",
         "Web news items verified on their source page": "Web items rejected",
         "Every red flag shows the figures or source behind it": "Red flags without evidence"}


def short_title(check):
    return SHORT.get(check, check)


PAGE_SHORT = {"spread": "Spread", "forensic": "Forensic", "fraud": "Screening", "proposal": "Proposal", "reports": "Reports",
              "ratios": "Ratios", "market": "Market", "desk": "Desk"}
