"""PDF ingestion: digital text first, OCR fallback for scanned pages,
and a page locator that finds the statements inside a 300-page annual report."""
import io
import re

try:
    import pymupdf as fitz
except ImportError:  # older PyMuPDF
    import fitz

_OCR_ENGINE = None
OCR_AVAILABLE = None


def _get_ocr():
    """Lazy-load RapidOCR (pure pip install, no Tesseract binary needed on Windows)."""
    global _OCR_ENGINE, OCR_AVAILABLE
    if OCR_AVAILABLE is False:
        return None
    if _OCR_ENGINE is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _OCR_ENGINE = RapidOCR()
            OCR_AVAILABLE = True
        except Exception:
            try:
                from rapidocr import RapidOCR  # newer package name
                _OCR_ENGINE = RapidOCR()
                OCR_AVAILABLE = True
            except Exception:
                OCR_AVAILABLE = False
                return None
    return _OCR_ENGINE


def _ocr_page(page, dpi=220):
    eng = _get_ocr()
    if eng is None:
        return ""
    pix = page.get_pixmap(dpi=dpi)
    img_bytes = pix.tobytes("png")
    try:
        result = eng(img_bytes)
    except Exception:
        return ""
    boxes = result[0] if isinstance(result, tuple) else getattr(result, "boxes", None)
    if boxes is None:
        return ""
    # newer rapidocr returns an object with boxes/txts
    if not isinstance(result, tuple) and hasattr(result, "txts"):
        items = [(b, t) for b, t in zip(result.boxes, result.txts)]
    else:
        items = [(r[0], r[1]) for r in (boxes or [])]
    if not items:
        return ""
    # rebuild table rows: group boxes whose vertical centres are close
    rows = []
    for box, txt in items:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        yc, h, x0 = sum(ys) / len(ys), (max(ys) - min(ys)) or 10, min(xs)
        rows.append((yc, h, x0, txt))
    rows.sort(key=lambda r: r[0])
    lines, cur, cur_y, cur_h = [], [], None, None
    for yc, h, x0, txt in rows:
        if cur_y is None or abs(yc - cur_y) <= max(cur_h, h) * 0.55:
            cur.append((x0, txt))
            cur_y = yc if cur_y is None else (cur_y + yc) / 2
            cur_h = h if cur_h is None else max(cur_h, h)
        else:
            lines.append("   ".join(t for _, t in sorted(cur)))
            cur, cur_y, cur_h = [(x0, txt)], yc, h
    if cur:
        lines.append("   ".join(t for _, t in sorted(cur)))
    return "\n".join(lines)


def _layout_text(page):
    """Rebuild visual rows (label ... note ... FY25 ... FY24) from word boxes, so table rows stay on one line."""
    try:
        words = page.get_text("words")  # x0,y0,x1,y1,word,block,line,wno
    except Exception:
        return page.get_text("text") or ""
    if not words:
        return ""
    words.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines, cur, cy = [], [], None
    for w in words:
        yc, h = (w[1] + w[3]) / 2, (w[3] - w[1]) or 8
        if cy is None or abs(yc - cy) <= h * 0.45:
            cur.append(w)
            cy = yc if cy is None else cy
        else:
            lines.append(cur)
            cur, cy = [w], yc
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda w: w[0])
        s, last_x1 = "", None
        for w in ln:
            gap = (w[0] - last_x1) if last_x1 is not None else 0
            s += ("   " if gap > 12 else " ") if s else ""
            s += w[4]
            last_x1 = w[2]
        out.append(s)
    return "\n".join(out)


def read_pdf(data: bytes, ocr_mode="auto", max_pages=None, progress=None):
    """Return list of dicts: {page, text, ocr}.
    ocr_mode: 'auto' (OCR only pages with no text layer), 'force', 'off'."""
    doc = fitz.open(stream=data, filetype="pdf")
    pages = []
    n = len(doc) if max_pages is None else min(len(doc), max_pages)
    for i in range(n):
        page = doc[i]
        text = _layout_text(page)
        used_ocr = False
        if ocr_mode == "force" or (ocr_mode == "auto" and len(text.strip()) < 60):
            o = _ocr_page(page)
            if o.strip():
                text, used_ocr = o, True
        pages.append({"page": i + 1, "text": text, "ocr": used_ocr})
        if progress:
            progress((i + 1) / n, f"Reading page {i + 1}/{n}{' (OCR)' if used_ocr else ''}")
    doc.close()
    return pages


