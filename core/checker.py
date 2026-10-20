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
    for y in years:
        c = d[y]
        ta, tel = g(c, "total_assets"), g(c, "total_equity_and_liabilities")
        if ta and tel:
            ok = abs(ta - tel) <= max(0.01 * ta, 0.01)
            _add(out, "Arithmetic", f"Balance sheet tallies - {y}", PASS if ok else FAIL, f"assets {ta:,.2f} vs equity & liabilities {tel:,.2f} Cr")
        else:
            _add(out, "Arithmetic", f"Balance sheet tallies - {y}", WARN, "total assets or total equity & liabilities not read")
        pbt, tax, pat = c.get("pbt"), c.get("tax_expense"), c.get("pat")
        if None not in (pbt, tax, pat):
            ok = abs((pbt - tax) - pat) <= max(0.02 * abs(pat), 0.02)
            _add(out, "Arithmetic", f"PBT - tax = PAT - {y}", PASS if ok else FAIL, f"{pbt:,.2f} - {tax:,.2f} vs PAT {pat:,.2f}")
        neg = [schema.LABELS.get(k, k) for k in ("revenue", "inventories", "trade_receivables", "cash_and_equivalents", "total_assets", "ppe")
               if (c.get(k) or 0) < 0]
        _add(out, "Arithmetic", f"No negative assets / revenue - {y}", FAIL if neg else PASS, ", ".join(neg) or "")

    # independent recomputation (written separately from core/ratios.py on purpose)
    y0 = years[0]
    c, rr = d[y0], r[y0]
    rev, tca, tcl = c.get("revenue"), c.get("total_current_assets"), c.get("total_current_liabilities")
    eq = c.get("total_equity")
    debt = sum((c.get(k) or 0) for k in ("long_term_borrowings", "short_term_borrowings", "lease_liabilities_nc", "lease_liabilities_c"))
    pbt = c.get("pbt")
    ebitda = None if pbt is None else pbt - (c.get("exceptional_items") or 0) + (c.get("finance_cost") or 0) + (c.get("depreciation") or 0) - (c.get("other_income") or 0)
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
    core = [k for k in ("revenue", "pat", "total_equity", "total_current_assets", "total_current_liabilities", "total_assets") if c.get(k) is None]
    _add(out, "Coverage", "Core statement lines read", FAIL if core else PASS, ("missing: " + ", ".join(core)) if core else "")


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
    ebit = z("pbt") - z("exceptional_items") + z("finance_cost")
    eq, rev, ta = z("total_equity"), z("revenue"), z("total_assets")
    tnw = eq - z("goodwill") - z("intangibles")
    out = {}
    if tnw:
        out["tol_tnw"] = (ta - eq - z("minority_interest")) / tnw
    if eq + debt:
        out["roce"] = ebit / (eq + debt)
    if ta:
        out["asset_turnover"] = rev / ta
    if abs(z("finance_cost")) >= max(0.005, 0.001 * abs(rev)):
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
    if abs(g(c0, "finance_cost")) < max(0.005, 0.001 * abs(g(c0, "revenue"))) and r0.get("icr") is not None:
        nm.append("interest cover shown on nil interest")
    ebitda = g(c0, "pbt") - g(c0, "exceptional_items") + g(c0, "finance_cost") + g(c0, "depreciation") - g(c0, "other_income")
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


def run(b, narr):
    out = []
    check_figures(b, out)
    check_dual(b, out)
    narr2, _ = trace_ai_text(b, narr, out)
    narr2 = enforce_policy(b, narr2, out)
    check_consistency(b, narr2, out)
    check_rules(b, narr2, out)
    check_web(b, out)
    return narr2, out


def summary(checks):
    n = {PASS: 0, WARN: 0, FAIL: 0}
    for c in checks:
        n[c["result"]] = n.get(c["result"], 0) + 1
    return n
