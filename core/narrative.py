"""Credit narrative: the LLM writes the committee-ready prose from numbers we computed
(it never computes numbers itself). A template fallback works without a key."""
import json

from . import ratios as R
from . import schema

NARR_SYSTEM = """You are the head of credit appraisal at an Indian scheduled commercial bank writing a credit appraisal memorandum
for the credit committee. Write in formal, precise banking English (third person, no exclamation, no casual phrasing),
as an experienced credit analyst would: interpret the numbers, explain causes and implications, connect trends across
statements, and state clearly what must be verified. Use only the numbers provided - never invent or recompute figures.
The credit officer's own comments and flag dispositions are in the fact pack: weave them in, attribute them
("the credit officer notes ..."), and point out politely where they conflict with the financial evidence.
Use INR Crore. Be candid about weaknesses and red flags; do not soften them."""


def fact_pack(bundle):
    years = bundle["years"]
    y0 = years[0]
    d = bundle["data"]
    r = bundle["ratios"]
    keyfin = {}
    for y in years:
        keyfin[y] = {k: d[y].get(k) for k in ["revenue", "ebitda", "pat", "total_equity", "total_debt", "net_debt", "cfo", "total_assets", "liquid_funds"]}
    rat = {y: {R.RATIO_META[k][1]: R.fmt(k, v) for k, v in r[y].items() if v is not None} for y in years}
    fz = bundle["forensics"]
    flags = [{"title": f["title"], "severity": f["severity"], "evidence": f["evidence"]} for f in fz["flags"]][:40]
    pack = {
        "company": bundle.get("company"), "statement_type": bundle.get("statement_type"), "years": years,
        "key_financials_inr_cr": keyfin, "ratios": rat,
        "scores": {"internal_score": fz["score"], "grade": fz["grade"], "beneish_m": fz["beneish"],
                   "piotroski_f": fz["piotroski"], "altman_z_em": fz["altman_z"]},
        "red_flags": flags,
        "auditor": {k: (bundle.get("notes") or {}).get(k) for k in ["auditor_name", "auditor_opinion", "going_concern_uncertainty", "emphasis_of_matter", "key_audit_matters"]},
        "market_intel": (bundle.get("brief") or {}),
        "brsr": {k: (bundle.get("brsr") or {}).get(k) for k in ["scope1_tco2e", "scope2_tco2e", "ghg_assurance", "energy_renewable_pct", "esg_red_flags", "summary"]},
        "pcaf": {k: (bundle.get("pcaf") or {}).get(k) for k in ["attribution_factor", "financed_scope12", "data_quality_score", "method"]},
        "proposal": bundle.get("proposal", {}),
        "credit_officer_comments": [c.get("text") for c in bundle.get("comments") or []],
        "officer_flag_dispositions": [{"flag": f["title"], "status": f.get("status"), "remark": f.get("remark")}
                                      for f in fz["flags"] if f.get("remark") or f.get("status", "Open") != "Open"],
        "supporting_documents": {"files": [d.get("name") for d in (bundle.get("support") or {}).get("docs", [])],
                                 "ai_summary": (bundle.get("support") or {}).get("summary"),
                                 "key_facts": (bundle.get("support") or {}).get("facts")},
    }
    try:  # structuring facts so the AI comments on repayment capacity, pricing and EWS consistently with the tables
        from . import credit_tools as CT
        P = CT.proposal(bundle)
        rows_, asm = CT.projections(bundle, P)
        sm = CT.dscr_summary(rows_)
        ews, n_trig = CT.rbi_ews(bundle, P)
        sc = CT.security_cover(bundle, P)
        rp = CT.risk_pricing(bundle, P)
        pack["structuring"] = {
            "facilities": {k: P.get(k) for k in ("tl_amount", "tl_tenor_years", "tl_moratorium_months", "tl_rate", "cc_amount", "nfb_amount", "purpose")},
            "projection_assumptions": {k: round(v, 4) if isinstance(v, float) else v for k, v in asm.items()},
            "projected_dscr_avg": sm.get("avg"), "projected_dscr_min": sm.get("min"), "ebitda_cushion_before_dscr_below_1": CT.breakeven(bundle, P),
            "scenarios": [{k: s_[k] for k in ("scenario", "avg_dscr", "min_dscr")} for s_ in CT.scenarios(bundle, P)],
            "security_cover": sc.get("cover"), "facr": sc.get("facr"), "hurdle_rate": rp["floor"], "proposed_rate": rp["proposed"], "raroc": rp["raroc"],
            "rbi_ews_triggered": [e[0] for e in ews if e[1] == "Triggered"], "ews_count": n_trig}
    except Exception:
        pass
    return pack


