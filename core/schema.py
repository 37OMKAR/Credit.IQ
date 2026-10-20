"""Canonical line-item schema (Indian Ind-AS / Schedule III layout).

Every extractor (LLM or heuristic) maps the source document onto these keys,
so ratios, forensics, Excel and Word all speak one language.
All amounts are normalised to INR Crore.
"""

# (key, label, section, synonyms used by the heuristic extractor)
BALANCE_SHEET = [
    # ---- Equity
    ("share_capital", "Equity Share Capital", "Equity", ["equity share capital", "share capital"]),
    ("other_equity", "Other Equity (Reserves & Surplus)", "Equity", ["other equity", "reserves and surplus", "reserves & surplus"]),
    ("total_equity", "Total Equity (Net Worth)", "Equity", ["total equity", "shareholders' funds", "shareholders funds", "net worth"]),
    ("minority_interest", "Non-controlling Interest", "Equity", ["non-controlling interest", "non controlling interest", "minority interest"]),
    # ---- Non-current liabilities
    ("long_term_borrowings", "Long-term Borrowings", "Non-current Liabilities", ["long-term borrowings", "long term borrowings", "non-current borrowings", "borrowings (non-current)"]),
    ("lease_liabilities_nc", "Lease Liabilities (Non-current)", "Non-current Liabilities", ["lease liabilities (non-current)"]),
    ("other_nc_fin_liabilities", "Other Non-current Financial Liabilities", "Non-current Liabilities", ["other non-current financial liabilities"]),
    ("long_term_provisions", "Long-term Provisions", "Non-current Liabilities", ["long-term provisions", "long term provisions", "non-current provisions"]),
    ("deferred_tax_liabilities", "Deferred Tax Liabilities (Net)", "Non-current Liabilities", ["deferred tax liabilities (net)", "deferred tax liabilities", "deferred tax liability"]),
    ("other_nc_liabilities", "Other Non-current Liabilities", "Non-current Liabilities", ["other non-current liabilities", "other long-term liabilities", "other non-current non-financial liabilities", "other non current non financial liabilities"]),
    # ---- Current liabilities
    ("short_term_borrowings", "Short-term Borrowings", "Current Liabilities", ["short-term borrowings", "short term borrowings", "current borrowings", "borrowings (current)"]),
    ("current_maturities_ltd", "of which: Current Maturities of LTD (memo, inside ST borrowings)", "Current Liabilities", ["current maturities of long-term debt", "current maturities of long term borrowings", "current maturities"]),
    ("lease_liabilities_c", "Lease Liabilities (Current)", "Current Liabilities", ["lease liabilities (current)"]),
    ("trade_payables", "Trade Payables", "Current Liabilities", ["trade payables", "trade payable", "sundry creditors", "total outstanding dues of micro enterprises and small enterprises", "total outstanding dues of other than msme", "total outstanding dues of creditors other than micro enterprises and small enterprises", "total outstanding dues of other than micro", "micro and small enterprises", "dues of msme", "dues of creditors other than msme"]),
    ("other_current_fin_liabilities", "Other Current Financial Liabilities", "Current Liabilities", ["other current financial liabilities", "other financial liabilities"]),
    ("other_current_liabilities", "Other Current Liabilities", "Current Liabilities", ["other current liabilities", "contract liabilities", "contract liability", "advance from customers", "advances from customers"]),
    ("short_term_provisions", "Short-term Provisions", "Current Liabilities", ["short-term provisions", "short term provisions", "current provisions"]),
    ("current_tax_liabilities", "Current Tax Liabilities (Net)", "Current Liabilities", ["current tax liabilities (net)", "current tax liabilities"]),
    ("total_current_liabilities", "Total Current Liabilities", "Current Liabilities", ["total current liabilities"]),
    ("total_equity_and_liabilities", "Total Equity & Liabilities", "Totals", ["total equity and liabilities", "total equity & liabilities", "total liabilities and equity", "total equity and liabilites", "total equity & liabilites", "total equity and liabilities total"]),
    # ---- Non-current assets
    ("ppe", "Property, Plant & Equipment (Net Block)", "Non-current Assets", ["property, plant and equipment", "property plant and equipment", "tangible assets", "fixed assets"]),
    ("cwip", "Capital Work-in-Progress", "Non-current Assets", ["capital work-in-progress", "capital work in progress", "cwip"]),
    ("right_of_use", "Right-of-Use Assets", "Non-current Assets", ["right-of-use assets", "right of use assets", "right of use asset"]),
    ("investment_property", "Investment Property", "Non-current Assets", ["investment property"]),
    ("goodwill", "Goodwill", "Non-current Assets", ["goodwill"]),
    ("intangibles", "Other Intangible Assets (incl. under development)", "Non-current Assets", ["other intangible assets", "intangible assets", "intangible assets under development"]),
    ("nc_investments", "Non-current Investments", "Non-current Assets", ["non-current investments", "investments (non-current)", "long-term investments"]),
    ("nc_loans", "Non-current Loans & Advances", "Non-current Assets", ["loans (non-current)", "long-term loans and advances", "non-current loans"]),
    ("other_nc_fin_assets", "Other Non-current Financial Assets", "Non-current Assets", ["other non-current financial assets", "other financial assets - non-current", "other financial assets non-current"]),
    ("deferred_tax_assets", "Deferred Tax Assets (Net)", "Non-current Assets", ["deferred tax assets (net)", "deferred tax assets"]),
    ("capital_advances", "Capital Advances", "Non-current Assets", ["capital advances"]),
    ("other_nc_assets", "Other Non-current Assets", "Non-current Assets", ["other non-current assets", "other non-current non-financial assets", "other non current non financial assets"]),
    # ---- Current assets
    ("inventories", "Inventories", "Current Assets", ["inventories", "stock-in-trade", "inventory"]),
    ("current_investments", "Current Investments", "Current Assets", ["current investments"]),
    ("trade_receivables", "Trade Receivables", "Current Assets", ["trade receivables", "trade receivable", "sundry debtors"]),
    ("cash_and_equivalents", "Cash & Cash Equivalents", "Current Assets", ["cash and cash equivalents", "cash & cash equivalents"]),
    ("other_bank_balances", "Other Bank Balances", "Current Assets", ["bank balances other than", "other bank balances"]),
    ("current_loans", "Current Loans & Advances", "Current Assets", ["loans (current)", "short-term loans and advances", "current loans"]),
    ("other_current_fin_assets", "Other Current Financial Assets", "Current Assets", ["other current financial assets"]),
    ("current_tax_assets", "Current Tax Assets (Net)", "Current Assets", ["current tax assets (net)", "current tax assets"]),
    ("other_current_assets", "Other Current Assets", "Current Assets", ["other current assets", "contract assets", "contract asset", "unbilled revenue", "unbilled work-in-progress", "unbilled work in progress"]),
    ("total_current_assets", "Total Current Assets", "Current Assets", ["total current assets"]),
    ("total_assets", "Total Assets", "Totals", ["total assets"]),
]

