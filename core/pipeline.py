"""Glue: from confirmed extracted data -> full analysis bundle -> Word + Excel."""
from . import forensics, narrative, pcaf, ratios, report_excel, report_word, schema


def analyse(data, years, company, notes=None, news=None, brief=None, brsr=None, pcaf_inputs=None,
            statement_type="standalone", source_file="", method="", meta=None, proposal=None, cin=None,
            comments=None, flag_remarks=None, support=None, screening=None):
    years = list(years)
    clean = {y: schema.fill_derived(dict(data[y])) for y in years}
    # notes-derived disclosures flow into the latest year if the statement extraction missed them
    if notes and notes.get("available"):
        y0 = years[0]
        for k_src, k_dst in [("contingent_liabilities_total", "contingent_liabilities"),
                             ("loans_advances_to_related_parties", "rpt_loans_given"),
                             ("guarantees_given_for_related_parties", "guarantees_given")]:
            if clean[y0].get(k_dst) in (None, 0) and isinstance(notes.get(k_src), (int, float)):
                clean[y0][k_dst] = notes[k_src]
    rat, enriched = ratios.compute(clean, years)
    support = support or {}
    screening = screening or {}
    extra = list(support.get("red_flags") or [])
    if screening.get("hits"):
        from . import watchlist
        extra += watchlist.to_flags(screening["hits"])
    fz = forensics.run(enriched, rat, years, notes=notes, news=news, extra_flags=extra, remarks=flag_remarks)
    bundle = {"company": company, "years": years, "data": enriched, "ratios": rat, "forensics": fz,
              "notes": notes or {}, "news": news or [], "brief": brief or {}, "brsr": brsr or {},
              "statement_type": statement_type, "source_file": source_file, "method": method,
              "meta": meta or {}, "proposal": proposal or {}, "cin": cin,
              "comments": comments or [], "support": support, "screening": screening}
    if pcaf_inputs:
        y0 = enriched[years[0]]
        bundle["pcaf"] = pcaf.calculate(
            outstanding_cr=pcaf_inputs.get("outstanding_cr", 0), asset_class=pcaf_inputs.get("asset_class", "Business loans / unlisted equity"),
            total_equity=schema.g(y0, "total_equity"), total_debt=schema.g(y0, "total_debt"), minority=schema.g(y0, "minority_interest"),
            market_cap=pcaf_inputs.get("market_cap"), scope1=pcaf_inputs.get("scope1"), scope2=pcaf_inputs.get("scope2"),
            scope3=pcaf_inputs.get("scope3"), verified=pcaf_inputs.get("verified", False), revenue=schema.g(y0, "revenue"),
            total_assets=schema.g(y0, "total_assets"), sector_ef=pcaf_inputs.get("sector_ef"), sector_name=pcaf_inputs.get("sector_name"))
    return bundle


def write_narrative(bundle, llm=None):
    if llm is not None and llm.ready:
        try:
            out = narrative.llm_narrative(llm, bundle)
            out["_source"] = "AI"
            return out
        except Exception as e:
            fb = narrative.template_narrative(bundle)
            fb["_source"] = f"template (AI failed: {e})"
            return fb
    fb = narrative.template_narrative(bundle)
    fb["_source"] = "template"
    return fb


def outputs(bundle, narr, pcaf_inputs=None, officer="", branch=""):
    docx_bytes = report_word.build(bundle, narr, officer=officer, branch=branch)
    xlsx_bytes = report_excel.build(bundle, pcaf_inputs=pcaf_inputs)
    return docx_bytes, xlsx_bytes
