"""Fraud / defaulter / regulatory watch-list screening.

Lists live in the central database (table `watchlist`) so every officer screens against the same data. The admin
imports them from CSV / Excel exports, for example:
  * Wilful-defaulter and suit-filed lists (TransUnion CIBIL suit-filed search, as directed by RBI)
  * SEBI debarred entities / orders, MCA disqualified directors and struck-off companies
  * RBI Alert List / caution lists, IBBI insolvency (CIRP / liquidation) public announcements, NFRA orders against auditors
  * The bank's own fraud (FMR) / Red-Flagged Account / internal negative list
Screening runs locally - names never leave the PC - except the optional OpenSanctions API lookup (sanctions / PEP).

Parties screened: borrower (name + CIN), directors / promoters / guarantors (name + DIN / PAN), related parties and
other entities named in the documents, and the statutory auditor.

Matching layers (strongest first):
  1. Identifier match (CIN / DIN / PAN / LLPIN)          -> High, "Confirmed identifier match"
  2. Name similarity >= 92 after normalisation             -> High, "Probable name match"
  3. Name similarity 85 - 92                               -> Medium, "Possible name match - verify"
  4. Group linkage: a listed entity shares a distinctive name token with the borrower or a related party -> Medium
  5. Shared director: a screened person appears as director of a listed entity -> High
Several hits on one party are escalated.
"""
import csv
import datetime as dt
import difflib
import io
import re

try:
    from rapidfuzz import fuzz as _fz

    def _ratio(a, b):
        return max(_fz.token_sort_ratio(a, b), _fz.ratio(a, b))
except ImportError:  # pure-python fallback
    def _ratio(a, b):
        s1 = difflib.SequenceMatcher(None, a, b).ratio()
        s2 = difflib.SequenceMatcher(None, " ".join(sorted(a.split())), " ".join(sorted(b.split()))).ratio()
        return 100 * max(s1, s2)

LEGAL = r"\b(private|pvt|limited|ltd|llp|plc|inc|corp|corporation|company|co|the|m/s|ms|and|&|of)\b"
HONORIFIC = r"\b(mr|mrs|ms|miss|shri|sri|smt|kum|dr|late|capt|col)\b"
GENERIC = {"india", "indian", "industries", "industry", "enterprises", "enterprise", "trading", "traders", "international", "global",
           "infra", "infrastructure", "projects", "project", "solutions", "services", "holdings", "investments", "ventures",
           "agro", "exports", "imports", "impex", "overseas", "group", "steel", "textiles", "pharma", "chemicals", "power",
           "energy", "finance", "financial", "capital", "developers", "construction", "logistics", "foods", "technologies",
           "tech", "systems", "packaging", "products", "metals", "mills", "motors", "auto", "realty", "estates", "bank",
           "national", "new", "shree", "shri", "sri", "jai", "maa", "om", "sai", "bharat", "hindustan", "united", "royal", "star",
           "east", "west", "north", "south", "development", "parks", "park", "distribution", "renewable", "renewables",
           "solar", "wind", "ultra", "mega", "facility", "facilities", "polyfab", "plastics", "communication", "communications", "polymers", "engineering"}
STATE_WORDS = {"gujarat", "maharashtra", "punjab", "rajasthan", "karnataka", "kerala", "bengal", "delhi", "mumbai", "pune", "chennai"}

LIST_TYPES = ["RBI Central Fraud Registry (CFR)", "Wilful defaulter - suit filed (CIBIL, Rs 25 lakh+)",
              "Defaulter - suit filed (CIBIL, Rs 1 crore+)", "Wilful defaulter / defaulter - non-suit filed (CIC member data)",
              "CRILC - SMA / RFA / fraud status", "Fraud / RFA (bank internal)", "ECGC Specific Approval List",
              "SEBI debarred", "MCA disqualified director", "MCA struck-off company", "RBI alert / caution list",
              "IBBI insolvency / liquidation", "NFRA / ICAI action (auditors)", "Sanctions / PEP", "Other negative list",
              "Wilful defaulter", "Suit-filed defaulter"]  # last two kept for lists imported by older versions
