"""Verification of facts that come from the web.

Nothing found by an AI web search is used in the analysis or the reports unless it passes these checks:
  1. The source URL was actually returned by the search engine (an AI cannot cite a page it never saw).
  2. The page can be opened and it mentions the company (distinctive name words or the CIN).
  3. Every number taken from the page (emissions, market cap, rating grade ...) is actually written on that page.
Anything that fails is kept aside as "unverified" (shown to the officer as a lead to check by hand) and is
never used in ratios, PCAF, flags or report conclusions.
"""
import html
import io
import ipaddress
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

import requests

from . import watchlist as WL

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"}
MAX_BYTES = 15 * 1024 * 1024
_CACHE = {}


# ------------------------------------------------------------------ fetching
def _norm_url(u):
    try:
        p = urlsplit((u or "").strip())
        return (p.netloc.lower().removeprefix("www.") + p.path.rstrip("/")).lower()
    except Exception:
        return (u or "").lower()


ALLOW_PRIVATE = False  # the self-test turns this on for its local test site; never in normal use
MAX_REDIRECTS = 5


def url_blocked(url):
    """Reason a URL must not be fetched, or ''. Links come from web search results and AI output, so they could point
    the server at the bank's internal network (SSRF): only public http(s) hosts on the standard ports are allowed,
    checked on every address the name resolves to and again after each redirect."""
    try:
        p = urlsplit(str(url).strip())
    except ValueError:
        return "malformed URL"
    if p.scheme not in ("http", "https") or not p.hostname:
        return "only http(s) links are fetched"
    if p.username or p.password:
        return "links with credentials are not fetched"
    try:
        port = p.port
    except ValueError:
        return "invalid port"
    if port not in (None, 80, 443) and not ALLOW_PRIVATE:
        return f"non-standard port {port} not fetched"
    if ALLOW_PRIVATE:
        return ""
    try:
        infos = socket.getaddrinfo(p.hostname, port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return "host name does not resolve"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if not ip.is_global or ip.is_multicast:
            return f"host resolves to a non-public address ({ip}) - not fetched"
    return ""


def _get(url, timeout):
    """GET that follows redirects itself so every hop is checked against url_blocked()."""
    for _ in range(MAX_REDIRECTS + 1):
        why = url_blocked(url)
        if why:
            raise PermissionError(why)
        r = requests.get(url, headers=UA, timeout=timeout, stream=True, allow_redirects=False)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
            url = urljoin(url, r.headers["location"])
            r.close()
            continue
        return r
    raise PermissionError("too many redirects")


def fetch_text(url, timeout=15):
    """Plain text of a web page or PDF (None, reason) if it cannot be read."""
    if not url or not str(url).startswith(("http://", "https://")):
        return None, "no valid URL"
    if url in _CACHE:
        return _CACHE[url]
    try:
        r = _get(url, timeout)
        if r.status_code >= 400:
            res = (None, f"page returned HTTP {r.status_code}")
        else:
            data = b""
            started = time.monotonic()
            for chunk in r.iter_content(65536):
                data += chunk
                if len(data) > MAX_BYTES or time.monotonic() - started > 4 * timeout:
                    break
            ctype = (r.headers.get("content-type") or "").lower()
            if "pdf" in ctype or data[:5] == b"%PDF-":
                try:
                    try:
                        import pymupdf as fitz
                    except ImportError:
                        import fitz
                    doc = fitz.open(stream=data, filetype="pdf")
                    txt = "\n".join(doc[i].get_text() for i in range(min(len(doc), 120)))
                    doc.close()
                    res = (txt, "")
                except Exception as e:
                    res = (None, f"PDF could not be read ({e})")
            else:
                t = data.decode(r.encoding or "utf-8", errors="ignore")
                t = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", t)
                t = re.sub(r"(?s)<[^>]+>", " ", t)
                res = (html.unescape(re.sub(r"\s+", " ", t)), "")
    except PermissionError as e:
        res = (None, f"blocked: {e}")
    except Exception as e:
        res = (None, f"page could not be opened ({type(e).__name__})")
    _CACHE[url] = res
    return res


def fetch_many(urls):
    urls = [u for u in dict.fromkeys(urls) if u]
    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(zip(urls, pool.map(fetch_text, urls)))


# ------------------------------------------------------------------ matching
def _name_words(name):
    """All words of a name except legal suffixes and fillers (Ltd, Pvt, Limited, of, the ...)."""
    return [w for w in WL.norm(name).split() if len(w) >= 3 or w.isdigit()] or WL.norm(name).split()


def mentions_company(text, company, cin=None):
    """Strict: the CIN, or every word of the company's name (not just one distinctive word - 'Deccan Plastics' is not 'Deccan Polyfab')."""
    if not text:
        return False
    if cin and cin.upper() in text.upper():
        return True
    need = _name_words(company)
    words = set(WL.norm(text[:600000]).split())
    return bool(need) and all(w in words for w in need)


def mentions_name(text, name):
    """A person or entity named in a finding: every word of the name must be on the page."""
    if not text or not name:
        return False
    need = _name_words(name)
    words = set(WL.norm(text[:600000]).split())
    return bool(need) and all(w in words for w in need)


def _number_forms(v):
    """Ways a number can be printed: 1234.5 -> 1234.5, 1,234.5, 1,234.50, 1235, 1,235 (also Indian 12,34,567)."""
    out = set()
    try:
        v = float(v)
    except (TypeError, ValueError):
        return out
    for d in (0, 1, 2):
        s = f"{abs(v):.{d}f}"
        out.add(s)
        ip, _, fp = s.partition(".")
        west = f"{int(ip):,}"
        out.add(west + (("." + fp) if fp else ""))
        if len(ip) > 3:  # Indian grouping
            head, tail = ip[:-3], ip[-3:]
            head = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head)
            out.add(head + "," + tail + (("." + fp) if fp else ""))
    return {s for s in out if s not in ("0", "0.0", "0.00")}


