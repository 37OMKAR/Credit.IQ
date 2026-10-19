"""Credit-structuring and regulatory toolkit (Indian banking practice).

Everything here is deterministic and works without AI:
  * proposal defaults           - facility structure the officer can edit (term loan, CC, non-fund, security)
  * amortisation                 - repayment schedule with moratorium (quarterly instalments, yearly roll-up)
  * projections                  - multi-year P&L / cash-flow projection with DSCR, ICR, TOL/TNW per year
  * scenarios / breakeven        - base / upside / downside and the EBITDA fall the loan can absorb
  * wc_methods / drawing_power   - Tandon I & II, Nayak (turnover) method, drawing power from stock statement
  * security_cover               - primary + collateral cover, FACR, LTV
  * risk_pricing                 - PD / LGD / EAD / expected loss, hurdle rate, RAROC at proposed price
  * dupont / earnings_quality    - ROE decomposition, accruals, cash conversion
  * rbi_ews                      - RBI Early Warning Signals checklist (Master Directions on Fraud Risk Management, 2024)
  * regulatory                   - exposure norms (Large Exposures Framework), SMA / NPA status
  * plan_vs_actual               - last projections vs actuals (annual review)

Assumptions that are bank-specific (PD table, haircuts, cost of funds, capital ratio) are ILLUSTRATIVE
defaults and are shown in the outputs so they can be replaced with the bank's own policy figures.
"""
from .schema import g

TAX = 0.2517

# Illustrative one-year PD by internal grade (replace with the bank's validated master scale)
PD_DEFAULT = {"CI-1": 0.0025, "CI-2": 0.0060, "CI-3": 0.0120, "CI-4": 0.0250, "CI-5": 0.0500, "CI-6": 0.1000, "CI-7": 0.2000}
import csv as _csv
import os as _os
PD_FILE = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "pd_scale.csv")


def load_pd():
    """Bank's PD master scale from data/pd_scale.csv (editable in Admin > Bank parameters); defaults if absent."""
    out = {}
    try:
        with open(PD_FILE, newline="", encoding="utf-8") as f:
            for r in _csv.DictReader(f):
                if "illustrative" in (r.get("note") or "").lower():
                    continue
                out[r["grade"].strip()] = float(r["pd"])
    except (FileNotFoundError, KeyError, ValueError):
        pass
    return out


def pd_configured():
    return len(load_pd()) >= 7


PD_BY_GRADE = load_pd()

PROPOSAL_DEFAULTS = {
    "purpose": "",
    "tl_amount": 0.0, "tl_tenor_years": 5, "tl_moratorium_months": 6, "tl_rate": 0.0975, "tl_capex": True,
    "cc_amount": 0.0, "cc_rate": 0.0950,
    "nfb_amount": 0.0,                       # BG / LC (non-fund based)
    "existing_ltd_years": 0,                 # remaining tenor of existing term debt (0 = implied from current maturities)
    "proj_years": 5,
    "growth": None,                          # None -> derived from history
    "margin_shift": 0.0,                     # change in EBITDA margin (absolute, e.g. -0.01)
    "rate_shift": 0.0,                       # change in interest rate (absolute)
    "collateral_value": 0.0,                 # market value of collateral (₹ Cr)
    "collateral_type": "",
    "primary_security": "",
    "guarantee": "",
    "stock_margin": 0.25, "debtor_margin": 0.40, "eligible_debtor_share": 0.85,
    "base_rate": 0.0900,                     # EBLR / MCLR used as pricing anchor
    "cost_of_funds": 0.0650, "opex_ratio": 0.0075, "capital_ratio": 0.115, "risk_weight": 1.00,
    "target_roe": 0.15, "collateral_haircut": 0.40, "ccf_nfb": 0.50,
    "tier1_capital": 0.0, "existing_exposure": 0.0, "group_exposure": 0.0,
    "dpd": 0, "stock_stmt_delay": False, "cheque_returns": 0, "adhoc_overdrawn": False,
    "unrecorded_charges": False, "cash_withdrawals_high": False, "non_routing": False,
    "takeover_amount": 0.0,                  # existing debt being taken over / repaid from this loan
    "prev_proj_revenue": 0.0, "prev_proj_pat": 0.0, "prev_grade": "",
}


