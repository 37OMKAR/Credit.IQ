"""Plain-language explanations: what each ratio is, how to read it, and a one-line reading of the
company's own value. Used for the 'Read this first' summary, the ratio glossary and the dashboard."""
from . import ratios as R
from . import schema

# key: (what it is - simple words, how to read it)
RATIO_HELP = {
    "current_ratio": ("Short-term assets divided by short-term liabilities.", "Shows whether bills due within a year can be paid from assets that turn into cash within a year. Banks like 1.33 or more."),
    "quick_ratio": ("Current ratio without inventory.", "A stricter liquidity test - stock may not sell quickly. Around 1.0 is comfortable."),
    "cash_ratio": ("Cash and liquid investments divided by short-term liabilities.", "How much of the short-term dues could be paid today from cash alone."),
    "nwc_cr": ("Current assets minus current liabilities (₹ Cr).", "Positive = long-term money funds day-to-day needs (healthy). Negative = short-term borrowing is funding long-term assets (risky)."),
    "mpbf2": ("Maximum Permissible Bank Finance - Tandon Committee Method II (₹ Cr).", "The ceiling for working-capital bank limits: 75% of current assets minus other current liabilities."),
    "de": ("Total borrowings divided by the owners' money (net worth).", "How much the company has borrowed for every ₹1 of its own money. Below 1x is conservative, above 2x is high."),
    "tol_tnw": ("All outside liabilities divided by tangible net worth.", "Banks' favourite leverage test - everything owed to outsiders vs the owners' real stake. 3x or less is the usual norm."),
    "debt_ebitda": ("Total debt divided by yearly operating profit (EBITDA).", "Roughly how many years of operating profit it would take to repay all debt. Under 3 years is comfortable, above 5 is stretched."),
    "netdebt_ebitda": ("Debt minus cash, divided by EBITDA.", "Same as above but gives credit for cash held. Negative = more cash than debt."),
    "icr": ("Operating profit (EBIT) divided by interest cost.", "How many times profit covers interest. Below 1.5x the company is struggling to pay interest."),
    "ebitda_int": ("EBITDA divided by interest cost.", "Interest cover before depreciation; 4x or more is strong."),
    "dscr": ("(Profit + depreciation + interest) ÷ (interest + loan instalments due this year).", "Can yearly cash earnings pay all interest and principal falling due? Banks look for 1.25x-1.5x or more. Needs 'current maturities of LTD' to be entered."),
    "ebitda_margin": ("Operating profit as a % of sales.", "How much of every ₹100 of sales is left after running costs. Compare with industry peers."),
    "pat_margin": ("Net profit as a % of sales.", "What finally remains for owners from every ₹100 of sales."),
    "roe": ("Net profit divided by net worth.", "Return the owners earn on their money. 15%+ is good."),
    "roce": ("EBIT divided by (net worth + debt).", "Return on all the money used in the business. Should be above the cost of borrowing."),
    "roa": ("Net profit divided by total assets.", "How productively all assets generate profit."),
    "asset_turnover": ("Sales divided by total assets.", "Sales generated for every ₹1 of assets."),
    "fa_turnover": ("Sales divided by net fixed assets (plant, machinery, buildings).", "How well the plant and machinery are being used. Very high values are normal for service/trading firms."),
    "debtor_days": ("Trade receivables ÷ sales × 365.", "Average days customers take to pay. Rising days = slower collection or doubtful sales."),
    "inventory_days": ("Inventory ÷ cost of goods × 365.", "Days of stock held. Rising days = slow-moving or inflated stock."),
    "creditor_days": ("Trade payables ÷ cost of goods × 365.", "Days the company takes to pay suppliers. Very high may mean it is stretching suppliers because cash is short."),
    "ccc": ("Debtor days + inventory days - creditor days.", "Days of working capital the company must finance itself. Shorter is better."),
    "cfo_ebitda": ("Cash from operations divided by EBITDA.", "Is reported profit actually arriving as cash? Below 0.5 is a warning sign."),
    "cfo_pat": ("Cash from operations divided by net profit.", "Above 1 = profits are backed by cash. Persistently below 1 = paper profits."),
    "fcf_cr": ("Cash from operations minus capital expenditure (₹ Cr).", "Cash left after investing in the business - available to repay debt."),
    "other_inc_pbt": ("Other income as a % of profit before tax.", "If high, profit comes from treasury/one-offs, not the core business."),
    "etr": ("Tax expense as a % of profit before tax.", "Normal is around 25%. Very low tax on high profit can mean profits are not real or are sheltered."),
    "implied_rate": ("Interest cost divided by total debt.", "Effective borrowing rate. Too low = possible hidden or capitalised interest; too high = costly private/NBFC money."),
    "cash_yield": ("Interest income divided by cash and liquid investments.", "Cash should earn some interest. A very low yield on large cash can mean the cash is blocked, pledged or not real."),
    "la_nw": ("Loans and advances given by the company as a % of its net worth.", "Lending money is not a manufacturer's business - high values may indicate funds moved to group companies."),
    "inv_nw": ("Long-term investments as a % of net worth.", "Money put into subsidiaries/associates - outside the bank's security."),
    "cl_nw": ("Contingent liabilities (incl. guarantees) as a % of net worth.", "Possible future liabilities (court cases, tax demands, guarantees). Above 50% of net worth is serious."),
    "cwip_ppe": ("Capital work-in-progress as a % of net fixed assets.", "Projects not yet complete. If large and not falling, projects may be stuck or money diverted."),
    "rpt_rev": ("Sales + purchases with related parties as a % of revenue.", "High share = business depends on group firms; risk of profit shifting / round-tripping."),
    "rev_growth": ("Change in sales vs last year.", "Is the business growing?"),
    "ebitda_growth": ("Change in operating profit vs last year.", "Is profit growing along with sales?"),
    "pat_growth": ("Change in net profit vs last year.", ""),
    "debt_growth": ("Change in total borrowings vs last year.", "Compare with growth in sales and assets - debt rising faster is a warning."),
    "recv_vs_rev": ("Growth in receivables minus growth in sales.", "If receivables grow much faster than sales, sales may be inflated or customers are not paying."),
    "altman_z": ("Altman Z'' score (emerging-market version) combining liquidity, retained profit, earnings and leverage.", "Above 2.6 = safe zone; 1.1-2.6 = grey zone; below 1.1 = distress zone (higher default risk)."),
}

