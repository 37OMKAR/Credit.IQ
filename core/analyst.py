"""Deterministic 'analyst engine': writes professional credit-appraisal commentary from the numbers.

Every sentence is generated from computed figures, so the report is detailed and consistent even
without an AI key. When an AI model is available its narrative is added on top, never instead."""
from . import ratios as R
from . import schema

g = schema.g


# ------------------------------------------------------------------ formatting helpers
def cr(v, d=2):
    if v is None:
        return "n.a."
    return f"₹{v:,.{d}f} Cr" if v >= 0 else f"(₹{abs(v):,.{d}f} Cr)"


def pct(v, d=1):
    return "n.a." if v is None else f"{v * 100:,.{d}f}%"


def x(v, d=2):
    return "n.a." if v is None else f"{v:,.{d}f}x"


def chg(a, b):
    if a is None or b in (None, 0):
        return None
    return a / b - 1


def moved(new, old, unit="cr"):
    """'rose 28.8% to ₹146.20 Cr from ₹113.48 Cr'"""
    c = chg(new, old)
    if c is None:
        return f"stood at {cr(new)}"
    verb = "rose" if c > 0.005 else ("declined" if c < -0.005 else "was broadly flat")
    if verb == "was broadly flat":
        return f"was broadly flat at {cr(new)}"
    return f"{verb} {abs(c) * 100:.1f}% to {cr(new)} from {cr(old)}"


def bps(new, old):
    if new is None or old is None:
        return None
    return (new - old) * 10000


def _status_word(key, v):
    st = R.status(key, v)
    return {"good": "within", "watch": "close to", "bad": "outside"}.get(st, "")


# ------------------------------------------------------------------ analysis blocks
def horizontal_table(b, keys):
    """Rows: label, values by year (oldest->latest), YoY change of latest."""
    years = list(reversed(b["years"]))
    d = b["data"]
    lbl = {**schema.LABELS, **R.DERIVED_LABELS}
    rows = []
    for k in keys:
        vals = [d[y].get(k) for y in years]
        if all(v in (None, 0) for v in vals):
            continue
        yoy = chg(vals[-1], vals[-2]) if len(vals) > 1 else None
        rows.append([lbl.get(k, k)] + vals + [yoy])
    return years, rows


def vertical_pl(b):
    """Common-size P&L: each line as % of revenue."""
    years = list(reversed(b["years"]))
    d = b["data"]
    keys = [("revenue", "Revenue from operations"), ("cogs", "Cost of goods / services"), ("employee_cost", "Employee cost"),
            ("other_expenses", "Other expenses"), ("ebitda", "EBITDA"), ("depreciation", "Depreciation"),
            ("finance_cost", "Finance cost"), ("other_income", "Other income"), ("pbt", "Profit before tax"),
            ("tax_expense", "Tax"), ("pat", "Profit after tax")]
    rows = []
    for k, lab in keys:
        r = [lab]
        for y in years:
            rev = g(d[y], "revenue")
            r.append(g(d[y], k) / rev if rev else None)
        if any(v not in (None, 0) for v in r[1:]):
            rows.append(r)
    return years, rows


def vertical_bs(b):
    """Common-size balance sheet: each group as % of total assets."""
    years = list(reversed(b["years"]))
    d = b["data"]
    groups = [
        ("Net fixed assets (PPE + RoU + intangibles)", ["ppe", "right_of_use", "intangibles", "goodwill"]),
        ("Capital work-in-progress & capital advances", ["cwip", "capital_advances"]),
        ("Non-current investments", ["nc_investments"]),
        ("Loans & advances given", ["nc_loans", "current_loans"]),
        ("Inventories", ["inventories"]),
        ("Trade receivables", ["trade_receivables"]),
        ("Cash, bank & current investments", ["cash_and_equivalents", "other_bank_balances", "current_investments"]),
        ("Other assets", ["other_nc_fin_assets", "other_nc_assets", "deferred_tax_assets", "other_current_fin_assets",
                          "current_tax_assets", "other_current_assets", "investment_property"]),
        ("Net worth", ["total_equity"]),
        ("Long-term borrowings & leases", ["long_term_borrowings", "lease_liabilities_nc"]),
        ("Short-term borrowings", ["short_term_borrowings", "lease_liabilities_c"]),
        ("Trade payables", ["trade_payables"]),
        ("Other liabilities & provisions", ["other_nc_fin_liabilities", "long_term_provisions", "deferred_tax_liabilities",
                                            "other_nc_liabilities", "other_current_fin_liabilities", "other_current_liabilities",
                                            "short_term_provisions", "current_tax_liabilities", "minority_interest"]),
    ]
    rows = []
    for lab, ks in groups:
        r = [lab]
        for y in years:
            ta = g(d[y], "total_assets")
            r.append(sum(g(d[y], k) for k in ks) / ta if ta else None)
        if any(v not in (None, 0) for v in r[1:]):
            rows.append(r)
    return years, rows