def llm_narrative(llm, bundle):
    pack = fact_pack(bundle)
    user = f"""Using the fact pack, return JSON:
{{"executive_summary": str (350-450 words: borrower, proposal, financial standing, key strengths, key risks, forensic findings, conclusion),
 "business_profile": str (150-250 words from what the documents show: activities, revenue model, scale, customers/segments if visible; say 'not disclosed' where unknown),
 "financial_performance": str (400-550 words: revenue drivers, cost structure, margin movement in bps, other income, cash conversion, balance-sheet changes, capital structure),
 "working_capital": str (200-300 words: operating cycle, receivable quality, inventory, creditor stretch, bank finance need),
 "forensic_assessment": str (350-500 words: explain each High and Medium flag, what it may indicate - diversion, window-dressing, hidden liabilities - and what evidence would clear it),
 "market_intelligence": str (150-250 words),
 "esg_assessment": str (120-200 words),
 "key_risks": [{{"risk": str, "mitigant": str}}],
 "strengths": [str],
 "suggested_covenants": [str],
 "due_diligence_checklist": [str],
 "recommendation": "Approve" | "Approve with conditions" | "Refer / further diligence" | "Decline",
 "recommendation_rationale": str (150-250 words)}}

FACT PACK:
{json.dumps(pack, default=str)[:60000]}"""
    return llm.chat_json(NARR_SYSTEM, user, max_tokens=9000)


