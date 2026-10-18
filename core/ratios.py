"""Ratio engine.

Each derived figure and ratio is written ONCE as a formula template. The same template is
evaluated in Python (dashboard / Word) and written as a live Excel formula (Tab 2), so the
numbers in all three outputs always agree.
  {key}    -> this year's value of a schema / derived key
  {key@p}  -> previous year's value
"""
import re

from . import schema

DERIVED = [
    ("total_debt", "Total Debt (LT + ST borrowings + leases)", "{long_term_borrowings}+{short_term_borrowings}+{lease_liabilities_nc}+{lease_liabilities_c}"),
    ("liquid_funds", "Liquid Funds (cash + bank + current investments)", "{cash_and_equivalents}+{other_bank_balances}+{current_investments}"),
    ("net_debt", "Net Debt", "{total_debt}-{liquid_funds}"),
    ("cogs", "Cost of Goods Sold", "{cost_of_materials}+{purchases_stock}+{change_in_inventories}"),
    ("ebitda", "EBITDA (operating, excl. other income)", "{pbt}-{exceptional_items}+{finance_cost}+{depreciation}-{other_income}"),
    ("ebit", "EBIT (incl. other income)", "{pbt}-{exceptional_items}+{finance_cost}"),
    ("tol", "Total Outside Liabilities (TOL)", "{total_assets}-{total_equity}-{minority_interest}"),
    ("tnw", "Tangible Net Worth (TNW)", "{total_equity}-{goodwill}-{intangibles}"),
    ("nwc", "Net Working Capital", "{total_current_assets}-{total_current_liabilities}"),
    ("loans_advances", "Loans & Advances given (current + non-current)", "{nc_loans}+{current_loans}"),
    ("fcf", "Free Cash Flow (CFO - capex)", "{cfo}-ABS({capex})"),
]
DERIVED_KEYS = [k for k, *_ in DERIVED]
DERIVED_LABELS = {k: l for k, l, _ in DERIVED}