def income_commentary(b):
    years, d, r = b["years"], b["data"], b["ratios"]
    y0 = years[0]
    c, p = d[y0], (d[years[1]] if len(years) > 1 else None)
    out = []
    if p:
        s = (f"Revenue from operations {moved(g(c, 'revenue'), g(p, 'revenue'))} in {y0}. "
             f"Operating profit (EBITDA) {moved(g(c, 'ebitda'), g(p, 'ebitda'))}, with the EBITDA margin moving from "
             f"{pct(r[years[1]].get('ebitda_margin'))} to {pct(r[y0].get('ebitda_margin'))}")
        dm = bps(r[y0].get("ebitda_margin"), r[years[1]].get("ebitda_margin"))
        s += f" ({dm:+,.0f} bps)." if dm is not None else "."
        rg, eg = r[y0].get("rev_growth"), r[y0].get("ebitda_growth")
        if rg is not None and eg is not None and rg < 0:
            if (g(c, "ebitda") or 0) <= 0 < (g(p, "ebitda") or 0):
                s += " The fall in revenue pushed the business into an operating loss - costs did not come down in line with sales."
            elif eg < rg - 0.05:
                s += " Operating profit fell faster than revenue, showing limited flexibility to cut costs."
            else:
                s += " Costs were reduced broadly in line with the lower revenue."
        elif rg is not None and eg is not None:
            if eg < rg - 0.05:
                s += " Profit growth has lagged revenue growth, indicating that cost increases absorbed part of the top-line expansion."
            elif eg > rg + 0.05:
                s += " Profit has grown faster than revenue, reflecting operating leverage or improved cost control."
            else:
                s += " Profit growth has broadly kept pace with revenue."
        out.append(s)
        if len(years) >= 3 and g(d[years[-1]], "revenue") > 0:
            n = len(years) - 1
            cagr = (g(c, "revenue") / g(d[years[-1]], "revenue")) ** (1 / n) - 1
            out.append(f"Over {n} years revenue compounded at {pct(cagr)} a year.")
    else:
        out.append(f"Revenue from operations stood at {cr(g(c, 'revenue'))} in {y0} with an EBITDA margin of {pct(r[y0].get('ebitda_margin'))}.")
    rev = g(c, "revenue")
    if rev:
        parts = []
        for k, lab in [("cogs", "cost of goods and services"), ("employee_cost", "employee cost"), ("other_expenses", "other expenses")]:
            if g(c, k):
                parts.append(f"{lab} {pct(g(c, k) / rev)}")
        if parts:
            out.append("Cost structure (as a share of revenue): " + ", ".join(parts) + ". "
                       + ("The business is cost-of-sales intensive, so margins are sensitive to input prices and pass-through ability."
                          if g(c, "cogs") / rev > 0.7 else "Operating costs are spread across materials, people and overheads."))
    oi = r[y0].get("other_inc_pbt")
    fc = g(c, "finance_cost")
    s = (f"Finance cost was {cr(fc)} and depreciation {cr(g(c, 'depreciation'))}, leaving profit before tax of {cr(g(c, 'pbt'))} "
         f"and profit after tax of {cr(g(c, 'pat'))} (PAT margin {pct(r[y0].get('pat_margin'))}).")
    if oi is not None:
        s += (f" Other income contributed {pct(oi)} of PBT" +
              (", a material dependence on non-operating income that should be examined for recurrence." if oi > 0.3
               else ", which is not material to the earnings profile." if oi < 0.15 else "."))
    etr = r[y0].get("etr")
    if etr is not None:
        s += f" The effective tax rate was {pct(etr)}" + (" - unusually low and worth reconciling to the tax computation." if etr < 0.12 and g(c, "pbt") > 0 else ".")
    out.append(s)
    return out