SEVERITY = {t: "High" for t in LIST_TYPES}
SEVERITY.update({"MCA disqualified director": "Medium", "IBBI insolvency / liquidation": "Medium", "MCA struck-off company": "Medium",
                 "NFRA / ICAI action (auditors)": "Medium", "Other negative list": "Medium", "ECGC Specific Approval List": "Medium"})

# Sources a credit file must show as checked (RBI Master Directions on Wilful Defaulters 2024 / Fraud Risk Management 2024,
# CIC reporting, bank credit policy). key, name, how to check, public link, list types that cover it automatically
REQUIRED_SOURCES = [
    ("cfr", "RBI Central Fraud Registry (CFR)", "Search on the RBI CFR portal (bank login)", "",
     ["RBI Central Fraud Registry (CFR)"]),
    ("cibil_wd", "Wilful defaulters - suit filed (Rs 25 lakh+)", "TransUnion CIBIL suit-filed search", "https://suit.cibil.com/",
     ["Wilful defaulter - suit filed (CIBIL, Rs 25 lakh+)", "Wilful defaulter"]),
    ("cibil_sf", "Defaulters - suit filed (Rs 1 crore+)", "TransUnion CIBIL suit-filed search", "https://suit.cibil.com/",
     ["Defaulter - suit filed (CIBIL, Rs 1 crore+)", "Suit-filed defaulter"]),
    ("cic_nsf", "Wilful defaulters / defaulters - non-suit filed", "CIC member login (CIBIL / Equifax / Experian / CRIF)", "",
     ["Wilful defaulter / defaulter - non-suit filed (CIC member data)"]),
    ("crilc", "CRILC - SMA / RFA / fraud status of the borrower and group", "CRILC report (bank login)", "", ["CRILC - SMA / RFA / fraud status"]),
    ("internal", "Bank's own fraud (FMR) / RFA / negative list", "Bank internal systems", "", ["Fraud / RFA (bank internal)"]),
    ("ecgc", "ECGC Specific Approval List (exporters)", "ECGC website", "https://www.ecgc.in/", ["ECGC Specific Approval List"]),
    ("mca", "MCA - company status, charges, disqualified directors", "MCA21 master data / charge search", "https://www.mca.gov.in/",
     ["MCA disqualified director", "MCA struck-off company"]),
    ("sebi", "SEBI orders / debarred entities", "SEBI enforcement orders", "https://www.sebi.gov.in/", ["SEBI debarred"]),
    ("ibbi", "IBBI / NCLT insolvency proceedings", "IBBI public announcements", "https://ibbi.gov.in/", ["IBBI insolvency / liquidation"]),
]
ATTEST_STATUS = ["Not checked", "Checked - not found", "Checked - FOUND (adverse)"]


def coverage(entries, screening, attest):
    """One row per required source: automated list coverage + officer's manual check. Nothing is assumed clear."""
    hits = (screening or {}).get("hits") or []
    rows = []
    for key, name, how, url, types in REQUIRED_SOURCES:
        ents = [e for e in entries if e.get("list_name") in types and not str(e.get("source", "")).startswith("SAMPLE")]
        srcs = sorted({str(e.get("source") or "") for e in ents})
        auto_hits = [h for h in hits if h.get("list") in types]
        a = (attest or {}).get(key) or {}
        st_ = a.get("status") or "Not checked"
        if auto_hits or st_.startswith("Checked - FOUND"):
            overall = "ADVERSE - see details"
        elif ents and screening:
            overall = "Clear (list screened)" + (" + officer check" if st_ == "Checked - not found" else "")
        elif st_ == "Checked - not found":
            overall = "Clear (officer check)"
        else:
            overall = "NOT CHECKED"
        rows.append({"key": key, "source": name, "how": how, "url": url,
                     "list": f"{len(ents):,} entries ({'; '.join(srcs)[:80]})" if ents else "not loaded",
                     "auto": (f"{len(auto_hits)} match(es)" if auto_hits else ("no match" if ents and screening else "-")),
                     "officer": st_ + (f" on {a.get('date')}" if a.get("date") else "") + (f" - {a.get('ref')}" if a.get("ref") else ""),
                     "overall": overall})
    return rows


