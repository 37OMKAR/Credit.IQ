"""BRSR (Business Responsibility & Sustainability Report) intelligence extraction."""
import re

from .extractor import parse_number
from .pdf_reader import pages_text

BRSR_SYSTEM = """You are an ESG analyst reading SEBI BRSR / BRSR Core filings of Indian listed companies for a bank's
credit and climate-risk team. Extract figures exactly as reported; never estimate. Use null if not disclosed."""

BRSR_SCHEMA = """{
 "company_name": str|null, "cin": str|null, "financial_year": str|null,
 "sector_or_products": str|null, "nic_code": str|null,
 "employees_total": number|null, "women_employees_pct": number|null, "women_board_pct": number|null,
 "turnover_inr_cr": number|null,
 "scope1_tco2e": number|null, "scope2_tco2e": number|null, "scope3_tco2e": number|null,
 "scope1_prev": number|null, "scope2_prev": number|null,
 "emission_intensity_per_rupee": number|null, "emission_intensity_unit": str|null,
 "energy_total_gj": number|null, "energy_renewable_pct": number|null,
 "water_withdrawal_kl": number|null, "water_consumption_kl": number|null,
 "waste_generated_t": number|null, "hazardous_waste_t": number|null,
 "ghg_assurance": "reasonable"|"limited"|"none"|"not stated", "assurance_provider": str|null,
 "net_zero_target": str|null, "decarbonisation_actions": [str],
 "ltifr_employees": number|null, "fatalities": number|null,
 "complaints_pending": [str], "penalties_or_regulatory_actions": [str],
 "csr_spend_inr_cr": number|null, "csr_obligation_inr_cr": number|null,
 "principle_compliance_gaps": [str],
 "climate_risks_disclosed": [str],
 "esg_red_flags": [{"title": str, "severity": "High"|"Medium"|"Low", "evidence": str}],
 "esg_strengths": [str],
 "summary": str (120-200 words)
}"""

KEYWORDS = ["scope 1", "scope 2", "scope 3", "ghg", "greenhouse", "energy consumption", "water withdrawal", "waste generated",
            "assurance", "ltifr", "fatalit", "complaints", "penalty", "csr", "principle 6", "section a", "turnover", "employees"]


def relevant_pages(pages, max_pages=40):
    scored = []
    for p in pages:
        t = p["text"].lower()
        s = sum(t.count(k) for k in KEYWORDS)
        if s:
            scored.append((s, p["page"]))
    scored.sort(reverse=True)
    return sorted(pg for _, pg in scored[:max_pages])


def llm_extract_brsr(llm, pages):
    nums = relevant_pages(pages)
    text = pages_text(pages, set(nums), max_chars=70000)
    user = f"Extract BRSR intelligence as JSON with this shape:\n{BRSR_SCHEMA}\n\nBRSR PAGES:\n{text}"
    out = llm.chat_json(BRSR_SYSTEM, user, max_tokens=6000)
    out["_pages_used"] = nums
    out["method"] = f"LLM ({llm.provider})"
    return out


_SC = {
    "scope1_tco2e": r"total\s+scope\s*1\s+emissions?",
    "scope2_tco2e": r"total\s+scope\s*2\s+emissions?",
    "scope3_tco2e": r"total\s+scope\s*3\s+emissions?",
    "energy_total_gj": r"total\s+energy\s+consum\w*",
    "water_withdrawal_kl": r"total\s+volume\s+of\s+water\s+withdrawal",
    "waste_generated_t": r"total\s+waste\s+generated",
}


def heuristic_brsr(pages):
    """Offline fallback: regex scan for the headline BRSR numbers."""
    text = "\n".join(p["text"] for p in pages)
    out = {"method": "heuristic", "esg_red_flags": [], "esg_strengths": [], "decarbonisation_actions": []}
    for k, pat in _SC.items():
        m = re.search(pat, text, re.I)
        if m:
            window = text[m.end():m.end() + 160]
            nums = [parse_number(x) for x in re.findall(r"\d[\d,]*(?:\.\d+)?", window)]
            nums = [n for n in nums if n is not None and n > 3]  # skip stray '1','2'
            out[k] = nums[0] if nums else None
    low = text.lower()
    if "reasonable assurance" in low:
        out["ghg_assurance"] = "reasonable"
    elif "limited assurance" in low:
        out["ghg_assurance"] = "limited"
    else:
        out["ghg_assurance"] = "not stated"
    m = re.search(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b", text)
    out["cin"] = m.group(0) if m else None
    out["summary"] = "Heuristic scan only (no AI key). Headline environmental figures were pattern-matched; verify against the filing."
    return out