def balance_commentary(b):
    years, d, r = b["years"], b["data"], b["ratios"]
    y0 = years[0]
    c, p = d[y0], (d[years[1]] if len(years) > 1 else None)
    out = []
    s = f"Total assets {moved(g(c, 'total_assets'), g(p, 'total_assets'))}." if p else f"Total assets stood at {cr(g(c, 'total_assets'))}."
    ta = g(c, "total_assets")
    if ta:
        items = []
        for k in ["trade_receivables", "inventories", "ppe", "cash_and_equivalents", "nc_investments", "cwip", "current_tax_assets", "nc_loans", "current_loans"]:
            if g(c, k) > 0:
                items.append((g(c, k) / ta, schema.LABELS[k]))
        items.sort(reverse=True)
        if items:
            s += " The largest assets are " + ", ".join(f"{lab.lower()} ({pct(v)})" for v, lab in items[:3]) + " of total assets."
            if items[0][1] == "Trade Receivables" and items[0][0] > 0.4:
                s += " The balance sheet is dominated by receivables, so credit quality of the debtor book is central to this assessment."
    out.append(s)
    nw = g(c, "total_equity")
    s = f"Net worth {moved(nw, g(p, 'total_equity'))}." if p else f"Net worth stood at {cr(nw)}."
    if p:
        accrual = g(c, "pat")
        d_oe = g(c, "other_equity") - g(p, "other_equity")
        if accrual > 0:
            retained = d_oe / accrual
            if retained < 0.7:
                s += (f" Reserves increased by {cr(d_oe)} against PAT of {cr(accrual)} - about {pct(1 - retained, 0)} of profit "
                      "did not stay in the business (dividends, OCI losses or other adjustments).")
            else:
                s += f" Reserves increased by {cr(d_oe)}, retaining most of the year's profit of {cr(accrual)}."
    td = g(c, "total_debt")
    if td > 0:
        st_share = (g(c, "short_term_borrowings") + g(c, "lease_liabilities_c")) / td
        s += (f" Total borrowings of {cr(td)} are {pct(st_share, 0)} short-term; debt-to-equity is {x(r[y0].get('de'))} "
              f"and TOL/TNW {x(r[y0].get('tol_tnw'))}.")
    else:
        s += (f" The company carries no funded borrowings; its outside liabilities (TOL/TNW {x(r[y0].get('tol_tnw'))}) "
              "consist of trade payables, provisions and other operating liabilities.")
    out.append(s)
    return out