SCORE_HELP = [
    ("Internal credit score (0-100)", "Our model's overall score: 70 points from key ratios versus bank norms, plus 30 points reduced for each red flag (High -6, Medium -3, Low -1). Grades CI-1 (very low risk) to CI-7 (very high risk)."),
    ("Beneish M-score", "A statistical test for earnings manipulation using 8 accounting indicators. Above -1.78 suggests the accounts may be manipulated."),
    ("Piotroski F-score (0-9)", "Nine yes/no tests of financial strength (profitability, leverage, efficiency). 7-9 strong, 0-3 weak."),
    ("Altman Z''", "Bankruptcy-risk score for emerging-market companies. Below 1.1 = distress zone."),
    ("PCAF financed emissions", "The share of the company's greenhouse-gas emissions attributable to the bank's loan = (loan ÷ company's equity + debt) × company emissions. Data quality score 1 (best, verified) to 5 (rough estimate)."),
]

VERDICT_WORDS = {"good": "✓ Comfortable", "watch": "! Watch", "bad": "✗ Concern"}


def _f(v, d=2):
    return "n.a." if v is None else f"{v:,.{d}f}"


def reading(key, v, data):
    """One plain sentence about the company's own value."""
    if v is None:
        return "Not available from the documents."
    g = lambda k: schema.g(data, k)
    s = {
        "current_ratio": f"For every ₹1 due within a year, the company has ₹{v:.2f} of short-term assets.",
        "quick_ratio": f"Excluding stock, it has ₹{v:.2f} of quick assets per ₹1 of short-term dues.",
        "de": f"It has borrowed ₹{v:.2f} for every ₹1 of owners' money.",
        "tol_tnw": f"Outsiders' money is {v:.2f} times the owners' tangible stake.",
        "debt_ebitda": (f"Debt equals about {v:.1f} years of operating profit." if v > 0 else "The company has no meaningful debt relative to profit."),
        "icr": f"Operating profit covers interest {v:.1f} times.",
        "dscr": f"Cash earnings cover interest + instalments due {v:.2f} times.",
        "ebitda_margin": f"₹{v*100:.1f} of every ₹100 of sales is operating profit.",
        "pat_margin": f"₹{v*100:.1f} of every ₹100 of sales is net profit.",
        "roe": f"Owners earn {v:.1%} a year on their money.",
        "roce": f"The business earns {v:.1%} on all capital employed.",
        "debtor_days": f"Customers take about {v:.0f} days to pay.",
        "inventory_days": f"Stock is held for about {v:.0f} days.",
        "creditor_days": f"Suppliers are paid in about {v:.0f} days.",
        "cfo_ebitda": f"₹{v:.2f} of cash arrives for every ₹1 of operating profit reported.",
        "cfo_pat": f"₹{v:.2f} of operating cash per ₹1 of net profit.",
        "altman_z": "Safe zone." if v > 2.6 else ("Distress zone - elevated default risk." if v < 1.1 else "Grey zone - neither clearly safe nor distressed."),
        "rev_growth": f"Sales {'grew' if v >= 0 else 'fell'} {abs(v):.1%} over the previous year.",
        "nwc_cr": f"Net working capital is ₹{v:,.2f} Cr ({'positive - healthy' if v >= 0 else 'negative - short-term money funds long-term assets'}).",
    }.get(key)
    if s:
        return s
    return R.fmt(key, v)


SUMMARY_KEYS = ["rev_growth", "ebitda_margin", "current_ratio", "tol_tnw", "de", "debt_ebitda", "icr", "dscr",
                "debtor_days", "cfo_ebitda", "roce", "altman_z"]


def grade_meaning(grade):
    g = (grade or "").split(" ")[0]
    return {
        "CI-1": "very strong borrower - low chance of default",
        "CI-2": "strong borrower",
        "CI-3": "acceptable borrower with some weaknesses",
        "CI-4": "average risk - lend with conditions and monitoring",
        "CI-5": "elevated risk - needs strong mitigants and closer due diligence",
        "CI-6": "high risk - serious concerns must be resolved first",
        "CI-7": "very high risk - not recommended in present form",
    }.get(g, "")