PROFIT_LOSS = [
    ("revenue", "Revenue from Operations", "Income", ["revenue from operations", "net sales", "turnover", "income from operations",
                                                       # not-for-profit (Section 8 / trust / society) income & expenditure statements
                                                       "grant income", "grants received", "income from grants", "grant-in-aid", "grants-in-aid",
                                                       "donations received", "income from donations", "contributions received",
                                                       "csr contribution received", "csr contributions received", "corpus and grant income"]),
    ("other_income", "Other Income", "Income", ["other income"]),
    ("interest_income", "of which: Interest Income", "Income", ["interest income"]),
    ("total_income", "Total Income", "Income", ["total income"]),
    ("cost_of_materials", "Cost of Materials Consumed", "Expenses", ["cost of materials consumed", "cost of raw materials consumed", "raw materials consumed", "cost of material consumed",
                                                                     "materials consumed", "cost of raw material consumed",
                                                                     "sub-contracting and other construction expenses", "subcontracting and other construction expenses",
                                                                     "sub-contracting expenses", "subcontracting expenses", "construction expenses", "project execution expenses",
                                                                     "operating expenses", "contract expenses", "direct expenses"]),
    ("purchases_stock", "Purchases of Stock-in-Trade", "Expenses", ["purchases of stock-in-trade", "purchase of stock-in-trade", "purchases of traded goods", "purchase of traded goods",
                                                                         "purchase of power", "purchase of electricity", "purchase of energy", "purchase of solar power",
                                                                         "power purchase", "cost of power purchased", "purchase of goods"]),
    ("change_in_inventories", "Changes in Inventories", "Expenses", ["changes in inventories", "change in inventories", "(increase)/decrease in inventories"]),
    ("employee_cost", "Employee Benefits Expense", "Expenses", ["employee benefits expense", "employee benefit expenses", "employee benefits expenses", "employee benefit expense", "employee cost", "employees benefit expenses"]),
    ("finance_cost", "Finance Costs", "Expenses", ["finance costs", "finance cost", "finance expense", "finance expenses", "financial expense", "financial expenses", "financial costs", "finance charges", "borrowing costs", "borrowing cost", "interest and finance charges", "interest & finance charges", "interest and other finance costs", "interest and finance expenses", "interest expense"]),
    ("depreciation", "Depreciation & Amortisation", "Expenses", ["depreciation and amortisation expense", "depreciation and amortization expense", "depreciation & amortisation", "depreciation"]),
    ("other_expenses", "Other Expenses", "Expenses", ["other expenses"]),
    ("total_expenses", "Total Expenses", "Expenses", ["total expenses", "total expenditure"]),
    ("exceptional_items", "Exceptional Items (gain +, loss -)", "Profit", ["exceptional items"]),
    ("share_jv_profit", "Share of Profit of Joint Ventures / Associates (consolidated)", "Profit",
     ["share of profit of joint venture", "share of profit of joint ventures", "share of profit/(loss) of joint venture", "share of profit of associate",
      "share of profit/(loss) of associates", "share in profit of joint venture", "share of net profit of joint venture"]),
    ("pbt", "Profit Before Tax", "Profit", ["profit before tax", "profit/(loss) before tax", "profit / (loss) before tax", "(loss)/profit before tax",
                                                   # income & expenditure statements (not-for-profit)
                                                   "(deficit)/surplus before tax", "surplus/(deficit) before tax", "surplus before tax",
                                                   "deficit before tax", "excess of income over expenditure before tax"]),
    ("tax_expense", "Total Tax Expense", "Profit", ["total tax expense", "tax expense"]),
    ("pat", "Profit After Tax", "Profit", ["profit for the year", "profit after tax", "profit/(loss) for the year", "net profit", "(loss)/profit for the year",
                                                   "(deficit)/surplus for the year", "surplus/(deficit) for the year", "surplus for the year",
                                                   "deficit for the year", "excess of income over expenditure"]),
]