def cashflow_commentary(b):
    years, d, r = b["years"], b["data"], b["ratios"]
    y0 = years[0]
    c = d[y0]
    cfo, pat, ebitda = c.get("cfo"), g(c, "pat"), g(c, "ebitda")
    if cfo is None:
        return ["The cash-flow statement could not be read from the documents; cash conversion has not been assessed."]
    out = []
    s = f"Net cash from operating activities was {cr(cfo)} against PAT of {cr(pat)} and EBITDA of {cr(ebitda)} (CFO/EBITDA {x(r[y0].get('cfo_ebitda'))})."
    if (ebitda or 0) <= 0 and cfo is not None:
        s += (" EBITDA was negative, so the positive operating cash flow came from releasing working capital (for example collecting "
              "receivables) rather than from earnings - this is not repeatable." if cfo > 0 else
              " Both EBITDA and operating cash flow were negative - the business is consuming cash.")
    elif r[y0].get("cfo_ebitda") is not None:
        v = r[y0]["cfo_ebitda"]
        s += (" Earnings are well backed by cash." if v >= 0.8 else
              " A significant part of operating profit was absorbed by working capital." if v >= 0.3 else
              " Very little of the reported profit converted to cash - a key quality-of-earnings concern.")
    out.append(s)
    capex = abs(g(c, "capex"))
    fcf = cfo - capex
    s = f"Capital expenditure was {cr(capex)}, giving free cash flow of {cr(fcf)}."
    if c.get("cfi") is not None:
        s += f" Net investing outflow was {cr(-g(c, 'cfi')) if g(c, 'cfi') < 0 else cr(g(c, 'cfi'))}"
        other_inv = -g(c, "cfi") - capex
        if other_inv > 0.25 * max(abs(cfo), 1):
            s += f", of which {cr(other_inv)} went to investments, deposits or loans other than fixed assets - the destination should be confirmed."
        else:
            s += "."
    if c.get("cff") is not None:
        s += f" Financing activities {'brought in' if g(c, 'cff') > 0 else 'used'} {cr(abs(g(c, 'cff')))}."
    out.append(s)
    if len(years) > 1:
        cum_cfo = sum(g(d[y], "cfo") for y in years)
        cum_pat = sum(g(d[y], "pat") for y in years)
        if cum_pat > 0:
            out.append(f"Across the {len(years)} years reviewed, cumulative CFO of {cr(cum_cfo)} compares with cumulative PAT of {cr(cum_pat)} "
                       f"(conversion {pct(cum_cfo / cum_pat, 0)}).")
    return out


def sources_uses(b):
    """Classic fund-flow statement between the two latest balance sheets."""
    years, d = b["years"], b["data"]
    if len(years) < 2:
        return None
    c, p = d[years[0]], d[years[1]]
    liab = [k for k, _, sec, _ in schema.BALANCE_SHEET if sec in ("Equity", "Non-current Liabilities", "Current Liabilities")
            and not k.startswith("total") and k not in ("current_maturities_ltd", "total_equity")]
    assets = [k for k, _, sec, _ in schema.BALANCE_SHEET if sec in ("Non-current Assets", "Current Assets") and not k.startswith("total")]
    src, use = [], []
    for k in liab:
        dv = g(c, k) - g(p, k)
        if abs(dv) > 0.005:
            (src if dv > 0 else use).append((schema.LABELS[k], abs(dv), "increase" if dv > 0 else "decrease"))
    for k in assets:
        dv = g(c, k) - g(p, k)
        if abs(dv) > 0.005:
            (use if dv > 0 else src).append((schema.LABELS[k], abs(dv), "increase" if dv > 0 else "decrease"))
    src.sort(key=lambda t: -t[1])
    use.sort(key=lambda t: -t[1])
    return {"from": years[1], "to": years[0], "sources": src, "uses": use,
            "total_sources": sum(t[1] for t in src), "total_uses": sum(t[1] for t in use)}


def sources_uses_commentary(su):
    if not su:
        return []
    s = su["sources"][:3]
    u = su["uses"][:3]
    txt = (f"Between {su['from']} and {su['to']} the main sources of funds were " + "; ".join(f"{a.lower()} ({cr(v)})" for a, v, _ in s)
           + ". These were deployed mainly into " + "; ".join(f"{a.lower()} ({cr(v)})" for a, v, _ in u) + ".")
    # only money put INTO assets that earn nothing can be diversion; repaying liabilities or booking a loss cannot
    risky = [a for a, v, kind in su["uses"] if kind == "increase"
             and any(w in a.lower() for w in ("loan", "investment", "capital advance", "advance", "other current assets", "other non-current assets"))
             and "liabilit" not in a.lower() and "equity" not in a.lower() and v > 0.1 * max(su["total_uses"], 1e-9)]
    if risky:
        txt += (" A notable part of the funds went into " + ", ".join(r.lower() for r in risky) +
                " - items that do not generate operating income and are a common route for diversion; the end-use should be documented.")
    return [txt]