def proposal(bundle):
    p = dict(PROPOSAL_DEFAULTS)
    p.update({k: v for k, v in (bundle.get("proposal") or {}).items() if v is not None})
    # legacy proposal (facility text + amount) -> treat amount as term loan if no split given
    if not (p["tl_amount"] or p["cc_amount"] or p["nfb_amount"]) and p.get("amount"):
        fac = (p.get("facility") or "").lower()
        if "cc" in fac or "cash credit" in fac or "working" in fac:
            if "term" in fac or "tl" in fac:
                p["tl_amount"], p["cc_amount"] = p["amount"] * 0.6, p["amount"] * 0.4
            else:
                p["cc_amount"] = p["amount"]
        else:
            p["tl_amount"] = p["amount"]
    for k_ in ("primary_security", "guarantee", "collateral_type"):
        if not (p.get(k_) or "").strip():
            p[k_] = "Not yet specified (to be entered in the Proposal page)"
    return p


def total_proposed(p):
    return (p.get("tl_amount") or 0) + (p.get("cc_amount") or 0) + (p.get("nfb_amount") or 0)


# ------------------------------------------------------------------ amortisation
def amortisation(amount, tenor_years, moratorium_months, rate):
    """Equal quarterly principal instalments after the moratorium; interest serviced throughout.
    Returns (yearly rows, instalment, n_instalments)."""
    if not amount or amount <= 0 or not tenor_years:
        return [], 0.0, 0
    q_total = int(round(tenor_years * 4))
    q_mor = int(round(moratorium_months / 3))
    n = max(q_total - q_mor, 1)
    inst = amount / n
    bal = amount
    years = {}
    for q in range(1, q_total + 1):
        yr = (q - 1) // 4 + 1
        r_ = years.setdefault(yr, {"year": yr, "opening": bal, "interest": 0.0, "principal": 0.0, "closing": bal})
        intr = bal * rate / 4
        prin = inst if q > q_mor else 0.0
        prin = min(prin, bal)
        r_["interest"] += intr
        r_["principal"] += prin
        bal -= prin
        r_["closing"] = bal
    return list(years.values()), inst, n


# ------------------------------------------------------------------ projections
def _hist_growth(b):
    years, d = b["years"], b["data"]
    if len(years) >= 2:
        a, c = g(d[years[-1]], "revenue"), g(d[years[0]], "revenue")
        n = len(years) - 1
        if a > 0 and c > 0:
            cagr = (c / a) ** (1 / n) - 1
            return max(min(cagr, 0.20), -0.10)
    return 0.08


def projections(b, p, growth=None, margin_shift=None, rate_shift=None, ebitda_haircut=0.0):
    """Year-by-year projection. Existing term debt runs off evenly; the new term loan follows its schedule;
    working-capital debt is held at the proposed CC limit (or existing ST borrowings)."""
    y0 = b["years"][0]
    c = b["data"][y0]
    gr = growth if growth is not None else (p.get("growth") if p.get("growth") is not None else _hist_growth(b))
    ms = margin_shift if margin_shift is not None else (p.get("margin_shift") or 0.0)
    rs = rate_shift if rate_shift is not None else (p.get("rate_shift") or 0.0)
    rev0 = g(c, "revenue")
    ebitda0 = g(c, "ebitda")
    margin = (ebitda0 / rev0 if rev0 else 0.0) + ms
    dep0 = g(c, "depreciation")
    oi = g(c, "other_income")
    fc0 = g(c, "finance_cost")
    ltd = g(c, "long_term_borrowings") + g(c, "current_maturities_ltd")
    stb = g(c, "short_term_borrowings") - g(c, "current_maturities_ltd")
    td0 = max(g(c, "total_debt"), 1e-9)
    hist_rate = fc0 / td0 if td0 > 1e-6 else 0.10
    hist_rate = min(max(hist_rate, 0.06), 0.16) + rs
    cm0 = g(c, "current_maturities_ltd")
    if p.get("existing_ltd_years"):
        n_ex = max(int(p["existing_ltd_years"]), 1)
    elif cm0 > 1e-6 and ltd > 0:
        n_ex = max(min(int(round(ltd / cm0)), 15), 1)   # implied remaining tenor from current maturities
    else:
        n_ex = 4
    ex_rep = ltd / n_ex
    sched, inst, _ = amortisation(p.get("tl_amount"), p.get("tl_tenor_years"), p.get("tl_moratorium_months") or 0, (p.get("tl_rate") or 0.1) + rs)
    wc_debt = max(stb, 0.0) + (p.get("cc_amount") or 0.0)
    wc_rate = (p.get("cc_rate") or hist_rate) + rs
    new_dep = (p.get("tl_amount") or 0) / 10 if p.get("tl_capex", True) else 0.0
    nw = g(c, "total_equity")
    tol0 = g(c, "tol")
    intang = g(c, "goodwill") + g(c, "intangibles")
    rows = []
    ex_bal = ltd
    rev = rev0
    for yr in range(1, int(p.get("proj_years") or 5) + 1):
        rev = rev * (1 + gr)
        ebitda = rev * margin * (1 - ebitda_haircut)
        dep = dep0 + new_dep
        ex_open = ex_bal
        ex_prin = min(ex_rep, ex_bal)
        ex_int = (ex_open - ex_prin / 2) * hist_rate
        ex_bal -= ex_prin
        tl = sched[yr - 1] if yr - 1 < len(sched) else {"interest": 0.0, "principal": 0.0, "closing": 0.0}
        wc_int = wc_debt * wc_rate
        interest = ex_int + tl["interest"] + wc_int
        pbt = ebitda + oi - dep - interest
        tax = max(pbt, 0) * TAX
        pat = pbt - tax
        cash_acc = pat + dep
        term_int = ex_int + tl["interest"]
        term_prin = ex_prin + tl["principal"]
        dscr = (pat + dep + term_int) / (term_int + term_prin) if (term_int + term_prin) > 1e-9 else None
        icr = (ebitda + oi - dep) / interest if interest > 1e-9 else None
        nw = nw + pat
        debt_close = ex_bal + tl["closing"] + wc_debt
        tol = max(tol0 - ltd - max(stb, 0) + debt_close, 0)
        rows.append({"year": f"Y+{yr}", "revenue": rev, "ebitda": ebitda, "margin": margin * (1 - ebitda_haircut), "depreciation": dep,
                     "interest": interest, "term_interest": term_int, "pbt": pbt, "tax": tax, "pat": pat, "cash_accruals": cash_acc,
                     "term_principal": term_prin, "new_tl_principal": tl["principal"], "surplus": cash_acc - term_prin,
                     "dscr": dscr, "icr": icr, "net_worth": nw, "debt": debt_close,
                     "tol_tnw": tol / (nw - intang) if (nw - intang) > 1e-9 else None,
                     "debt_ebitda": debt_close / ebitda if ebitda > 1e-9 else None})
    return rows, {"growth": gr, "margin": margin, "debt_rate": hist_rate, "wc_rate": wc_rate, "existing_ltd": ltd,
                  "existing_ltd_years": n_ex, "instalment": inst, "wc_debt": wc_debt, "new_dep": new_dep}