# key, name, category, template, fmt, direction ('high' good / 'low' good / 'band'), good, bad, note
RATIOS = [
    ("current_ratio", "Current Ratio", "Liquidity", "{total_current_assets}/{total_current_liabilities}", "x", "high", 1.33, 1.0, "Bank benchmark 1.33x"),
    ("quick_ratio", "Quick Ratio", "Liquidity", "({total_current_assets}-{inventories})/{total_current_liabilities}", "x", "high", 1.0, 0.7, ""),
    ("cash_ratio", "Cash Ratio", "Liquidity", "{liquid_funds}/{total_current_liabilities}", "x", "high", 0.3, 0.1, ""),
    ("nwc_cr", "Net Working Capital (Cr)", "Liquidity", "{nwc}", "cr", "high", 0, -0.0001, "Negative NWC = short-term funds in long-term assets"),
    ("mpbf2", "MPBF - Tandon Method II (Cr)", "Liquidity", "0.75*{total_current_assets}-({total_current_liabilities}-{short_term_borrowings})", "cr", None, None, None, "Max permissible bank finance"),
    ("de", "Debt / Equity", "Leverage", "{total_debt}/{total_equity}", "x", "low", 1.0, 2.0, ""),
    ("tol_tnw", "TOL / TNW", "Leverage", "{tol}/{tnw}", "x", "low", 3.0, 4.0, "Bank benchmark <= 3x"),
    ("debt_ebitda", "Total Debt / EBITDA", "Leverage", "{total_debt}/{ebitda}", "x", "low", 3.0, 5.0, ""),
    ("netdebt_ebitda", "Net Debt / EBITDA", "Leverage", "{net_debt}/{ebitda}", "x", "low", 2.5, 4.5, ""),
    ("icr", "Interest Coverage (EBIT / Finance cost)", "Coverage", "{ebit}/{finance_cost}", "x", "high", 3.0, 1.5, ""),
    ("ebitda_int", "EBITDA / Finance cost", "Coverage", "{ebitda}/{finance_cost}", "x", "high", 4.0, 2.0, ""),
    ("dscr", "DSCR (approx.)", "Coverage", "({pat}+{depreciation}+{finance_cost})/({finance_cost}+{current_maturities_ltd})", "x", "high", 1.5, 1.2, "(PAT+Dep+Int)/(Int+current maturities)"),
    ("ebitda_margin", "EBITDA Margin", "Profitability", "{ebitda}/{revenue}", "%", "high", 0.12, 0.05, ""),
    ("pat_margin", "PAT Margin", "Profitability", "{pat}/{revenue}", "%", "high", 0.06, 0.0, ""),
    ("roe", "Return on Equity (closing)", "Profitability", "{pat}/{total_equity}", "%", "high", 0.15, 0.05, ""),
    ("roce", "ROCE (EBIT / (Equity + Debt))", "Profitability", "{ebit}/({total_equity}+{total_debt})", "%", "high", 0.15, 0.08, ""),
    ("roa", "Return on Assets", "Profitability", "{pat}/{total_assets}", "%", "high", 0.06, 0.02, ""),
    ("asset_turnover", "Asset Turnover", "Efficiency", "{revenue}/{total_assets}", "x", "high", 1.0, 0.5, ""),
    ("fa_turnover", "Fixed Asset Turnover", "Efficiency", "{revenue}/{ppe}", "x", "high", 2.0, 1.0, ""),
    ("debtor_days", "Debtor Days", "Efficiency", "{trade_receivables}/{revenue}*365", "days", "low", 60, 120, ""),
    ("inventory_days", "Inventory Days (on COGS)", "Efficiency", "{inventories}/MAX({cogs},0.0001)*365", "days", "low", 60, 120, ""),
    ("creditor_days", "Creditor Days (on COGS)", "Efficiency", "{trade_payables}/MAX({cogs},0.0001)*365", "days", None, None, None, "Very high = stretched suppliers"),
    ("ccc", "Cash Conversion Cycle", "Efficiency", "{trade_receivables}/{revenue}*365+{inventories}/MAX({cogs},0.0001)*365-{trade_payables}/MAX({cogs},0.0001)*365", "days", "low", 60, 120, ""),
    ("cfo_ebitda", "CFO / EBITDA", "Cash Flow Quality", "{cfo}/{ebitda}", "x", "high", 0.7, 0.4, "Earnings converting to cash?"),
    ("cfo_pat", "CFO / PAT", "Cash Flow Quality", "{cfo}/{pat}", "x", "high", 1.0, 0.5, ""),
    ("fcf_cr", "Free Cash Flow (Cr)", "Cash Flow Quality", "{fcf}", "cr", "high", 0, -0.0001, ""),
    ("other_inc_pbt", "Other Income / PBT", "Earnings Quality", "{other_income}/{pbt}", "%", "low", 0.15, 0.30, "High = core business weak"),
    ("etr", "Effective Tax Rate", "Earnings Quality", "{tax_expense}/{pbt}", "%", "band", 0.18, 0.10, "Statutory ~25.17%"),
    ("implied_rate", "Implied Cost of Debt", "Forensic", "{finance_cost}/{total_debt}", "%", "band", 0.06, 0.15, "Too low = hidden debt / capitalised interest"),
    ("cash_yield", "Yield on Liquid Funds", "Forensic", "{interest_income}/{liquid_funds}", "%", "high", 0.04, 0.02, "Low yield on large cash = cash may not exist / is encumbered"),
    ("la_nw", "Loans & Advances / Net Worth", "Forensic", "{loans_advances}/{total_equity}", "%", "low", 0.10, 0.25, "High = possible fund diversion to group"),
    ("inv_nw", "Non-current Investments / Net Worth", "Forensic", "{nc_investments}/{total_equity}", "%", "low", 0.25, 0.50, "Upstreaming to group entities"),
    ("cl_nw", "Contingent Liabilities / Net Worth", "Forensic", "MAX({contingent_liabilities},{guarantees_given})/{total_equity}", "%", "low", 0.25, 0.50, ""),
    ("cwip_ppe", "CWIP / Net Block", "Forensic", "{cwip}/{ppe}", "%", "low", 0.20, 0.50, "Stuck CWIP = capex diversion risk"),
    ("rpt_rev", "Related-party Sales+Purchases / Revenue", "Forensic", "({rpt_sales}+{rpt_purchases})/{revenue}", "%", "low", 0.10, 0.25, ""),
    ("rev_growth", "Revenue Growth", "Growth", "{revenue}/{revenue@p}-1", "%", "high", 0.10, 0.0, ""),
    ("ebitda_growth", "EBITDA Growth", "Growth", "{ebitda}/{ebitda@p}-1", "%", "high", 0.10, 0.0, ""),
    ("pat_growth", "PAT Growth", "Growth", "{pat}/{pat@p}-1", "%", "high", 0.10, 0.0, ""),
    ("debt_growth", "Debt Growth", "Growth", "{total_debt}/{total_debt@p}-1", "%", None, None, None, ""),
    ("recv_vs_rev", "Receivable growth minus Revenue growth", "Forensic", "({trade_receivables}/{trade_receivables@p}-1)-({revenue}/{revenue@p}-1)", "%", "low", 0.10, 0.25, "Receivables outrunning sales = possible fictitious sales"),
    ("altman_z", "Altman Z'' (emerging-market)", "Distress Scores",
     "6.56*{nwc}/{total_assets}+3.26*{other_equity}/{total_assets}+6.72*{ebit}/{total_assets}+1.05*{total_equity}/{tol}", "x", "high", 2.6, 1.1, ">2.6 safe, <1.1 distress"),
]
RATIO_META = {r[0]: r for r in RATIOS}

