"""Additional memorandum sections (structuring, projections, pricing, EWS, regulatory) and shared document helpers
used by the extra report types in report_types.py."""
import datetime as dt
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from . import analyst as AN
from . import credit_tools as CT
from . import report_word as W
from .schema import g

STAT_FILL = {"Triggered": "FEE2E2", "Not observed": "DCFCE7", "Bank data needed": "FEF3C7",
             "Within limit": "DCFCE7", "Breach": "FEE2E2", "Needs Board approval": "FEF3C7", "Adequate": "DCFCE7"}


def xr(v, d=2):
    return "n.a." if v is None else f"{v:,.{d}f}x"


def pc(v, d=1):
    return "n.a." if v is None else f"{v * 100:,.{d}f}%"


def crv(v):
    return W._fmtv(v)


# ------------------------------------------------------------------ document scaffold for the shorter reports
def new_doc(title, subtitle, bundle, officer="", branch="", confidential=True, banner=True):
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = W.FONT_BODY
    st.element.rPr.rFonts.set(qn("w:eastAsia"), W.FONT_BODY)
    st.font.size = Pt(10.5)
    W.style_headings(doc, (14, 12, 11))
    sec = doc.sections[0]
    sec.left_margin = sec.right_margin = Cm(2.0)
    sec.top_margin, sec.bottom_margin = Cm(1.6), Cm(1.6)
    company = bundle.get("company") or "Company"
    hp = sec.header.paragraphs[0]
    hp.text = f"{'STRICTLY CONFIDENTIAL  |  ' if confidential else ''}{title}  |  {company}"
    hp.runs[0].font.size, hp.runs[0].font.color.rgb = Pt(8), W.GREY
    fp = sec.footer.paragraphs[0]
    rr = fp.add_run("Page " if not banner else "Credit Intelligence Workbench - decision support; verify against source documents.   Page ")
    rr.font.size, rr.font.color.rgb = Pt(7.5), W.GREY
    W._field(fp, "PAGE")
    if not banner:
        return doc
    W.cover_band(doc, title.upper(), company, subtitle)
    W._p(doc, f"{dt.date.today():%d %B %Y}   ·   Prepared by {officer or '-'}{', ' + branch if branch else ''}", 9.5,
         color=W.GREY, space_after=12)
    return doc


def save(doc):
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ charts
def chart_dscr(rows):
    fig, ax = plt.subplots(figsize=(8, 3.0), dpi=160)
    yrs = [r_["year"] for r_ in rows]
    xs = range(len(yrs))
    acc = [r_["pat"] + r_["depreciation"] + r_["term_interest"] for r_ in rows]
    ds = [r_["term_interest"] + r_["term_principal"] for r_ in rows]
    ax.bar([i - 0.2 for i in xs], acc, 0.4, label="Cash available (PAT + dep. + term interest)", color=W.SERIES[0])
    ax.bar([i + 0.2 for i in xs], ds, 0.4, label="Term debt service (interest + principal)", color=W.SERIES[1])
    ax.set_xticks(list(xs))
    ax.set_xticklabels(yrs)
    W._style(ax)
    ax2 = ax.twinx()
    dv = [r_["dscr"] if r_["dscr"] is not None and r_["dscr"] < 10 else None for r_ in rows]
    ax2.plot(list(xs), [v if v is not None else float("nan") for v in dv], color=W.SERIES[2], marker="o", lw=2, label="DSCR")
    ax2.axhline(1.25, color="#999999", ls="--", lw=1)
    ax2.set_ylabel("DSCR (x)", fontsize=8)
    ax2.tick_params(labelsize=8)
    for s in ("top",):
        ax2.spines[s].set_visible(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, fontsize=7, loc="upper left", frameon=False)
    ax.set_ylabel("₹ crore", fontsize=8)
    return W._png(fig)