def working_capital(b):
    years, d, r = b["years"], b["data"], b["ratios"]
    y0 = years[0]
    c = d[y0]
    tca, tcl, stb = g(c, "total_current_assets"), g(c, "total_current_liabilities"), g(c, "short_term_borrowings")
    ocl = tcl - stb
    margin = 0.25 * tca
    mpbf = 0.75 * tca - ocl
    table = [
        ["Total current assets (A)", cr(tca)],
        ["Other current liabilities excl. bank borrowings (B)", cr(ocl)],
        ["Working-capital gap (A - B)", cr(tca - ocl)],
        ["Minimum margin: 25% of current assets (C)", cr(margin)],
        ["MPBF - Method II (A x 75% - B)", cr(mpbf)],
        ["Existing short-term bank borrowings", cr(stb)],
        ["Headroom / (excess) over MPBF", cr(mpbf - stb)],
        ["Net working capital (actual)", cr(tca - tcl)],
    ]
    dd, idd, cdd = r[y0].get("debtor_days"), r[y0].get("inventory_days"), r[y0].get("creditor_days")
    txt = [(f"The operating cycle comprises debtor days of {_d(dd)}, inventory days of {_d(idd)} and creditor days of {_d(cdd)}, "
            f"giving a cash conversion cycle of {_d(r[y0].get('ccc'))}. Current ratio is {x(r[y0].get('current_ratio'))} against the "
            f"bank benchmark of 1.33x and net working capital is {cr(tca - tcl)}.")]
    if len(years) > 1:
        dd1 = r[years[1]].get("debtor_days")
        if dd and dd1:
            txt.append(f"Debtor days moved from {_d(dd1)} to {_d(dd)}" + (", a material stretch in collections." if dd - dd1 > 20 else "."))
    txt.append(f"On the Tandon Committee Method II, the maximum permissible bank finance works out to {cr(mpbf)} against existing "
               f"short-term bank borrowings of {cr(stb)}" + (f", leaving headroom of {cr(mpbf - stb)}." if mpbf - stb >= 0
                                                             else f", an excess of {cr(stb - mpbf)} over MPBF that requires justification."))
    return txt, table


def _d(v):
    return "n.a." if v is None else f"{v:,.0f} days"


def stress_test(b):
    """Two simple shocks on the latest year: EBITDA -20% and interest rate +200 bp."""
    y0 = b["years"][0]
    c = b["data"][y0]
    ebitda, fc, dep, td = g(c, "ebitda"), g(c, "finance_cost"), g(c, "depreciation"), g(c, "total_debt")
    oi, cm = g(c, "other_income"), g(c, "current_maturities_ltd")
    tax_rate = 0.2517

    tiny = max(0.005, 0.001 * abs(g(c, "revenue") or 0))  # nil / negligible interest or debt service

    def metrics(e, f):
        ebit = e + oi - dep
        icr = ebit / f if f >= tiny else None
        pat = (ebit - f) * (1 - tax_rate)
        dscr = (pat + dep + f) / (f + cm) if (f + cm) >= tiny else None
        de_ebitda = td / e if e > 0 else None
        return icr, dscr, de_ebitda

    base = metrics(ebitda, fc)
    s1 = metrics(ebitda * 0.8, fc)
    s2 = metrics(ebitda, fc + 0.02 * td)
    s3 = metrics(ebitda * 0.8, fc + 0.02 * td)
    rows = [["Base case", *base], ["EBITDA -20%", *s1], ["Interest +200 bp", *s2], ["Combined", *s3]]
    return [[r_[0]] + ["n.a." if v is None else f"{v:,.2f}x" for v in r_[1:]] for r_ in rows], s3