def number_on_page(v, text):
    if not text:
        return False
    compact = text.replace(" ", " ")
    for s in _number_forms(v):
        if re.search(r"(?<![\d.,])" + re.escape(s) + r"(?![\d])", compact):
            return True
    return False


# ------------------------------------------------------------------ verifiers for each kind of web result
def cited(url, citations):
    """True if the search engine itself returned this URL (or the same page)."""
    if not citations:
        return None  # engine gave no citation list - fall back to opening the page
    n = _norm_url(url)
    return any(_norm_url(c.get("url")) == n for c in citations)


def check_source(url, company, cin, citations, must_contain=(), numbers=()):
    """-> dict(status 'verified'|'unverified', reason)"""
    c = cited(url, citations)
    if c is False:
        return {"status": "unverified", "reason": "link was not among the search results (possibly invented by the AI)"}
    text, err = fetch_text(url)
    if text is None:
        return {"status": "unverified", "reason": err}
    if not mentions_company(text, company, cin):
        return {"status": "unverified", "reason": "page does not mention the company"}
    for s in must_contain:
        if s and WL.norm(str(s)) not in WL.norm(text):
            return {"status": "unverified", "reason": f"'{s}' is not on the page"}
    for v in numbers:
        if v is not None and not number_on_page(v, text):
            return {"status": "unverified", "reason": f"value {v} is not on the page"}
    return {"status": "verified", "reason": "source opened; company" + (" and figures" if numbers else "") + " found on the page"}


STOP = set("a an the of to in on for and or with by from at as is are was were be been its it this that after over into amid says said "
           "new news report reports latest private limited pvt ltd company co india indian".split())
ADVERSE = {"raid": ["raid", "searched", "search operation"], "fraud": ["fraud"], "enforcement directorate": ["enforcement directorate", " ed "],
           "cbi": ["cbi", "central bureau"], "default": ["default"], "wilful": ["wilful", "willful"], "insolvency": ["insolvency", "cirp", "ibc"],
           "nclt": ["nclt", "tribunal"], "sebi": ["sebi"], "penalty": ["penalty", "fine", "fined"], "downgrade": ["downgrad"],
           "arrest": ["arrest"], "probe": ["probe", "investigat"], "npa": ["npa", "non-performing"], "liquidation": ["liquidat"]}