def dscr_summary(rows):
    ds = [r_["dscr"] for r_ in rows if r_["dscr"] is not None]
    if not ds:
        return {"avg": None, "min": None, "min_year": None}
    mn = min(ds)
    num = sum(r_["pat"] + r_["depreciation"] + r_["term_interest"] for r_ in rows)
    den = sum(r_["term_interest"] + r_["term_principal"] for r_ in rows)
    return {"avg": num / den if den > 1e-9 else None, "min": mn, "min_year": next(r_["year"] for r_ in rows if r_["dscr"] == mn),
            "cum_surplus": sum(r_["surplus"] for r_ in rows)}


def scenarios(b, p):
    base_g = p.get("growth") if p.get("growth") is not None else _hist_growth(b)
    defs = [("Base case", base_g, p.get("margin_shift") or 0.0, p.get("rate_shift") or 0.0),
            ("Upside", base_g + 0.05, (p.get("margin_shift") or 0.0) + 0.01, p.get("rate_shift") or 0.0),
            ("Downside", base_g - 0.10, (p.get("margin_shift") or 0.0) - 0.02, (p.get("rate_shift") or 0.0) + 0.01),
            ("Severe stress", -0.10, (p.get("margin_shift") or 0.0) - 0.04, (p.get("rate_shift") or 0.0) + 0.02)]
    out = []
    for name, gr, ms, rs in defs:
        rows, _ = projections(b, p, growth=gr, margin_shift=ms, rate_shift=rs)
        s = dscr_summary(rows)
        out.append({"scenario": name, "growth": gr, "margin_shift": ms, "rate_shift": rs, "avg_dscr": s["avg"], "min_dscr": s["min"],
                    "min_year": s["min_year"], "y1_icr": rows[0]["icr"] if rows else None, "cum_surplus": s.get("cum_surplus"),
                    "y1_pat": rows[0]["pat"] if rows else None})
    return out


def breakeven(b, p, target=1.0):
    """Largest uniform fall in projected EBITDA for which the minimum DSCR stays >= target."""
    rows, _ = projections(b, p)
    s = dscr_summary(rows)
    if s["min"] is None:
        return None
    if s["min"] < target:
        return 0.0
    lo, hi = 0.0, 0.95
    for _ in range(40):
        mid = (lo + hi) / 2
        r2, _ = projections(b, p, ebitda_haircut=mid)
        m = dscr_summary(r2)["min"]
        if m is not None and m >= target:
            lo = mid
        else:
            hi = mid
    return lo