def risk_matrix(b):
    y0 = b["years"][0]
    r = b["ratios"][y0]
    fz = b["forensics"]
    flags = fz["flags"]

    def lvl(*statuses):
        sts = [s for s in statuses if s]
        if not sts:
            return "Not assessed"
        if "bad" in sts:
            return "High"
        if "watch" in sts:
            return "Medium"
        return "Low"

    def flag_lvl(cats):
        fs = [f for f in flags if f["category"] in cats]
        if any(f["severity"] == "High" for f in fs):
            return "High"
        if fs:
            return "Medium"
        return "Low"

    news = b.get("news") or []
    neg_hi = [n for n in news if n.get("severity") == "High" and n.get("sentiment") == "Negative"]
    rows = [
        ["Financial risk - leverage", lvl(R.status("tol_tnw", r.get("tol_tnw")), R.status("de", r.get("de")), R.status("debt_ebitda", r.get("debt_ebitda"))),
         f"TOL/TNW {x(r.get('tol_tnw'))}, D/E {x(r.get('de'))}, Debt/EBITDA {x(r.get('debt_ebitda'))}"],
        ["Financial risk - debt servicing", lvl(R.status("icr", r.get("icr")), R.status("dscr", r.get("dscr"))),
         f"ICR {x(r.get('icr'))}, DSCR {x(r.get('dscr'))}"],
        ["Liquidity & working capital", lvl(R.status("current_ratio", r.get("current_ratio")), R.status("debtor_days", r.get("debtor_days"))),
         f"Current ratio {x(r.get('current_ratio'))}, debtor days {_d(r.get('debtor_days'))}"],
        ["Profitability & earnings quality", lvl(R.status("ebitda_margin", r.get("ebitda_margin")), R.status("cfo_ebitda", r.get("cfo_ebitda")), R.status("roce", r.get("roce"))),
         f"EBITDA margin {pct(r.get('ebitda_margin'))}, CFO/EBITDA {x(r.get('cfo_ebitda'))}, ROCE {pct(r.get('roce'))}"],
        ["Accounting & fund-diversion risk", flag_lvl({"Fund diversion", "Revenue quality", "Earnings quality", "Hidden items", "Hidden liabilities", "Asset quality"}),
         f"{sum(1 for f in flags if f['category'] in ('Fund diversion', 'Revenue quality', 'Earnings quality', 'Hidden items', 'Hidden liabilities', 'Asset quality'))} forensic flag(s); Beneish M {fz.get('beneish') if fz.get('beneish') is not None else 'n.a.'}"],
        ["Audit, governance & related parties", flag_lvl({"Audit", "Governance", "Related parties", "Notes review (AI)", "Notes review (keyword scan)"}),
         f"Auditor opinion: {((b.get('notes') or {}).get('auditor_opinion') or 'n.a.').title()}"],
        ["Market & reputation", "High" if neg_hi else ("Low" if news else "Not assessed"),
         f"{len(news)} news items, {len(neg_hi)} serious adverse" if news else "News not scanned"],
        ["ESG & climate transition", "Medium" if (b.get("brsr") or {}).get("esg_red_flags") else ("Low" if b.get("brsr") else "Not assessed"),
         "BRSR reviewed" if b.get("brsr") else "BRSR not provided"],
    ]
    return rows


def covenants(b):
    y0 = b["years"][0]
    r = b["ratios"][y0]
    out = []
    for key, name, limit, op in [("tol_tnw", "TOL/TNW", 3.0, "max"), ("de", "Debt/Equity", 2.0, "max"),
                                  ("debt_ebitda", "Total Debt/EBITDA", 3.5, "max"), ("dscr", "DSCR", 1.25, "min"),
                                  ("icr", "Interest coverage (EBIT/interest)", 2.0, "min"), ("current_ratio", "Current ratio", 1.20, "min")]:
        v = r.get(key)
        if v is None:
            out.append([name, f"{'Not to exceed' if op == 'max' else 'Not below'} {limit:.2f}x", "n.a.", "Set once data available"])
            continue
        if key in ("icr", "dscr") and g(b["data"][y0], "total_debt") < 0.01:
            out.append([name, f"Not below {limit:.2f}x", "n.a.", "Not applicable - no borrowings"])
            continue
        ok = v <= limit if op == "max" else v >= limit
        out.append([name, f"{'Not to exceed' if op == 'max' else 'Not below'} {limit:.2f}x", f"{v:,.2f}x",
                    "Complied" if ok else "Currently breached - require cure plan / tighter terms"])
    return out


