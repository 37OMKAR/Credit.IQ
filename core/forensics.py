"""Forensic engine: hidden-risk / fund-siphoning red flags, Beneish M-score,
Piotroski F-score and a transparent internal credit score."""
from . import schema
from .ratios import status

g = schema.g


def _pct(a, b):
    return None if not b else a / b - 1


def beneish(cur, prev):
    """8-variable Beneish M-score. > -1.78 suggests likely earnings manipulation."""
    try:
        s1, s0 = g(cur, "revenue"), g(prev, "revenue")
        if not s1 or not s0:
            return None, {}
        rec1, rec0 = g(cur, "trade_receivables"), g(prev, "trade_receivables")
        cogs1, cogs0 = g(cur, "cogs"), g(prev, "cogs")
        ta1, ta0 = g(cur, "total_assets"), g(prev, "total_assets")
        ca1, ca0 = g(cur, "total_current_assets"), g(prev, "total_current_assets")
        ppe1, ppe0 = g(cur, "ppe"), g(prev, "ppe")
        sec1, sec0 = g(cur, "nc_investments"), g(prev, "nc_investments")
        dep1, dep0 = g(cur, "depreciation"), g(prev, "depreciation")
        sga1, sga0 = g(cur, "other_expenses") + g(cur, "employee_cost"), g(prev, "other_expenses") + g(prev, "employee_cost")
        cl1, cl0 = g(cur, "total_current_liabilities"), g(prev, "total_current_liabilities")
        ltd1, ltd0 = g(cur, "long_term_borrowings"), g(prev, "long_term_borrowings")
        gm1 = (s1 - cogs1) / s1 if cogs1 else None
        gm0 = (s0 - cogs0) / s0 if cogs0 else None
        v = {}
        v["DSRI"] = (rec1 / s1) / (rec0 / s0) if rec0 else 1.0
        v["GMI"] = gm0 / gm1 if (gm0 is not None and gm1) else 1.0
        aq1 = 1 - (ca1 + ppe1 + sec1) / ta1 if ta1 else 0
        aq0 = 1 - (ca0 + ppe0 + sec0) / ta0 if ta0 else 0
        v["AQI"] = aq1 / aq0 if aq0 else 1.0
        v["SGI"] = s1 / s0
        d1 = dep1 / (dep1 + ppe1) if (dep1 + ppe1) else 0
        d0 = dep0 / (dep0 + ppe0) if (dep0 + ppe0) else 0
        v["DEPI"] = d0 / d1 if d1 else 1.0
        v["SGAI"] = (sga1 / s1) / (sga0 / s0) if sga0 else 1.0
        lv1 = (cl1 + ltd1) / ta1 if ta1 else 0
        lv0 = (cl0 + ltd0) / ta0 if ta0 else 0
        v["LVGI"] = lv1 / lv0 if lv0 else 1.0
        v["TATA"] = (g(cur, "pat") - g(cur, "cfo")) / ta1 if ta1 else 0
        m = (-4.84 + 0.92 * v["DSRI"] + 0.528 * v["GMI"] + 0.404 * v["AQI"] + 0.892 * v["SGI"]
             + 0.115 * v["DEPI"] - 0.172 * v["SGAI"] + 4.679 * v["TATA"] - 0.327 * v["LVGI"])
        return round(m, 2), {k: round(x, 3) for k, x in v.items()}
    except Exception:
        return None, {}


def piotroski(cur, prev):
    try:
        ta1, ta0 = g(cur, "total_assets"), g(prev, "total_assets")
        if not ta1 or not ta0:
            return None, {}
        roa1, roa0 = g(cur, "pat") / ta1, g(prev, "pat") / ta0
        tests = {
            "Positive ROA": roa1 > 0,
            "Positive CFO": g(cur, "cfo") > 0,
            "ROA improving": roa1 > roa0,
            "CFO > PAT (accrual quality)": g(cur, "cfo") > g(cur, "pat"),
            "Leverage falling": (g(cur, "long_term_borrowings") / ta1) <= (g(prev, "long_term_borrowings") / ta0),
            "Current ratio improving": (g(cur, "total_current_assets") / max(g(cur, "total_current_liabilities"), 1e-9))
            > (g(prev, "total_current_assets") / max(g(prev, "total_current_liabilities"), 1e-9)),
            "No equity dilution": g(cur, "share_capital") <= g(prev, "share_capital") + 1e-6,
            "Gross margin improving": ((g(cur, "revenue") - g(cur, "cogs")) / max(g(cur, "revenue"), 1e-9))
            > ((g(prev, "revenue") - g(prev, "cogs")) / max(g(prev, "revenue"), 1e-9)),
            "Asset turnover improving": g(cur, "revenue") / ta1 > g(prev, "revenue") / ta0,
        }
        return sum(1 for v in tests.values() if v), tests
    except Exception:
        return None, {}