# ------------------------------------------------------------------ working capital assessment
def wc_methods(b, p):
    y0 = b["years"][0]
    c = b["data"][y0]
    gr = p.get("growth") if p.get("growth") is not None else _hist_growth(b)
    tca, tcl, stb = g(c, "total_current_assets"), g(c, "total_current_liabilities"), g(c, "short_term_borrowings")
    cm = g(c, "current_maturities_ltd")
    ocl = tcl - stb + 0.0  # other current liabilities (excl. bank borrowings)
    wcg = tca - ocl
    m1 = 0.75 * wcg
    m2 = 0.75 * tca - ocl
    proj_turn = g(c, "revenue") * (1 + gr)
    nayak_wc = 0.25 * proj_turn
    nayak_bank = 0.20 * proj_turn
    rows = [
        ["Total current assets (A)", tca, tca, None],
        ["Other current liabilities excl. bank borrowings (B)", ocl, ocl, None],
        ["Working-capital gap (A - B)", wcg, wcg, nayak_wc],
        ["Minimum borrower margin", 0.25 * wcg, 0.25 * tca, 0.05 * proj_turn],
        ["Maximum permissible bank finance", m1, m2, nayak_bank],
    ]
    exist_wc = stb - cm
    req = (p.get("cc_amount") or 0.0) or exist_wc
    assessed = min(m2, nayak_bank) if proj_turn <= 500 else m2  # Nayak applies up to ₹5 Cr for MSE (bank policy often extends)
    return {"rows": rows, "tandon1": m1, "tandon2": m2, "nayak": nayak_bank, "proj_turnover": proj_turn, "existing": exist_wc,
            "requested": req, "assessed": assessed, "headroom": assessed - req, "growth": gr}


def drawing_power(b, p):
    y0 = b["years"][0]
    c = b["data"][y0]
    inv, rec, pay = g(c, "inventories"), g(c, "trade_receivables"), g(c, "trade_payables")
    sm, dm, el = p.get("stock_margin", 0.25), p.get("debtor_margin", 0.40), p.get("eligible_debtor_share", 0.85)
    stock_dp = max(inv - pay, 0) * (1 - sm)
    elig = rec * el
    debt_dp = elig * (1 - dm)
    dp = stock_dp + debt_dp
    limit = (p.get("cc_amount") or 0.0) or (g(c, "short_term_borrowings") - g(c, "current_maturities_ltd"))
    rows = [["Inventory", inv], ["Less: trade creditors (unpaid stock)", pay], ["Paid stock", max(inv - pay, 0)],
            [f"Less: margin {sm:.0%}", max(inv - pay, 0) * sm], ["DP on stock (a)", stock_dp],
            ["Trade receivables", rec], [f"Eligible receivables (< 90 days, assumed {el:.0%})", elig],
            [f"Less: margin {dm:.0%}", elig * dm], ["DP on receivables (b)", debt_dp],
            ["Drawing power (a + b)", dp], ["Sanctioned / proposed CC limit", limit], ["Available DP = lower of DP and limit", min(dp, limit) if limit else dp]]
    return {"rows": rows, "dp": dp, "limit": limit, "shortfall": (limit - dp) if limit and limit > dp else 0.0}


# ------------------------------------------------------------------ security
def security_cover(b, p):
    y0 = b["years"][0]
    c = b["data"][y0]
    current_sec = g(c, "inventories") + g(c, "trade_receivables")
    fixed_sec = g(c, "ppe") + g(c, "cwip")
    coll = p.get("collateral_value") or 0.0
    exposure = total_proposed(p) or ((g(c, "short_term_borrowings")) + g(c, "long_term_borrowings"))
    existing_debt = max(g(c, "total_debt") - (p.get("takeover_amount") or 0.0), 0.0)
    all_debt = existing_debt + total_proposed(p)  # security is shared pari-passu with existing lenders
    fb = (p.get("tl_amount") or 0) + (p.get("cc_amount") or 0)
    ltd = g(c, "long_term_borrowings") + g(c, "current_maturities_ltd") + (p.get("tl_amount") or 0)
    facr = (fixed_sec + (p.get("tl_amount") or 0) * (1 if p.get("tl_capex", True) else 0)) / ltd if ltd > 1e-9 else None
    total_sec = current_sec + fixed_sec + coll
    rows = [["Current assets (stock + receivables) - primary for CC", current_sec],
            ["Net fixed assets incl. CWIP - primary for TL", fixed_sec],
            [f"Collateral ({p.get('collateral_type') or 'collateral'}) - market value", coll],
            ["Total security available", total_sec],
            ["Proposed exposure (fund + non-fund)", exposure],
            ["Total debt incl. existing lenders (security shared pari-passu)", all_debt]]
    share = exposure / all_debt if all_debt > 1e-9 else 1.0
    return {"rows": rows, "cover": total_sec / all_debt if all_debt > 1e-9 else None, "share": share,
            "collateral_cover": coll / exposure if exposure > 1e-9 else None, "facr": facr,
            "ltv": exposure / (fixed_sec + coll) if (fixed_sec + coll) > 1e-9 else None, "exposure": exposure, "fund_based": fb,
            "total_security": total_sec}