def story_on_page(title, text, company):
    """The page must carry the story, not merely mention the company: most of the headline's own words must be on it,
    and every adverse claim in the headline (raid, fraud, default ...) must be on it too."""
    if not text:
        return False, "page could not be read"
    page = " " + WL.norm(text[:600000]) + " "
    ttl = WL.norm(title or "")
    co = set(WL.norm(company or "").split())
    words = [w for w in ttl.split() if len(w) > 2 and w not in STOP and w not in co]
    for key, forms in ADVERSE.items():
        if key in " " + ttl + " " or any(f.strip() in ttl.split() for f in forms if " " not in f.strip()):
            if not any(f in page for f in forms):
                return False, f"the page does not mention '{key}' - the headline's claim is not supported"
    if words:
        hit = sum(1 for w in words if f" {w} " in page or w in page)
        if hit / len(words) < 0.6:
            return False, f"only {hit} of {len(words)} headline words are on the page - it is a different story"
    return True, "headline found on the page"


def verify_news(items, company, cin, citations):
    """Split web news items into (verified, unverified)."""
    urls = [i.get("url") for i in items]
    fetch_many(urls)
    ok, bad = [], []
    for it in items:
        res = check_source(it.get("url"), company, cin, citations)
        if res["status"] == "verified":
            good, why = story_on_page(it.get("title"), fetch_text(it.get("url"))[0], company)
            if not good:
                res = {"status": "unverified", "reason": why}
        it = dict(it, verification=res["reason"])
        (ok if res["status"] == "verified" else bad).append(it)
    return ok, bad


def verify_rating(cr, company, cin, citations):
    if not cr or not cr.get("rating"):
        return None, None
    if not cr.get("url"):
        return None, dict(cr, verification="no source link given")
    res = check_source(cr["url"], company, cin, citations)
    if res["status"] == "verified":
        text, _ = fetch_text(cr["url"])
        grade = re.escape(str(cr["rating"]).strip())
        # the exact grade as written (A+ is not A, AA- is not AA), and the agency's name, must both be on the page
        if not re.search(r"(?<![A-Za-z0-9+\-])" + grade + r"(?![A-Za-z0-9+\-])", text or ""):
            res = {"status": "unverified", "reason": f"rating '{cr['rating']}' is not written on the page"}
        elif cr.get("agency") and not re.search(re.escape(str(cr["agency"]).split()[0]), text or "", re.I):
            res = {"status": "unverified", "reason": f"agency '{cr['agency']}' is not named on the page"}
    if res["status"] == "verified":
        return dict(cr, verification=res["reason"]), None
    return None, dict(cr, verification=res["reason"])


def verify_findings(findings, company, cin, citations):
    """Screening findings: the page must mention the party named in the finding."""
    fetch_many([f.get("url") for f in findings])
    ok, bad = [], []
    for f in findings:
        url = f.get("url")
        c = cited(url, citations)
        text, err = fetch_text(url) if c is not False else (None, "link was not among the search results (possibly invented by the AI)")
        if text is None:
            bad.append(dict(f, verification=err))
        elif not mentions_name(text, f.get("party") or company):
            bad.append(dict(f, verification="page does not mention this party"))
        elif not story_on_page(" ".join(str(f.get(k) or "") for k in ("list_or_action",)), text, company)[0]:
            bad.append(dict(f, verification="the adverse action named in the finding is not on the page"))
        else:
            ok.append(dict(f, verification="source opened; party named on the page"))
    return ok, bad


WEB_NUM_FIELDS = ["market_cap_inr_cr", "scope1_tco2e", "scope2_tco2e", "scope3_tco2e", "revenue_inr_cr", "water_kl", "energy_gj",
                  "renewable_share_pct"]


FIELD_LABELS = {"market_cap_inr_cr": r"market\s*cap", "scope1_tco2e": r"scope[\s-]*(1|i)\b", "scope2_tco2e": r"scope[\s-]*(2|ii)\b",
                "scope3_tco2e": r"scope[\s-]*(3|iii)\b", "revenue_inr_cr": r"revenue|turnover|income from operations|total income|sales",
                "water_kl": r"water", "energy_gj": r"energy", "renewable_share_pct": r"renewable"}