CASH_FLOW = [
    ("cfo", "Net Cash from Operating Activities", "Cash Flow", ["net cash generated from operating activities", "net cash from operating activities", "net cash flow from operating activities", "net cash (used in)/generated from operating activities"]),
    ("cfi", "Net Cash from Investing Activities", "Cash Flow", ["net cash used in investing activities", "net cash from investing activities", "net cash flow from investing activities"]),
    ("cff", "Net Cash from Financing Activities", "Cash Flow", ["net cash used in financing activities", "net cash from financing activities", "net cash flow from financing activities"]),
    ("capex", "Capex (PPE, intangibles, CWIP and capital advances - outflow)", "Cash Flow",
     ["purchase of property, plant and equipment", "acquisition of property, plant and equipment", "purchase of fixed assets",
      "purchase of property plant and equipment", "purchase of ppe", "purchase of intangible assets", "acquisition of intangible assets",
      "investment in capital work in progress", "investment in capital work-in-progress", "expenditure on capital work in progress",
      "payment for capital work in progress", "additions to capital work in progress", "capital work in progress",
      "capital advances", "payment for property, plant and equipment"]),
    ("dividend_paid", "Dividend Paid", "Cash Flow", ["dividend paid", "dividends paid"]),
]

# Disclosures that are not in the face statements but matter for credit
DISCLOSURES = [
    ("contingent_liabilities", "Contingent Liabilities (not provided for)", "Notes", ["contingent liabilities"]),
    ("guarantees_given", "of which: Corporate Guarantees Given (memo)", "Notes", ["corporate guarantee", "guarantees given"]),
    ("rpt_sales", "Sales to Related Parties", "Notes", []),
    ("rpt_purchases", "Purchases from Related Parties", "Notes", []),
    ("rpt_loans_given", "Loans/Advances to Related Parties (closing)", "Notes", []),
    ("promoter_pledge_pct", "Promoter Shares Pledged (%)", "Notes", ["pledged"]),
    ("market_cap", "Market Capitalisation (if listed)", "Notes", []),
]