# ------------------------------------------------------------------ risk-based pricing
def grade_code(grade):
    return (grade or "CI-4").split(" ")[0]


def risk_pricing(b, p):
    fz = b["forensics"]
    code = grade_code(fz.get("grade"))
    pd_ = load_pd().get(code)
    if pd_ is None:
        return {"configured": False, "grade": code, "rows": [["Status", "Not computed - the bank's PD master scale is not configured "
                                                              "(Admin › Bank parameters › pd_scale.csv)"]],
                "pd": None, "lgd": None, "ead": None, "el": None, "el_rate": None, "hurdle": None, "floor": None, "raroc": None,
                "proposed": p.get("tl_rate") or p.get("cc_rate"), "base_rate": p.get("base_rate", 0.09)}
    sc = security_cover(b, p)
    ead = (p.get("tl_amount") or 0) + (p.get("cc_amount") or 0) + (p.get("nfb_amount") or 0) * p.get("ccf_nfb", 0.5)
    if ead <= 0:
        ead = sc["exposure"] or 0.0
    # realisable value of the shared assets attributable to this bank, plus its exclusive collateral
    coll = p.get("collateral_value") or 0.0
    realisable = ((sc["total_security"] - coll) * sc.get("share", 1.0) + coll) * (1 - p.get("collateral_haircut", 0.4))
    recovery = min(realisable / ead, 1.0) if ead > 1e-9 else 0.0
    lgd = min(max(1 - recovery, 0.10), 0.75)
    el = pd_ * lgd * ead
    el_rate = pd_ * lgd
    cap = p.get("capital_ratio", 0.115) * p.get("risk_weight", 1.0)
    cost_capital = cap * (p.get("target_roe", 0.15) - p.get("cost_of_funds", 0.065))
    hurdle = p.get("cost_of_funds", 0.065) + p.get("opex_ratio", 0.0075) + el_rate + cost_capital
    proposed = p.get("tl_rate") if (p.get("tl_amount") or 0) >= (p.get("cc_amount") or 0) else p.get("cc_rate")
    proposed = proposed or hurdle
    raroc = ((proposed - p.get("cost_of_funds", 0.065) - p.get("opex_ratio", 0.0075) - el_rate) * 1 + cap * p.get("cost_of_funds", 0.065)) / cap if cap else None
    floor = max(hurdle, p.get("base_rate", 0.09))
    spread = floor - p.get("base_rate", 0.09)
    return {"configured": True, "grade": code, "pd": pd_, "lgd": lgd, "ead": ead, "el": el, "el_rate": el_rate, "capital": cap * ead, "hurdle": hurdle,
            "proposed": proposed, "raroc": raroc, "floor": floor, "spread_over_base": spread, "base_rate": p.get("base_rate", 0.09),
            "recovery": recovery, "rows": [
                ["Internal grade", code], ["Probability of default (1-yr, illustrative master scale)", f"{pd_:.2%}"],
                ["Exposure at default (non-fund at CCF %.0f%%)" % (p.get("ccf_nfb", 0.5) * 100), f"₹{ead:,.2f} Cr"],
                [f"Realisable security (after {p.get('collateral_haircut', 0.4):.0%} haircut)", f"₹{realisable:,.2f} Cr"],
                ["Loss given default", f"{lgd:.1%}"], ["Expected loss (PD x LGD x EAD)", f"₹{el:,.3f} Cr  ({el_rate:.2%} p.a.)"],
                [f"Capital required ({p.get('capital_ratio', 0.115):.1%} x RW {p.get('risk_weight', 1):.0%})", f"₹{cap * ead:,.2f} Cr"],
                ["Cost of funds + operating cost", f"{p.get('cost_of_funds', 0.065) + p.get('opex_ratio', 0.0075):.2%}"],
                ["Cost of capital charge", f"{cost_capital:.2%}"],
                ["Risk-based hurdle rate", f"{hurdle:.2%}"],
                ["Minimum price (not below benchmark)", f"{floor:.2%}  (benchmark {p.get('base_rate', 0.09):.2%} + {spread * 1e4:,.0f} bp)"],
                ["Proposed rate", f"{proposed:.2%}"],
                ["RAROC at proposed rate", "n.a." if raroc is None else f"{raroc:.1%}  (target {p.get('target_roe', 0.15):.0%})"]]}


