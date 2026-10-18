"""Market intelligence: pulls live news (Google News RSS - no key needed, optional NewsAPI / GNews keys),
then the LLM tags each item and writes an intelligence brief."""
import datetime as dt
import html
import os
import re
import urllib.parse

import requests

UA = {"User-Agent": "Mozilla/5.0 (CreditIntel research bot)"}

ADVERSE_QUERIES = [
    '"{c}" fraud OR scam OR siphon OR diversion OR forensic',
    '"{c}" default OR NPA OR insolvency OR NCLT OR "wilful defaulter"',
    '"{c}" ED OR CBI OR SEBI OR "income tax" OR raid OR GST',
    '"{c}" rating downgrade OR CRISIL OR ICRA OR CARE OR "India Ratings"',
    '"{c}" auditor resigns OR resignation OR promoter pledge',
]
GENERAL_QUERIES = ['"{c}"', '"{c}" results OR revenue OR profit', '"{c}" order OR expansion OR acquisition OR plant']


def _clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def google_news(query, days=365, limit=25):
    import feedparser
    q = urllib.parse.quote(f"{query} when:{days}d")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    r = requests.get(url, headers=UA, timeout=20)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    out = []
    for e in feed.entries[:limit]:
        src = e.get("source", {}).get("title") if isinstance(e.get("source"), dict) else None
        title = _clean(e.get("title"))
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        date = ""
        if e.get("published_parsed"):
            date = dt.date(*e.published_parsed[:3]).isoformat()
        out.append({"title": title, "source": src or "", "date": date, "url": e.get("link", ""),
                    "snippet": _clean(e.get("summary", ""))[:300], "query": query})
    return out


def newsapi(query, key, limit=25):
    r = requests.get("https://newsapi.org/v2/everything", headers=UA, timeout=20,
                     params={"q": query, "language": "en", "sortBy": "publishedAt", "pageSize": limit, "apiKey": key})
    r.raise_for_status()
    return [{"title": a.get("title", ""), "source": (a.get("source") or {}).get("name", ""), "date": (a.get("publishedAt") or "")[:10],
             "url": a.get("url", ""), "snippet": (a.get("description") or "")[:300], "query": query}
            for a in r.json().get("articles", [])]


def gnews(query, key, limit=25):
    r = requests.get("https://gnews.io/api/v4/search", headers=UA, timeout=20,
                     params={"q": query, "lang": "en", "country": "in", "max": min(limit, 25), "apikey": key})
    r.raise_for_status()
    return [{"title": a.get("title", ""), "source": (a.get("source") or {}).get("name", ""), "date": (a.get("publishedAt") or "")[:10],
             "url": a.get("url", ""), "snippet": (a.get("description") or "")[:300], "query": query}
            for a in r.json().get("articles", [])]


def fetch_news(company, aliases=(), days=365, newsapi_key=None, gnews_key=None, progress=None):
    names = [company] + [a for a in aliases if a]
    queries = []
    for n in names[:2]:
        queries += [q.format(c=n) for q in GENERAL_QUERIES + ADVERSE_QUERIES]
    items, errors = [], []
    for i, q in enumerate(queries):
        try:
            items += google_news(q, days=days)
        except Exception as e:
            errors.append(f"Google News: {e}")
        if progress:
            progress((i + 1) / len(queries), f"Searching news: {q[:60]}")
    newsapi_key = newsapi_key or os.getenv("NEWSAPI_KEY")
    gnews_key = gnews_key or os.getenv("GNEWS_KEY")
    if newsapi_key:
        try:
            items += newsapi(f'"{company}"', newsapi_key)
        except Exception as e:
            errors.append(f"NewsAPI: {e}")
    if gnews_key:
        try:
            items += gnews(f'"{company}"', gnews_key)
        except Exception as e:
            errors.append(f"GNews: {e}")
    # de-duplicate by normalised title
    seen, uniq = set(), []
    for it in sorted(items, key=lambda x: x.get("date", ""), reverse=True):
        k = re.sub(r"[^a-z0-9]", "", it["title"].lower())[:80]
        if k and k not in seen:
            seen.add(k)
            uniq.append(it)
    return uniq[:120], errors