ALL_ITEMS = BALANCE_SHEET + PROFIT_LOSS + CASH_FLOW + DISCLOSURES
KEYS = [k for k, *_ in ALL_ITEMS]
LABELS = {k: lbl for k, lbl, *_ in ALL_ITEMS}
SECTIONS = {k: sec for k, _, sec, _ in ALL_ITEMS}

STATEMENT_OF = {}
for _k, *_ in BALANCE_SHEET:
    STATEMENT_OF[_k] = "Balance Sheet"
for _k, *_ in PROFIT_LOSS:
    STATEMENT_OF[_k] = "Profit & Loss"
for _k, *_ in CASH_FLOW:
    STATEMENT_OF[_k] = "Cash Flow"
for _k, *_ in DISCLOSURES:
    STATEMENT_OF[_k] = "Disclosures"


def empty_year():
    return {k: None for k in KEYS}


def g(d, k, default=0.0):
    """Null-safe getter: returns float or default."""
    if d is None:
        return default
    v = d.get(k)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fill_derived(y, log=None):
    """Fill totals the document did not print (or that were not read) from their components, so downstream calculations
    have inputs. Never overwrites a value that was read. Every filled value is recorded in `log` ({key: how}) so the
    checker and the reports can say it was DERIVED, not read - and so a tie-out is never 'passed' on a figure that was
    itself made to tie."""
    log = log if log is not None else {}

    def setdefault(key, value, how):
        if y.get(key) in (None, "") and value is not None:
            y[key] = round(value, 2)
            log[key] = how

    if y.get("share_capital") not in (None, "") and y.get("other_equity") not in (None, ""):  # both parts, never one alone
        setdefault("total_equity", g(y, "share_capital") + g(y, "other_equity"), "share capital + other equity (total not read)")
    ca_keys = ["inventories", "current_investments", "trade_receivables", "cash_and_equivalents",
               "other_bank_balances", "current_loans", "other_current_fin_assets", "current_tax_assets",
               "other_current_assets"]
    n_ca = sum(y.get(k) is not None for k in ca_keys)
    if n_ca >= 3:  # don't build a total from one or two stray items
        setdefault("total_current_assets", sum(g(y, k) for k in ca_keys), f"sum of {n_ca} current-asset lines read (total not read) - "
                                                                          "understated if a line was missed")
    cl_keys = ["short_term_borrowings", "lease_liabilities_c", "trade_payables",
               "other_current_fin_liabilities", "other_current_liabilities", "short_term_provisions",
               "current_tax_liabilities"]
    n_cl = sum(y.get(k) is not None for k in cl_keys)
    if n_cl >= 3:
        setdefault("total_current_liabilities", sum(g(y, k) for k in cl_keys), f"sum of {n_cl} current-liability lines read (total not read) - "
                                                                               "understated if a line was missed")
    if y.get("total_assets") in (None, "") and y.get("total_equity_and_liabilities") not in (None, ""):
        setdefault("total_assets", g(y, "total_equity_and_liabilities"), "copied from total equity & liabilities - the tally cannot be verified")
    if y.get("total_equity_and_liabilities") in (None, "") and y.get("total_assets") not in (None, ""):
        setdefault("total_equity_and_liabilities", g(y, "total_assets"), "copied from total assets - the tally cannot be verified")
    if y.get("total_income") in (None, "") and y.get("revenue") is not None:
        setdefault("total_income", g(y, "revenue") + g(y, "other_income"), "revenue + other income")
    if y.get("pat") in (None, "") and y.get("pbt") not in (None, "") and y.get("tax_expense") not in (None, ""):
        setdefault("pat", g(y, "pbt") - g(y, "tax_expense"), "PBT - tax (PAT not read)")  # never PBT - 0
    if y.get("tax_expense") in (None, "") and y.get("pbt") not in (None, "") and y.get("pat") not in (None, ""):
        setdefault("tax_expense", g(y, "pbt") - g(y, "pat"), "PBT - PAT (tax line not read)")
    return y