# ------------------------------------------------------------------ DuPont & earnings quality
def dupont(b):
    out = []
    for y in b["years"]:
        c = b["data"][y]
        pat, pbt, ebit, rev, ta, eq = g(c, "pat"), g(c, "pbt"), g(c, "ebit"), g(c, "revenue"), g(c, "total_assets"), g(c, "total_equity")
        if not (rev and ta and eq):
            continue
        tb = pat / pbt if pbt else None
        ib = pbt / ebit if ebit else None
        om = ebit / rev
        at = rev / ta
        em = ta / eq
        out.append({"year": y, "tax_burden": tb, "interest_burden": ib, "ebit_margin": om, "asset_turnover": at,
                    "equity_multiplier": em, "roe": pat / eq})
    return out


def dupont_commentary(rows):
    if len(rows) < 2:
        return []
    a, p_ = rows[0], rows[1]
    drivers = []
    for k, lab in [("ebit_margin", "operating margin"), ("asset_turnover", "asset turnover"), ("equity_multiplier", "financial leverage"),
                   ("interest_burden", "interest burden"), ("tax_burden", "tax burden")]:
        if a.get(k) is not None and p_.get(k) not in (None, 0):
            drivers.append((abs(a[k] / p_[k] - 1), lab, a[k] > p_[k]))
    drivers.sort(reverse=True)
    if not drivers:
        return []
    top = drivers[0]
    lev = a["equity_multiplier"] > p_["equity_multiplier"]
    txt = (f"Return on equity moved from {p_['roe']:.1%} in {p_['year']} to {a['roe']:.1%} in {a['year']}. The largest driver was "
           f"{top[1]} ({'higher' if top[2] else 'lower'}). ")
    if lev and a["roe"] > p_["roe"] and a["ebit_margin"] <= p_["ebit_margin"]:
        txt += "The improvement in ROE comes from higher leverage rather than better operations - a lower-quality source of return for a lender."
    elif a["roe"] < p_["roe"]:
        txt += "Lower returns reduce internal accruals available to support the balance sheet and repay debt."
    else:
        txt += "Returns are supported by operating performance rather than additional leverage."
    return [txt]


def earnings_quality(b):
    years, d = b["years"], b["data"]
    out = []
    for i, y in enumerate(years):
        c = d[y]
        pat, cfo, rev = g(c, "pat"), g(c, "cfo"), g(c, "revenue")
        ta = g(c, "total_assets")
        ta_p = g(d[years[i + 1]], "total_assets") if i + 1 < len(years) else ta
        avg_ta = (ta + ta_p) / 2 if (ta + ta_p) else None
        accr = (pat - cfo) / avg_ta if (avg_ta and c.get("cfo") is not None) else None
        nwc_sales = (g(c, "inventories") + g(c, "trade_receivables") - g(c, "trade_payables")) / rev if rev else None
        oi_share = g(c, "other_income") / g(c, "pbt") if g(c, "pbt") else None
        exc = g(c, "exceptional_items") / g(c, "pbt") if g(c, "pbt") else None
        out.append({"year": y, "accrual_ratio": accr, "cfo_pat": cfo / pat if (pat and c.get("cfo") is not None) else None,
                    "nwc_sales": nwc_sales, "other_income_share": oi_share, "exceptional_share": exc})
    return out


# ------------------------------------------------------------------ RBI early-warning signals
def _has(flags, *words):
    hits = [f for f in flags if f.get("category") != "Fraud & watch-list screening"
            and any(w in (f["title"] + " " + f.get("category", "")).lower() for w in words)]
    return hits