def attest_flags(attest):
    out = []
    names = {k: n for k, n, *_ in REQUIRED_SOURCES}
    for k, a in (attest or {}).items():
        if (a or {}).get("status", "").startswith("Checked - FOUND"):
            out.append({"title": f"Listed: {names.get(k, k)}", "category": "Fraud & watch-list screening", "severity": "High",
                        "evidence": f"Officer check on {a.get('date') or 'n.d.'}: {a.get('ref') or 'see remarks'}",
                        "why": "RBI directions bar fresh credit to listed wilful defaulters and require fraud-listed borrowers to be escalated.",
                        "action": "Escalate to the sanctioning authority / fraud monitoring cell; do not process further without approval.",
                        "source": names.get(k, k)})
    return out


def norm(name):
    s = (name or "").lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(HONORIFIC, " ", s)
    s = re.sub(r"[^a-z0-9& ]", " ", s)
    s = re.sub(LEGAL, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def distinctive(name):
    return {t for t in norm(name).split() if len(t) >= 4 and t not in GENERIC and t not in STATE_WORDS and not t.isdigit()}


IDRX = {"CIN": r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b", "DIN": r"\b\d{8}\b", "PAN": r"\b[A-Z]{5}\d{4}[A-Z]\b", "LLPIN": r"\b[A-Z]{3}-\d{4}\b"}


def id_type(v):
    v = (v or "").strip().upper()
    for k, rx in IDRX.items():
        if re.fullmatch(rx, v):
            return k
    return "ID" if v else ""


# ------------------------------------------------------------------ party extraction from the documents (no AI needed)
ENTITY_RX = re.compile(r"((?:[A-Z][A-Za-z0-9.'\-]*|&|and|of|\(India\))(?:\s+(?:[A-Z][A-Za-z0-9.'\-]*|&|and|of|\(India\))){0,7}\s+"
                       r"(?:Private\s+Limited|Pvt\.?\s*Ltd\.?|Limited|Ltd\.?|LLP))")
PERSON_RX = re.compile(r"\b(?:Mr|Mrs|Ms|Shri|Smt|Dr|Sri)\.?\s+([A-Z][a-zA-Z.]+(?:\s+[A-Z][a-zA-Z.]+){0,3})")
DIN_RX = re.compile(r"([A-Z][A-Za-z.]+(?:\s+[A-Z][A-Za-z.]+){1,4})\s*[,(]?\s*(?:DIN|D\.I\.N\.?)\s*[:\-–]?\s*(\d{8})")
ROLE_WORDS = {"director", "independent", "govt", "government", "secretary", "company", "chairman", "chairperson", "cfo", "ceo", "managing",
              "whole-time", "wholetime", "nominee", "executive", "non-executive", "member", "partner", "proprietor", "din", "and"}
LEAD_JUNK = {"Joint", "Venture", "Research", "Development", "Projects", "Particulars", "Name", "Related", "Party", "Parties", "Subsidiary",
             "Associate", "Holding", "M/s", "M/s.", "Messrs", "Solar", "Power"} - set()
JUNK_WORDS = {"particulars", "rs", "inr", "lakhs", "crores", "total", "year", "ended", "note", "schedule"}
STOP_LEAD = {"To", "The", "Of", "And", "In", "On", "For", "With", "From", "By", "At", "Note", "Members", "Report", "Annexure", "Our", "We", "Board"}


def extract_parties(pages, borrower=""):
    """Entities, persons and DINs mentioned in the documents, with page references."""
    ents, persons, dins = {}, {}, {}
    bn = norm(borrower)
    for doc, pgs in (pages or {}).items():
        for p in pgs:
            txt = re.sub(r"\s+", " ", p.get("text") or "")
            for m in ENTITY_RX.finditer(txt):
                toks = m.group(1).split()
                while toks and (toks[0] in STOP_LEAD or toks[0][:1].islower() or toks[0] in ("&",)):
                    toks = toks[1:]
                while len(toks) > 3 and toks[0] in LEAD_JUNK and distinctive(" ".join(toks[1:])):
                    toks = toks[1:]
                name = " ".join(toks)
                n = norm(name)
                words = n.split()
                if not distinctive(name) or len(words) != len(set(words)) or any(w in JUNK_WORDS for w in words):
                    continue
                if len(n) < 4 or (bn and _ratio(n, bn) >= 90):
                    continue
                if any(w in n.split() for w in ("auditor", "auditors", "order", "annexure", "report")):
                    continue
                ents.setdefault(n, {"name": name, "pages": set(), "doc": doc})["pages"].add(p.get("page"))
            for m in DIN_RX.finditer(txt):
                dins[m.group(2)] = {"name": m.group(1).strip(), "din": m.group(2), "pages": {p.get("page")}, "doc": doc}
            for m in PERSON_RX.finditer(txt):
                nm = m.group(1).strip()
                parts = nm.split()
                while parts and parts[-1].strip(".,").lower() in ROLE_WORDS:
                    parts = parts[:-1]
                nm = " ".join(parts)
                if len(nm.split()) >= 2:
                    persons.setdefault(norm(nm), {"name": nm, "pages": set(), "doc": doc})["pages"].add(p.get("page"))
    # drop entities whose name is contained in a longer one already found (e.g. 'X Limited' inside 'Joint Venture X Limited')
    ents = dict(sorted(ents.items(), key=lambda kv: -len(kv[1]["pages"]))[:30])
    persons = dict(sorted(persons.items(), key=lambda kv: -len(kv[1]["pages"]))[:20])
    out = []
    for v in ents.values():
        out.append({"name": v["name"], "role": "Entity named in documents", "id": "", "pages": sorted(x for x in v["pages"] if x)})
    seen = set()
    for v in dins.values():
        seen.add(norm(v["name"]))
        out.append({"name": v["name"], "role": "Director (from documents)", "id": v["din"], "pages": sorted(v["pages"])})
    for k, v in persons.items():
        if k not in seen:
            out.append({"name": v["name"], "role": "Person named in documents", "id": "", "pages": sorted(x for x in v["pages"] if x)})
    return out


def parties_for(bundle_like, officer_parties=None, pages=None):
    """Assemble every party to screen."""
    company = bundle_like.get("company") or ""
    out = [{"name": company, "role": "Borrower", "id": bundle_like.get("cin") or "", "pages": []}]
    notes = bundle_like.get("notes") or {}
    if notes.get("auditor_name"):
        out.append({"name": notes["auditor_name"], "role": "Statutory auditor", "id": "", "pages": []})
    for rp in notes.get("related_parties") or []:
        if rp.get("name"):
            out.append({"name": rp["name"], "role": f"Related party ({rp.get('relationship') or 'per notes'})", "id": "", "pages": []})
    for p in officer_parties or []:
        if (p.get("name") or "").strip():
            out.append({"name": p["name"].strip(), "role": p.get("role") or "Director / promoter / guarantor", "id": (p.get("id") or "").strip(), "pages": []})
    out += extract_parties(pages, company)
    # de-duplicate on normalised name + id, keeping the most specific role
    def rank(p):
        r = p["role"]
        base = 0 if r == "Borrower" else 1 if r == "Statutory auditor" else 4 if "named in documents" in r else 3 if "from documents" in r else 2
        return (base, 0 if p.get("id") else 1)
    best = {}
    for p in out:
        k = norm(p["name"])
        if not k:
            continue
        if k not in best or rank(p) < rank(best[k]):
            if k in best and not p.get("id") and best[k].get("id"):
                p = {**p, "id": best[k]["id"]}
            best[k] = p
    return list(best.values())


# ------------------------------------------------------------------ list import
COLS = {"name": ["name", "entity", "borrower", "party", "company", "person", "defaulter", "name of the borrower", "entity name",
                 "director name", "name of entity"],
        "identifier": ["cin", "din", "pan", "llpin", "identifier", "id", "registration", "cin/llpin"],
        "reason": ["reason", "remarks", "category", "nature", "order", "status"],
        "list_date": ["date", "as on", "order date", "listed on", "quarter"],
        "directors": ["directors", "director", "promoters", "partners"],
        "amount": ["amount", "outstanding", "amount (rs. lakh)", "amount in lakhs", "o/s"]}


def guess_columns(cols):
    low = {c: str(c).strip().lower() for c in cols}
    out = {}
    for k, cands in COLS.items():
        for c, l in low.items():
            if l in cands or any(l.startswith(x) for x in cands):
                out[k] = c
                break
    return out


def rows_from_df(df, mapping, list_name, source=""):
    rows = []
    for _, r in df.iterrows():
        name = str(r.get(mapping.get("name"), "") or "").strip()
        if not name or name.lower() == "nan":
            continue
        get = lambda k: ("" if mapping.get(k) is None or str(r.get(mapping[k])) == "nan" else str(r.get(mapping[k])).strip())
        rows.append({"list_name": list_name, "name": name, "identifier": get("identifier").upper(), "reason": get("reason"),
                     "list_date": get("list_date"), "directors": get("directors"), "amount": get("amount"), "source": source})
    return rows


# ------------------------------------------------------------------ screening
def screen(parties, entries, borrower_tokens=None):
    """parties: [{name, role, id}], entries: watchlist rows. Returns (hits, summary)."""
    idx_id = {}
    for e in entries:
        if e.get("identifier"):
            idx_id.setdefault(e["identifier"].upper(), []).append(e)
        e["_norm"] = e.get("norm") or norm(e["name"])
        e["_tok"] = distinctive(e["name"])
        e["_dirs"] = [norm(x) for x in re.split(r"[;,/|]", e.get("directors") or "") if norm(x)]
    hits = []
    btok = set(borrower_tokens or [])
    for p in parties:
        pn = norm(p["name"])
        if not pn:
            continue
        pid = (p.get("id") or "").upper()
        found = []
        for e in idx_id.get(pid, []) if pid else []:
            found.append((e, 100, "Confirmed identifier match", "High"))
        ptoks = distinctive(p["name"])
        for e in entries:
            if any(e is f[0] for f in found):
                continue
            sc = _ratio(pn, e["_norm"])
            if sc >= 92:
                found.append((e, sc, "Probable name match", SEVERITY.get(e["list_name"], "Medium")))
            elif sc >= 85:
                found.append((e, sc, "Possible name match - verify identity", "Medium"))
            elif e["_dirs"] and any(_ratio(pn, d) >= 92 for d in e["_dirs"]):
                found.append((e, 95, f"Shared director / promoter - {p['name']} is linked to a listed entity", "High"))
            elif p["role"] in ("Borrower",) or p["role"].startswith("Related party") or p["role"] == "Entity named in documents":
                shared = (ptoks | (btok if p["role"] == "Borrower" else set())) & e["_tok"]
                if shared and len(e["_tok"]) and len(shared) / len(e["_tok"]) >= 0.5:
                    found.append((e, 70, f"Possible group connection - shares the distinctive name '{', '.join(sorted(shared))}'", "Medium"))
        weak_person = (not pid) and p["role"] not in ("Borrower", "Entity named in documents", "Statutory auditor") \
            and sum(1 for t in pn.split() if len(t) > 2) < 2
        for e, sc, kind, sev in found:
            if weak_person and sev == "High" and kind != "Confirmed identifier match":
                sev, kind = "Medium", kind + " (initials only - confirm with DIN / PAN)"
            hits.append({"party": p["name"], "role": p["role"], "party_id": p.get("id") or "", "pages": p.get("pages") or [],
                         "listed_name": e["name"], "list": e["list_name"], "listed_id": e.get("identifier") or "", "reason": e.get("reason") or "",
                         "list_date": e.get("list_date") or "", "score": round(sc), "match": kind, "severity": sev, "source": e.get("source") or ""})
    # escalate parties with several hits
    by_party = {}
    for h in hits:
        by_party.setdefault(h["party"], []).append(h)
    for ph in by_party.values():
        if len({h["list"] for h in ph}) >= 2:
            for h in ph:
                h["severity"] = "High"
                h["match"] += " (appears on several lists)"
    order = {"High": 0, "Medium": 1, "Low": 2}
    hits.sort(key=lambda h: (order.get(h["severity"], 3), -h["score"]))
    summary = {"parties": len(parties), "lists": len({e["list_name"] for e in entries}), "entries": len(entries),
               "hits": len(hits), "high": sum(1 for h in hits if h["severity"] == "High"),
               "when": dt.datetime.now().strftime("%d-%b-%Y %H:%M")}
    return hits, summary


def to_flags(hits):
    """Convert hits into forensic flags (one per party / list)."""
    flags, seen = [], set()
    for h in hits:
        k = (h["party"], h["list"])
        if k in seen:
            continue
        seen.add(k)
        flags.append({"title": f"Watch-list hit: {h['role'].split(' (')[0].lower()} on {h['list'].lower()} list",
                      "category": "Fraud & watch-list screening", "severity": h["severity"],
                      "evidence": f"{h['party']} vs listed '{h['listed_name']}' ({h['match']}, score {h['score']})"
                                  + (f"; reason: {h['reason']}" if h["reason"] else "") + (f"; listed {h['list_date']}" if h["list_date"] else ""),
                      "why": "Lending to, or through, a party on a defaulter / fraud / regulatory list is a direct credit and reputational risk; "
                             "RBI restricts fresh facilities to listed wilful defaulters and their associated entities.",
                      "action": "Confirm identity with CIN / DIN / PAN; obtain the listing details; if confirmed, escalate to the sanctioning "
                                "authority / fraud monitoring cell before any further processing."})
    return flags


# ------------------------------------------------------------------ optional online sanctions / PEP lookup
def opensanctions(parties, api_key, threshold=0.7, timeout=20):
    """OpenSanctions /match API (international sanctions, PEPs, debarment). Returns hits in the same format."""
    import requests
    queries = {}
    for i, p in enumerate(parties[:40]):
        person = not any(w in p["name"].lower() for w in ("limited", "ltd", "llp", "private", "pvt", "corporation", "company")) and \
            p["role"] not in ("Borrower", "Statutory auditor", "Entity named in documents")
        queries[f"q{i}"] = {"schema": "Person" if person else "Company", "properties": {"name": [p["name"]]}}
    r = requests.post("https://api.opensanctions.org/match/default", params={"threshold": threshold},
                      headers={"Authorization": f"ApiKey {api_key}"}, json={"queries": queries}, timeout=timeout)
    r.raise_for_status()
    res = r.json().get("responses", {})
    hits = []
    for i, p in enumerate(parties[:40]):
        for c in (res.get(f"q{i}") or {}).get("results", []):
            if not c.get("match"):
                continue
            hits.append({"party": p["name"], "role": p["role"], "party_id": p.get("id") or "", "pages": p.get("pages") or [],
                         "listed_name": c.get("caption"), "list": "Sanctions / PEP", "listed_id": c.get("id", ""),
                         "reason": ", ".join(c.get("datasets") or [])[:200], "list_date": c.get("last_seen", "")[:10],
                         "score": round(100 * (c.get("score") or 0)), "match": "OpenSanctions match", "severity": "High",
                         "source": f"https://www.opensanctions.org/entities/{c.get('id', '')}/"})
    return hits


def template_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["name", "identifier", "reason", "date", "directors", "amount"])
    w.writerow(["Example Traders Private Limited", "U12345MH2010PTC123456", "Wilful defaulter - Bank X", "2025-03-31", "A Kumar; B Shah", "1250"])
    return buf.getvalue()
