"""Low-cost web search through OpenRouter's `openrouter:web_search` server tool.

Default engine: Parallel 'fast' - USD 0.001 per search request (up to 10 results), the cheapest engine
OpenRouter lists. Falls back to Exa (USD 0.007) and finally the legacy ':online' suffix if a model or
account does not support the server tool. Every call is written to the shared LLM ledger so the
cost meter includes search fees.
"""
import json
import time

import requests

from .llm import LEDGER, LLMError, parse_json, squeeze

URL = "https://openrouter.ai/api/v1/chat/completions"
ENGINES = [("parallel", "fast", 0.001), ("exa", "fast", 0.007)]
SEARCH_PRICE = {"parallel": 0.001, "exa": 0.007, "online": 0.02}


class WebSearch:
    def __init__(self, api_key, model="deepseek/deepseek-chat", max_results=6, case_id=None, task="web"):
        self.api_key = api_key
        self.model = (model or "deepseek/deepseek-chat").replace(":online", "")
        self.max_results = max_results
        self.case_id = case_id
        self.task = task
        self.provider = "OpenRouter"
        self.engine_used = None

    @property
    def ready(self):
        return bool(self.api_key)

    @property
    def label(self):
        return f"OpenRouter / {self.model} + web search"

    def _post(self, body):
        r = requests.post(URL, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                                        "HTTP-Referer": "http://localhost:8501", "X-Title": "Credit Intelligence Workbench"},
                          json=body, timeout=180)
        if r.status_code >= 400:
            raise LLMError(f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json()

    def chat(self, system, user, max_tokens=2500, json_mode=False):
        """Returns (text, citations[{url,title}])."""
        if not self.ready:
            raise LLMError("No OpenRouter key - add it in Settings.")
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": squeeze(user)}]
        attempts = [{"tools": [{"type": "openrouter:web_search",
                                "parameters": {"engine": e, "mode": m, "max_results": self.max_results}}], "_engine": e}
                    for e, m, _ in ENGINES]
        attempts.append({"model": self.model + ":online", "_engine": "online"})
        last = None
        for att in attempts:
            eng = att.pop("_engine")
            body = {"model": att.pop("model", self.model), "messages": msgs, "max_tokens": max_tokens, "temperature": 0.1, **att}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            for _ in range(2):
                try:
                    data = self._post(body)
                    msg = (data.get("choices") or [{}])[0].get("message") or {}
                    text = msg.get("content") or ""
                    cites = []
                    for a in msg.get("annotations") or []:
                        uc = a.get("url_citation") or {}
                        if uc.get("url"):
                            cites.append({"url": uc["url"], "title": uc.get("title") or uc["url"]})
                    u = data.get("usage") or {}
                    n_search = ((u.get("server_tool_use") or {}).get("web_search_requests")) or 1
                    LEDGER.append({"task": self.task, "case": self.case_id, "provider": "OpenRouter", "model": self.model,
                                   "in": u.get("prompt_tokens", 0) or 0, "out": u.get("completion_tokens", 0) or 0, "cached": False,
                                   "search_usd": SEARCH_PRICE.get(eng, 0.007) * n_search})
                    self.engine_used = eng
                    return text, cites
                except LLMError as e:
                    last = e
                    if "response_format" in body and ("response_format" in str(e) or "json" in str(e).lower()):
                        body.pop("response_format")
                        continue
                    break
                except Exception as e:  # network
                    last = e
                    time.sleep(2)
        raise LLMError(f"Web search failed: {last}")

    def chat_json(self, system, user, max_tokens=3000):
        text, cites = self.chat(system + "\nReturn ONLY valid JSON. No markdown fences.", user, max_tokens=max_tokens, json_mode=True)
        out = parse_json(text)
        if isinstance(out, dict):
            out.setdefault("_citations", cites)
        return out


# ------------------------------------------------------------------ prompts used across the app
NEWS_SYS = """You are a credit-intelligence analyst for an Indian bank. Search the web for recent, verifiable information about the
borrower. Prefer Economic Times, Business Standard, Mint, Moneycontrol, NSE/BSE filings, rating-agency rationales (CRISIL, ICRA, CARE,
India Ratings, Acuite, Brickwork), MCA, SEBI, NCLT, RBI and court records. Never invent articles - every item needs a real URL."""
NEWS_PROMPT = """Borrower: {company}{extra}
Return JSON: {{"items": [{{"date": "YYYY-MM-DD"|null, "title": str, "source": str, "url": str, "summary": str (1-2 sentences),
 "category": "Fraud / investigation"|"Default / NPA / insolvency"|"Rating action"|"Regulatory / legal"|"Management / governance"|
 "Financial results"|"Business / orders / expansion"|"Other",
 "sentiment": "Positive"|"Neutral"|"Negative", "severity": "High"|"Medium"|"Low"}}] (up to 15, newest first),
 "brief": {{"overview": str (120-200 words), "key_positives": [str], "key_concerns": [str], "regulatory_legal": [str],
            "management_governance": [str], "items_needing_verification": [str]}},
 "credit_rating": {{"agency": str|null, "rating": str|null, "outlook": str|null, "date": str|null, "url": str|null}}}}"""

SCREEN_SYS = """You are a KYC / fraud-screening analyst for an Indian bank. Search the web for each party and report ONLY findings
backed by a source URL: wilful-defaulter or suit-filed listings, SEBI / RBI / MCA / IBBI / NCLT / ED / CBI / SFIO actions, fraud cases,
disqualified directors, insolvency, sanctions. Be careful with common names - say how confident you are that the finding is the same
party (matching CIN / DIN / city / company). If nothing adverse is found, say so."""
SCREEN_PROMPT = """Borrower: {company}
Parties to check:
{parties}
Return JSON: {{"findings": [{{"party": str, "finding": str, "list_or_action": str, "date": str|null, "url": str,
 "same_party_confidence": "High"|"Medium"|"Low", "severity": "High"|"Medium"|"Low"}}],
 "clear_parties": [str], "notes": str}}"""

ASK_SYS = """You answer a bank credit officer's question. Use the document pages provided first and cite them as (document, p.N).
Use web search only to add current or external facts, and cite those with their URL. Keep the two clearly separated:
'From the documents:' and 'From the web:'. End with 'Confidence: High / Medium / Low - <reason>'."""
