"""Fetch PCAF / BRSR inputs from the internet with a web-search-enabled model (OpenRouter ':online').

Returns market capitalisation, reported Scope 1/2/3, sector and the sources it used, so the
officer can verify before the PCAF calculation uses them."""
from .websearch import WebSearch

WEB_SYSTEM = """You are an ESG and equity research assistant for an Indian bank. Use web search.
Prefer primary sources: the company's BRSR / BRSR Core filing, annual report, NSE/BSE pages.
Never guess a number - if you cannot find it in a source, return null."""

WEB_PROMPT = """Company: {company}{extra}
Find and return JSON:
{{"company_name": str, "listed": bool, "exchange_symbol": str|null,
 "market_cap_inr_cr": number|null, "market_cap_date": str|null,
 "financial_year": str|null,
 "scope1_tco2e": number|null, "scope2_tco2e": number|null, "scope3_tco2e": number|null,
 "emissions_declared": bool, "ghg_assurance": "reasonable"|"limited"|"none"|"not stated",
 "sector": str|null, "nic_or_industry": str|null,
 "revenue_inr_cr": number|null,
 "brsr_filed": bool, "brsr_years_filed": [str], "brsr_latest_url": str|null, "brsr_core_assured": bool|null,
 "brsr_applicable": "mandatory (top 1000 listed)"|"voluntary"|"not applicable"|"unknown",
 "water_kl": number|null, "energy_gj": number|null, "renewable_share_pct": number|null, "net_zero_target": str|null,
 "sources": [{{"field": str, "url": str, "note": str}}],
 "notes": str}}
brsr_filed = true only if you found a BRSR (or BRSR Core) for the company (NSE/BSE filing or annual report section).
Market cap in INR crore (1 crore = 10 million). Emissions in tonnes CO2e for the latest year in the BRSR."""


def web_llm(openrouter_key, base_model="deepseek/deepseek-chat", case_id=None):
    if not openrouter_key:
        return None
    return WebSearch(openrouter_key, base_model, max_results=8, case_id=case_id, task="web")


def fetch_pcaf_inputs(llm, company, cin=None, extra=""):
    ex = (f"\nCIN: {cin}" if cin else "") + (f"\n{extra}" if extra else "")
    return llm.chat_json(WEB_SYSTEM, WEB_PROMPT.format(company=company, extra=ex), max_tokens=2500)