NEWS_SYSTEM = """You are a market-intelligence analyst supporting a bank credit officer in India.
You classify news strictly from the headline and snippet provided. Do not add facts that are not in the text.
If an article is not about the target company (name clash), mark relevant=false."""


def classify_news(llm, company, items, batch=40):
    out = []
    for i in range(0, len(items), batch):
        chunk = items[i:i + batch]
        lines = "\n".join(f"{j}. [{it['date']}] {it['title']} | {it['source']} | {it['snippet'][:200]}" for j, it in enumerate(chunk))
        user = f"""Target company: {company}
For each numbered item return JSON {{"items":[{{"i":int,"relevant":bool,"sentiment":"Positive"|"Neutral"|"Negative",
"category":"Fraud/Investigation"|"Default/Insolvency"|"Regulatory/Legal"|"Rating action"|"Governance/Management"|"Financial results"|"Business/Expansion"|"Industry/Macro"|"ESG"|"Other",
"severity":"High"|"Medium"|"Low","summary":str (<=25 words)}}]}}
High severity = fraud, default, insolvency, raids/investigation, rating downgrade, auditor resignation, wilful default.
ITEMS:
{lines}"""
        try:
            res = llm.chat_json(NEWS_SYSTEM, user, max_tokens=5000)
            tags = {t.get("i"): t for t in res.get("items", [])}
        except Exception:
            tags = {}
        for j, it in enumerate(chunk):
            t = tags.get(j, {})
            it = dict(it)
            it.update({"relevant": t.get("relevant", True), "sentiment": t.get("sentiment", "Neutral"),
                       "category": t.get("category", "Other"), "severity": t.get("severity", "Low"),
                       "summary": t.get("summary", "")})
            out.append(it)
    return [x for x in out if x.get("relevant", True)]


ADVERSE_WORDS = {
    "High": ["fraud", "scam", "siphon", "divert", "diversion", "default", "insolven", "nclt", "wilful", "raid", "arrest", "cbi", "enforcement directorate",
             " ed ", "downgrade", "auditor resign", "forensic", "money laundering", "npa", "bankrupt"],
    "Medium": ["sebi", "penalty", "probe", "notice", "show cause", "pledge", "loss", "delay", "strike", "gst", "income tax", "litigation"],
}
POSITIVE_WORDS = ["order", "wins", "profit rises", "upgrade", "expansion", "record", "growth", "acquires", "contract", "launch"]


def keyword_classify(items):
    """Offline fallback when no LLM key."""
    out = []
    for it in items:
        t = f" {it['title'].lower()} {it['snippet'].lower()} "
        sev, sent, cat = "Low", "Neutral", "Other"
        if any(w in t for w in ADVERSE_WORDS["High"]):
            sev, sent, cat = "High", "Negative", "Fraud/Investigation" if any(w in t for w in ["fraud", "raid", "cbi", "probe", "forensic", "laundering"]) else "Default/Insolvency"
            if "downgrade" in t:
                cat = "Rating action"
        elif any(w in t for w in ADVERSE_WORDS["Medium"]):
            sev, sent, cat = "Medium", "Negative", "Regulatory/Legal"
        elif any(w in t for w in POSITIVE_WORDS):
            sent, cat = "Positive", "Business/Expansion"
        x = dict(it)
        x.update({"relevant": True, "sentiment": sent, "category": cat, "severity": sev, "summary": ""})
        out.append(x)
    return out


def intelligence_brief(llm, company, items, fin_summary=""):
    top = items[:60]
    lines = "\n".join(f"- [{it['date']}] ({it['sentiment']}/{it['severity']}/{it['category']}) {it['title']} - {it['source']}" for it in top)
    user = f"""Write a market-intelligence brief on {company} for a credit committee, using ONLY the headlines below
plus the financial summary. Return JSON:
{{"overview": str (150-250 words), "key_positives": [str], "key_concerns": [str], "regulatory_legal": [str],
"management_governance": [str], "industry_outlook": str, "news_sentiment_score": int (-100..100),
"items_needing_verification": [str]}}
If something is not covered by the headlines, say 'No information in news scan'.

FINANCIAL SUMMARY:
{fin_summary}

HEADLINES:
{lines}"""
    return llm.chat_json(NEWS_SYSTEM, user, max_tokens=3000)