def rbi_ews(b, p):
    """RBI EWS indicators (Master Directions on Fraud Risk Management in Commercial Banks, July 2024, and the earlier
    2015 framework). Status: 'Triggered', 'Not observed' (testable from the documents) or 'Bank data needed'."""
    fz = b["forensics"]
    flags = fz["flags"]
    y0 = b["years"][0]
    c = b["data"][y0]
    r = b["ratios"][y0]
    notes = b.get("notes") or {}
    news = b.get("news") or []

    def news_hit(*words):
        return [n for n in news if any(w in (n.get("title", "") + " " + n.get("category", "")).lower() for w in words)]

    out = []

    def add(sig, status, basis):
        out.append([sig, status, basis])

    def from_flags(sig, hits, basis_ok="No indication in the financial statements"):
        add(sig, "Triggered" if hits else "Not observed", "; ".join(h["title"] for h in hits[:3]) if hits else basis_ok)

    scr = b.get("screening") or {}
    wl_hits = [h for h in scr.get("hits") or [] if h["severity"] == "High"]
    found_att = [k for k, a_ in (scr.get("attest") or {}).items() if (a_ or {}).get("status", "").startswith("Checked - FOUND")]
    if found_att:
        from .watchlist import REQUIRED_SOURCES as _RS
        _nm = {k_: n_ for k_, n_, *_ in _RS}
        wl_hits = wl_hits + [{"party": b.get("company"), "list": _nm.get(k, k), "match": "officer check"} for k in found_att]
    if scr.get("summary") or found_att:
        add("Borrower / promoter / related party on wilful-defaulter, fraud or regulatory lists", "Triggered" if wl_hits else "Not observed",
            "; ".join(f"{h['party']} - {h['list']} ({h['match'].split(' -')[0]})" for h in wl_hits[:3]) if wl_hits else
            f"{scr['summary'].get('parties', 0)} parties screened against {scr['summary'].get('entries', 0)} list entries"
            + (f"; {scr['summary'].get('hits')} possible match(es) to verify" if scr["summary"].get("hits") else ""))
    else:
        add("Borrower / promoter / related party on wilful-defaulter, fraud or regulatory lists", "Bank data needed",
            "Run the Fraud & watch-list screening tab (CIBIL suit-filed / wilful-defaulter, SEBI, MCA, RBI, internal FMR lists)")
    from_flags("Default in undisputed statutory dues / delay in payment to lenders", _has(flags, "default", "statutory", "delay"))
    from_flags("Diversion of funds / end-use not established", _has(flags, "end-use", "diversion", "not visibly deployed", "loans & advances", "capital advances"))
    from_flags("Substantial related-party transactions / funds to group entities", _has(flags, "related", "group"))
    from_flags("Receivables disproportionate to sales / stretched debtors", _has(flags, "receivables", "debtor"))
    from_flags("Inventory build-up / stock not commensurate with turnover", _has(flags, "inventory"))
    from_flags("Frequent change in project scope / delay in implementation (CWIP)", _has(flags, "work-in-progress", "cwip"))
    from_flags("Critical remarks by statutory auditor / qualification / CARO", _has(flags, "auditor opinion", "caro", "emphasis", "going concern", "qualified"))
    from_flags("Large contingent or off-balance-sheet liabilities", _has(flags, "contingent", "guarantee", "hidden liabilit"))
    from_flags("Cash-rich yet borrowing / low yield on liquid funds (possible fictitious cash)", _has(flags, "cash-rich", "yield on cash"))
    from_flags("Manipulation indicators (Beneish / accrual-heavy profits)", _has(flags, "beneish", "cash-negative", "operating cash flow down"))
    pledge = g(c, "promoter_pledge_pct")
    add("High promoter pledge / reduction in promoter stake", "Triggered" if pledge > 25 else ("Not observed" if c.get("promoter_pledge_pct") is not None else "Bank data needed"),
        f"Pledge {pledge:.0f}% of promoter holding" if c.get("promoter_pledge_pct") is not None else "Shareholding pattern / NSDL data")
    tnw = g(c, "tnw")
    add("Erosion of net worth / negative tangible net worth", "Triggered" if tnw <= 0 or (r.get("pat_margin") or 0) < 0 else "Not observed",
        f"TNW ₹{tnw:,.2f} Cr; PAT margin {(r.get('pat_margin') or 0):.1%}")
    nh = news_hit("downgrade", "resign", "auditor", "raid", "fraud", "default", "insolven", "nclt", "sebi", "ed ", "cbi")
    add("Rating downgrade / resignation of auditor or key personnel / regulatory action (news)", "Triggered" if nh else ("Not observed" if news else "Bank data needed"),
        "; ".join(n.get("title", "")[:90] for n in nh[:2]) if nh else (f"{len(news)} news items screened" if news else "News not scanned"))
    add("Delay in submission of stock statements / financial data", "Triggered" if p.get("stock_stmt_delay") else "Bank data needed",
        "Officer input" if p.get("stock_stmt_delay") else "Confirm from account monitoring")
    add("Bouncing of high-value cheques / devolvement of LC / invocation of BG", "Triggered" if (p.get("cheque_returns") or 0) > 0 else "Bank data needed",
        f"{p.get('cheque_returns')} return(s) reported" if (p.get("cheque_returns") or 0) > 0 else "12-month bank statement analysis")
    add("Frequent ad hoc / persistent overdrawing of limits", "Triggered" if p.get("adhoc_overdrawn") else "Bank data needed",
        "Officer input" if p.get("adhoc_overdrawn") else "CBS / account conduct")
    add("Heavy cash withdrawals / non-routing of sales through lending bank", "Triggered" if (p.get("cash_withdrawals_high") or p.get("non_routing")) else "Bank data needed",
        "Officer input" if (p.get("cash_withdrawals_high") or p.get("non_routing")) else "Compare credit summation with sales; GST turnover")
    add("Charges in ROC / CRILC not reflected in books (hidden borrowings)", "Triggered" if p.get("unrecorded_charges") else "Bank data needed",
        "Officer input" if p.get("unrecorded_charges") else "MCA charge search vs. borrowings in balance sheet")
    dpd = int(p.get("dpd") or 0)
    add("Overdue / irregular account (SMA status)", "Triggered" if dpd > 0 else "Not observed", sma_status(dpd))
    n_trig = sum(1 for r_ in out if r_[1] == "Triggered")
    return out, n_trig