# ------------------------------------------------------------------ section builders (all take doc, bundle, p)
def proposal_snapshot(doc, b, p):
    rows, _ = CT.projections(b, p)
    s = CT.dscr_summary(rows)
    sc = CT.security_cover(b, p)
    rp = CT.risk_pricing(b, p)
    ews, n_trig = CT.rbi_ews(b, p)
    fac = []
    if p.get("tl_amount"):
        fac.append(f"Term loan ₹{p['tl_amount']:,.2f} Cr ({p.get('tl_tenor_years')} yrs incl. {p.get('tl_moratorium_months')} m moratorium, {pc(p.get('tl_rate'), 2)})")
    if p.get("cc_amount"):
        fac.append(f"Cash credit ₹{p['cc_amount']:,.2f} Cr ({pc(p.get('cc_rate'), 2)})")
    if p.get("nfb_amount"):
        fac.append(f"Non-fund based (BG/LC) ₹{p['nfb_amount']:,.2f} Cr")
    W._keyvalue(doc, [
        ["Facilities proposed", "; ".join(fac) or (p.get("facility") or "Not specified")],
        ["Purpose", p.get("purpose") or "-"],
        ["Projected DSCR (average / minimum)", f"{xr(s['avg'])} / {xr(s['min'])}" + (f" in {s['min_year']}" if s.get("min_year") else "")],
        ["Security cover (total / collateral only)", f"{xr(sc['cover'])} / {xr(sc['collateral_cover'])}"],
        ["Risk-based minimum price vs proposed", (f"{pc(rp['floor'], 2)} vs {pc(rp['proposed'], 2)}  (RAROC {pc(rp['raroc'])})" if rp.get("configured")
                                                  else "Not computed - bank PD master scale not configured")],
        ["RBI early-warning signals triggered", f"{n_trig} of {len(ews)} tested"],
    ])


def dupont_section(doc, b, num="4.8"):
    dp = CT.dupont(b)
    if not dp:
        return
    doc.add_heading(f"{num} Return on equity decomposition (DuPont) and earnings quality", 2)
    W._paras(doc, CT.dupont_commentary(dp) or ["ROE decomposition for the years analysed."])
    cols = [r_["year"] for r_ in reversed(dp)]
    lines = [("Tax burden (PAT / PBT)", "tax_burden", "x"), ("Interest burden (PBT / EBIT)", "interest_burden", "x"),
             ("Operating margin (EBIT / revenue)", "ebit_margin", "%"), ("Asset turnover (revenue / assets)", "asset_turnover", "x"),
             ("Equity multiplier (assets / equity)", "equity_multiplier", "x"), ("Return on equity", "roe", "%")]
    rows = [[lab] + [(pc if f == "%" else xr)(r_[k]) for r_ in reversed(dp)] for lab, k, f in lines]
    W._table(doc, ["DuPont component"] + cols, rows, font_size=8.5)
    eq = CT.earnings_quality(b)
    rows = [[lab] + [(pc if f == "%" else xr)(r_[k]) for r_ in reversed(eq)] for lab, k, f in
            [("Accrual ratio ((PAT - CFO) / avg. assets)", "accrual_ratio", "%"), ("CFO / PAT", "cfo_pat", "x"),
             ("Net working capital / revenue", "nwc_sales", "%"), ("Other income / PBT", "other_income_share", "%"),
             ("Exceptional items / PBT", "exceptional_share", "%")]]
    W._table(doc, ["Earnings-quality indicator"] + [r_["year"] for r_ in reversed(eq)], rows, font_size=8.5)
    W._note(doc, "A high positive accrual ratio (profits not backed by cash) and a rising share of other or exceptional income are "
                 "classic indicators of low-quality or managed earnings.")


def wc_section(doc, b, p, num="5"):
    w = CT.wc_methods(b, p)
    doc.add_heading(f"{num}.1 Comparison of assessment methods", 2)
    W._paras(doc, [f"Working-capital requirement has been assessed under the Tandon Committee methods and the turnover (Nayak Committee) "
                   f"method on projected turnover of ₹{w['proj_turnover']:,.2f} Cr (growth assumed {pc(w['growth'])}). The requested / existing "
                   f"working-capital limit of ₹{w['requested']:,.2f} Cr compares with an assessed eligibility of ₹{w['assessed']:,.2f} Cr"
                   + (f", leaving headroom of ₹{w['headroom']:,.2f} Cr." if w["headroom"] >= 0 else
                      f", an excess of ₹{-w['headroom']:,.2f} Cr that should be curtailed or justified by a cash budget.")])
    W._table(doc, ["Particulars (₹ Cr)", "Tandon Method I", "Tandon Method II", "Turnover method"],
             [[r_[0]] + [crv(v) if v is not None else "-" for v in r_[1:]] for r_ in w["rows"]], widths=[6.5, 3.4, 3.4, 3.7], font_size=8.5)
    W._note(doc, "Turnover method: working capital at 25% of projected turnover, of which 20% bank finance and 5% borrower margin "
                 "(RBI guidance for MSE borrowers up to ₹5 Cr; many banks apply it more widely).")
    dp = CT.drawing_power(b, p)
    doc.add_heading(f"{num}.2 Drawing power (from latest balance sheet)", 2)
    W._paras(doc, [f"Drawing power on the year-end stock and receivables works out to ₹{dp['dp']:,.2f} Cr against a limit of "
                   f"₹{dp['limit']:,.2f} Cr" + (f"; the DP shortfall of ₹{dp['shortfall']:,.2f} Cr means the full limit cannot be drawn on "
                                                  "current-asset levels." if dp["shortfall"] > 0 else "; the limit is fully covered by drawing power.")
                   + " Drawing power must be recomputed monthly from the stock and book-debt statement."])
    W._table(doc, ["Drawing-power computation", "₹ Cr"], [[a, crv(v)] for a, v in dp["rows"]], widths=[11, 5], font_size=8.5)