_TOKEN = re.compile(r"\{([a-z0-9_]+)(@p)?\}")


def _eval(template, cur, prev):
    if "@p}" in template and prev is None:
        return None
    expr = _TOKEN.sub(lambda m: f'P("{m.group(1)}")' if m.group(2) else f'C("{m.group(1)}")', template)
    expr = expr.replace("ABS(", "abs(").replace("MAX(", "max(").replace("MIN(", "min(")
    ns = {"C": lambda k: schema.g(cur, k), "P": lambda k: schema.g(prev, k), "abs": abs, "max": max, "min": min}
    try:
        v = eval(expr, {"__builtins__": {}}, ns)
    except ZeroDivisionError:
        return None
    except Exception:
        return None
    return float(v)


def enrich(year_data):
    """Add derived keys to each year (in place copy)."""
    out = {}
    years = list(year_data.keys())
    for i, y in enumerate(years):
        cur = dict(year_data[y])
        for k, _l, t in DERIVED:
            cur[k] = _eval(t, cur, None)
        out[y] = cur
    return out


def compute(year_data, years):
    """years: latest first. Returns {year: {ratio_key: value}} and the enriched data."""
    enriched = enrich({y: year_data[y] for y in years})
    res = {}
    for i, y in enumerate(years):
        prev = enriched[years[i + 1]] if i + 1 < len(years) else None
        res[y] = {}
        for key, _n, _c, t, *_ in RATIOS:
            # guard ratios whose denominator input was never supplied
            res[y][key] = _eval(t, enriched[y], prev)
    # meaningless results when the key inputs are blank
    for y in years:
        e = enriched[y]
        if not e.get("interest_income"):
            res[y]["cash_yield"] = None
        if not (e.get("rpt_sales") or e.get("rpt_purchases")):
            res[y]["rpt_rev"] = None
        if not e.get("current_maturities_ltd"):
            res[y]["dscr"] = None  # without scheduled repayments DSCR would be overstated
        if not e.get("finance_cost"):
            for k in ("icr", "ebitda_int", "implied_rate"):
                res[y][k] = None
    return res, enriched


def status(key, value):
    """'good' | 'watch' | 'bad' | None"""
    meta = RATIO_META.get(key)
    if meta is None or value is None:
        return None
    direction, good, bad = meta[5], meta[6], meta[7]
    if direction == "high":
        return "good" if value >= good else ("bad" if value < bad else "watch")
    if direction == "low":
        return "good" if value <= good else ("bad" if value > bad else "watch")
    if direction == "band":
        lo, hi = good, bad
        if key == "etr":  # good band 18-30%
            return "good" if 0.18 <= value <= 0.32 else ("bad" if value < 0.10 else "watch")
        return "good" if lo <= value <= hi else "watch"
    return None


def fmt(key, value):
    if value is None:
        return "n.a."
    f = RATIO_META[key][4] if key in RATIO_META else "cr"
    if f == "%":
        return f"{value * 100:,.1f}%"
    if f == "x":
        return f"{value:,.2f}x"
    if f == "days":
        return f"{value:,.0f} d"
    return f"{value:,.2f}"


def excel_formula(template, cell_of, year_col, prev_col):
    """cell_of(key, col) -> 'Financials!C12'"""
    if "@p}" in template and prev_col is None:
        return '="n.a."'
    def rep(m):
        col = prev_col if m.group(2) else year_col
        return cell_of(m.group(1), col)
    return f'=IFERROR({_TOKEN.sub(rep, template)},"n.a.")'