def _flag(flags, title, category, severity, year, evidence, why, action):
    flags.append({"title": title, "category": category, "severity": severity, "year": year,
                  "evidence": evidence, "why": why, "action": action, "source": "Quantitative"})


def run(enriched, ratios, years, notes=None, news=None, extra_flags=None, remarks=None):
    """Return dict(flags, beneish, piotroski, score, grade)."""
    flags = []
    y0 = years[0]
    cur = enriched[y0]
    prev = enriched[years[1]] if len(years) > 1 else None
    r0 = ratios[y0]

    # ---------- data integrity
    for y in years:
        ta, tel = g(enriched[y], "total_assets"), g(enriched[y], "total_equity_and_liabilities")
        if ta and tel and abs(ta - tel) / ta > 0.01:
            _flag(flags, "Balance sheet does not tally", "Data integrity", "Medium", y,
                  f"Total assets {ta:,.2f} vs equity & liabilities {tel:,.2f} Cr",
                  "Either an extraction error or an incomplete statement.", "Re-check extracted figures against the PDF.")

    # ---------- siphoning / diversion checks
    if prev:
        d_debt = g(cur, "total_debt") - g(prev, "total_debt")
        capex = abs(g(cur, "capex"))
        d_wc = (g(cur, "inventories") + g(cur, "trade_receivables") - g(cur, "trade_payables")) - \
               (g(prev, "inventories") + g(prev, "trade_receivables") - g(prev, "trade_payables"))
        d_la = g(cur, "loans_advances") - g(prev, "loans_advances")
        d_inv = g(cur, "nc_investments") - g(prev, "nc_investments")
        d_oth = (g(cur, "other_current_assets") + g(cur, "other_nc_assets") + g(cur, "other_current_fin_assets") + g(cur, "other_nc_fin_assets") + g(cur, "capital_advances")) - \
                (g(prev, "other_current_assets") + g(prev, "other_nc_assets") + g(prev, "other_current_fin_assets") + g(prev, "other_nc_fin_assets") + g(prev, "capital_advances"))
        if d_debt > 0 and g(cur, "total_debt") > 0:
            productive = capex + max(d_wc, 0)
            unexplained = d_debt - productive
            if unexplained > 0.2 * d_debt and unexplained > 0.02 * g(cur, "total_assets"):
                where = []
                if d_la > 0: where.append(f"loans & advances +{d_la:,.1f}")
                if d_inv > 0: where.append(f"investments +{d_inv:,.1f}")
                if d_oth > 0: where.append(f"other assets / capital advances +{d_oth:,.1f}")
                _flag(flags, "Borrowed funds not visibly deployed in business (end-use gap)", "Fund diversion",
                      "High" if unexplained > 0.5 * d_debt else "Medium", y0,
                      f"Debt rose {d_debt:,.1f} Cr but capex {capex:,.1f} + working-capital build {max(d_wc,0):,.1f}. "
                      f"Gap {unexplained:,.1f} Cr. Moved to: {', '.join(where) or 'not traceable from face statements'}",
                      "Classic indicator of diversion/siphoning of bank funds to group or unrelated purposes.",
                      "Obtain end-use certificate (CA), lender-wise utilisation, bank statements of disbursement accounts.")
        if d_la > 0 and g(cur, "total_equity") and d_la / g(cur, "total_equity") > 0.10:
            _flag(flags, "Sharp rise in loans & advances given", "Fund diversion", "High", y0,
                  f"Loans & advances up {d_la:,.1f} Cr ({d_la / g(cur, 'total_equity'):.0%} of net worth)",
                  "Loans to group/related entities are a common siphoning route.",
                  "Get party-wise list, interest charged, board approval u/s 186, recoverability.")
        if d_inv > 0 and d_debt > 0 and g(cur, "total_equity") and d_inv / g(cur, "total_equity") > 0.10:
            _flag(flags, "Debt-funded investments in other entities", "Fund diversion", "Medium", y0,
                  f"Non-current investments up {d_inv:,.1f} Cr while debt up {d_debt:,.1f} Cr",
                  "Borrowed money upstreamed to subsidiaries/associates is outside the lender's charge.",
                  "Identify investee companies, their financials and whether funded by term loan.")

        # receivables & inventory build-up
        if r0.get("recv_vs_rev") is not None and r0["recv_vs_rev"] > 0.15:
            _flag(flags, "Receivables growing much faster than revenue", "Revenue quality", "High" if r0["recv_vs_rev"] > 0.3 else "Medium", y0,
                  f"Receivable growth exceeds sales growth by {r0['recv_vs_rev']:.0%}",
                  "Possible fictitious / channel-stuffed sales or rising bad debts.",
                  "Debtor ageing, top-10 debtors, related-party debtors, post-balance-sheet collections.")
        dd0, dd1 = ratios[y0].get("debtor_days"), ratios[years[1]].get("debtor_days")
        if dd0 and dd1 and dd0 - dd1 > 30:
            _flag(flags, "Debtor days stretched", "Working capital", "Medium", y0,
                  f"Debtor days {dd1:,.0f} -> {dd0:,.0f}", "Cash locked in receivables; collection risk.", "Obtain ageing schedule.")
        id0, id1 = ratios[y0].get("inventory_days"), ratios[years[1]].get("inventory_days")
        if id0 and id1 and id0 - id1 > 30:
            _flag(flags, "Inventory build-up", "Working capital", "Medium", y0,
                  f"Inventory days {id1:,.0f} -> {id0:,.0f}", "Slow-moving / obsolete or inflated stock.",
                  "Stock audit, stock statements vs books reconciliation (DP vs books).")
        if g(cur, "revenue") > g(prev, "revenue") and g(cur, "cfo") < g(prev, "cfo"):
            _flag(flags, "Revenue up but operating cash flow down", "Earnings quality", "Medium", y0,
                  f"Revenue {g(prev,'revenue'):,.1f} -> {g(cur,'revenue'):,.1f}; CFO {g(prev,'cfo'):,.1f} -> {g(cur,'cfo'):,.1f}",
                  "Profits not converting to cash.", "Reconcile PAT to CFO; check working-capital movements.")
        if g(prev, "intangibles") and g(cur, "intangibles") / g(prev, "intangibles") > 1.5 and g(cur, "intangibles") > 0.03 * g(cur, "total_assets"):
            _flag(flags, "Large jump in intangible assets", "Asset quality", "Medium", y0,
                  f"Intangibles {g(prev,'intangibles'):,.1f} -> {g(cur,'intangibles'):,.1f} Cr",
                  "Capitalising expenses inflates profit and net worth.", "Obtain capitalisation policy and valuation.")
        if g(prev, "cwip") and g(cur, "cwip") >= g(prev, "cwip") * 0.9 and r0.get("cwip_ppe") and r0["cwip_ppe"] > 0.3:
            _flag(flags, "Capital work-in-progress stuck / ballooning", "Asset quality", "Medium", y0,
                  f"CWIP {g(prev,'cwip'):,.1f} -> {g(cur,'cwip'):,.1f} Cr ({r0['cwip_ppe']:.0%} of net block)",
                  "Stalled projects or capex money diverted while shown as CWIP.", "CWIP ageing schedule (Schedule III), LIE report, site visit.")
        if g(cur, "share_capital") > g(prev, "share_capital") * 1.05:
            _flag(flags, "Fresh equity issued", "Capital structure", "Low", y0,
                  f"Share capital {g(prev,'share_capital'):,.2f} -> {g(cur,'share_capital'):,.2f} Cr",
                  "Check source of promoter contribution (may be borrowed / circular).", "Bank trail of share application money.")

    # ---------- single-year checks
    lf, td = g(cur, "liquid_funds"), g(cur, "total_debt")
    if td > 0 and lf > 0.25 * td and (r0.get("debt_ebitda") or 0) > 2.5:
        cy = r0.get("cash_yield")
        _flag(flags, "Cash-rich yet heavily borrowed", "Fund diversion", "High" if (cy is not None and cy < 0.03) else "Medium", y0,
              f"Liquid funds {lf:,.1f} Cr vs debt {td:,.1f} Cr" + (f"; yield on cash only {cy:.1%}" if cy is not None else ""),
              "Borrowing expensively while holding cash is irrational unless the cash is encumbered, lien-marked or not real (cf. Satyam-type cases).",
              "Bank balance confirmations directly from banks; check lien/FD under DSRA; interest received trail.")
    elif r0.get("cash_yield") is not None and r0["cash_yield"] < 0.02 and lf > 0.05 * g(cur, "total_assets"):
        _flag(flags, "Very low yield on cash & investments", "Fund diversion", "Medium", y0,
              f"Interest income / liquid funds = {r0['cash_yield']:.1%}", "Cash may be idle in current a/c, encumbered or overstated.",
              "Direct bank confirmations.")
    ir = r0.get("implied_rate")
    if ir is not None and td > 0.1 * g(cur, "total_assets"):
        if ir < 0.05:
            _flag(flags, "Implied interest rate unusually low", "Hidden liabilities", "Medium", y0,
                  f"Finance cost / debt = {ir:.1%}", "Possible interest capitalised into CWIP, year-end debt window-dressing or off-book debt.",
                  "Monthly average debt from CIBIL/CRILC, borrowing cost capitalised (Ind AS 23).")
        elif ir > 0.15:
            _flag(flags, "Very high cost of borrowing", "Liquidity stress", "Medium", y0,
                  f"Finance cost / debt = {ir:.1%}", "Suggests reliance on NBFC / private / ICD money - stress signal.", "Lender-wise borrowing list.")
    oi = r0.get("other_inc_pbt")
    if oi is not None and g(cur, "pbt") > 0 and oi > 0.3:
        _flag(flags, "Profit depends on other income", "Earnings quality", "Medium", y0,
              f"Other income = {oi:.0%} of PBT", "Core operations may be loss-making.", "Break-up of other income; is it recurring?")
    etr = r0.get("etr")
    if etr is not None and g(cur, "pbt") > 0 and etr < 0.10:
        _flag(flags, "Abnormally low tax rate", "Earnings quality", "Low", y0,
              f"Effective tax {etr:.1%} vs statutory ~25%", "Profits may be book-only (not taxable) or tax holidays; verify.", "Tax computation, ITR.")
    if g(cur, "pat") > 0 and g(cur, "cfo") < 0:
        sev = "High" if (prev and g(prev, "pat") > 0 and g(prev, "cfo") < 0) else "Medium"
        _flag(flags, "Profitable on paper, cash-negative operations", "Earnings quality", sev, y0,
              f"PAT {g(cur,'pat'):,.1f} Cr vs CFO {g(cur,'cfo'):,.1f} Cr", "Aggressive revenue recognition or working-capital stress.", "Accrual analysis; debtor quality.")
    oth = g(cur, "other_current_assets") + g(cur, "other_nc_assets") + g(cur, "other_current_fin_assets") + g(cur, "other_nc_fin_assets")
    if g(cur, "total_assets") and oth / g(cur, "total_assets") > 0.12:
        _flag(flags, "Large 'other' assets", "Hidden items", "Medium", y0,
              f"Other assets {oth:,.1f} Cr = {oth / g(cur,'total_assets'):.0%} of total assets",
              "'Other' buckets often hide advances to related parties, claims, or unrecoverable items.", "Note-wise break-up.")
    if g(cur, "ppe") and g(cur, "capital_advances") / g(cur, "ppe") > 0.10:
        _flag(flags, "High capital advances", "Fund diversion", "Medium", y0,
              f"Capital advances {g(cur,'capital_advances'):,.1f} Cr", "Advances to vendors (often related) for capex that never arrives.", "Vendor names, contract, delivery schedule.")
    cl = r0.get("cl_nw")
    if cl is not None and cl > 0.5:
        _flag(flags, "Contingent liabilities large vs net worth", "Hidden liabilities", "High" if cl > 1 else "Medium", y0,
              f"Contingent liabilities (incl. guarantees) = {cl:.0%} of net worth", "Crystallisation could wipe out equity.", "Nature, probability, litigation status.")
    la = r0.get("la_nw")
    if la is not None and la > 0.25:
        _flag(flags, "High loans & advances relative to net worth", "Fund diversion", "Medium", y0,
              f"Loans & advances = {la:.0%} of net worth", "Lending is not the borrower's business - possible diversion.", "Party-wise details.")
    rr = r0.get("rpt_rev")
    if rr is not None and rr > 0.25:
        _flag(flags, "Heavy related-party trading", "Related parties", "High" if rr > 0.5 else "Medium", y0,
              f"RPT sales+purchases = {rr:.0%} of revenue", "Transfer-pricing, round-tripping, profit shifting.", "Arm's-length evidence; audit committee approvals.")
    if g(cur, "promoter_pledge_pct") > 25:
        _flag(flags, "High promoter pledge", "Governance", "High" if g(cur, "promoter_pledge_pct") > 50 else "Medium", y0,
              f"{g(cur,'promoter_pledge_pct'):.1f}% of promoter holding pledged", "Promoter liquidity stress; control-change risk.", "Shareholding pattern trend.")
    if r0.get("nwc_cr") is not None and r0["nwc_cr"] < 0:
        _flag(flags, "Negative net working capital", "Liquidity stress", "Medium", y0,
              f"NWC {r0['nwc_cr']:,.1f} Cr", "Short-term funds financing long-term assets (ALM mismatch).", "Check diversion of WC limits to capex.")

    # ---------- scores
    bm, bv = beneish(cur, prev) if prev else (None, {})
    if bm is not None and bm > -1.78:
        _flag(flags, "Beneish M-score indicates possible earnings manipulation", "Earnings quality", "High", y0,
              f"M-score {bm} (threshold -1.78)", "Statistical model of manipulators (DSRI, TATA, AQI drivers).", "Deep-dive on the highest index components.")
    pf, pt = piotroski(cur, prev) if prev else (None, {})
    z = r0.get("altman_z")
    if z is not None and z < 1.1:
        _flag(flags, "Altman Z'' in distress zone", "Distress", "High", y0, f"Z'' = {z:.2f}", "Elevated default probability.", "Stress-test cash flows.")

    # ---------- qualitative (from notes review)
    if notes and notes.get("available"):
        op = (notes.get("auditor_opinion") or "").lower()
        if op in ("qualified", "adverse", "disclaimer"):
            _flag(flags, f"Auditor opinion: {op.upper()}", "Audit", "High", y0, (notes.get("qualification_text") or "")[:400],
                  "Auditor could not confirm the accounts are true and fair.", "Obtain management response; quantify impact.")
        if notes.get("going_concern_uncertainty"):
            _flag(flags, "Material uncertainty on going concern", "Audit", "High", y0, "Auditor report", "Survival doubt.", "Restructuring / cash-flow plan.")
        for e in (notes.get("emphasis_of_matter") or [])[:5]:
            _flag(flags, "Emphasis of matter", "Audit", "Medium", y0, str(e)[:400], "Auditor highlighted a significant uncertainty.", "Understand financial impact.")
        for e in (notes.get("caro_adverse_remarks") or [])[:8]:
            _flag(flags, "CARO adverse remark", "Audit", "Medium", y0, str(e)[:400], "Statutory auditor reported a control/compliance failure.", "Seek explanation and rectification.")
        for e in (notes.get("defaults_or_delays") or [])[:5]:
            _flag(flags, "Default / delay disclosed", "Repayment track", "High", y0, str(e)[:400], "Direct evidence of repayment stress.", "CIBIL/CRILC check, lender confirmation.")
        ai = notes.get("method") != "keyword scan"
        for rf in (notes.get("red_flags") or [])[:15]:
            flags.append({"title": rf.get("title", "Red flag"), "category": "Notes review (AI)" if ai else "Notes review (keyword scan)", "severity": rf.get("severity", "Medium"),
                          "year": y0, "evidence": (rf.get("evidence") or "") + (f" [p.{rf['page']}]" if rf.get("page") else ""),
                          "why": rf.get("why") or "Identified in auditor report / notes.", "action": rf.get("action") or "Read the cited page; obtain management explanation.", "source": "AI" if ai else "Keyword"})

    # ---------- adverse news
    if news:
        for n in news:
            if n.get("severity") == "High" and n.get("sentiment") == "Negative":
                flags.append({"title": f"Adverse news: {n.get('category','')}", "category": "Market intelligence", "severity": "High",
                              "year": "", "evidence": f"{n.get('title','')} ({n.get('source','')}, {n.get('date','')})",
                              "why": n.get("summary", ""), "action": "Independent verification; check CRILC/RBI wilful defaulter list.", "source": "News"})

    for ef in extra_flags or []:
        flags.append({"title": ef.get("title", "Red flag"), "category": ef.get("category", "Supporting documents"),
                      "severity": ef.get("severity", "Medium") if ef.get("severity") in ("High", "Medium", "Low") else "Medium",
                      "year": y0, "evidence": ef.get("evidence", ""), "why": ef.get("why") or "Found in supporting documents.",
                      "action": ef.get("action", "Verify with the borrower / source document."), "source": ef.get("source", "Supporting docs")})
    # officer's disposition of each flag: 'Resolved' flags no longer reduce the score
    remarks = remarks or {}
    for fl in flags:
        r = remarks.get(flag_id(fl)) or {}
        fl["status"] = r.get("status", "Open")
        fl["remark"] = r.get("remark", "")
    score, grade, breakdown = credit_score(ratios[y0], [fl for fl in flags if fl["status"] != "Resolved - not a concern"])
    return {"flags": flags, "beneish": bm, "beneish_vars": bv, "piotroski": pf, "piotroski_tests": pt,
            "altman_z": z, "score": score, "grade": grade, "score_breakdown": breakdown}