def number_near_label(v, text, label_rx, window=160):
    """The number must be printed within ~250 characters of its own label (scope 1, market cap ...),
    so a value that merely appears somewhere else on the page is not accepted."""
    if not text:
        return False
    for s in _number_forms(v):
        for m in re.finditer(r"(?<![\d.,])" + re.escape(s) + r"(?![\d])", text):
            ctx = text[max(0, m.start() - window): m.start()]
            ctx = re.split(r"\n|\.\s|;\s", ctx)[-1]  # same line / sentence only; labels come before their values
            if re.search(label_rx, ctx, re.I):
                return True
    return False


def verify_web_pcaf(w, company, cin):
    """Keep a web BRSR / market figure only if one of the cited pages shows it next to the company."""
    if not w:
        return w
    w = dict(w)
    cites = w.get("_citations") or []
    src_urls = [s.get("url") for s in (w.get("sources") or []) if s.get("url")] + [c.get("url") for c in cites]
    if w.get("brsr_latest_url"):
        src_urls.append(w["brsr_latest_url"])
    pages = fetch_many(src_urls)
    good_pages = {u: t for u, (t, _e) in pages.items()
                  if t and mentions_company(t, company, cin) and cited(u, cites) is not False or (u == w.get("brsr_latest_url") and t and mentions_company(t, company, cin))}
    checks, removed = {}, {}
    for f in WEB_NUM_FIELDS:
        v = w.get(f)
        if v in (None, ""):
            continue
        lab = FIELD_LABELS.get(f)
        hit = next((u for u, t in good_pages.items() if (number_near_label(v, t, lab) if lab else number_on_page(v, t))), None)
        if hit:
            checks[f] = {"value": v, "url": hit, "status": "verified"}
        else:
            removed[f] = v
            w[f] = None
            checks[f] = {"value": v, "url": None, "status": "unverified - not printed next to its label on any source page; not used"}
    if w.get("brsr_filed"):
        u = w.get("brsr_latest_url")
        t = good_pages.get(u) if u else None
        if not (t and re.search(r"business\s+responsibility", t, re.I)):
            t = next((t_ for t_ in good_pages.values() if re.search(r"business\s+responsibility\s+(and|&)\s+sustainability", t_, re.I)), None)
        if t:
            checks["brsr_filed"] = {"value": True, "url": u, "status": "verified"}
        else:
            w["brsr_filed"] = None
            checks["brsr_filed"] = {"value": True, "url": u, "status": "unverified - no BRSR page for the company could be opened"}
            removed["brsr_filed"] = True
    # text claims: keep only if a page that names the company supports them
    all_text = " ".join(good_pages.values())
    text_rules = {
        "exchange_symbol": lambda v: re.search(r"(?<![A-Za-z0-9])" + re.escape(str(v)) + r"(?![A-Za-z0-9])", all_text) is not None,
        "net_zero_target": lambda v: re.search(r"net[\s-]?zero", all_text, re.I) is not None,
        "ghg_assurance": lambda v: v in ("none", "not stated") or re.search(r"assurance|assured", all_text, re.I) is not None,
        "brsr_core_assured": lambda v: v is not True or re.search(r"brsr\s+core", all_text, re.I) is not None,
    }
    for f, ok_ in text_rules.items():
        v = w.get(f)
        if v in (None, "", False):
            continue
        if ok_(v):
            checks[f] = {"value": v, "url": None, "status": "verified"}
        else:
            removed[f] = v
            w[f] = None if f != "ghg_assurance" else "not stated"
            checks[f] = {"value": v, "url": None, "status": "unverified - not supported by any source page; not used"}
    if removed:
        if any(k in removed for k in ("scope1_tco2e", "scope2_tco2e", "scope3_tco2e")):
            w["emissions_declared"] = bool(w.get("scope1_tco2e") or w.get("scope2_tco2e"))
    w["_verification"] = checks
    w["_unverified"] = removed
    w["_verified_sources"] = list(good_pages)
    return w