def template_narrative(bundle):
    """Deterministic fallback - no AI key needed."""
    years, d, r = bundle["years"], bundle["data"], bundle["ratios"]
    y0 = years[0]
    c = bundle.get("company") or "The company"
    fz = bundle["forensics"]
    hi = [f for f in fz["flags"] if f["severity"] == "High"]
    def v(k, y=y0):
        return schema.g(d[y], k)
    growth = r[y0].get("rev_growth")
    s = (f"{c} reported revenue of INR {v('revenue'):,.1f} Cr in {y0}"
         + (f" ({growth:+.1%} YoY)" if growth is not None else "")
         + f", EBITDA of INR {v('ebitda'):,.1f} Cr ({R.fmt('ebitda_margin', r[y0].get('ebitda_margin'))} margin) and PAT of INR {v('pat'):,.1f} Cr. "
         f"Net worth stands at INR {v('total_equity'):,.1f} Cr against total debt of INR {v('total_debt'):,.1f} Cr "
         f"(D/E {R.fmt('de', r[y0].get('de'))}, TOL/TNW {R.fmt('tol_tnw', r[y0].get('tol_tnw'))}, Debt/EBITDA {R.fmt('debt_ebitda', r[y0].get('debt_ebitda'))}). "
         f"Interest coverage is {R.fmt('icr', r[y0].get('icr'))} and DSCR {R.fmt('dscr', r[y0].get('dscr'))}. "
         f"The internal model scores the borrower {fz['score']}/100 ({fz['grade']}). "
         f"{len(fz['flags'])} red flags were raised, {len(hi)} of them high severity.")
    rec = "Approve with conditions"
    if fz["score"] < 40 or len(hi) >= 4:
        rec = "Refer / further diligence"
    if fz["score"] < 25:
        rec = "Decline"
    if fz["score"] >= 70 and not hi:
        rec = "Approve"
    if str(fz.get("grade", "")).startswith("NR"):
        rec = "Refer / further diligence"
    return {
        "executive_summary": s + ((" Credit officer's observations: " + " ".join(c.get("text", "") for c in bundle.get("comments") or [])) if bundle.get("comments") else ""),
        "business_profile": "Add an AI key for an auto-drafted business profile, or write it here.",
        "financial_performance": s,
        "working_capital": (f"Current ratio {R.fmt('current_ratio', r[y0].get('current_ratio'))}; debtor days {R.fmt('debtor_days', r[y0].get('debtor_days'))}, "
                            f"inventory days {R.fmt('inventory_days', r[y0].get('inventory_days'))}, creditor days {R.fmt('creditor_days', r[y0].get('creditor_days'))}. "
                            f"MPBF (Tandon II) INR {R.fmt('mpbf2', r[y0].get('mpbf2'))} Cr."),
        "forensic_assessment": " ".join(f"{f['title']}: {f['evidence']}." for f in hi) or "No high-severity forensic flags.",
        "market_intelligence": (bundle.get("brief") or {}).get("overview", "News scan not run."),
        "esg_assessment": (bundle.get("brsr") or {}).get("summary", "BRSR not provided."),
        "key_risks": [{"risk": f"{f['title']}: {f.get('why', '')}".strip(), "mitigant": f["action"]}
                      for f in sorted(fz["flags"], key=lambda z: {"High": 0, "Medium": 1, "Low": 2}.get(z["severity"], 3))[:8]],
        "strengths": [R.RATIO_META[k][1] + " " + R.fmt(k, val) for k, val in r[y0].items() if R.status(k, val) == "good"][:8],
        "suggested_covenants": ["Maximum TOL/TNW 3.0x", "Minimum DSCR 1.25x", "Maximum Debt/EBITDA 3.5x",
                                "No loans/advances/investments to group entities without lender consent",
                                "Quarterly stock & book-debt statements; annual stock audit", "End-use certificate from statutory auditor"],
        "due_diligence_checklist": [f["action"] for f in fz["flags"]][:15],
        "recommendation": rec,
        "recommendation_rationale": (f"The recommendation reflects an internal score of {fz['score']:.0f}/100 ({fz['grade']}) and "
                                     f"{len(hi)} high-severity observation(s). "
                                     + ("Sanction should be subject to satisfactory resolution of the high-severity observations listed in Section 7 "
                                        "and the conditions in Section 12." if hi else
                                        "No high-severity observation was identified; standard conditions in Section 12 apply.")),
    }


SUPPORT_SYSTEM = """You are a bank credit analyst reviewing supporting documents of a loan proposal (CMA data, stock and
book-debt statements, rating rationales, sanction notes, site-visit / inspection reports, bank statements, legal and
valuation reports). Extract facts and anything that contradicts the audited financials or signals risk. Quote evidence;
never invent."""


def llm_review_support(llm, company, docs):
    body = ""
    for d in docs:
        body += f"\n\n===== DOCUMENT: {d['name']} =====\n{d['text'][:20000]}"
    user = f"""Borrower: {company}. Review the documents and return JSON:
{{"summary": str (100-200 words),
 "facts": [str]  (limits sanctioned, drawing power, stock/debtor figures, rating & outlook, collateral, valuations, conduct of account),
 "red_flags": [{{"title": str, "severity": "High"|"Medium"|"Low", "evidence": str (quote + document name), "action": str}}]}}
Look for: stock statement vs balance-sheet inventory/receivables mismatch, DP shortfall, overdrawn / irregular account,
cheque returns, rating downgrade or 'issuer not cooperating', collateral shortfall, valuation issues, adverse site visit,
statutory dues, related-party routing in bank statements, round-tripping, cash withdrawals.
DOCUMENTS:{body[:70000]}"""
    out = llm.chat_json(SUPPORT_SYSTEM, user, max_tokens=4000)
    for f in out.get("red_flags") or []:
        f["category"] = "Supporting documents (AI)"
        f["source"] = "AI"
    return out