def flag_id(fl):
    import re as _re
    return _re.sub(r"\W+", "", (fl.get("title", "") + "|" + str(fl.get("evidence", ""))[:50]).lower())[:80]


FLAG_STATUSES = ["Open", "Explanation sought", "Mitigated by condition", "Resolved - not a concern"]


SCORE_WEIGHTS = {  # ratio: weight (points out of 70 for financial strength)
    "current_ratio": 6, "tol_tnw": 8, "de": 6, "debt_ebitda": 8, "icr": 8, "dscr": 8,
    "ebitda_margin": 5, "roce": 5, "cfo_ebitda": 6, "debtor_days": 4, "altman_z": 6,
}
SEV_PENALTY = {"High": 6, "Medium": 3, "Low": 1}

GRADES = [(80, "CI-1", "Very low risk"), (70, "CI-2", "Low risk"), (60, "CI-3", "Moderate-low risk"),
          (50, "CI-4", "Moderate risk"), (40, "CI-5", "Elevated risk"), (30, "CI-6", "High risk"), (-999, "CI-7", "Very high risk")]


def credit_score(r, flags):
    fin, avail = 0.0, 0.0
    breakdown = []
    for k, w in SCORE_WEIGHTS.items():
        st = status(k, r.get(k))
        if st is None:
            continue
        pts = {"good": 1.0, "watch": 0.5, "bad": 0.0}[st] * w
        fin += pts
        avail += w
        breakdown.append((k, st, pts, w))
    fin_score = (fin / avail * 70) if avail else 35
    penalty = min(sum(SEV_PENALTY.get(f["severity"], 0) for f in flags), 40)
    total = max(0, min(100, fin_score + 30 - penalty))
    grade = next(f"{gname} - {desc}" for th, gname, desc in GRADES if total >= th)
    return round(total, 1), grade, {"financial_strength": round(fin_score, 1), "of": 70,
                                    "red_flag_penalty": penalty, "items": breakdown}