def repayment_section(doc, b, p, num="6"):
    rows, a = CT.projections(b, p)
    s = CT.dscr_summary(rows)
    if p.get("tl_amount"):
        sched, inst, n = CT.amortisation(p["tl_amount"], p.get("tl_tenor_years"), p.get("tl_moratorium_months") or 0, p.get("tl_rate") or 0.1)
        doc.add_heading(f"{num}.1 Proposed term loan and repayment schedule", 2)
        W._paras(doc, [f"Term loan of ₹{p['tl_amount']:,.2f} Cr over {p.get('tl_tenor_years')} years including a moratorium of "
                       f"{p.get('tl_moratorium_months')} months, repayable in {n} equal quarterly instalments of ₹{inst:,.3f} Cr, with interest "
                       f"at {pc(p.get('tl_rate'), 2)} serviced as applied."])
        W._table(doc, ["Year", "Opening", "Interest", "Principal", "Closing"],
                 [[f"Y+{r_['year']}", crv(r_["opening"]), crv(r_["interest"]), crv(r_["principal"]), crv(r_["closing"])] for r_ in sched],
                 widths=[2.5, 3.6, 3.6, 3.6, 3.7], font_size=8.5)
    sub = 2 if p.get("tl_amount") else 1
    doc.add_heading(f"{num}.{sub} Projected financials and debt-service coverage", 2)
    no_debt = not any((r_.get("interest") or 0) + (r_.get("term_principal") or 0) > 0.005 for r_ in rows)
    W._paras(doc, [f"Projections assume revenue growth of {pc(a['growth'])} a year, an EBITDA margin of {pc(a['margin'])}, existing term debt of "
                   f"₹{a['existing_ltd']:,.2f} Cr running off over {a['existing_ltd_years']} years at {pc(a['debt_rate'])}, and working-capital "
                   f"borrowings of ₹{a['wc_debt']:,.2f} Cr at {pc(a['wc_rate'])}. Tax is provided at 25.17%.",
                   f"On these assumptions the average DSCR over the projection period is {xr(s['avg'])} and the minimum is {xr(s['min'])}"
                   + (f" ({s['min_year']})" if s.get("min_year") else "") + ". "
                   + ("There is no existing or proposed debt to service, so DSCR does not apply; enter the proposed facility on the Proposal "
                      "page to test repayment capacity." if no_debt else
                      "Both are above the usual 1.25x / 1.10x thresholds." if (s["min"] or 0) >= 1.10 and (s["avg"] or 0) >= 1.25 else
                      "Coverage falls below the usual thresholds (average 1.25x, minimum 1.10x); the repayment schedule should be restructured "
                      "(longer tenor, ballooning, or lower quantum) or additional cash flows identified.")])
    if rows:
        doc.add_picture(chart_dscr(rows), width=Cm(16.5))
        W._note(doc, "Figure - Projected cash available for term-debt service against debt service, with DSCR (dashed line = 1.25x).")
        lines = [("Revenue", "revenue", "cr"), ("EBITDA", "ebitda", "cr"), ("EBITDA margin", "margin", "%"), ("Depreciation", "depreciation", "cr"),
                 ("Interest (total)", "interest", "cr"), ("Profit before tax", "pbt", "cr"), ("Profit after tax", "pat", "cr"),
                 ("Cash accruals (PAT + dep.)", "cash_accruals", "cr"), ("Term-debt principal due", "term_principal", "cr"),
                 ("Surplus after term repayment", "surplus", "cr"), ("DSCR", "dscr", "x"), ("Interest coverage", "icr", "x"),
                 ("Net worth (closing)", "net_worth", "cr"), ("TOL / TNW", "tol_tnw", "x"), ("Debt / EBITDA", "debt_ebitda", "x")]
        tab = [[lab] + [(pc(r_[k]) if f == "%" else xr(r_[k]) if f == "x" else crv(r_[k])) for r_ in rows] for lab, k, f in lines]
        W._table(doc, ["Projection (₹ Cr)"] + [r_["year"] for r_ in rows], tab, font_size=8)
    sc = CT.scenarios(b, p)
    be = CT.breakeven(b, p)
    if no_debt:
        return sub + 1  # scenarios on DSCR are meaningless without debt service
    doc.add_heading(f"{num}.{sub + 1} Scenario analysis and break-even", 2)
    W._paras(doc, ["Four scenarios flex revenue growth, EBITDA margin and interest rates together over the full projection period. "
                   + (f"Break-even analysis shows projected EBITDA can fall by about {be:.0%} in every year before the minimum DSCR drops "
                      f"below 1.00x." if be not in (None, 0.0) else
                      "Even the base case does not hold minimum DSCR at 1.00x, so there is no cushion against an EBITDA decline." if be == 0.0 else "")])
    W._table(doc, ["Scenario", "Growth", "Margin shift", "Rate shift", "Avg DSCR", "Min DSCR", "Y+1 ICR", "Cum. surplus ₹ Cr"],
             [([s_["scenario"], pc(s_["growth"]), f"{s_['margin_shift'] * 100:+.1f} pp", f"{s_['rate_shift'] * 1e4:+.0f} bp", xr(s_["avg_dscr"]),
                xr(s_["min_dscr"]), xr(s_["y1_icr"]), crv(s_["cum_surplus"])],
               {5: "DCFCE7" if (s_["min_dscr"] or 0) >= 1.1 else "FEF3C7" if (s_["min_dscr"] or 0) >= 1.0 else "FEE2E2"}) for s_ in sc],
             widths=[2.8, 1.8, 2.0, 1.8, 1.9, 1.9, 1.9, 2.9], font_size=8)
    return sub + 2


