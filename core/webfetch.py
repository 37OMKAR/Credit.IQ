"""Fetch PCAF / BRSR inputs from the internet with a web-search-enabled model (OpenRouter ':online').

Returns market capitalisation, reported Scope 1/2/3, sector and the sources it used, so the
officer can verify before the PCAF calculation uses them."""
from .llm import LLM

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
 "sources": [{{"field": str, "url": str, "note": str}}],
 "notes": str}}
Market cap in INR crore (1 crore = 10 million). Emissions in tonnes CO2e for the latest year in the BRSR."""


def web_llm(openrouter_key, base_model="deepseek/deepseek-chat"):
    if not openrouter_key:
        return None
    model = base_model if base_model.endswith(":online") else base_model + ":online"
    llm = LLM("OpenRouter", api_key=openrouter_key, model=model)
    llm.task = "web"
    return llm


def fetch_pcaf_inputs(llm, company, cin=None, extra=""):
    ex = (f"\nCIN: {cin}" if cin else "") + (f"\n{extra}" if extra else "")
    return llm.chat_json(WEB_SYSTEM, WEB_PROMPT.format(company=company, extra=ex), max_tokens=2500)