# ---------------------------------------------------------------- locating
# keywords are matched on "squashed" text (lowercase, letters and & only) because OCR often drops spaces
SECTION_PATTERNS = {
    "balance_sheet": ["balancesheetasat", "statementoffinancialposition", "balancesheet"],
    "profit_loss": ["statementofprofitandloss", "statementofprofit&loss", "profitandlossaccount", "profit&lossaccount", "statementofprofit"],
    "cash_flow": ["cashflowstatement", "statementofcashflow"],
    "auditor": ["independentauditorsreport", "basisforqualifiedopinion", "basisforopinion", "emphasisofmatter", "keyauditmatter",
                "materialuncertaintyrelatedtogoingconcern", "auditorsreportorder", "annexuretotheauditorsreport", "annexureatotheindependent"],
    "related_party": ["relatedpartytransactions", "relatedpartydisclosures", "keymanagerialpersonnel", "significantinfluence", "relatedparties"],
    "contingent": ["contingentliabilities", "contingentandotherliabilities", "guaranteesgiven", "bankguarantee", "commitments"],
    "borrowings_note": ["termsofrepayment", "securedby", "hypothecation", "rateofinterest", "workingcapitalloan", "termloan"],
    "brsr": ["businessresponsibilityandsustainabilityreport", "scopeemissions", "principle"],
}

ANCHORS = {
    "balance_sheet": ["totalassets", "tradereceivable", "inventories", "totalequity", "borrowings", "tradepayable", "equitysharecapital", "otherequity"],
    "profit_loss": ["revenuefromoperation", "otherincome", "financecost", "depreciation", "profitbeforetax", "totalexpenses", "taxexpense"],
    "cash_flow": ["operatingactivities", "investingactivities", "financingactivities", "cashandcashequivalents"],
}
AUDIT_MARKERS = ["wehaveaudited", "auditorsresponsibility", "inouropinion", "basisforopinion", "reportonotherlegal"]


def squash(text):
    return re.sub(r"[^a-z&]", "", text.lower())


def score_page(text, section):
    sq = squash(text)
    head = squash(text[:400])
    s = 0.0
    for p in SECTION_PATTERNS.get(section, []):
        if p in sq:
            s += 3
        if p in head and section in ANCHORS:
            s += 4  # statement title at top of page
    for a in ANCHORS.get(section, []):
        if a in sq:
            s += 1
    if section in ANCHORS:
        nums = len(re.findall(r"\d[\d,.]*\.\d{1,2}\b|\d{1,3}(?:,\d{2,3})+", text))
        s += min(nums / 25.0, 3)
        if any(m in sq for m in AUDIT_MARKERS):
            s -= 6  # auditor's report mentions the statements but isn't one
        if sq.count("accountingpolic") > 1 or "significantaccountingpolicies" in head:
            s -= 3
    return s


def locate_sections(pages, prefer="standalone"):
    """Return {section: [page numbers]} best guesses. For statements we keep the top
    page plus its neighbour (statements often run over two pages)."""
    out = {}
    for sec in SECTION_PATTERNS:
        scored = []
        for p in pages:
            sc = score_page(p["text"], sec)
            low = p["text"].lower()
            if sec in ANCHORS:
                if prefer == "standalone" and "consolidated" in low[:600]:
                    sc -= 5
                if prefer == "consolidated" and "consolidated" in low[:600]:
                    sc += 5
            if sc > 0:
                scored.append((sc, p["page"]))
        scored.sort(reverse=True)
        if not scored:
            out[sec] = []
            continue
        if sec in ANCHORS:
            best = scored[0][1]
            picks = [best]
            nxt = next((q for q in pages if q["page"] == best + 1), None)
            if nxt and score_page(nxt["text"], sec) >= 4 and not any(
                    p in squash(nxt["text"][:400]) for other in ANCHORS if other != sec for p in SECTION_PATTERNS[other][:2]):
                picks.append(best + 1)
            out[sec] = picks
        else:
            out[sec] = sorted({pg for sc, pg in scored[:6] if sc >= 3})
    return out


def detect_unit(text):
    """Return multiplier that converts the document's unit into INR Crore."""
    t = text.lower()
    rules = [
        (r"(in|rs\.?|₹|inr)\s*(\w+\s+)?crores?|crore", 1.0),
        (r"(in|rs\.?|₹|inr)\s*(\w+\s+)?lakhs?|lakh|lacs", 0.01),
        (r"(in|rs\.?|₹|inr)\s*(\w+\s+)?millions?|\bmn\b|million", 0.1),
        (r"(in|rs\.?|₹|inr)\s*(\w+\s+)?billions?|billion", 100.0),
        (r"(in|rs\.?|₹|inr)\s*(\w+\s+)?thousands?|'000|in 000", 0.0001),
    ]
    for pat, mult in rules:
        if re.search(pat, t[:4000]):
            return mult
    return 1.0


def pages_text(pages, nums, max_chars=60000):
    chunks = []
    for p in pages:
        if p["page"] in nums:
            chunks.append(f"\n===== PAGE {p['page']} =====\n{p['text']}")
    txt = "".join(chunks)
    return txt[:max_chars]


def doc_profile(pages):
    """Quick facts for the UI."""
    n_ocr = sum(1 for p in pages if p["ocr"])
    first = " ".join(p["text"] for p in pages[:3])
    cin = re.search(r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b", " ".join(p["text"] for p in pages[:40]))
    return {"pages": len(pages), "ocr_pages": n_ocr, "cin": cin.group(0) if cin else None,
            "first_text": first[:1500]}