def ews_section(doc, b, p, num="7.2"):
    ews, n = CT.rbi_ews(b, p)
    doc.add_heading(f"{num} RBI early-warning signals", 2)
    W._paras(doc, [f"The account was tested against the early-warning signals listed in the RBI framework for fraud risk management. "
                   f"{n} signal(s) are triggered on the information available. {CT.ews_action(n)} Signals marked 'Bank data needed' "
                   "depend on account conduct, bank statements or registry searches and must be confirmed by the branch."])
    W._table(doc, ["Early-warning signal", "Status", "Basis"], [([a, s_, c_], {1: STAT_FILL.get(s_)}) for a, s_, c_ in ews],
             widths=[7, 2.6, 7.4], font_size=8)


def security_pricing_section(doc, b, p, num="12"):
    sc = CT.security_cover(b, p)
    doc.add_heading(f"{num}.1 Security and collateral cover", 2)
    W._paras(doc, [f"Primary security: {p.get('primary_security')}. Collateral: {p.get('collateral_type')} valued at ₹{p.get('collateral_value') or 0:,.2f} Cr. "
                   f"Guarantee: {p.get('guarantee')}.",
                   f"Total security cover is {xr(sc['cover'])} of total borrowings including existing lenders, who share the current and fixed assets "
                   f"pari-passu (exclusive collateral alone covers {xr(sc['collateral_cover'])} of the proposed exposure); the fixed-asset "
                   f"coverage ratio (net fixed assets / term debt) is {xr(sc['facr'])}"
                   + (", below the usual 1.25x - consider additional collateral." if (sc["facr"] or 0) < 1.25 else ".")])
    W._table(doc, ["Security", "₹ Cr"], [[a, crv(v)] for a, v in sc["rows"]] +
             [["Security cover (x)", xr(sc["cover"])], ["Fixed-asset coverage ratio (x)", xr(sc["facr"])],
              ["Loan-to-value on fixed assets + collateral", pc(sc["ltv"])]], widths=[11, 5], font_size=8.5)
    W._note(doc, "Book values are used for current and fixed assets; obtain valuation reports from bank-empanelled valuers and apply the bank's margins.")
    rp = CT.risk_pricing(b, p)
    doc.add_heading(f"{num}.2 Risk-based pricing and return on capital", 2)
    if not rp.get("configured"):
        W._paras(doc, ["Risk-based pricing is not computed because the bank's PD master scale has not been configured by the administrator. "
                       "No placeholder default probabilities are used."])
    else:
        W._paras(doc, [f"Expected loss is estimated at {pc(rp['el_rate'], 2)} a year (PD {pc(rp['pd'], 2)} for grade {rp['grade']} x LGD {pc(rp['lgd'])}). "
                   f"Adding the cost of funds, operating cost and a charge for regulatory capital gives a risk-based hurdle of {pc(rp['hurdle'], 2)}; "
                   f"the minimum price is {pc(rp['floor'], 2)}. At the proposed rate of {pc(rp['proposed'], 2)} the risk-adjusted return on capital is "
                   f"{pc(rp['raroc'])}" + (", above the target return." if (rp["raroc"] or 0) >= p.get("target_roe", 0.15) else
                                           ", below the target return - the pricing should be revisited or the exposure better secured.")])
    W._table(doc, ["Pricing component", "Value"], rp["rows"], widths=[10, 7], font_size=8.5)
    W._note(doc, "PD from the bank's master scale (Admin › Bank parameters); haircut, cost of funds, operating cost and capital ratio as entered "
                 "under Proposal › Bank policy parameters.")
    doc.add_heading(f"{num}.3 Regulatory and policy compliance", 2)
    W._table(doc, ["Check", "Position", "Result"], [([a, b_, c_], {2: STAT_FILL.get(c_)}) for a, b_, c_ in CT.regulatory(b, p)],
             widths=[7.5, 4.5, 5], font_size=8.5)