def strengths_concerns(b):
    y0 = b["years"][0]
    r = b["ratios"][y0]
    s, c = [], []
    for key in ["current_ratio", "de", "tol_tnw", "debt_ebitda", "icr", "dscr", "ebitda_margin", "roce", "cfo_ebitda", "debtor_days", "altman_z", "rev_growth"]:
        v = r.get(key)
        st = R.status(key, v)
        if st is None:
            continue
        name = R.RATIO_META[key][1]
        good = R.RATIO_META[key][6]
        txt = f"{name} of {R.fmt(key, v)} (benchmark {'≥' if R.RATIO_META[key][5] == 'high' else '≤'} {R.fmt(key, good)})"
        (s if st == "good" else c if st == "bad" else []).append(txt)
    for f in b["forensics"]["flags"]:
        if f["severity"] == "High":
            c.append(f"{f['title']} - {f['evidence'][:140]}")
    return s[:8], c[:10]


def rating_rationale(b, narrative):
    fz = b["forensics"]
    bd = fz.get("score_breakdown") or {}
    nh = sum(1 for f in fz["flags"] if f["severity"] == "High")
    nm = sum(1 for f in fz["flags"] if f["severity"] == "Medium")
    return (f"The internal score of {fz['score']:.0f}/100 places the borrower in grade {fz['grade']}. The financial-strength component "
            f"scores {bd.get('financial_strength', 'n.a.')} out of 70, based on leverage, coverage, liquidity, profitability, cash conversion and "
            f"distress indicators measured against bank benchmarks. The red-flag component deducts {bd.get('red_flag_penalty', 0)} points for "
            f"{nh} high-severity and {nm} medium-severity observations from the forensic, audit and market reviews. "
            f"Recommendation: {narrative.get('recommendation', 'n.a.')}.")


def data_validation(b):
    """V7-style validation: tie-outs and data coverage, with source pages."""
    years, d = b["years"], b["data"]
    rows = []
    for y in years:
        ta, tel = g(d[y], "total_assets"), g(d[y], "total_equity_and_liabilities")
        ok = ta > 0 and abs(ta - tel) <= 0.01 * ta
        rows.append([f"Balance sheet tie-out {y}", "Passed" if ok else "Check", f"Assets {cr(ta)} vs equity & liabilities {cr(tel)}"])
        pbt, pat, tax = g(d[y], "pbt"), g(d[y], "pat"), g(d[y], "tax_expense")
        if pbt or pat:
            ok2 = abs(pbt - tax - pat) <= max(0.02 * abs(pbt), 0.05)
            rows.append([f"P&L tie-out {y}", "Passed" if ok2 else "Check", f"PBT {cr(pbt)} - tax {cr(tax)} = PAT {cr(pat)}"])
        filled = sum(v is not None for k, v in d[y].items() if k in schema.KEYS)
        rows.append([f"Line items captured {y}", "Info", f"{filled} of {len(schema.KEYS)} standard items"])
    meta = b.get("meta") or {}
    loc = meta.get("located") or {}
    for src, l in loc.items():
        rows.append([f"Source pages - {src}", "Info",
                     f"Balance sheet p.{', '.join(map(str, l.get('balance_sheet', []))) or '-'}; P&L p.{', '.join(map(str, l.get('profit_loss', []))) or '-'}; "
                     f"cash flow p.{', '.join(map(str, l.get('cash_flow', []))) or '-'}; auditor p.{', '.join(map(str, l.get('auditor', [])[:4])) or '-'}"])
    for n in (meta.get("extraction_notes") or [])[:10]:
        rows.append(["Extraction note", "Verify", str(n)])
    return rows


# ------------------------------------------------------------------ sector benchmarking
import csv as _csv
import os as _os

BENCH_FILE = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "sector_benchmarks.csv")
BENCH_KEYS = [("ebitda_margin", "EBITDA margin", "high"), ("current_ratio", "Current ratio", "high"), ("de", "Debt / Equity", "low"),
              ("tol_tnw", "TOL / TNW", "low"), ("debtor_days", "Debtor days", "low"), ("inventory_days", "Inventory days", "low"),
              ("roce", "ROCE", "high")]


