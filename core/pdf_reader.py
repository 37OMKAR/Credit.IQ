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


def _render(page, dpi=220):
    return page.get_pixmap(dpi=dpi).tobytes("png")


def _ocr_page(page, dpi=220):
    return _ocr_bytes(_render(page, dpi))


def _ocr_bytes(img_bytes):
    eng = _get_ocr()
    if eng is None:
        return ""
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


def _ocr_workers():
    import os
    try:
        n = int(os.getenv("OCR_WORKERS", "0"))
    except ValueError:
        n = 0
    return n if n > 0 else max(1, min(4, (os.cpu_count() or 2) // 2))


def read_pdf(data: bytes, ocr_mode="auto", max_pages=None, progress=None):
    """Return list of dicts: {page, text, ocr}.
    ocr_mode: 'auto' (OCR only pages with no text layer), 'force', 'off'.
    Scanned pages are OCR'd several at a time (OCR_WORKERS in .env, default = half the CPU cores, max 4)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    doc = fitz.open(stream=data, filetype="pdf")
    n = len(doc) if max_pages is None else min(len(doc), max_pages)
    pages, need = [], []
    for i in range(n):
        text = _layout_text(doc[i])
        pages.append({"page": i + 1, "text": text, "ocr": False})
        if ocr_mode == "force" or (ocr_mode == "auto" and len(text.strip()) < 60):
            need.append(i)
        if progress and not need:
            progress((i + 1) / n, f"Reading page {i + 1}/{n}")
    if need and _get_ocr() is not None:
        workers = _ocr_workers()
        done = 0
        with ThreadPoolExecutor(max_workers=workers) as pool:
            # render in this thread (PyMuPDF is not thread-safe), OCR in the pool; small batches keep memory low
            for k in range(0, len(need), workers * 2):
                batch = need[k:k + workers * 2]
                futs = {pool.submit(_ocr_bytes, _render(doc[i])): i for i in batch}
                for f in as_completed(futs):
                    i = futs[f]
                    try:
                        o = f.result()
                    except Exception:
                        o = ""
                    if o.strip():
                        pages[i]["text"], pages[i]["ocr"] = o, True
                    done += 1
                    if progress:
                        progress(done / len(need), f"OCR of scanned pages: {done}/{len(need)} ({workers} at a time)")
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


def statement_basis(text):
    head = (text or "")[:700].lower()
    return "consolidated" if "consolidated" in head else "standalone"


def locate_sections(pages, prefer="standalone"):
    """Return {section: [page numbers]} best guesses plus 'basis' (standalone / consolidated actually used).
    The preferred basis is used when the document contains it; a document that only contains the other basis is read
    on that basis (and labelled so) - it is never forced onto the wrong pages."""
    out = {}
    have = {"standalone": 0, "consolidated": 0}
    for p in pages:  # which bases have a titled balance sheet / P&L page?
        for sec in ("balance_sheet", "profit_loss"):
            if score_page(p["text"], sec) >= 9:
                have[statement_basis(p["text"])] += 1
    basis = prefer if have.get(prefer) or not any(have.values()) else max(have, key=have.get)
    out["basis"] = basis
    out["basis_note"] = ("" if basis == prefer else
                         f"The document contains {basis} statements only - analysed on a {basis} basis (the {prefer} statements were not supplied).")
    for sec in SECTION_PATTERNS:
        scored = []
        for p in pages:
            sc = score_page(p["text"], sec)
            if sec in ANCHORS:
                sc += 5 if statement_basis(p["text"]) == basis else -5
            if sc > 0:
                scored.append((sc, p["page"]))
        scored.sort(reverse=True)
        if not scored:
            out[sec] = []
            continue
        if sec in ANCHORS:
            best = scored[0][1]
            picks = [best]
            by_no = {q["page"]: q for q in pages}

            def same_statement(q):
                if not q or statement_basis(q["text"]) != basis:
                    return False
                head = squash(q["text"][:400])
                if any(pt in head for other in ANCHORS if other != sec for pt in SECTION_PATTERNS[other][:2]):
                    return False  # a different statement starts on this page
                return score_page(q["text"], sec) >= 3

            for step in (1, -1):  # statements can run over two or three pages, before or after the best-scoring page
                for k in (1, 2):
                    q = by_no.get(best + step * k)
                    if same_statement(q):
                        picks.append(best + step * k)
                    else:
                        break
            out[sec] = sorted(picks)
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
        (r"(in|rs\.?|₹|inr)\s*(\w+\s+)?hundreds?|'00\b", 0.00001),
        (r"amounts?\s+(are\s+)?in\s+(indian\s+)?(rupees|inr|₹)\b(?!\s*(crore|lakh|lac|million|billion|thousand|hundred|'0))|"
         r"\(\s*(in\s+)?(rupees|rs\.?|₹|inr)\s*\)|figures in rupees|\(amount in (₹|rs\.?|inr|rupees)\)", 1e-7),
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