def coverage_table(doc, b):
    from . import db as _db
    from . import watchlist as _wl
    scr = b.get("screening") or {}
    try:
        ents = _db.wl_entries()
    except Exception:
        ents = []
    rows = _wl.coverage(ents, scr if scr.get("summary") else None, scr.get("attest"))
    W._p(doc, "Screening coverage - defaulter, fraud and regulatory sources", 10.5, bold=True, space_after=2)
    W._table(doc, ["Source", "Automated list", "List result", "Officer check", "Status"],
             [([r_["source"], r_["list"], r_["auto"], r_["officer"], r_["overall"]],
               {4: "FEE2E2" if r_["overall"].startswith(("ADVERSE", "NOT")) else "DCFCE7"}) for r_ in rows],
             widths=[4.6, 3.4, 2.2, 4.0, 2.8], font_size=7.5)
    n_nc = sum(1 for r_ in rows if r_["overall"] == "NOT CHECKED")
    W._note(doc, (f"{n_nc} source(s) NOT CHECKED - the credit file is incomplete until each is checked and recorded on the Fraud screening page. "
                  if n_nc else "All required sources are checked. ")
            + "CFR, CRILC and non-suit-filed CIC data are bank-login sources and cannot be queried by this system; the officer records the result.")


def screening_section(doc, b, num="7.3", level=2):
    scr = b.get("screening") or {}
    doc.add_heading(f"{num} Fraud, defaulter and regulatory watch-list screening", level)
    coverage_table(doc, b)
    sm = scr.get("summary")
    if not sm:
        W._paras(doc, ["Watch-list screening was not run for this memorandum. Screen the borrower, its directors, promoters, guarantors and "
                       "related parties against the wilful-defaulter / suit-filed lists (TransUnion CIBIL), SEBI debarment orders, MCA "
                       "disqualified directors and struck-off companies, RBI alert lists, IBBI insolvency announcements and the bank's own "
                       "fraud / RFA list before sanction."])
        return
    hits = scr.get("hits") or []
    W._paras(doc, [f"On {sm.get('when')}, {sm.get('parties')} parties (borrower, auditor, directors / promoters / guarantors and entities named "
                   f"in the documents) were screened against {sm.get('entries')} entries on {sm.get('lists')} list(s)"
                   + (" and the OpenSanctions sanctions / PEP database" if scr.get("online") else "")
                   + f". {len(hits)} potential match(es) were found, {sm.get('high', 0)} of high severity. "
                   + ("Name matches are indicative only; identity must be confirmed with CIN / DIN / PAN before any adverse view is taken."
                      if hits else "No party matched any list entry.")])
    if hits:
        W._table(doc, ["Party (role)", "Listed as", "List", "Match", "Score"],
                 [([f"{h['party']} ({h['role']})", h["listed_name"] + (f" [{h['listed_id']}]" if h["listed_id"] else ""), h["list"],
                    h["match"], str(h["score"])], {3: W.SEV_FILL.get(h["severity"])}) for h in hits[:25]],
                 widths=[4.6, 4.2, 3.0, 4.2, 1.0], font_size=7.5)
    parties = scr.get("parties") or []
    if parties:
        W._note(doc, "Parties screened: " + "; ".join(f"{p['name']} ({p['role']})" for p in parties[:30]) + ("..." if len(parties) > 30 else ""))