def load_benchmarks():
    out = {}
    try:
        with open(BENCH_FILE, newline="", encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                if "illustrative" in (row.get("note") or "").lower():
                    continue  # never compare against placeholder norms - admin must approve them first
                out[row["sector"]] = {k: float(row[k]) for k, *_ in BENCH_KEYS if row.get(k) not in (None, "")}
    except FileNotFoundError:
        pass
    return out


def sector_comparison(b, sector):
    bm = load_benchmarks().get(sector)
    if not bm:
        return None
    y0 = b["years"][0]
    r = b["ratios"][y0]
    rows = []
    for k, lab, better in BENCH_KEYS:
        v, s = r.get(k), bm.get(k)
        if v is None or s is None:
            continue
        fmt = "%" if k in ("ebitda_margin", "roce") else ("days" if "days" in k else "x")
        f = (lambda z: f"{z * 100:.1f}%") if fmt == "%" else ((lambda z: f"{z:,.0f} d") if fmt == "days" else (lambda z: f"{z:,.2f}x"))
        if s == 0:
            pos = "-"
        else:
            diff = (v - s) / abs(s)
            good = diff >= -0.1 if better == "high" else diff <= 0.1
            pos = "Better than / in line with sector" if good else "Weaker than sector"
        rows.append([lab, f(v), f(s), pos])
    return rows


# ------------------------------------------------------------------ line-item anomaly detection
def anomalies(b, threshold=0.5, materiality=0.02):
    """Line items whose year-on-year movement is large AND material (>2% of total assets or revenue)."""
    years = b["years"]
    if len(years) < 2:
        return []
    c, p = b["data"][years[0]], b["data"][years[1]]
    base = max(g(c, "total_assets"), g(c, "revenue"), 1e-9)
    out = []
    for k, lab, sec, _ in schema.BALANCE_SHEET + schema.PROFIT_LOSS:
        if k.startswith("total") or k in ("current_maturities_ltd",):
            continue
        a, b0 = c.get(k), p.get(k)
        if a is None or b0 is None:
            continue
        delta = a - b0
        if abs(delta) < materiality * base:
            continue
        rel = delta / abs(b0) if b0 else None
        if rel is None or abs(rel) >= threshold:
            out.append([lab, cr(b0), cr(a), "new item" if rel is None else f"{rel * 100:+.0f}%", f"{abs(delta) / base * 100:.1f}% of {'assets' if sec != 'Income' and sec != 'Expenses' and sec != 'Profit' else 'revenue'}"])
    out.sort(key=lambda r_: -float(r_[4].split("%")[0]))
    return out[:15]


# ------------------------------------------------------------------ next-year projection
def projection(b):
    """Base-case next-year view: revenue at last growth (capped 25%), margins held, working-capital days held."""
    years, d, r = b["years"], b["data"], b["ratios"]
    y0 = years[0]
    c = d[y0]
    gr = r[y0].get("rev_growth")
    gr = 0.08 if gr is None else max(min(gr, 0.25), -0.20)
    rev = g(c, "revenue") * (1 + gr)
    em = r[y0].get("ebitda_margin") or 0
    ebitda = rev * em
    dep, fc = g(c, "depreciation"), g(c, "finance_cost")
    pat = (ebitda + g(c, "other_income") - dep - fc) * (1 - 0.2517)
    wc_now = g(c, "inventories") + g(c, "trade_receivables") - g(c, "trade_payables")
    wc_next = wc_now * (1 + gr)
    cfo = pat + dep - (wc_next - wc_now)
    debt_service = fc + g(c, "current_maturities_ltd")
    liquid = g(c, "liquid_funds")
    rows = [["Revenue growth assumed", pct(gr)], ["Revenue", cr(rev)], ["EBITDA (margin held)", cr(ebitda)], ["PAT", cr(pat)],
            ["Working-capital build", cr(wc_next - wc_now)], ["Operating cash flow", cr(cfo)], ["Debt service due (interest + maturities)", cr(debt_service)],
            ["Opening liquid funds", cr(liquid)], ["Liquidity after debt service", cr(liquid + cfo - debt_service)]]
    note = ("Base case shows a cash shortfall - operating cash flow and liquid funds do not cover debt service."
            if liquid + cfo - debt_service < 0 else
            "Base case: operating cash flow and liquid funds cover the debt service due in the next year.")
    return rows, note