def sma_status(dpd):
    dpd = int(dpd or 0)
    if dpd <= 0:
        return "Standard - no overdues"
    if dpd <= 30:
        return f"SMA-0 ({dpd} DPD)"
    if dpd <= 60:
        return f"SMA-1 ({dpd} DPD)"
    if dpd <= 90:
        return f"SMA-2 ({dpd} DPD) - CRILC reporting / resolution plan under the Prudential Framework"
    return f"NPA ({dpd} DPD) - classify per IRACP norms"


def ews_action(n_trig):
    if n_trig >= 4:
        return ("Multiple EWS triggered - the RBI framework requires the account to be examined for Red-Flagging (RFA) and a decision "
                "within the prescribed timeline; consider a forensic audit before any fresh exposure.")
    if n_trig >= 2:
        return "Two or more EWS triggered - place the account on the watch-list, seek explanations and verify before sanction."
    if n_trig == 1:
        return "One EWS triggered - obtain a satisfactory explanation and record it in the appraisal."
    return "No EWS triggered on the available information; bank-side indicators must still be confirmed from account conduct."


# ------------------------------------------------------------------ regulatory checks
def regulatory(b, p):
    rows = []
    t1 = p.get("tier1_capital") or 0
    exp = (p.get("existing_exposure") or 0) + total_proposed(p)
    grp = (p.get("group_exposure") or 0) + total_proposed(p)
    if t1 > 0:
        s = exp / t1
        gp = grp / t1
        rows.append(["Single counterparty exposure (LEF limit 20% of Tier-1, up to 25% with Board approval)", f"{s:.2%}",
                     "Within limit" if s <= 0.20 else ("Needs Board approval" if s <= 0.25 else "Breach")])
        rows.append(["Group of connected counterparties (LEF limit 25% of Tier-1)", f"{gp:.2%}", "Within limit" if gp <= 0.25 else "Breach"])
    else:
        rows.append(["Large Exposures Framework (single 20% / group 25% of Tier-1)", "n.a.", "Enter bank Tier-1 capital to test"])
    rows.append(["Asset classification (IRACP)", sma_status(p.get("dpd")), "Standard" if int(p.get("dpd") or 0) <= 90 else "NPA"])
    y0 = b["years"][0]
    r = b["ratios"][y0]
    rows.append(["Unhedged foreign-currency exposure", "Bank data needed", "Obtain UFCE certificate (incremental provisioning / capital)"])
    rows.append(["Wilful defaulter / CRILC / CIBIL screening", "Bank data needed", "Mandatory before sanction"])
    rows.append(["Minimum promoter margin on working capital", f"{(r.get('current_ratio') or 0):.2f}x current ratio",
                 "Adequate" if (r.get("current_ratio") or 0) >= 1.25 else "Below 1.25x - check margin compliance"])
    return rows


# ------------------------------------------------------------------ plan vs actual
def plan_vs_actual(b, p):
    y0 = b["years"][0]
    c = b["data"][y0]
    rows = []
    for key, lab, pk in [("revenue", "Revenue", "prev_proj_revenue"), ("pat", "PAT", "prev_proj_pat")]:
        pv = p.get(pk) or 0
        if pv:
            av = g(c, key)
            rows.append([lab, pv, av, av - pv, (av - pv) / abs(pv)])
    return rows
