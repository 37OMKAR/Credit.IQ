"""Credit Intelligence Workbench - Streamlit dashboard.
Run:  streamlit run app.py   (or double-click run_app.bat on Windows)"""
import datetime as dt
import json
import os
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from core import analyst as AN
from core import credit_tools as CT
from core import report_types as RT
from core import brsr as BR
from core import db as DB
from core import webfetch as WF
from core import watchlist as WL
from core import docs as DOCS
from core import explain as EXPL
from core import extractor as EX
from core import forensics as FZ
from core import narrative as NA
from core import news as NW
from core import pcaf as PC
from core import pdf_reader as PR
from core import pipeline
from core import ratios as R
from core import schema
from core.llm import LEDGER, LLM, PROVIDERS, TASKS, Router, case_cost, ledger_summary

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
REPORTS = os.path.join(HERE, "reports")
CASES = os.path.join(HERE, "cases")
os.makedirs(REPORTS, exist_ok=True)
os.makedirs(CASES, exist_ok=True)

st.set_page_config(page_title="Credit Intelligence Workbench", page_icon="🏦", layout="wide")

# palette (validated categorical slots + reserved status colours)
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
GOOD, WARN, SERIOUS, CRIT = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
SEV_COLOR = {"High": CRIT, "Medium": WARN, "Low": GOOD}
SEV_ICON = {"High": "🔴", "Medium": "🟠", "Low": "🟢"}
DOC_TYPES = ["pdf", "png", "jpg", "jpeg", "tif", "tiff"]
SUPPORT_TYPES = DOC_TYPES + ["docx", "xlsx", "csv", "txt"]
COMMENT_TOPICS = ["General", "Financials", "Management / promoters", "Collateral & security", "Site visit / inspection",
                  "Conduct of account", "Market feedback", "Instruction to AI"]

st.markdown("""
<style>
.block-container {padding-top: 3.2rem; max-width: 1500px;}
.kpi {border: 1px solid rgba(128,128,128,.25); border-radius: 10px; padding: 12px 14px; height: 100%;}
.kpi .l {font-size: .78rem; opacity: .75; margin-bottom: 2px;}
.kpi .v {font-size: 1.45rem; font-weight: 700; line-height: 1.2;}
.kpi .s {font-size: .75rem; opacity: .75;}
.flag {border-left: 4px solid; padding: 6px 10px; margin: 6px 0; border-radius: 4px; background: rgba(255,255,255,.04);}
.kpi {background: rgba(255,255,255,.03);}
.cmt {border: 1px solid rgba(128,128,128,.22); border-radius: 8px; padding: 8px 12px; margin: 6px 0;}
.cmt .m {font-size: .75rem; opacity: .7;}
.kc {background: linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,.02)); border: 1px solid rgba(255,255,255,.08);
      border-radius: 14px; padding: 12px 14px 4px; height: 100%;}
.kc .kl, .mini .kl {font-size: .72rem; letter-spacing: .06em; text-transform: uppercase; opacity: .7;}
.kc .kv {font-size: 1.55rem; font-weight: 700; margin-top: 2px;}
.kc .kd {font-size: .76rem; font-weight: 600; min-height: 1.1em;}
.kc .spark {width: 100%; height: 34px; display: block; margin-top: 4px;}
.mini {background: rgba(255,255,255,.035); border-radius: 12px; padding: 9px 12px; margin-bottom: 9px;}
.mini .mv {font-size: 1.3rem; font-weight: 700;} .mini .ms {font-size: .72rem; opacity: .65;}
.insight {display: flex; gap: 14px; align-items: flex-start; background: rgba(76,141,255,.10); border: 1px solid rgba(76,141,255,.35);
          border-radius: 14px; padding: 12px 16px; margin: 14px 0 6px; font-size: .92rem;}
.insight .ava {font-size: 1.6rem; background: rgba(255,255,255,.08); border-radius: 50%; width: 42px; height: 42px; display: flex;
               align-items: center; justify-content: center; flex-shrink: 0;}
.insight .im {font-size: .74rem; opacity: .7; margin-bottom: 2px;} .insight .ia {opacity: .85; margin-top: 3px;}
.dhead .dt {font-size: .78rem; letter-spacing: .14em; opacity: .6; display: block;}
.dhead .dc {font-size: 1.5rem; font-weight: 700; margin-right: 12px;} .dhead .dm {font-size: .85rem; opacity: .65;}
.pill {float: right; margin-top: 14px; border: 1px solid rgba(255,255,255,.18); border-radius: 999px; padding: 6px 14px; font-weight: 600;}
.step {font-size: .8rem; font-weight: 700; letter-spacing: .04em; opacity: .65; text-transform: uppercase; margin: 6px 0 2px;}
.sub {opacity: .7; margin-top: 0;}
</style>""", unsafe_allow_html=True)

ss = st.session_state
CASE_KEYS = ["ext", "notes", "brsr", "news", "brief", "narr", "pcaf_in", "company", "statement_type", "method",
             "source_file", "cin", "comments", "flag_remarks", "support", "case", "aliases", "web_pcaf", "case_uid", "parties", "screening"]
for k, v in {"pages": {}, "located": {}, "ext": None, "notes": None, "brsr": None, "news": [], "brief": None, "narr": None,
             "pcaf_in": None, "company": "", "statement_type": "standalone", "method": "", "source_file": "", "cin": None,
             "xcheck": None, "web_pcaf": None, "case_uid": None, "comments": [], "flag_remarks": {}, "support": {}, "case": {}, "aliases": "", "_out": None,
             "parties": [], "screening": None}.items():
    ss.setdefault(k, v)


# ------------------------------------------------------------------ accounts / login
DB.init()
FX = float(os.getenv("USD_INR", "88"))
if not ss.get("user"):
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("## 🏦 Credit Intelligence Workbench")
        if not DB.has_admin():
            st.info("First-time setup: create the administrator account.")
            with st.form("setup_admin"):
                u = st.text_input("Admin username")
                n = st.text_input("Full name")
                p1 = st.text_input("Password (min 8 characters)", type="password")
                p2 = st.text_input("Confirm password", type="password")
                if st.form_submit_button("Create admin", type="primary"):
                    if p1 != p2:
                        st.error("Passwords do not match.")
                    else:
                        try:
                            DB.create_user(u, p1, n, "admin")
                            st.success("Admin created - please sign in.")
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
        else:
            with st.form("login"):
                u = st.text_input("Username")
                p = st.text_input("Password", type="password")
                if st.form_submit_button("Sign in", type="primary", use_container_width=True):
                    user = DB.verify(u, p)
                    if user:
                        ss.user = user
                        st.rerun()
                    else:
                        st.error("Wrong username or password, or the account is disabled.")
    st.stop()
USER = ss.user
IS_ADMIN = USER["role"] == "admin"
if not ss.get("case_uid"):
    ss.case_uid = f"{USER['username']}-{dt.datetime.now():%Y%m%d%H%M%S%f}"


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown(f"**👤 {USER.get('name') or USER['username']}** · {USER['role']}" + (f" · {USER.get('branch')}" if USER.get("branch") else ""))
    if st.button("Sign out", use_container_width=True):
        DB.log(USER["username"], "logout")
        for k in list(ss.keys()):
            del ss[k]
        st.rerun()
    st.markdown("### AI keys")
    st.caption("Add any you have. Keys stay on this PC (session only, or save them in the .env file).")
    k_ds = st.text_input("DeepSeek API key", value=os.getenv("DEEPSEEK_API_KEY", ""), type="password")
    k_or = st.text_input("OpenRouter API key", value=os.getenv("OPENROUTER_API_KEY", ""), type="password")
    k_lc = st.text_input("LongCat API key", value=os.getenv("LONGCAT_API_KEY", ""), type="password")
    with st.expander("Models & other providers"):
        m_ds = st.text_input("DeepSeek model", value=os.getenv("DEEPSEEK_MODEL", PROVIDERS["DeepSeek"]["model"]))
        m_or = st.text_input("OpenRouter model", value=os.getenv("OPENROUTER_MODEL", PROVIDERS["OpenRouter"]["model"]),
                             help="Any OpenRouter model id, e.g. deepseek/deepseek-chat, google/gemini-2.5-flash, meituan/longcat-flash-chat")
        m_lc = st.text_input("LongCat model", value=os.getenv("LONGCAT_MODEL", PROVIDERS["LongCat"]["model"]),
                             help="Model id exactly as shown on your LongCat API platform page.")
        oth = st.selectbox("Other provider (optional)", ["-"] + [p for p in PROVIDERS if p not in ("DeepSeek", "OpenRouter", "LongCat")])
        k_ot = m_ot = b_ot = None
        if oth != "-":
            k_ot = st.text_input(f"{oth} API key", value=os.getenv(PROVIDERS[oth]["env"], ""), type="password")
            m_ot = st.text_input(f"{oth} model", value=PROVIDERS[oth]["model"])
            b_ot = st.text_input(f"{oth} base URL", value=PROVIDERS[oth]["base_url"])
    llms = {
        "DeepSeek": LLM("DeepSeek", api_key=k_ds or None, model=m_ds) if k_ds else None,
        "OpenRouter": LLM("OpenRouter", api_key=k_or or None, model=m_or) if k_or else None,
        "LongCat": LLM("LongCat", api_key=k_lc or None, model=m_lc) if k_lc else None,
    }
    if oth != "-" and (k_ot or "Ollama" in oth):
        llms[oth] = LLM(oth, api_key=k_ot or None, model=m_ot or None, base_url=b_ot or None)
    ready_names = [n for n, l in llms.items() if l is not None and l.ready]

    st.markdown("### Cost mode")
    mode = st.radio("Cost mode", ["Cheapest", "Balanced", "Best quality"], horizontal=True, label_visibility="collapsed",
                    help="Cheapest: rule-based reader first, AI only where needed, cheap model for reading, heavy model only for the final report.")
    def _pick(order):
        return next((n for n in order if n in ready_names), ready_names[0] if ready_names else None)
    cheap_order = ["DeepSeek", "OpenRouter", "LongCat"] + ready_names
    heavy_order = ["LongCat", "DeepSeek", "OpenRouter"] + ready_names
    defaults = {}
    for t in TASKS:
        if mode == "Best quality" or t == "narrative":
            defaults[t] = _pick(heavy_order)
        else:
            defaults[t] = _pick(cheap_order)
    assignment = dict(defaults)
    if ready_names:
        with st.expander("Which AI does which job"):
            for t, lbl in TASKS.items():
                assignment[t] = st.selectbox(lbl, ready_names, index=ready_names.index(defaults[t]) if defaults[t] in ready_names else 0, key=f"route_{t}")
            if st.button("Test all keys", use_container_width=True):
                for n in ready_names:
                    try:
                        st.success(f"{n}: {llms[n].test()[:12]}")
                    except Exception as e:
                        st.error(f"{n}: {str(e)[:200]}")
    for _l in llms.values():
        if _l is not None:
            _l.case_id = ss.case_uid
    router = Router(llms, assignment, mode.lower())
    st.caption(("✅ AI ready: " + ", ".join(ready_names)) if ready_names else "⚪ No key - rule-based mode (extraction, ratios, forensics, Excel and Word still work)")

    st.markdown("### Extraction")
    ss.statement_type = st.radio("Statements to analyse", ["standalone", "consolidated"], horizontal=True,
                                 index=1 if ss.statement_type == "consolidated" else 0)
    ocr_mode = st.selectbox("OCR for scanned pages", ["auto", "force", "off"], help="auto = OCR only pages without a text layer")
    max_pages = st.number_input("Max pages to read per PDF", 20, 1000, 450, 10)

    st.markdown("### News (optional keys)")
    newsapi_key = st.text_input("NewsAPI.org key", value=os.getenv("NEWSAPI_KEY", ""), type="password")
    gnews_key = st.text_input("GNews.io key", value=os.getenv("GNEWS_KEY", ""), type="password")
    st.caption("Google News is used without a key.")
    os_key = st.text_input("OpenSanctions API key (sanctions / PEP screening)", value=os.getenv("OPENSANCTIONS_API_KEY", ""), type="password")

    st.markdown("### Officer")
    officer = st.text_input("Your name", value=USER.get("name") or USER["username"])
    branch = st.text_input("Branch / unit", value=USER.get("branch") or os.getenv("BRANCH_NAME", ""))

    st.markdown("### Saved cases")
    mydir = DB.officer_dir(USER["username"])
    files = sorted([f for f in os.listdir(mydir) if f.endswith(".json")], reverse=True)
    pick = st.selectbox("Open one of my saved cases", ["-"] + files)
    if pick != "-" and st.button("Load case", use_container_width=True):
        with open(os.path.join(mydir, pick), encoding="utf-8") as f:
            c = json.load(f)
        for k in CASE_KEYS:
            if k in c:
                ss[k] = c.get(k)
        ss._out = None
        ss.rt_out = None
        st.rerun()
    if st.button("New case (clear)", use_container_width=True):
        keep = ss.get("user")
        for k in list(ss.keys()):
            del ss[k]
        ss.user = keep
        st.rerun()


# ------------------------------------------------------------------ helpers
def _spark(vals, color):
    v = [x_ for x_ in vals if x_ is not None]
    if len(v) < 2:
        return ""
    lo, hi = min(v), max(v)
    rng = (hi - lo) or 1
    pts = [(i * 100 / (len(v) - 1), 34 - (x_ - lo) / rng * 30) for i, x_ in enumerate(v)]
    line = " ".join(f"{x_:.1f},{y_:.1f}" for x_, y_ in pts)
    return (f"<svg viewBox='0 0 100 36' preserveAspectRatio='none' class='spark'><polygon points='0,36 {line} 100,36' fill='{color}' "
            f"fill-opacity='.18'/><polyline points='{line}' fill='none' stroke='{color}' stroke-width='2'/></svg>")


def kcard(col, label, value, delta=None, up_good=True, series=None, unit="%"):
    """KPI card: value, change vs prior year (green when the move is favourable) and a sparkline."""
    if delta is None:
        dtxt, dcol = "", "#8b95a5"
    else:
        good = (delta >= 0) == up_good
        dcol = "#1baf7a" if good else "#ec5d5d"
        arrow = "▲" if delta >= 0 else "▼"
        if unit == "%":
            dtxt = f"{arrow} {abs(delta):.1%} YoY"
        elif unit == "pp":
            dtxt = f"{arrow} {abs(delta) * 100:.1f} pp YoY"
        elif unit == "d":
            dtxt = f"{arrow} {abs(delta):.0f} days YoY"
        else:
            dtxt = f"{arrow} {abs(delta):.2f}x YoY"
    col.markdown(f"<div class='kc'><div class='kl'>{label}</div><div class='kv'>{value}</div>"
                 f"<div class='kd' style='color:{dcol}'>{dtxt}</div>{_spark(series or [], dcol if delta is not None else '#4c8dff')}</div>",
                 unsafe_allow_html=True)


def mini(col, label, value, sub="", color=None):
    col.markdown(f"<div class='mini' style='border-left:4px solid {color or '#4c8dff'}'><div class='kl'>{label}</div>"
                 f"<div class='mv'>{value}</div><div class='ms'>{sub}</div></div>", unsafe_allow_html=True)


def kpi(col, label, value, sub="", color=None):
    style = f"border-left: 5px solid {color};" if color else ""
    col.markdown(f'<div class="kpi" style="{style}"><div class="l">{label}</div><div class="v">{value}</div><div class="s">{sub}</div></div>', unsafe_allow_html=True)


def ext_to_df(ext):
    rows = []
    for k, label, sec, _ in schema.ALL_ITEMS:
        r = {"key": k, "Statement": schema.STATEMENT_OF[k], "Section": sec, "Particulars": label}
        for y in ext["years"]:
            r[y] = ext["data"][y].get(k)
        rows.append(r)
    df = pd.DataFrame(rows)
    for y in ext["years"]:
        df[y] = pd.to_numeric(df[y], errors="coerce").astype("float64")
    return df


def df_to_ext(df, years):
    data = {y: schema.empty_year() for y in years}
    for _, r in df.iterrows():
        for y in years:
            v = r.get(y)
            data[y][r["key"]] = None if (v is None or (isinstance(v, float) and pd.isna(v))) else float(v)
    return data


def merge_ext(base, new):
    if base is None:
        return new
    years = sorted(set(base["years"]) | set(new["years"]), reverse=True)
    data = {}
    for y in years:
        a, b = base["data"].get(y), new["data"].get(y)
        if a is None:
            data[y] = b
        elif b is None:
            data[y] = a
        else:
            data[y] = {k: (a.get(k) if a.get(k) is not None else b.get(k)) for k in schema.KEYS}
    out = dict(base)
    out.update(years=years[:4], data={y: data[y] for y in years[:4]},
               extraction_notes=list(base.get("extraction_notes") or []) + list(new.get("extraction_notes") or []))
    return out


def chart_layout(fig, title, h=320, yfmt=None):
    fig.update_layout(template="plotly_dark", font=dict(color="#d7dbe2"), title=dict(text=title, x=0, y=0.98, yanchor="top", font=dict(size=14)), height=h, margin=dict(l=10, r=10, t=78, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
                      legend=dict(orientation="h", y=1.0, x=0, xanchor="left", yanchor="bottom"), bargap=0.25, bargroupgap=0.08)
    fig.update_xaxes(showgrid=False, type="category")
    fig.update_yaxes(gridcolor="rgba(128,128,128,.18)", zerolinecolor="rgba(128,128,128,.35)", tickformat=yfmt)
    return fig


def case_stem():
    return re.sub(r"[^A-Za-z0-9]+", "_", ss.company or "case").strip("_")[:40]


def save_case(stem=None):
    payload = {k: ss.get(k) for k in CASE_KEYS}
    return DB.save_local(USER["username"], payload, stem or f"{dt.date.today():%Y%m%d}_{case_stem()}")


def clean_company():
    return (ss.company or "").replace("(fictional sample)", "").strip()


# ------------------------------------------------------------------ processing steps (shared by the desk and the tabs)
def process_reports(srcs, log):
    """srcs: list of (name, bytes). Images are grouped into one PDF (photos of a balance sheet)."""
    imgs = [(n, d) for n, d in srcs if n.lower().endswith(DOCS.IMAGE_EXT)]
    pdfs = [(n, d) for n, d in srcs if not n.lower().endswith(DOCS.IMAGE_EXT)]
    if imgs:
        pdfs.append((f"{len(imgs)} photo(s) - {imgs[0][0]}", DOCS.images_to_pdf(imgs)))
    ss.ext, ss.notes, ss.xcheck = None, None, None
    ss.pages, ss.located = {}, {}
    ss.pdf_bytes = dict(pdfs)
    methods = []
    for name, data in pdfs:
        bar = st.progress(0.0, text=f"Reading {name}")
        pages = PR.read_pdf(data, ocr_mode=ocr_mode, max_pages=int(max_pages), progress=lambda p, t: bar.progress(min(p, 1.0), text=t))
        prof = PR.doc_profile(pages)
        if prof["ocr_pages"] and PR.OCR_AVAILABLE is False:
            st.warning("Scanned pages found but the OCR engine is not installed - run setup.bat again (installs rapidocr).")
        loc = PR.locate_sections(pages, prefer=ss.statement_type)
        ss.pages[name], ss.located[name] = pages, loc
        ss.cin = ss.cin or prof["cin"]
        log(f"**{name}** - {prof['pages']} pages ({prof['ocr_pages']} via OCR). Balance sheet p.{loc['balance_sheet']}, "
            f"P&L p.{loc['profit_loss']}, cash flow p.{loc['cash_flow']}")
        heur = EX.heuristic_extract(pages, loc)
        ext = heur
        llm = router.get("extract")
        good, why = rule_spread_ok(heur)
        if llm and router.mode == "cheapest" and good:
            log(f"Rule-based spread passed checks ({why}) - AI extraction skipped, cost ₹0")
        elif llm:
            try:
                log(f"AI extraction with {llm.label} ...")
                ext = EX.llm_extract_financials(llm, pages, loc, ss.statement_type)
                diffs = []
                for y in ext["years"]:
                    if y not in heur["data"]:
                        continue
                    for k in schema.KEYS:
                        a, b = ext["data"][y].get(k), heur["data"][y].get(k)
                        if a is not None and b is not None and abs(a - b) > max(0.01 * abs(a), 0.05):
                            diffs.append({"Year": y, "Item": schema.LABELS[k], "AI": a, "Rule-based": b})
                ss.xcheck = diffs
                if ext.get("company_name") and not ss.company:
                    ss.company = ext["company_name"]
            except Exception as e:
                st.warning(f"AI extraction failed ({e}); using the rule-based reader.")
                ext = heur
        methods.append(ext.get("method", "rule-based"))
        ss.ext = merge_ext(ss.ext, ext)
    if pdfs:
        name0 = pdfs[0][0]
        llm = router.get("notes")
        if llm:
            try:
                log(f"AI review ({llm.label}) of auditor's report, CARO, related-party and contingent-liability notes ...")
                ss.notes = EX.llm_review_notes(llm, ss.pages[name0], ss.located[name0])
            except Exception as e:
                st.warning(f"AI notes review failed ({e}); using keyword scan.")
                ss.notes = EX.heuristic_notes_review(ss.pages[name0], ss.located[name0])
        else:
            ss.notes = EX.heuristic_notes_review(ss.pages[name0], ss.located[name0])
    ss.method = ", ".join(sorted(set(methods)))
    ss.source_file = ", ".join(n for n, _ in srcs)


def process_brsr(name, data, log):
    log(f"Reading BRSR **{name}** ...")
    pages = PR.read_pdf(DOCS.as_pdf_bytes(name, data), ocr_mode=ocr_mode, max_pages=int(max_pages))
    llm = router.get("brsr")
    if llm:
        try:
            ss.brsr = BR.llm_extract_brsr(llm, pages)
            return
        except Exception as e:
            st.warning(f"AI BRSR extraction failed ({e}); using pattern scan.")
    ss.brsr = BR.heuristic_brsr(pages)


def process_support(files, log):
    docs, kw_flags = [], []
    for name, data in files:
        log(f"Reading supporting document **{name}** ...")
        d = DOCS.read_any(name, data, ocr_mode=ocr_mode, max_pages=int(max_pages))
        docs.append({"name": name, "text": d["text"][:60000]})
        scan = EX.heuristic_notes_review(d["pages"], {})
        for f in scan.get("red_flags", []):
            kw_flags.append({"title": f["title"], "severity": f["severity"], "evidence": f"{f['evidence']} [{name}]", "why": f.get("why"),
                             "category": "Supporting documents (keyword scan)", "source": "Keyword"})
    sup = {"docs": docs, "red_flags": kw_flags}
    llm = router.get("support")
    if llm and docs:
        try:
            log("AI review of supporting documents ...")
            rv = NA.llm_review_support(llm, clean_company(), docs)
            sup.update(summary=rv.get("summary"), facts=rv.get("facts"))
            sup["red_flags"] = (rv.get("red_flags") or []) + kw_flags
        except Exception as e:
            st.warning(f"AI review of supporting documents failed ({e}); keyword scan used.")
    ss.support = sup


def process_news(days, log):
    bar = st.progress(0.0, text="Searching news ...")
    raw, errs = NW.fetch_news(clean_company(), [x.strip() for x in (ss.aliases or "").split(",")], days=days,
                              newsapi_key=newsapi_key or None, gnews_key=gnews_key or None,
                              progress=lambda p, t: bar.progress(min(p, 1.0), text=t))
    for e in errs[:2]:
        st.warning(e)
    log(f"{len(raw)} news items found")
    llm = router.get("news")
    if llm and raw:
        ss.news = NW.classify_news(llm, clean_company(), raw)
        try:
            ss.brief = NW.intelligence_brief(llm, clean_company(), ss.news, "")
        except Exception as e:
            st.warning(f"News brief failed: {e}")
    else:
        ss.news = NW.keyword_classify(raw)
        ss.brief = {"overview": f"{len(raw)} articles scanned with keyword rules (add an AI key for a written brief)."}


def pcaf_from_case():
    c = ss.case or {}
    if not c.get("exposure"):
        return
    br = ss.brsr or {}
    factors = PC.load_factors()
    sec = next((f for f in factors if f["sector"] == c.get("sector")), None)
    ss.pcaf_in = dict(outstanding_cr=c["exposure"], asset_class="Listed equity & corporate bonds" if c.get("listed") else "Business loans / unlisted equity",
                      market_cap=c.get("market_cap") or None, scope1=br.get("scope1_tco2e"), scope2=br.get("scope2_tco2e"),
                      scope3=br.get("scope3_tco2e"), verified=br.get("ghg_assurance") in ("reasonable", "limited"),
                      sector_ef=sec["tco2e_per_inr_cr_revenue"] if sec else None, sector_name=sec["sector"] if sec else None)


def rule_spread_ok(heur):
    """Is the free rule-based spread good enough to skip paid AI extraction?"""
    y = heur["years"][0]
    d = heur["data"][y]
    filled = sum(v is not None for v in d.values())
    ta, tel = schema.g(d, "total_assets"), schema.g(d, "total_equity_and_liabilities")
    tallies = ta > 0 and abs(ta - tel) <= 0.01 * ta
    core = all(d.get(k) is not None for k in ("revenue", "pat", "total_equity", "total_current_assets", "total_current_liabilities"))
    if tallies and core and filled >= 25:
        return True, f"{filled} items, balance sheet tallies"
    return False, f"{filled} items, tallies={tallies}, core items={'yes' if core else 'missing'}"


def get_bundle():
    if not (ss.ext and any(any(v is not None for v in ss.ext["data"][y].values()) for y in ss.ext["years"])):
        return None
    years = [y for y in ss.ext["years"] if any(v is not None for v in ss.ext["data"][y].values())]
    c = ss.case or {}
    return pipeline.analyse(ss.ext["data"], years, ss.company or "Company", notes=ss.notes, news=ss.news, brief=ss.brief,
                            brsr=ss.brsr, pcaf_inputs=ss.pcaf_in, statement_type=ss.statement_type, source_file=ss.source_file,
                            method=ss.method, cin=ss.cin, comments=ss.comments, flag_remarks=ss.flag_remarks, support=ss.support,
                            screening=ss.get("screening"),
                            proposal={"facility": c.get("facility"), "amount": c.get("amount", 0), **(c.get("prop") or {})},
                            meta={"sector": (ss.case or {}).get("sector") if (ss.case or {}).get("sector") not in (None, "-") else None,
                                  "located": {k_: {s_: v_ for s_, v_ in l_.items()} for k_, l_ in (ss.located or {}).items()},
                                  "extraction_notes": (ss.ext or {}).get("extraction_notes"),
                                  "model": "; ".join(f"{t}: {v}" for t, v in router.describe().items()) if router.ready else "none (rule-based only)",
                                  "newsapi": bool(newsapi_key)})


def make_outputs(bundle):
    ss.narr = pipeline.write_narrative(bundle, router.get("narrative"))
    cc = case_cost(ss.case_uid, FX)
    bundle.setdefault("meta", {})["ai_cost"] = cc
    bundle["meta"]["fx"] = FX
    docx_b, xlsx_b = pipeline.outputs(bundle, ss.narr, pcaf_inputs=ss.pcaf_in, officer=officer, branch=branch)
    stem = case_stem() + f"_{dt.datetime.now():%Y%m%d_%H%M}"
    rdir = os.path.join(REPORTS, USER["username"])
    os.makedirs(rdir, exist_ok=True)
    paths = {}
    for ext_, data_ in (("docx", docx_b), ("xlsx", xlsx_b)):
        paths[ext_] = os.path.join(rdir, f"CreditIntel_{stem}.{ext_}")
        with open(paths[ext_], "wb") as fh:
            fh.write(data_)
    ss._out = (stem, docx_b, xlsx_b)
    jpath = save_case(stem)
    fz = bundle["forensics"]
    DB.add_case(USER["username"], bundle["company"],
                {"score": fz["score"], "grade": fz["grade"], "recommendation": ss.narr.get("recommendation"),
                 "flags_high": sum(1 for f in fz["flags"] if f["severity"] == "High"), "flags_total": len(fz["flags"])},
                cc["inr"], cc["usd"], cc["calls"], paths["docx"], paths["xlsx"], jpath, ss.source_file, metrics=portfolio_metrics(bundle))
    DB.log(USER["username"], "report_generated", bundle["company"])


def portfolio_metrics(bundle):
    """Snapshot stored with every report so the Portfolio tab can compare borrowers without re-opening cases."""
    y0 = bundle["years"][0]
    d0, r0 = bundle["data"][y0], bundle["ratios"][y0]
    p = CT.proposal(bundle)
    try:
        rows_, _ = CT.projections(bundle, p)
        sm = CT.dscr_summary(rows_)
        _, n_ews = CT.rbi_ews(bundle, p)
    except Exception:
        sm, n_ews = {}, None
    pcf = bundle.get("pcaf") or {}
    return {"year": y0, "sector": (bundle.get("meta") or {}).get("sector"), "exposure": CT.total_proposed(p) or (ss.case or {}).get("exposure") or 0,
            "revenue": schema.g(d0, "revenue"), "net_worth": schema.g(d0, "total_equity"), "ebitda_margin": r0.get("ebitda_margin"),
            "tol_tnw": r0.get("tol_tnw"), "de": r0.get("de"), "current_ratio": r0.get("current_ratio"), "icr": r0.get("icr"),
            "debtor_days": r0.get("debtor_days"), "roce": r0.get("roce"), "proj_avg_dscr": sm.get("avg"), "proj_min_dscr": sm.get("min"),
            "ews": n_ews, "financed_emissions": pcf.get("financed_scope12")}


def downloads(where, prefix="x"):
    if not ss.get("_out"):
        return
    stem, docx_b, xlsx_b = ss._out
    d1, d2 = where.columns(2)
    d1.download_button("⬇ Word credit report (.docx)", docx_b, f"CreditIntel_{stem}.docx", use_container_width=True, type="primary",
                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"dl_docx_{prefix}")
    d2.download_button("⬇ Excel workbook (.xlsx)", xlsx_b, f"CreditIntel_{stem}.xlsx", use_container_width=True, type="primary",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"dl_xlsx_{prefix}")
    where.caption(f"Also saved in: {REPORTS}")


def comment_list(container, allow_delete=True, prefix="c"):
    if not ss.comments:
        container.caption("No comments yet.")
        return
    for i, c in enumerate(ss.comments):
        a, b = container.columns([12, 1])
        a.markdown(f'<div class="cmt"><div class="m">{c.get("when", "")} · {c.get("author") or "Officer"} · {c.get("topic", "General")}</div>'
                   f'{c.get("text", "")}</div>', unsafe_allow_html=True)
        if allow_delete and b.button("🗑", key=f"{prefix}_del_{i}", help="Delete this comment"):
            ss.comments.pop(i)
            st.rerun()


def top_flags(container, fz, n=6):
    for f in sorted(fz["flags"], key=lambda f: {"High": 0, "Medium": 1, "Low": 2}.get(f["severity"], 3))[:n]:
        container.markdown(f'<div class="flag" style="border-color:{SEV_COLOR.get(f["severity"], "#999")}">{SEV_ICON.get(f["severity"], "")} '
                           f'<b>{f["severity"]}</b> · {f["title"]}<br><span style="opacity:.8;font-size:.88rem">{f["evidence"]}</span></div>',
                           unsafe_allow_html=True)


# ------------------------------------------------------------------ header
st.markdown("## 🏦 Credit Intelligence Workbench")
st.markdown('<p class="sub">Upload the borrower\'s documents, add your observations, and get the full credit intelligence back - dashboard, Word report and Excel.</p>', unsafe_allow_html=True)

_tab_names = ["🏠 Officer desk", "Spread review", "Dashboard", "🏦 Proposal & what-if", "Ratios", "Forensic & hidden items",
              "🚨 Early warning", "🕵 Fraud screening", "Market intelligence", "BRSR & PCAF", "📑 Report centre", "💬 Ask the documents", "📈 Portfolio",
              "🗂 History"] + (["🛡 Admin"] if IS_ADMIN else [])
_tabs = st.tabs(_tab_names)
T = dict(zip(["desk", "spread", "dash", "proposal", "ratios", "forensic", "ews", "fraud", "market", "brsr", "reports", "ask", "portfolio",
              "history", "admin"], _tabs))

# ================================================================== OFFICER DESK
with T["desk"]:
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown('<p class="step">Step 1 · Case details</p>', unsafe_allow_html=True)
        c = dict(ss.case or {})
        a, b = st.columns(2)
        ss.company = a.text_input("Borrower / company name *", value=ss.company or "", placeholder="e.g. ABC Industries Limited")
        ss.aliases = b.text_input("Other names / brand / ticker (for news)", value=ss.aliases or "")
        a, b, d = st.columns(3)
        c["facility"] = a.text_input("Proposed facility", value=c.get("facility", ""), placeholder="Term loan + CC")
        c["amount"] = b.number_input("Proposed amount (₹ Cr)", 0.0, 1e7, float(c.get("amount", 0.0)))
        c["exposure"] = d.number_input("Existing / proposed exposure for PCAF (₹ Cr)", 0.0, 1e7, float(c.get("exposure", 0.0)))
        a, b, d = st.columns(3)
        factors = PC.load_factors()
        sectors = ["-"] + [f["sector"] for f in factors]
        c["sector"] = a.selectbox("Sector", sectors, index=sectors.index(c["sector"]) if c.get("sector") in sectors else 0)
        c["listed"] = b.checkbox("Listed company", value=bool(c.get("listed")))
        c["market_cap"] = d.number_input("Market cap (₹ Cr, if listed)", 0.0, 1e8, float(c.get("market_cap") or 0.0), disabled=not c["listed"])
        ss.case = c

        st.markdown('<p class="step">Step 2 · Upload documents</p>', unsafe_allow_html=True)
        ar_files = st.file_uploader("Annual report / audited balance sheet - PDF (digital or scanned) or phone photos. Latest year first; add an older report for 3+ years.",
                                    type=DOC_TYPES, accept_multiple_files=True, key="desk_ar")
        a, b = st.columns(2)
        brsr_file = a.file_uploader("BRSR filing (optional)", type=DOC_TYPES, key="desk_brsr")
        sup_files = b.file_uploader("Supporting documents (optional) - CMA, stock statement, rating rationale, sanction / visit notes, bank statement",
                                    type=SUPPORT_TYPES, accept_multiple_files=True, key="desk_sup")
        sample = os.path.join(HERE, "samples", "Sample_Annual_Report_DeccanPolyfab_FY25.pdf")
        use_sample = False
        if not ar_files and os.path.exists(sample):
            use_sample = st.checkbox("No document handy? Use the fictional sample annual report + BRSR")

    with right:
        st.markdown('<p class="step">Step 3 · Your comments & observations</p>', unsafe_allow_html=True)
        st.caption("Site visit, management meeting, account conduct, collateral, or instructions to the AI. "
                   "They go into the AI narrative and a dedicated section of the Word report.")
        with st.form("add_comment", clear_on_submit=True):
            topic = st.selectbox("Topic", COMMENT_TOPICS)
            txt = st.text_area("Comment", height=110, placeholder="e.g. Plant visited on 12 Oct - 2 of 4 lines idle; promoter says new order from NTPC expected in Q4.")
            if st.form_submit_button("➕ Add comment", use_container_width=True) and txt.strip():
                ss.comments.append({"when": dt.datetime.now().strftime("%d-%b-%Y %H:%M"), "author": officer, "topic": topic, "text": txt.strip()})
                st.rerun()
        comment_list(st, prefix="desk")

    st.markdown('<p class="step">Step 4 · Run</p>', unsafe_allow_html=True)
    o1, o2, o3 = st.columns([2, 1, 1])
    want_news = o2.checkbox("Pull live news", value=True)
    days = o3.selectbox("News look-back", [90, 180, 365, 730], index=2, format_func=lambda x: f"{x} days", label_visibility="collapsed")
    can_run = bool(ar_files or use_sample or ss.ext)
    run_all = o1.button("▶  Run full credit analysis", type="primary", use_container_width=True, disabled=not can_run,
                        help="Reads every document, spreads the financials, runs ratios & forensic checks, pulls news, BRSR & PCAF, and writes the Word + Excel.")
    if not can_run:
        st.caption("Upload at least the annual report / balance sheet (or tick the sample) to run.")

    if run_all:
        if ar_files or use_sample:  # a fresh document = a fresh cost meter
            ss.case_uid = f"{USER['username']}-{dt.datetime.now():%Y%m%d%H%M%S%f}"
            for _l in llms.values():
                if _l is not None:
                    _l.case_id = ss.case_uid
        DB.log(USER["username"], "analysis_run", ss.company)
        with st.status("Running full credit analysis ...", expanded=True) as status:
            log = st.write
            if use_sample:
                ss.company = ss.company or "Deccan Polyfab Industries Ltd (fictional sample)"
                srcs = [(os.path.basename(sample), open(sample, "rb").read())]
                bs = os.path.join(HERE, "samples", "Sample_BRSR_DeccanPolyfab_FY25.pdf")
                brsr_src = (os.path.basename(bs), open(bs, "rb").read()) if os.path.exists(bs) else None
            else:
                srcs = [(f.name, f.getvalue()) for f in ar_files] if ar_files else []
                brsr_src = (brsr_file.name, brsr_file.getvalue()) if brsr_file else None
            if srcs:
                log("**1/6 Reading the financial statements**")
                process_reports(srcs, log)
            else:
                log("1/6 Using the spread already in this case")
            if brsr_src:
                log("**2/6 BRSR**")
                process_brsr(*brsr_src, log)
            if sup_files:
                log("**3/6 Supporting documents**")
                process_support([(f.name, f.getvalue()) for f in sup_files], log)
            pcaf_from_case()
            if want_news and clean_company():
                log("**4/6 Market intelligence**")
                try:
                    process_news(days, log)
                except Exception as e:
                    st.warning(f"News search failed ({e}) - continuing without it.")
            log("**5/6 Ratios, forensic checks and scoring**")
            bundle_ = get_bundle()
            if bundle_ is None:
                status.update(label="Could not read any financial figures - open 'Spread review' to enter them manually.", state="error")
            else:
                log("**6/6 Writing the Word report and Excel workbook**")
                make_outputs(bundle_)
                status.update(label="Done - results below. Explore the other tabs for detail.", state="complete", expanded=False)

    bundle_d = get_bundle()
    if bundle_d:
        st.divider()
        fz = bundle_d["forensics"]
        y0 = bundle_d["years"][0]
        r0 = bundle_d["ratios"][y0]
        nh = sum(1 for f in fz["flags"] if f["severity"] == "High")
        st.markdown(f"#### Result · {bundle_d['company']} · {y0}")
        k = st.columns(5)
        kpi(k[0], "Internal credit score", f"{fz['score']:.0f}/100", fz["grade"], GOOD if fz["score"] >= 60 else (WARN if fz["score"] >= 40 else CRIT))
        kpi(k[1], "Recommendation", (ss.narr or {}).get("recommendation", "—"), "run analysis to refresh" if not ss.narr else (ss.narr.get("_source") or ""))
        kpi(k[2], "Red flags", len(fz["flags"]), f"{nh} high severity", CRIT if nh else GOOD)
        kpi(k[3], "Revenue (₹ Cr)", f"{schema.g(bundle_d['data'][y0], 'revenue'):,.1f}", f"EBITDA margin {R.fmt('ebitda_margin', r0.get('ebitda_margin'))}")
        kpi(k[4], "TOL/TNW · D/E", R.fmt("tol_tnw", r0.get("tol_tnw")), f"D/E {R.fmt('de', r0.get('de'))} · ICR {R.fmt('icr', r0.get('icr'))}")
        st.write("")
        a, b = st.columns([3, 2], gap="large")
        with a:
            st.markdown("**Top red flags** - give your disposition in *Forensic & hidden items*")
            top_flags(st, fz, 5)
        with b:
            st.markdown("**Your outputs**")
            if ss.get("_out"):
                downloads(st, "desk")
            else:
                st.caption("Not generated yet.")
            cc = case_cost(ss.case_uid, FX)
            cost_rows = cc["rows"]
            if True:
                st.markdown(f"**💰 Cost of this report:** ≈ **₹{cc['inr']:,.2f}** (${cc['usd']:,.4f}) · {cc['calls']} AI calls, "
                            f"{cc['cached']} from cache (free)" + ("  ·  ₹0 - rule-based only" if not cc["calls"] else ""))
                with st.expander("Cost by model"):
                    st.dataframe(pd.DataFrame(cost_rows).rename(columns={"in": "input tokens", "out": "output tokens", "usd": "USD (est.)"}),
                                 hide_index=True, use_container_width=True)
                    st.caption(f"USD→INR {FX}. Prices are estimates from data/llm_prices.csv - edit them to match your plans.")
            if st.button("🔁 Update report with my latest comments & edits", use_container_width=True):
                with st.spinner("Re-writing report ..."):
                    make_outputs(get_bundle())
                st.rerun()
            if ss.narr:
                with st.expander("Executive summary"):
                    st.write(ss.narr.get("executive_summary"))
                    st.markdown(f"**{ss.narr.get('recommendation')}** - {ss.narr.get('recommendation_rationale')}")

# ------------------------------------------------------------------ analysis for the remaining tabs
bundle = get_bundle()


def need_data():
    st.info("Run the analysis from the 🏠 Officer desk first (or open a saved case from the sidebar).")


# ================================================================== SPREAD REVIEW
with T["spread"]:
    if not ss.ext:
        st.info("No spread yet. Run the analysis from the 🏠 Officer desk, or start a blank spread for manual / CMA entry.")
        if st.button("Start a blank spread"):
            yrs = [f"FY{dt.date.today().year - i}" for i in range(1, 4)]
            ss.ext = {"years": yrs, "data": {y: schema.empty_year() for y in yrs}, "method": "manual"}
            ss.method = "manual entry"
            st.rerun()
    else:
        st.markdown("#### Review the spread (₹ Crore)")
        st.caption("Correct any cell - every tab updates instantly. Then press *Update report* on the desk. Totals left blank are derived automatically. "
                   "Disclosures (contingent liabilities, related-party amounts, current maturities of LTD, promoter pledge %) can be typed in from the notes.")
        if ss.xcheck:
            with st.expander(f"⚠ {len(ss.xcheck)} items where the AI and the rule-based reader disagree - check these against the PDF"):
                st.dataframe(pd.DataFrame(ss.xcheck), use_container_width=True, hide_index=True)
        if ss.ext.get("extraction_notes"):
            with st.expander(f"ℹ {len(ss.ext['extraction_notes'])} extraction notes (OCR repairs, ambiguities) - please verify"):
                for n_ in ss.ext["extraction_notes"]:
                    st.write("• " + str(n_))
        df = ext_to_df(ss.ext)
        stmt = st.radio("Show", ["Balance Sheet", "Profit & Loss", "Cash Flow", "Disclosures", "All"], horizontal=True)
        view = df if stmt == "All" else df[df["Statement"] == stmt]
        edited = st.data_editor(view, hide_index=True, use_container_width=True, height=min(38 * (len(view) + 1), 900),
                                disabled=["key", "Statement", "Section", "Particulars"],
                                column_config={"key": None, "Statement": None,
                                               **{y: st.column_config.NumberColumn(y, format="%.2f") for y in ss.ext["years"]}},
                                key=f"ed_{stmt}")
        yrs_ = ss.ext["years"]
        if not edited[yrs_].equals(view[yrs_]):
            df.loc[edited.index, yrs_] = edited[yrs_].astype("float64")
            ss.ext["data"] = df_to_ext(df, ss.ext["years"])
        if ss.get("pdf_bytes"):
            with st.expander("📄 Check a figure against the source page"):
                docn = st.selectbox("Document", list(ss.pdf_bytes))
                loc_ = (ss.located or {}).get(docn, {})
                jump = {"Balance sheet": (loc_.get("balance_sheet") or [1])[0], "Profit & loss": (loc_.get("profit_loss") or [1])[0],
                        "Cash flow": (loc_.get("cash_flow") or [1])[0], "Auditor's report": (loc_.get("auditor") or [1])[0]}
                cA, cB = st.columns([1, 1])
                which = cA.radio("Jump to", list(jump), horizontal=False)
                npages = len(ss.pages.get(docn, [])) or 1
                pg_no = cB.number_input("Page", 1, npages, int(jump[which]))
                try:
                    import pymupdf as _fz
                except ImportError:
                    import fitz as _fz
                _d = _fz.open(stream=ss.pdf_bytes[docn], filetype="pdf")
                st.image(_d[int(pg_no) - 1].get_pixmap(dpi=110).tobytes("png"), caption=f"{docn} - page {pg_no}", use_container_width=True)
        cols = st.columns(4)
        new_year = cols[0].text_input("Add year column", placeholder="e.g. FY2023")
        if cols[1].button("Add year") and new_year and new_year not in ss.ext["years"]:
            ss.ext["years"] = sorted(ss.ext["years"] + [new_year], reverse=True)
            ss.ext["data"][new_year] = schema.empty_year()
            st.rerun()
        if cols[2].button("Save case"):
            st.success(f"Saved: {save_case()}")
        if ss.notes and ss.notes.get("available"):
            with st.expander("Auditor's report & notes - what was found"):
                n = ss.notes
                st.write(f"**Opinion:** {(n.get('auditor_opinion') or '-').title()}  ·  **Auditor:** {n.get('auditor_name') or '-'}  ·  "
                         f"**Going-concern doubt:** {'Yes' if n.get('going_concern_uncertainty') else 'No'}  ·  method: {n.get('method', 'AI')}")
                for f in n.get("red_flags") or []:
                    st.markdown(f"{SEV_ICON.get(f.get('severity'), '⚪')} **{f.get('title')}** - {f.get('evidence', '')[:400]} {'(p.' + str(f['page']) + ')' if f.get('page') else ''}")

# ================================================================== DASHBOARD
with T["dash"]:
    if not bundle:
        need_data()
    else:
        y = bundle["years"]
        y0, cols_y = y[0], list(reversed(y))
        d, r, fz = bundle["data"], bundle["ratios"], bundle["forensics"]
        nh = sum(1 for f in fz["flags"] if f["severity"] == "High")
        score_color = GOOD if fz["score"] >= 60 else (WARN if fz["score"] >= 40 else CRIT)
        P_ = CT.proposal(bundle)
        try:
            prow_, _ = CT.projections(bundle, P_)
            psm_ = CT.dscr_summary(prow_)
            ews_, n_ews_ = CT.rbi_ews(bundle, P_)
        except Exception:
            prow_, psm_, n_ews_ = [], {}, 0
        prev_ = y[1] if len(y) > 1 else None
        hd1, hd2 = st.columns([4, 1])
        hd1.markdown(f"<div class='dhead'><span class='dt'>DASHBOARD</span><span class='dc'>{bundle['company']}</span>"
                     f"<span class='dm'>{ss.statement_type} · {cols_y[0]}–{y0} · ₹ crore</span></div>", unsafe_allow_html=True)
        hd2.markdown(f"<div class='pill'>{fz['grade'].split(' - ')[0]} · {fz['score']:.0f}/100</div>", unsafe_allow_html=True)

        def _ser(key, src="d"):
            return [(schema.g(d[yy], key) if src == "d" else r[yy].get(key)) for yy in cols_y]

        def _chg(key, src="d", pct=True):
            if not prev_:
                return None
            a_ = schema.g(d[y0], key) if src == "d" else r[y0].get(key)
            b_ = schema.g(d[prev_], key) if src == "d" else r[prev_].get(key)
            if a_ is None or b_ in (None, 0):
                return None
            return (a_ - b_) / abs(b_) if pct else a_ - b_

        k = st.columns(6)
        kcard(k[0], "💰 Revenue", f"₹{schema.g(d[y0], 'revenue'):,.0f} Cr", _chg("revenue"), True, _ser("revenue"))
        kcard(k[1], "📈 EBITDA margin", R.fmt("ebitda_margin", r[y0].get("ebitda_margin")), _chg("ebitda_margin", "r", False), True,
              _ser("ebitda_margin", "r"), unit="pp")
        kcard(k[2], "🧾 PAT", f"₹{schema.g(d[y0], 'pat'):,.0f} Cr", _chg("pat"), True, _ser("pat"))
        kcard(k[3], "💵 Cash from ops", f"₹{schema.g(d[y0], 'cfo'):,.0f} Cr", _chg("cfo"), True, _ser("cfo"))
        kcard(k[4], "🏦 TOL / TNW", R.fmt("tol_tnw", r[y0].get("tol_tnw")), _chg("tol_tnw", "r", False), False, _ser("tol_tnw", "r"), unit="x")
        kcard(k[5], "⏱ Debtor days", R.fmt("debtor_days", r[y0].get("debtor_days")), _chg("debtor_days", "r", False), False,
              _ser("debtor_days", "r"), unit="d")

        # analyst update banner (insight first, like a CFO note)
        s_, c_ = AN.strengths_concerns(bundle)
        top_c = "; ".join(x_.split(" - ")[0].split(" (benchmark")[0] for x_ in c_[:3]) or "no material concerns from the rule set"
        act_ = CT.ews_action(n_ews_)
        st.markdown(f"<div class='insight'><div class='ava'>🧠</div><div><div class='im'>Analyst update · {dt.date.today():%a, %d %b %Y}</div>"
                    f"<div>🚩 <b>{fz['grade']}</b> - score {fz['score']:.0f}/100 with {nh} high-severity flag(s). Key concerns: {top_c}.</div>"
                    f"<div class='ia'>{act_}</div></div></div>", unsafe_allow_html=True)

        sv = st.tabs(["SNAPSHOT", "PROFITABILITY", "CASH FLOW & WORKING CAPITAL", "RISK & ANALYSIS"])
        with sv[0]:
            a, b, c3 = st.columns([1.1, 2.2, 1])
            with a:
                fig = go.Figure(go.Indicator(mode="gauge+number", value=fz["score"], number=dict(suffix="/100", font=dict(size=30), valueformat=".0f"),
                                             gauge=dict(axis=dict(range=[0, 100], tickwidth=0), bar=dict(color="#e8ecf2", thickness=0.25),
                                                        steps=[dict(range=[0, 40], color=CRIT), dict(range=[40, 60], color=WARN),
                                                               dict(range=[60, 100], color=GOOD)], threshold=dict(line=dict(color="white", width=3), value=fz["score"]))))
                st.plotly_chart(chart_layout(fig, "Internal credit score", h=300), use_container_width=True)
                st.caption(fz["grade"])
            with b:
                fig = go.Figure()
                fig.add_bar(x=cols_y, y=_ser("revenue"), name="Revenue actual", marker_color="#16935f", text=[f"{v_:,.0f}" for v_ in _ser("revenue")],
                            textposition="outside")
                if prow_:
                    fig.add_bar(x=[r_["year"] for r_ in prow_], y=[r_["revenue"] for r_ in prow_], name="Revenue projected",
                                marker_color="rgba(120,220,170,.55)", text=[f"{r_['revenue']:,.0f}" for r_ in prow_], textposition="outside")
                st.plotly_chart(chart_layout(fig, "Revenue - actual vs projected (₹ Cr)", h=300), use_container_width=True)
            with c3:
                mini(st, "Projected min DSCR", "n.a." if psm_.get("min") is None else f"{psm_['min']:.2f}x", "norm ≥ 1.10x",
                     GOOD if (psm_.get("min") or 0) >= 1.1 else CRIT)
                mini(st, "Early-warning signals", f"{n_ews_}", "triggered (RBI list)", CRIT if n_ews_ >= 4 else WARN if n_ews_ else GOOD)
                scr_ = (bundle.get("screening") or {}).get("summary")
                mini(st, "Watch-list hits", "not run" if not scr_ else f"{scr_.get('hits', 0)}", "fraud / defaulter lists",
                     None if not scr_ else (CRIT if scr_.get("high") else WARN if scr_.get("hits") else GOOD))
                mini(st, "Red flags", f"{len(fz['flags'])}", f"{nh} high", CRIT if nh else GOOD)
            st.markdown("##### Top red flags")
            top_flags(st, fz, 4)
        with sv[1]:
            a, b = st.columns(2)
            fig = go.Figure()
            for i, (kk, lbl) in enumerate([("revenue", "Revenue"), ("ebitda", "EBITDA"), ("pat", "PAT")]):
                fig.add_bar(x=cols_y, y=[schema.g(d[yy], kk) for yy in cols_y], name=lbl, marker_color=[C1, C2, C3][i], hovertemplate="%{y:,.1f} Cr")
            a.plotly_chart(chart_layout(fig, "Scale & profitability (₹ Cr)"), use_container_width=True)
            fig = go.Figure()
            for i, (kk, lbl) in enumerate([("ebitda_margin", "EBITDA margin"), ("pat_margin", "PAT margin"), ("roce", "ROCE")]):
                fig.add_scatter(x=cols_y, y=[(r[yy].get(kk) or 0) * 100 for yy in cols_y], name=lbl, mode="lines+markers",
                                line=dict(width=2, color=[C1, C2, C3][i]), marker=dict(size=8), hovertemplate="%{y:.1f}%")
            b.plotly_chart(chart_layout(fig, "Margins & returns (%)"), use_container_width=True)
            yv_, vrows_ = AN.vertical_pl(bundle)
            fig = go.Figure()
            for i_, r_ in enumerate(vrows_[:6]):
                fig.add_bar(x=yv_, y=[(v_ or 0) * 100 for v_ in r_[1:]], name=r_[0], marker_color=[C1, C2, C3, C4, "#8a63d2", "#7a8699"][i_ % 6])
            fig.update_layout(barmode="stack")
            st.plotly_chart(chart_layout(fig, "Cost structure - % of revenue"), use_container_width=True)
        with sv[2]:
            a, b = st.columns(2)
            fig = go.Figure()
            fig.add_bar(x=cols_y, y=[schema.g(d[yy], "pat") for yy in cols_y], name="PAT", marker_color=C1, hovertemplate="%{y:,.1f} Cr")
            fig.add_bar(x=cols_y, y=[schema.g(d[yy], "cfo") for yy in cols_y], name="Cash from operations", marker_color=C2, hovertemplate="%{y:,.1f} Cr")
            a.plotly_chart(chart_layout(fig, "Do profits turn into cash? PAT vs CFO (₹ Cr)"), use_container_width=True)
            fig = go.Figure()
            for i, (kk, lbl) in enumerate([("debtor_days", "Debtor days"), ("inventory_days", "Inventory days"), ("creditor_days", "Creditor days")]):
                fig.add_scatter(x=cols_y, y=[r[yy].get(kk) for yy in cols_y], name=lbl, mode="lines+markers",
                                line=dict(width=2, color=[C1, C2, C3][i]), marker=dict(size=8), hovertemplate="%{y:.0f} d")
            b.plotly_chart(chart_layout(fig, "Working-capital cycle (days)"), use_container_width=True)
            if prow_:
                fig = go.Figure()
                yy_ = [r_["year"] for r_ in prow_]
                fig.add_bar(x=yy_, y=[r_["cash_accruals"] for r_ in prow_], name="Cash accruals", marker_color=C3)
                fig.add_bar(x=yy_, y=[r_["term_principal"] for r_ in prow_], name="Term repayments", marker_color=C2)
                fig.add_scatter(x=yy_, y=[r_["surplus"] for r_ in prow_], name="Surplus", mode="lines+markers", line=dict(color=C4, width=3))
                st.plotly_chart(chart_layout(fig, "Projected cash accruals vs repayments (₹ Cr) - see Proposal & what-if"), use_container_width=True)
        with sv[3]:
            a, b = st.columns(2)
            fig = go.Figure()
            for i, (kk, lbl) in enumerate([("de", "Debt/Equity"), ("tol_tnw", "TOL/TNW"), ("debt_ebitda", "Debt/EBITDA")]):
                fig.add_scatter(x=cols_y, y=[r[yy].get(kk) for yy in cols_y], name=lbl, mode="lines+markers",
                                line=dict(width=2, color=[C1, C2, C3][i]), marker=dict(size=8), hovertemplate="%{y:.2f}x")
            a.plotly_chart(chart_layout(fig, "Leverage (x)"), use_container_width=True)
            cats_ = {}
            for f_ in fz["flags"]:
                cats_.setdefault(f_["category"], {"High": 0, "Medium": 0, "Low": 0})[f_["severity"]] += 1
            fig = go.Figure()
            for sev_, col_ in (("High", CRIT), ("Medium", WARN), ("Low", GOOD)):
                fig.add_bar(y=list(cats_), x=[v_[sev_] for v_ in cats_.values()], name=sev_, orientation="h", marker_color=col_)
            fig.update_layout(barmode="stack")
            b.plotly_chart(chart_layout(fig, "Red flags by area"), use_container_width=True)
            sec_ = (ss.case or {}).get("sector")
            comp_ = AN.sector_comparison(bundle, sec_) if sec_ and sec_ != "-" else None
            an_ = AN.anomalies(bundle)
            cA_, cB_ = st.columns(2)
            with cA_:
                st.markdown(f"##### Sector comparison" + (f" - {sec_}" if comp_ else ""))
                if comp_:
                    st.dataframe(pd.DataFrame(comp_, columns=["Measure", "Company", "Sector norm", "Position"]), hide_index=True, use_container_width=True)
                    st.caption("Indicative norms (data/sector_benchmarks.csv) - replace with your bank's sector norms.")
                else:
                    st.caption("Pick the sector on the Officer desk to compare against sector norms.")
            with cB_:
                st.markdown("##### Line-item anomalies")
                if an_:
                    st.dataframe(pd.DataFrame(an_, columns=["Line item", "Prior", "Latest", "Change", "Materiality"]), hide_index=True, use_container_width=True)
                else:
                    st.caption("No material line-item swings (>50% and >2% of assets/revenue).")
            with st.expander("📊 Horizontal & vertical analysis"):
                yrs_, hrows = AN.horizontal_table(bundle, ["revenue", "other_income", "cogs", "employee_cost", "other_expenses", "ebitda",
                                                           "depreciation", "finance_cost", "pbt", "pat", "cfo", "total_debt", "total_equity", "total_assets"])
                hdf = pd.DataFrame([[r_[0]] + r_[1:-1] + [None if r_[-1] is None else r_[-1] * 100] for r_ in hrows], columns=["Item (₹ Cr)"] + yrs_ + ["YoY %"])
                st.dataframe(hdf, hide_index=True, use_container_width=True, column_config={"YoY %": st.column_config.NumberColumn(format="%.1f%%")})
                yrs_, vrows = AN.vertical_pl(bundle)
                vdf = pd.DataFrame([[r_[0]] + [None if v_ is None else v_ * 100 for v_ in r_[1:]] for r_ in vrows], columns=["% of revenue"] + yrs_)
                st.dataframe(vdf, hide_index=True, use_container_width=True, column_config={y_: st.column_config.NumberColumn(format="%.1f%%") for y_ in yrs_})
                su_ = AN.sources_uses(bundle)
                if su_:
                    st.markdown("**Sources & uses of funds** - " + " ".join(AN.sources_uses_commentary(su_)))


# ================================================================== RATIOS
with T["ratios"]:
    if not bundle:
        need_data()
    else:
        y = bundle["years"]
        cols_y = list(reversed(y))
        rows = []
        for key, name, cat, t, f, direction, good, bad, note in R.RATIOS:
            row = {"Category": cat, "Ratio": name}
            for yy in cols_y:
                row[yy] = R.fmt(key, bundle["ratios"][yy].get(key))
            stt = R.status(key, bundle["ratios"][y[0]].get(key))
            row["Status"] = {"good": "🟢 Within benchmark", "watch": "🟠 Watch", "bad": "🔴 Outside benchmark"}.get(stt, "")
            row["Benchmark"] = ("≥ " if direction == "high" else "≤ " if direction == "low" else "") + (R.fmt(key, good) if good is not None else "")
            row["What it means"] = EXPL.RATIO_HELP.get(key, ("", ""))[1] or note
            rows.append(row)
        cats = ["All"] + list(dict.fromkeys(r_[2] for r_ in R.RATIOS))
        cf = st.radio("Category", cats, horizontal=True)
        rdf = pd.DataFrame(rows)
        if cf != "All":
            rdf = rdf[rdf["Category"] == cf]
        st.dataframe(rdf, hide_index=True, use_container_width=True, height=min(36 * (len(rdf) + 1), 1200))
        fz = bundle["forensics"]
        a, b, c3 = st.columns(3)
        kpi(a, "Beneish M-score", "n.a." if fz["beneish"] is None else f"{fz['beneish']:.2f}", "> -1.78 = manipulation risk",
            None if fz["beneish"] is None else (CRIT if fz["beneish"] > -1.78 else GOOD))
        kpi(b, "Piotroski F-score", "n.a." if fz["piotroski"] is None else f"{fz['piotroski']}/9", "≥7 strong · ≤3 weak")
        kpi(c3, "Altman Z'' (EM)", "n.a." if fz["altman_z"] is None else f"{fz['altman_z']:.2f}", ">2.6 safe · <1.1 distress",
            None if fz["altman_z"] is None else (GOOD if fz["altman_z"] > 2.6 else CRIT if fz["altman_z"] < 1.1 else WARN))

# ================================================================== FORENSIC
with T["forensic"]:
    if not bundle:
        need_data()
    else:
        fz = bundle["forensics"]
        st.caption("For each flag, record your disposition and remark - they print in the Word report. Flags marked "
                   "'Resolved - not a concern' stop reducing the internal score.")
        sev = st.multiselect("Severity", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
        fl = [f for f in fz["flags"] if f["severity"] in sev]
        cnt = pd.DataFrame(fz["flags"]) if fz["flags"] else pd.DataFrame(columns=["category", "severity"])
        if len(cnt):
            piv = cnt.groupby(["category", "severity"]).size().unstack(fill_value=0)
            fig = go.Figure()
            for s_ in ["High", "Medium", "Low"]:
                if s_ in piv:
                    fig.add_bar(y=piv.index, x=piv[s_], name=s_, orientation="h", marker_color=SEV_COLOR[s_], hovertemplate="%{x} flags")
            fig.update_layout(barmode="stack")
            fig = chart_layout(fig, "Red flags by area", h=60 + 34 * len(piv))
            fig.update_yaxes(type="category", autorange="reversed")
            fig.update_xaxes(type="linear", dtick=1)
            fig.update_layout(hovermode="closest")
            st.plotly_chart(fig, use_container_width=True)
        changed = False
        for f in sorted(fl, key=lambda f: {"High": 0, "Medium": 1, "Low": 2}.get(f["severity"], 3)):
            fid = FZ.flag_id(f)
            cur = ss.flag_remarks.get(fid, {})
            tag = "" if cur.get("status", "Open") == "Open" else f"  ·  ✎ {cur['status']}"
            with st.expander(f"{SEV_ICON.get(f['severity'], '')} {f['severity']} · {f['category']} · {f['title']}{tag}"):
                st.markdown(f"**Evidence:** {f['evidence']}\n\n**Why it matters:** {f['why']}\n\n**Action:** {f['action']}\n\n*Source: {f.get('source')}*")
                a, b = st.columns([1, 2])
                stt = a.selectbox("Your disposition", FZ.FLAG_STATUSES, index=FZ.FLAG_STATUSES.index(cur.get("status", "Open")), key=f"st_{fid}")
                rmk = b.text_area("Your remark", value=cur.get("remark", ""), key=f"rm_{fid}", height=70,
                                  placeholder="e.g. Loan to group co. repaid on 30-Jun per bank statement; obtained CA certificate.")
                if stt != cur.get("status", "Open") or rmk != cur.get("remark", ""):
                    ss.flag_remarks[fid] = {"status": stt, "remark": rmk}
                    changed = True
        if changed:
            st.rerun()
        a, b = st.columns(2)
        if fz.get("beneish_vars"):
            a.markdown("**Beneish components** (index > 1 = deterioration)")
            a.dataframe(pd.DataFrame([fz["beneish_vars"]]).T.rename(columns={0: "Index"}), use_container_width=True)
        if fz.get("piotroski_tests"):
            b.markdown("**Piotroski tests**")
            b.dataframe(pd.DataFrame([(k_, "✅" if v_ else "❌") for k_, v_ in fz["piotroski_tests"].items()], columns=["Test", "Pass"]), hide_index=True, use_container_width=True)
        n = ss.notes or {}
        if n.get("related_parties"):
            st.markdown("**Related-party transactions (from notes)**")
            st.dataframe(pd.DataFrame(n["related_parties"]), hide_index=True, use_container_width=True)
        if n.get("borrowing_details"):
            st.markdown("**Borrowing profile (from notes)**")
            st.dataframe(pd.DataFrame(n["borrowing_details"]), hide_index=True, use_container_width=True)
        sup = ss.support or {}
        if sup.get("summary") or sup.get("facts"):
            st.markdown("**Supporting documents - AI review**")
            st.write(sup.get("summary", ""))
            for x in sup.get("facts") or []:
                st.markdown(f"- {x}")

# ================================================================== MARKET INTELLIGENCE
with T["market"]:
    if not ss.company:
        st.info("Enter the company name on the 🏠 Officer desk.")
    else:
        a, b = st.columns([1, 3])
        days_t = a.selectbox("Look-back", [90, 180, 365, 730], index=2, format_func=lambda x: f"{x} days", key="news_days")
        if b.button("Pull live news & build intelligence", type="primary"):
            process_news(days_t, st.write)
            st.rerun()
        if ss.news:
            nd = pd.DataFrame(ss.news)
            k = st.columns(4)
            kpi(k[0], "Articles", len(nd))
            kpi(k[1], "Negative", int((nd["sentiment"] == "Negative").sum()), "", CRIT)
            kpi(k[2], "High-severity", int((nd["severity"] == "High").sum()), "fraud / default / probe / downgrade", CRIT)
            if ss.brief and ss.brief.get("news_sentiment_score") is not None:
                kpi(k[3], "Sentiment score", ss.brief["news_sentiment_score"], "-100 … +100")
            if ss.brief:
                st.markdown("##### Intelligence brief")
                st.write(ss.brief.get("overview", ""))
                c1, c2 = st.columns(2)
                for col, title, kk in [(c1, "Positives", "key_positives"), (c2, "Concerns", "key_concerns"),
                                       (c1, "Regulatory / legal", "regulatory_legal"), (c2, "Governance", "management_governance")]:
                    if ss.brief.get(kk):
                        col.markdown(f"**{title}**\n" + "\n".join(f"- {x}" for x in ss.brief[kk]))
            fsel = st.multiselect("Filter tone", ["Negative", "Neutral", "Positive"], default=["Negative", "Neutral", "Positive"])
            show = nd[nd["sentiment"].isin(fsel)][["date", "title", "source", "sentiment", "severity", "category", "summary", "url"]]
            st.dataframe(show, hide_index=True, use_container_width=True, column_config={"url": st.column_config.LinkColumn("Link", display_text="open")})
        else:
            st.caption("No news pulled yet.")

# ================================================================== BRSR & PCAF
with T["brsr"]:
    a, b = st.columns([1, 1])
    with a:
        st.markdown("#### BRSR filing")
        bf = st.file_uploader("Upload / replace BRSR", type=DOC_TYPES, key="brsr_up")
        if bf and st.button("Scan BRSR", type="primary"):
            with st.spinner("Reading BRSR..."):
                process_brsr(bf.name, bf.getvalue(), lambda *_: None)
                pcaf_from_case()
            st.rerun()
        if ss.brsr:
            br = ss.brsr
            st.caption(f"Method: {br.get('method')}")
            show = {k_: v_ for k_, v_ in br.items() if not isinstance(v_, (list, dict)) and v_ not in (None, "") and not k_.startswith("_") and k_ not in ("summary", "method")}
            st.dataframe(pd.DataFrame(show.items(), columns=["Indicator", "Value"]).astype(str), hide_index=True, use_container_width=True)
            if br.get("summary"):
                st.write(br["summary"])
            for f in br.get("esg_red_flags") or []:
                st.markdown(f"{SEV_ICON.get(f.get('severity'), '⚪')} **{f.get('title')}** - {f.get('evidence')}")
        else:
            st.caption("No BRSR scanned yet.")
    with b:
        st.markdown("#### PCAF financed emissions")
        factors = PC.load_factors()
        # ---- web fetch of market cap / emissions / sector
        wl = WF.web_llm(k_or, m_or.replace(":online", "")) if k_or else None
        if wl:
            wl.case_id = ss.case_uid
        c1_, c2_ = st.columns([2, 1])
        c1_.caption("Pull market cap, reported Scope 1/2/3 (BRSR) and sector from the internet, then calculate.")
        if c2_.button("🌐 Fetch from web", type="primary", use_container_width=True, disabled=not (wl and ss.company),
                      help="Needs the OpenRouter key (web search). Costs about ₹2-4 per fetch."):
            with st.spinner("Searching the web (BRSR, annual report, NSE/BSE) ..."):
                try:
                    ss.web_pcaf = WF.fetch_pcaf_inputs(wl, clean_company(), ss.cin)
                    DB.log(USER["username"], "web_fetch_pcaf", ss.company)
                except Exception as e:
                    st.error(f"Web fetch failed: {e}")
        if not wl:
            st.caption("Add the OpenRouter key in the sidebar to enable web fetch.")
        w = ss.web_pcaf or {}
        if w:
            wt = pd.DataFrame([
                ["Market capitalisation (₹ Cr)", w.get("market_cap_inr_cr"), w.get("market_cap_date")],
                ["Scope 1 (tCO2e)", w.get("scope1_tco2e"), w.get("financial_year")],
                ["Scope 2 (tCO2e)", w.get("scope2_tco2e"), w.get("financial_year")],
                ["Scope 3 (tCO2e)", w.get("scope3_tco2e"), w.get("financial_year")],
                ["Emissions declared?", "Yes" if w.get("emissions_declared") else "No", w.get("ghg_assurance")],
                ["Sector", w.get("sector"), w.get("nic_or_industry")],
                ["Listed", "Yes" if w.get("listed") else "No", w.get("exchange_symbol")],
            ], columns=["Field (from web)", "Value", "As of / detail"]).astype(str)
            st.dataframe(wt, hide_index=True, use_container_width=True)
            if w.get("sources"):
                with st.expander(f"Sources ({len(w['sources'])}) - verify before use"):
                    for src in w["sources"]:
                        st.markdown(f"- **{src.get('field', '')}**: [{src.get('url', '')}]({src.get('url', '')}) {src.get('note', '')}")
        br = dict(ss.brsr or {})
        for kk_ in ("scope1_tco2e", "scope2_tco2e", "scope3_tco2e"):
            if not br.get(kk_) and w.get(kk_):
                br[kk_] = w.get(kk_)
        prev = dict(ss.pcaf_in or {})
        if w.get("market_cap_inr_cr") and not prev.get("market_cap"):
            prev["market_cap"] = w["market_cap_inr_cr"]
            prev.setdefault("asset_class", "Listed equity & corporate bonds" if w.get("listed") else "Business loans / unlisted equity")
        if w and "verified" not in prev:
            prev["verified"] = w.get("ghg_assurance") in ("reasonable", "limited")
        with st.form("pcaf"):
            out_cr = st.number_input("Bank's outstanding exposure (INR Cr)", 0.0, 1e7, float(prev.get("outstanding_cr") or (ss.case or {}).get("exposure") or 0.0), 1.0)
            ac = st.selectbox("PCAF asset class", ["Business loans / unlisted equity", "Listed equity & corporate bonds"],
                              index=1 if str(prev.get("asset_class", "")).startswith("Listed") else 0)
            mc = st.number_input("Market capitalisation (INR Cr, listed only)", 0.0, 1e8, float(prev.get("market_cap") or 0.0), 10.0)
            s1 = st.number_input("Scope 1 (tCO2e)", 0.0, 1e10, float(prev.get("scope1") or br.get("scope1_tco2e") or 0.0))
            s2 = st.number_input("Scope 2 (tCO2e)", 0.0, 1e10, float(prev.get("scope2") or br.get("scope2_tco2e") or 0.0))
            s3 = st.number_input("Scope 3 (tCO2e, optional)", 0.0, 1e11, float(prev.get("scope3") or br.get("scope3_tco2e") or 0.0))
            ver = st.checkbox("GHG data is third-party assured", value=bool(prev.get("verified", br.get("ghg_assurance") in ("reasonable", "limited"))))
            names = [f["sector"] for f in factors]
            _ws = (w.get("sector") or "").lower()
            _guess = next((n_ for n_ in names if _ws and (n_.lower().split(" ")[0] in _ws or _ws.split(" ")[0] in n_.lower())), None)
            sec_i = names.index(prev.get("sector_name")) if prev.get("sector_name") in names else (names.index(_guess) if _guess else 0)
            sec = st.selectbox("Sector (fallback when no reported emissions)", names, index=sec_i)
            ef = st.number_input("Sector emission factor (tCO2e / INR Cr revenue)", 0.0, 1e5,
                                 float(prev.get("sector_ef") or next((f["tco2e_per_inr_cr_revenue"] for f in factors if f["sector"] == sec), 0.0)))
            st.caption("Default sector factors are illustrative placeholders (data/emission_factors.csv) - replace with PCAF database / bank-approved values.")
            if st.form_submit_button("Calculate", type="primary"):
                ss.pcaf_in = dict(outstanding_cr=out_cr, asset_class=ac, market_cap=mc or None, scope1=s1 or None, scope2=s2 or None,
                                  scope3=s3 or None, verified=ver, sector_ef=ef, sector_name=sec)
                st.rerun()
        if bundle and bundle.get("pcaf"):
            p = bundle["pcaf"]
            k = st.columns(3)
            kpi(k[0], "Attribution factor", "n.a." if p["attribution_factor"] is None else f"{p['attribution_factor']:.3%}", p["denominator_name"])
            kpi(k[1], "Financed Scope 1+2", "n.a." if p["financed_scope12"] is None else f"{p['financed_scope12']:,.0f} t", "tCO2e")
            kpi(k[2], "PCAF data quality", p["data_quality_score"] or "n.a.", "1 best · 5 worst")
            st.caption(f"Method: {p['method']}" + (f" · ⚠ {p['warning']}" if p.get("warning") else ""))
        elif not bundle:
            st.caption("Extract financials first - the denominator uses the balance sheet.")

# ================================================================== REPORTS & COMMENTS
with T["reports"]:
    if not bundle:
        need_data()
    else:
        a, b = st.columns([3, 2], gap="large")
        with a:
            st.markdown("#### Credit appraisal outputs")
            if st.button("Generate / refresh Word + Excel", type="primary"):
                with st.spinner("Writing the credit narrative..." if router.ready else "Building reports..."):
                    make_outputs(bundle)
                st.rerun()
            downloads(st, "rep")
            st.markdown("#### 📑 More reports from the same analysis")
            st.caption("Pick the documents you need - each is built from the same verified numbers, so they always agree with the memorandum and workbook.")
            names = [n_ for n_ in RT.REPORT_TYPES if not n_.startswith("Credit Appraisal Memorandum")]
            for n_ in names:
                st.markdown(f"<span style='opacity:.85'>• <b>{n_}</b> - {RT.REPORT_TYPES[n_][1]}</span>", unsafe_allow_html=True)
            pick = st.multiselect("Reports to generate", names, default=ss.get("rt_pick") or ["Credit Committee Note", "Query Letter to Borrower"])
            ss.rt_pick = pick
            if st.button("Generate selected reports", disabled=not pick):
                if not ss.narr:
                    ss.narr = pipeline.write_narrative(bundle, router.get("narrative"))
                rdir = os.path.join(REPORTS, USER["username"])
                os.makedirs(rdir, exist_ok=True)
                ss.rt_out = {}
                with st.spinner("Building reports..."):
                    for n_ in pick:
                        try:
                            data_ = RT.build(n_, bundle, ss.narr, officer=officer, branch=branch)
                            fn_ = f"{re.sub(r'[^A-Za-z0-9]+', '_', n_).strip('_')}_{case_stem()}_{dt.datetime.now():%Y%m%d_%H%M}.docx"
                            with open(os.path.join(rdir, fn_), "wb") as fh:
                                fh.write(data_)
                            ss.rt_out[n_] = (fn_, data_)
                        except Exception as e:
                            st.error(f"{n_}: {e}")
                DB.log(USER["username"], "reports_generated", f"{bundle['company']}: {', '.join(pick)}")
            for i_, (n_, (fn_, data_)) in enumerate((ss.get("rt_out") or {}).items()):
                st.download_button(f"⬇ {n_}", data_, fn_, key=f"rt_dl_{i_}", use_container_width=True,
                                   mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            if ss.narr:
                st.caption(f"Narrative source: {ss.narr.get('_source')}")
                st.markdown(f"**Recommendation: {ss.narr.get('recommendation')}** - {ss.narr.get('recommendation_rationale')}")
                st.write(ss.narr.get("executive_summary"))
        with b:
            st.markdown("#### Comments on this case")
            comment_list(st, prefix="rep")
            dispo = [f for f in bundle["forensics"]["flags"] if f.get("remark") or f.get("status", "Open") != "Open"]
            if dispo:
                st.markdown("**Flag dispositions**")
                for f in dispo:
                    st.markdown(f"- **{f['title']}** → {f['status']}" + (f": {f['remark']}" if f.get("remark") else ""))


# ================================================================== ASK THE DOCUMENTS
with T["ask"]:
    st.markdown("#### 💬 Ask the documents")
    st.caption("Ask anything about the uploaded statements, notes and auditor's report. Answers cite page numbers - check them in Spread review › source page.")
    qa_llm = router.get("notes")
    if not ss.get("pages"):
        st.info("Run an analysis first so the documents are loaded.")
    elif not qa_llm:
        st.info("Add an AI key in the sidebar to ask questions.")
    else:
        ss.setdefault("qa", [])
        for qa in ss.qa:
            st.chat_message("user").write(qa["q"])
            st.chat_message("assistant").write(qa["a"])
        q = st.chat_input("e.g. What are the contingent liabilities? Who are the related parties? Any delay in statutory dues?")
        if q:
            ctx = ""
            for name_, pgs in ss.pages.items():
                for p_ in pgs:
                    ctx += f"\n=== {name_} | page {p_['page']} ===\n{p_['text']}"
            # keep cost low: send only the pages that mention the question's words (plus statements)
            words = [w for w in re.findall(r"[a-zA-Z]{4,}", q.lower())]
            chunks = ctx.split("\n=== ")
            ranked = sorted(chunks, key=lambda c_: -sum(c_.lower().count(w) for w in words))[:12]
            with st.spinner(f"Reading with {qa_llm.label} ..."):
                try:
                    ans = qa_llm.chat("You answer questions about a company's financial documents for a bank credit officer. Answer only from the "
                                      "pages given, quote figures exactly, and cite pages as (document, p.N). If not found, say so. End with a line "
                                      "'Confidence: High / Medium / Low - <reason>' (Low when the pages only partly answer the question).",
                                      f"Question: {q}\n\nPAGES:\n=== " + "\n=== ".join(ranked)[:60000], max_tokens=1200)
                except Exception as e:
                    ans = f"Error: {e}"
            ss.qa.append({"q": q, "a": ans})
            DB.log(USER["username"], "ask", q[:200])
            st.rerun()

# ================================================================== HISTORY
with T["history"]:
    st.markdown("#### 🗂 Case history" + (" - all officers" if IS_ADMIN else " - my cases"))
    rows = DB.cases(None if IS_ADMIN else USER["username"])
    if not rows:
        st.info("No reports yet. Every report you generate is stored here automatically.")
    else:
        hd = pd.DataFrame(rows)
        q = st.text_input("Search company", "")
        if q:
            hd = hd[hd["company"].str.contains(q, case=False, na=False)]
        k = st.columns(4)
        kpi(k[0], "Reports", len(hd))
        kpi(k[1], "Total AI cost", f"₹{hd['cost_inr'].fillna(0).sum():,.2f}")
        kpi(k[2], "Avg cost / report", f"₹{(hd['cost_inr'].fillna(0).mean() if len(hd) else 0):,.2f}")
        kpi(k[3], "Companies", hd["company"].nunique())
        show_cols = ["id", "created", "username", "company", "score", "grade", "recommendation", "flags_high", "flags_total", "cost_inr", "ai_calls"]
        st.dataframe(hd[show_cols].rename(columns={"cost_inr": "cost ₹", "flags_high": "high flags", "username": "officer"}),
                     hide_index=True, use_container_width=True,
                     column_config={"cost ₹": st.column_config.NumberColumn(format="₹%.2f")})
        pick_id = st.selectbox("Open a report", hd["id"].tolist(),
                               format_func=lambda i: f"#{i} · {hd.set_index('id').loc[i, 'company']} · {hd.set_index('id').loc[i, 'created'][:16]}")
        row = hd.set_index("id").loc[pick_id]
        c1, c2, c3 = st.columns(3)
        for col, key_, lbl, mime in [(c1, "docx_path", "⬇ Word report", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                                     (c2, "xlsx_path", "⬇ Excel workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]:
            p_ = row[key_]
            if p_ and os.path.exists(p_):
                with open(p_, "rb") as fh:
                    col.download_button(lbl, fh.read(), os.path.basename(p_), mime=mime, use_container_width=True, key=f"h_{key_}_{pick_id}")
            else:
                col.caption("File not found on this PC")
        if c3.button("Re-open this case", use_container_width=True) and row["case_json_path"] and os.path.exists(row["case_json_path"]):
            with open(row["case_json_path"], encoding="utf-8") as f:
                cj = json.load(f)
            for k_ in CASE_KEYS:
                if k_ in cj:
                    ss[k_] = cj.get(k_)
            ss._out = None
            st.rerun()

# ================================================================== ADMIN
if IS_ADMIN:
    with T["admin"]:
        st.markdown("#### 🛡 Administration")
        a, b = st.columns([1, 1], gap="large")
        with a:
            st.markdown("**Create an officer account**")
            with st.form("new_user", clear_on_submit=True):
                nu = st.text_input("Username")
                nn = st.text_input("Full name")
                nb = st.text_input("Branch / unit")
                nr = st.selectbox("Role", ["officer", "admin"])
                npw = st.text_input("Temporary password (min 8)", type="password")
                if st.form_submit_button("Create account", type="primary"):
                    try:
                        DB.create_user(nu, npw, nn, nr, nb)
                        DB.log(USER["username"], "user_created", nu)
                        st.success(f"Created {nu}")
                    except Exception as e:
                        st.error(str(e))
            st.markdown("**Users**")
            ud = pd.DataFrame(DB.users())
            st.dataframe(ud, hide_index=True, use_container_width=True)
            if len(ud):
                tu = st.selectbox("Manage user", ud["username"].tolist())
                c1, c2 = st.columns(2)
                newpw = c1.text_input("New password", type="password", key="rpw")
                if c1.button("Reset password") and newpw:
                    try:
                        DB.set_password(tu, newpw)
                        st.success("Password reset")
                    except Exception as e:
                        st.error(str(e))
                if c2.button("Disable" if int(ud.set_index("username").loc[tu, "active"]) else "Enable") and tu != USER["username"]:
                    DB.set_active(tu, not int(ud.set_index("username").loc[tu, "active"]))
                    st.rerun()
        with b:
            allc = pd.DataFrame(DB.cases())
            st.markdown("**AI cost by officer**")
            if len(allc):
                agg = allc.groupby("username").agg(reports=("id", "count"), cost_inr=("cost_inr", "sum"),
                                                   avg_cost=("cost_inr", "mean"), last=("created", "max")).reset_index()
                st.dataframe(agg, hide_index=True, use_container_width=True,
                             column_config={"cost_inr": st.column_config.NumberColumn("total ₹", format="₹%.2f"),
                                            "avg_cost": st.column_config.NumberColumn("avg ₹ / report", format="₹%.2f")})
                kpi(st, "All-time AI spend", f"₹{allc['cost_inr'].fillna(0).sum():,.2f}", f"{len(allc)} reports")
            else:
                st.caption("No reports yet.")
            st.markdown("**Recent activity**")
            st.dataframe(pd.DataFrame(DB.activity(200)), hide_index=True, use_container_width=True, height=320)
            st.caption(f"Central database: {DB.DB_PATH}")


# ================================================================== PROPOSAL & WHAT-IF
def _pct_in(col, label, key, val, lo=0.0, hi=30.0, step=0.05, help=None):
    return col.number_input(label, lo, hi, float(round(val * 100, 2)), step, key=key, help=help) / 100


with T["proposal"]:
    if not bundle:
        need_data()
    else:
        c = dict(ss.case or {})
        P0 = CT.proposal({**bundle, "proposal": {"facility": c.get("facility"), "amount": c.get("amount", 0), **(c.get("prop") or {})}})
        st.markdown("#### 🏦 Loan proposal, repayment capacity and what-if")
        st.caption("Structure the facilities, then move the sliders - DSCR, scenarios, drawing power, security cover and pricing recalculate instantly. "
                   "Everything here flows into the memorandum, committee note, term sheet and the Excel 'Projections & DSCR' tab.")
        P = dict(P0)
        with st.container(border=True):
            st.markdown("**Facility structure**")
            a, b_, c_, d_ = st.columns(4)
            P["tl_amount"] = a.number_input("Term loan (₹ Cr)", 0.0, 1e6, float(P0["tl_amount"]), 1.0, key="pp_tl")
            P["tl_tenor_years"] = b_.number_input("Tenor (years)", 1, 20, int(P0["tl_tenor_years"]), key="pp_ten")
            P["tl_moratorium_months"] = c_.number_input("Moratorium (months)", 0, 60, int(P0["tl_moratorium_months"]), 3, key="pp_mor")
            P["tl_rate"] = _pct_in(d_, "TL rate (% p.a.)", "pp_tlr", P0["tl_rate"])
            a, b_, c_, d_ = st.columns(4)
            P["cc_amount"] = a.number_input("Cash credit / WC (₹ Cr)", 0.0, 1e6, float(P0["cc_amount"]), 1.0, key="pp_cc")
            P["cc_rate"] = _pct_in(b_, "CC rate (% p.a.)", "pp_ccr", P0["cc_rate"])
            P["nfb_amount"] = c_.number_input("BG / LC non-fund (₹ Cr)", 0.0, 1e6, float(P0["nfb_amount"]), 1.0, key="pp_nfb")
            P["takeover_amount"] = d_.number_input("Existing debt taken over (₹ Cr)", 0.0, 1e6, float(P0.get("takeover_amount") or 0.0), 1.0, key="pp_to",
                                                   help="Existing borrowings repaid out of this loan - excluded from 'other lenders' when computing security cover.")
            a, b_ = st.columns([2, 1])
            P["purpose"] = a.text_input("Purpose", P0.get("purpose") or "", key="pp_purp", placeholder="e.g. Capacity expansion - new extrusion line")
            P["tl_capex"] = b_.checkbox("Term loan funds new fixed assets", value=bool(P0.get("tl_capex", True)), key="pp_capex")
        with st.container(border=True):
            st.markdown("**Security**")
            a, b_, c_ = st.columns([1, 1, 2])
            P["collateral_value"] = a.number_input("Collateral market value (₹ Cr)", 0.0, 1e6, float(P0["collateral_value"]), 1.0, key="pp_coll")
            P["collateral_type"] = b_.text_input("Collateral type", P0["collateral_type"], key="pp_ctype")
            P["guarantee"] = c_.text_input("Guarantee", P0["guarantee"], key="pp_guar")
            P["primary_security"] = st.text_input("Primary security", P0["primary_security"], key="pp_prim")
        with st.container(border=True):
            st.markdown("**What-if assumptions**")
            a, b_, c_, d_ = st.columns(4)
            base_g = CT._hist_growth(bundle)
            P["growth"] = a.slider("Revenue growth p.a.", -30.0, 40.0, float(round((P0["growth"] if P0.get("growth") is not None else base_g) * 100, 1)), 0.5,
                                   key="pp_g", format="%.1f%%", help=f"History-based default: {base_g:.1%}") / 100
            P["margin_shift"] = b_.slider("EBITDA margin change (pp)", -10.0, 10.0, float(P0["margin_shift"] * 100), 0.25, key="pp_m", format="%+.2f") / 100
            P["rate_shift"] = c_.slider("Interest-rate change (bp)", -200, 400, int(P0["rate_shift"] * 1e4), 25, key="pp_r") / 1e4
            P["proj_years"] = d_.slider("Projection years", 3, 10, int(P0["proj_years"]), key="pp_y")
        with st.expander("Bank policy parameters (pricing, margins, exposure norms) - illustrative defaults, set once for your bank"):
            a, b_, c_, d_ = st.columns(4)
            P["base_rate"] = _pct_in(a, "Benchmark rate (EBLR / MCLR) %", "pp_base", P0["base_rate"])
            P["cost_of_funds"] = _pct_in(b_, "Cost of funds %", "pp_cof", P0["cost_of_funds"])
            P["opex_ratio"] = _pct_in(c_, "Operating cost %", "pp_opex", P0["opex_ratio"], step=0.05)
            P["target_roe"] = _pct_in(d_, "Target return on capital %", "pp_roe", P0["target_roe"], hi=40.0)
            a, b_, c_, d_ = st.columns(4)
            P["capital_ratio"] = _pct_in(a, "Capital ratio (CRAR incl. buffer) %", "pp_crar", P0["capital_ratio"])
            P["risk_weight"] = _pct_in(b_, "Risk weight %", "pp_rw", P0["risk_weight"], hi=250.0, step=5.0)
            P["collateral_haircut"] = _pct_in(c_, "Haircut on security %", "pp_hc", P0["collateral_haircut"], hi=90.0, step=5.0)
            P["ccf_nfb"] = _pct_in(d_, "CCF on non-fund %", "pp_ccf", P0["ccf_nfb"], hi=100.0, step=5.0)
            a, b_, c_, d_ = st.columns(4)
            P["stock_margin"] = _pct_in(a, "Margin on stock %", "pp_sm", P0["stock_margin"], hi=60.0, step=5.0)
            P["debtor_margin"] = _pct_in(b_, "Margin on receivables %", "pp_dm", P0["debtor_margin"], hi=60.0, step=5.0)
            P["eligible_debtor_share"] = _pct_in(c_, "Receivables < 90 days %", "pp_el", P0["eligible_debtor_share"], hi=100.0, step=5.0)
            P["existing_ltd_years"] = d_.number_input("Existing term debt - years left (0 = auto)", 0, 20, int(P0["existing_ltd_years"] or 0), key="pp_exy")
            a, b_, c_ = st.columns(3)
            P["tier1_capital"] = a.number_input("Bank Tier-1 capital (₹ Cr)", 0.0, 1e7, float(P0["tier1_capital"]), 100.0, key="pp_t1")
            P["existing_exposure"] = b_.number_input("Existing exposure to borrower (₹ Cr)", 0.0, 1e7, float(P0["existing_exposure"]), 1.0, key="pp_exe")
            P["group_exposure"] = c_.number_input("Existing exposure to the group (₹ Cr)", 0.0, 1e7, float(P0["group_exposure"]), 1.0, key="pp_grp")
            st.caption("PD by grade (illustrative): " + ", ".join(f"{k} {v:.2%}" for k, v in CT.PD_BY_GRADE.items()) + " - edit PD_BY_GRADE in core/credit_tools.py to your bank's master scale.")
        with st.expander("Account conduct & last year's projections (for renewals and early-warning signals)"):
            a, b_, c_, d_ = st.columns(4)
            P["dpd"] = a.number_input("Days past due (today)", 0, 999, int(P0["dpd"] or 0), key="pp_dpd")
            P["cheque_returns"] = b_.number_input("Cheque returns (12 m)", 0, 999, int(P0["cheque_returns"] or 0), key="pp_chq")
            P["prev_grade"] = c_.selectbox("Previous internal grade", ["", "CI-1", "CI-2", "CI-3", "CI-4", "CI-5", "CI-6", "CI-7"],
                                           index=["", "CI-1", "CI-2", "CI-3", "CI-4", "CI-5", "CI-6", "CI-7"].index(P0.get("prev_grade") or ""), key="pp_pg")
            P["prev_proj_revenue"] = d_.number_input("Last year's projected revenue (₹ Cr)", 0.0, 1e7, float(P0["prev_proj_revenue"] or 0), key="pp_ppr")
            a, b_, c_, d_ = st.columns(4)
            P["prev_proj_pat"] = a.number_input("Last year's projected PAT (₹ Cr)", -1e6, 1e7, float(P0["prev_proj_pat"] or 0), key="pp_ppp")
            P["stock_stmt_delay"] = b_.checkbox("Stock statements delayed", bool(P0["stock_stmt_delay"]), key="pp_ssd")
            P["adhoc_overdrawn"] = c_.checkbox("Frequent ad hoc / overdrawing", bool(P0["adhoc_overdrawn"]), key="pp_adh")
            P["non_routing"] = d_.checkbox("Sales not routed through us", bool(P0["non_routing"]), key="pp_nr")
            a, b_ = st.columns(2)
            P["cash_withdrawals_high"] = a.checkbox("Heavy cash withdrawals", bool(P0["cash_withdrawals_high"]), key="pp_cw")
            P["unrecorded_charges"] = b_.checkbox("ROC charges not in books", bool(P0["unrecorded_charges"]), key="pp_uc")
        c["prop"] = {k: v for k, v in P.items() if k in CT.PROPOSAL_DEFAULTS}
        ss.case = c
        bp = {**bundle, "proposal": {**(bundle.get("proposal") or {}), **c["prop"]}}

        rows_, asm = CT.projections(bp, P)
        sm = CT.dscr_summary(rows_)
        be = CT.breakeven(bp, P)
        sc = CT.security_cover(bp, P)
        rp = CT.risk_pricing(bp, P)
        k = st.columns(6)
        kpi(k[0], "Average DSCR", ("n.a." if sm["avg"] is None else f"{sm['avg']:.2f}x"), "norm ≥ 1.25x",
            GOOD if (sm["avg"] or 0) >= 1.25 else CRIT)
        kpi(k[1], "Minimum DSCR", "n.a." if sm["min"] is None else f"{sm['min']:.2f}x", sm.get("min_year") or "", GOOD if (sm["min"] or 0) >= 1.10 else CRIT)
        kpi(k[2], "EBITDA cushion", "n.a." if be is None else f"{be:.0%}", "fall before min DSCR < 1.0x", GOOD if (be or 0) >= 0.2 else WARN if (be or 0) > 0 else CRIT)
        kpi(k[3], "Security cover", "n.a." if sc["cover"] is None else f"{sc['cover']:.2f}x", "FACR " + ("n.a." if sc["facr"] is None else f"{sc['facr']:.2f}x"))
        kpi(k[4], "Minimum price", f"{rp['floor']:.2%}", f"proposed {rp['proposed']:.2%}", GOOD if rp["proposed"] >= rp["floor"] else CRIT)
        kpi(k[5], "RAROC", "n.a." if rp["raroc"] is None else f"{rp['raroc']:.1%}", f"target {P['target_roe']:.0%}", GOOD if (rp["raroc"] or 0) >= P["target_roe"] else WARN)

        t1, t2, t3, t4, t5 = st.tabs(["Projections & DSCR", "Scenarios", "Repayment schedule", "Working capital & DP", "Security & pricing"])
        with t1:
            fig = go.Figure()
            yrs_ = [r_["year"] for r_ in rows_]
            fig.add_bar(x=yrs_, y=[r_["pat"] + r_["depreciation"] + r_["term_interest"] for r_ in rows_], name="Cash available for debt service", marker_color=C1)
            fig.add_bar(x=yrs_, y=[r_["term_interest"] + r_["term_principal"] for r_ in rows_], name="Term debt service", marker_color=C2)
            fig.add_scatter(x=yrs_, y=[r_["dscr"] if r_["dscr"] is not None and r_["dscr"] < 10 else None for r_ in rows_], name="DSCR",
                            yaxis="y2", mode="lines+markers", line=dict(color=C3, width=3))
            fig.update_layout(yaxis2=dict(overlaying="y", side="right", title="DSCR (x)", showgrid=False, tickformat=".2f", rangemode="tozero"))
            fig.add_shape(type="line", xref="paper", x0=0, x1=1, yref="y2", y0=1.25, y1=1.25, line=dict(dash="dash", color="#999"))
            st.plotly_chart(chart_layout(fig, "Cash available vs term debt service (₹ Cr) and DSCR", h=360), use_container_width=True)
            lines = [("Revenue", "revenue", "cr"), ("EBITDA", "ebitda", "cr"), ("EBITDA margin", "margin", "%"), ("Interest", "interest", "cr"),
                     ("PAT", "pat", "cr"), ("Cash accruals", "cash_accruals", "cr"), ("Term principal due", "term_principal", "cr"),
                     ("Surplus after repayment", "surplus", "cr"), ("DSCR", "dscr", "x"), ("Interest coverage", "icr", "x"),
                     ("Net worth", "net_worth", "cr"), ("TOL / TNW", "tol_tnw", "x"), ("Debt / EBITDA", "debt_ebitda", "x")]
            fmt_ = lambda v, f: "n.a." if v is None else (f"{v:.1%}" if f == "%" else f"{v:,.2f}x" if f == "x" else f"{v:,.2f}")
            st.dataframe(pd.DataFrame([[lab] + [fmt_(r_[k_], f) for r_ in rows_] for lab, k_, f in lines], columns=["₹ Cr"] + yrs_),
                         hide_index=True, use_container_width=True, height=36 * (len(lines) + 1))
            st.caption(f"Assumptions: growth {asm['growth']:.1%}, EBITDA margin {asm['margin']:.1%}, existing term debt ₹{asm['existing_ltd']:,.2f} Cr over "
                       f"{asm['existing_ltd_years']} yrs at {asm['debt_rate']:.1%}, WC debt ₹{asm['wc_debt']:,.2f} Cr at {asm['wc_rate']:.1%}, tax 25.17%.")
        with t2:
            scn = CT.scenarios(bp, P)
            st.dataframe(pd.DataFrame([{"Scenario": s_["scenario"], "Growth": f"{s_['growth']:.1%}", "Margin shift": f"{s_['margin_shift'] * 100:+.1f} pp",
                                        "Rate shift": f"{s_['rate_shift'] * 1e4:+.0f} bp", "Avg DSCR": fmt_(s_["avg_dscr"], "x"),
                                        "Min DSCR": fmt_(s_["min_dscr"], "x"), "Y+1 ICR": fmt_(s_["y1_icr"], "x"),
                                        "Cumulative surplus ₹ Cr": fmt_(s_["cum_surplus"], "cr")} for s_ in scn]), hide_index=True, use_container_width=True)
            fig = go.Figure()
            for s_, col_ in zip(scn, [C1, C3, C4, CRIT]):
                r2, _ = CT.projections(bp, P, growth=s_["growth"], margin_shift=s_["margin_shift"], rate_shift=s_["rate_shift"])
                fig.add_scatter(x=[r_["year"] for r_ in r2], y=[r_["dscr"] if r_["dscr"] is not None and r_["dscr"] < 10 else None for r_ in r2],
                                name=s_["scenario"], mode="lines+markers", line=dict(color=col_))
            fig.add_hline(y=1.0, line_dash="dot", line_color="#888")
            st.plotly_chart(chart_layout(fig, "DSCR by scenario", h=320, yfmt=".2f"), use_container_width=True)
        with t3:
            sched, inst, n_ = CT.amortisation(P["tl_amount"], P["tl_tenor_years"], P["tl_moratorium_months"], P["tl_rate"] + P["rate_shift"])
            if sched:
                st.write(f"**{n_} quarterly instalments of ₹{inst:,.3f} Cr** after a {P['tl_moratorium_months']}-month moratorium.")
                st.dataframe(pd.DataFrame([{"Year": f"Y+{r_['year']}", "Opening": round(r_["opening"], 2), "Interest": round(r_["interest"], 2),
                                            "Principal": round(r_["principal"], 2), "Closing": round(r_["closing"], 2)} for r_ in sched]),
                             hide_index=True, use_container_width=True)
            else:
                st.info("Enter a term-loan amount above to see the repayment schedule.")
        with t4:
            w_ = CT.wc_methods(bp, P)
            a, b_ = st.columns(2)
            a.dataframe(pd.DataFrame([[r_[0]] + [None if v is None else round(v, 2) for v in r_[1:]] for r_ in w_["rows"]],
                                     columns=["₹ Cr", "Tandon I", "Tandon II", "Turnover"]), hide_index=True, use_container_width=True)
            a.write(f"Requested / existing WC: **₹{w_['requested']:,.2f} Cr** · assessed eligibility **₹{w_['assessed']:,.2f} Cr** · "
                    + (f"headroom ₹{w_['headroom']:,.2f} Cr" if w_["headroom"] >= 0 else f"**excess ₹{-w_['headroom']:,.2f} Cr**"))
            dp_ = CT.drawing_power(bp, P)
            b_.dataframe(pd.DataFrame([[a_, round(v, 2)] for a_, v in dp_["rows"]], columns=["Drawing power", "₹ Cr"]), hide_index=True, use_container_width=True)
        with t5:
            a, b_ = st.columns(2)
            a.dataframe(pd.DataFrame([[a_, round(v, 2)] for a_, v in sc["rows"]], columns=["Security", "₹ Cr"]), hide_index=True, use_container_width=True)
            a.write(f"Security cover **{fmt_(sc['cover'], 'x')}** · FACR **{fmt_(sc['facr'], 'x')}** · LTV {fmt_(sc['ltv'], '%')}")
            b_.dataframe(pd.DataFrame(rp["rows"], columns=["Pricing", "Value"]), hide_index=True, use_container_width=True, height=36 * (len(rp["rows"]) + 1))
            st.markdown("**Regulatory checks**")
            st.dataframe(pd.DataFrame(CT.regulatory(bp, P), columns=["Check", "Position", "Result"]), hide_index=True, use_container_width=True)

# ================================================================== EARLY WARNING
with T["ews"]:
    if not bundle:
        need_data()
    else:
        P = CT.proposal(bundle)
        ews_rows, n_trig = CT.rbi_ews(bundle, P)
        st.markdown("#### 🚨 RBI early-warning signals")
        st.caption("Tested against the EWS indicators in the RBI framework for fraud risk management. 'Bank data needed' items depend on account "
                   "conduct, bank statements or registry searches - record them under Proposal › Account conduct.")
        k = st.columns(4)
        kpi(k[0], "Signals triggered", n_trig, f"of {len(ews_rows)} tested", CRIT if n_trig >= 4 else WARN if n_trig >= 2 else GOOD)
        kpi(k[1], "Not observed", sum(1 for e in ews_rows if e[1] == "Not observed"))
        kpi(k[2], "Need bank data", sum(1 for e in ews_rows if e[1] == "Bank data needed"))
        kpi(k[3], "Account status", CT.sma_status(P.get("dpd")).split(" (")[0].split(" -")[0])
        (st.error if n_trig >= 4 else st.warning if n_trig >= 1 else st.success)(CT.ews_action(n_trig))
        icon = {"Triggered": "🔴", "Not observed": "🟢", "Bank data needed": "🟡"}
        st.dataframe(pd.DataFrame([{"": icon.get(s_, ""), "Signal": a_, "Status": s_, "Basis": b2} for a_, s_, b2 in ews_rows]),
                     hide_index=True, use_container_width=True, height=35 * (len(ews_rows) + 1) + 3)
        dp_rows = CT.dupont(bundle)
        if dp_rows:
            st.markdown("#### ROE decomposition (DuPont) & earnings quality")
            for t_ in CT.dupont_commentary(dp_rows):
                st.write(t_)
            eq = {e["year"]: e for e in CT.earnings_quality(bundle)}
            st.dataframe(pd.DataFrame([{"Year": r_["year"], "Tax burden": f"{r_['tax_burden']:.2f}" if r_["tax_burden"] is not None else "n.a.",
                                        "Interest burden": f"{r_['interest_burden']:.2f}" if r_["interest_burden"] is not None else "n.a.",
                                        "EBIT margin": f"{r_['ebit_margin']:.1%}", "Asset turnover": f"{r_['asset_turnover']:.2f}x",
                                        "Equity multiplier": f"{r_['equity_multiplier']:.2f}x", "ROE": f"{r_['roe']:.1%}",
                                        "Accrual ratio": "n.a." if eq[r_["year"]]["accrual_ratio"] is None else f"{eq[r_['year']]['accrual_ratio']:.1%}",
                                        "CFO / PAT": "n.a." if eq[r_["year"]]["cfo_pat"] is None else f"{eq[r_['year']]['cfo_pat']:.2f}x"}
                                       for r_ in reversed(dp_rows)]), hide_index=True, use_container_width=True)

# ================================================================== PORTFOLIO
with T["portfolio"]:
    st.markdown("#### 📈 Portfolio view" + (" - all officers" if IS_ADMIN else " - my borrowers"))
    st.caption("Latest report per borrower. Compare borrowers side by side, see the risk mix and watch-list, and track financed emissions.")
    rows_db = DB.cases(None if IS_ADMIN else USER["username"])
    recs = []
    for r_ in rows_db:
        try:
            m_ = json.loads(r_.get("metrics") or "{}")
        except Exception:
            m_ = {}
        recs.append({**{k_: r_.get(k_) for k_ in ("id", "created", "username", "company", "score", "grade", "recommendation", "flags_high")}, **m_})
    if not recs:
        st.info("No reports yet - each report you generate adds the borrower here.")
    else:
        pf = pd.DataFrame(recs).sort_values("id", ascending=False).drop_duplicates("company")
        pf["grade_code"] = pf["grade"].fillna("").str.split(" ").str[0]
        for col_ in ("exposure", "financed_emissions", "ews", "proj_min_dscr", "tol_tnw", "score"):
            if col_ not in pf:
                pf[col_] = None
            pf[col_] = pd.to_numeric(pf[col_], errors="coerce")
        expo = pf["exposure"].fillna(0)
        watch = pf[(pf["grade_code"].isin(["CI-5", "CI-6", "CI-7"])) | (pf["ews"].fillna(0) >= 2) | (pf["flags_high"].fillna(0) >= 3)]
        k = st.columns(5)
        kpi(k[0], "Borrowers", len(pf))
        kpi(k[1], "Proposed exposure", f"₹{expo.sum():,.0f} Cr")
        kpi(k[2], "Exposure-weighted score", f"{(pf['score'].fillna(0) * expo).sum() / expo.sum():.0f}/100" if expo.sum() else f"{pf['score'].mean():.0f}/100")
        kpi(k[3], "On watch-list", len(watch), "grade CI-5+, 2+ EWS or 3+ high flags", CRIT if len(watch) else GOOD)
        kpi(k[4], "Financed emissions", f"{pf['financed_emissions'].fillna(0).sum():,.0f} tCO2e", "Scope 1+2, PCAF")
        a, b_ = st.columns(2)
        gc = pf.groupby("grade_code").agg(n=("company", "count"), exp=("exposure", "sum")).reindex(["CI-1", "CI-2", "CI-3", "CI-4", "CI-5", "CI-6", "CI-7"]).fillna(0)
        fig = go.Figure()
        fig.add_bar(x=gc.index, y=gc["exp"], name="Exposure ₹ Cr", marker_color=[GOOD, GOOD, C1, C1, WARN, CRIT, CRIT])
        a.plotly_chart(chart_layout(fig, "Exposure by internal grade (₹ Cr)", h=300), use_container_width=True)
        if "sector" in pf:
            sg = pf.assign(sector=pf["sector"].fillna("Not set")).groupby("sector")["exposure"].sum().sort_values()
            fig = go.Figure()
            fig.add_bar(x=sg.values, y=sg.index, orientation="h", marker_color=C1, name="Exposure")
            fig.update_xaxes(range=[0, max(float(sg.max()), 1) * 1.15])
            b_.plotly_chart(chart_layout(fig, "Exposure by sector (₹ Cr)", h=300), use_container_width=True)
        if len(watch):
            st.markdown("**Watch-list**")
            st.dataframe(watch[["company", "grade", "score", "ews", "flags_high", "proj_min_dscr", "exposure", "recommendation", "created"]]
                         .rename(columns={"ews": "EWS", "flags_high": "high flags", "proj_min_dscr": "min DSCR (proj.)", "exposure": "exposure ₹ Cr"}),
                         hide_index=True, use_container_width=True,
                         column_config={"min DSCR (proj.)": st.column_config.NumberColumn(format="%.2fx"), "score": st.column_config.NumberColumn(format="%.0f")})
        st.markdown("**Peer comparison**")
        pick = st.multiselect("Borrowers to compare", pf["company"].tolist(), default=pf["company"].tolist()[:4])
        if pick:
            sel = pf.set_index("company").loc[pick]
            show = {"Year": "year", "Sector": "sector", "Grade": "grade_code", "Score": "score", "Revenue ₹ Cr": "revenue", "Net worth ₹ Cr": "net_worth",
                    "EBITDA margin": "ebitda_margin", "ROCE": "roce", "TOL/TNW": "tol_tnw", "Debt/Equity": "de", "Current ratio": "current_ratio",
                    "Interest cover": "icr", "Debtor days": "debtor_days", "Projected avg DSCR": "proj_avg_dscr", "Projected min DSCR": "proj_min_dscr",
                    "EWS triggered": "ews", "High flags": "flags_high", "Exposure ₹ Cr": "exposure", "Financed emissions tCO2e": "financed_emissions"}

            def _f(lab, v):
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return "-"
                if isinstance(v, (int, float)):
                    if lab in ("EBITDA margin", "ROCE"):
                        return f"{v:.1%}"
                    if lab in ("TOL/TNW", "Debt/Equity", "Current ratio", "Interest cover") or "DSCR" in lab:
                        return f"{v:.2f}x"
                    return f"{v:,.0f}" if abs(v) >= 100 or lab in ("Score", "Debtor days", "EWS triggered", "High flags") else f"{v:,.2f}"
                return str(v)
            st.dataframe(pd.DataFrame({c_: [_f(lab, sel.loc[c_].get(k_)) for lab, k_ in show.items()] for c_ in pick}, index=list(show)),
                         use_container_width=True, height=36 * (len(show) + 1))


# ================================================================== FRAUD & WATCH-LIST SCREENING
WL_SOURCES = [
    ("Wilful defaulters & suit-filed accounts", "TransUnion CIBIL suit-filed search (RBI directs banks to report these lists to CICs)", "https://transunioncibil.com/suit-filed-cases/overview"),
    ("SEBI debarred entities / orders", "SEBI enforcement orders", "https://www.sebi.gov.in/"),
    ("MCA disqualified directors / struck-off companies", "MCA21 master data and public notices", "https://www.mca.gov.in/"),
    ("RBI Alert List (unauthorised forex platforms)", "RBI", "https://www.rbi.org.in/"),
    ("IBBI insolvency / liquidation announcements", "IBBI public announcements", "https://ibbi.gov.in/"),
    ("Bank's own fraud (FMR) / RFA / negative list", "Export from the bank's internal systems", ""),
]

with T["fraud"]:
    st.markdown("#### 🕵 Fraud, defaulter & regulatory watch-list screening")
    st.caption("Screens the borrower, its directors / promoters / guarantors, the auditor and every company named in the documents against the lists "
               "your bank loads below. Matching runs on this PC (names are not sent out) - by identifier (CIN / DIN / PAN), fuzzy name, shared "
               "directors and group-name patterns. OpenSanctions (international sanctions / PEP) and adverse-media searches are optional online checks.")
    entries = DB.wl_entries()
    lists_ = DB.wl_lists()
    scr = ss.get("screening") or {}
    k = st.columns(5)
    kpi(k[0], "Lists loaded", len({l_["list_name"] for l_ in lists_}), f"{len(entries):,} entries")
    kpi(k[1], "Parties screened", (scr.get("summary") or {}).get("parties", "-"))
    kpi(k[2], "Potential matches", (scr.get("summary") or {}).get("hits", "-"), "", WARN if (scr.get("summary") or {}).get("hits") else None)
    kpi(k[3], "High severity", (scr.get("summary") or {}).get("high", "-"), "", CRIT if (scr.get("summary") or {}).get("high") else (GOOD if scr else None))
    kpi(k[4], "Last run", (scr.get("summary") or {}).get("when", "not run"))

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown("**1 · Parties to screen**")
        st.caption("Add directors, promoters, guarantors and group companies (with DIN / PAN / CIN where known - identifier matches are definitive).")
        pdf_ = pd.DataFrame(ss.parties or [], columns=["name", "role", "id"])
        if pdf_.empty:
            pdf_ = pd.DataFrame([{"name": "", "role": "Director / promoter", "id": ""}])
        ed = st.data_editor(pdf_, num_rows="dynamic", use_container_width=True, hide_index=True, key="wl_parties",
                            column_config={"name": st.column_config.TextColumn("Name", width="large"),
                                           "role": st.column_config.SelectboxColumn("Role", options=["Director / promoter", "Guarantor", "Group company",
                                                                                                      "Key managerial person", "Major customer / supplier", "Other"]),
                                           "id": st.column_config.TextColumn("DIN / PAN / CIN")})
        ss.parties = [r_ for r_ in ed.fillna("").to_dict("records") if str(r_.get("name", "")).strip()]
        auto = WL.parties_for({"company": ss.company, "cin": ss.cin, "notes": ss.notes}, ss.parties, ss.get("pages"))
        with st.expander(f"All {len(auto)} parties that will be screened (incl. those found in the documents)"):
            st.dataframe(pd.DataFrame([{"Name": p_["name"], "Role": p_["role"], "Identifier": p_.get("id", ""),
                                        "Pages": ", ".join(map(str, p_.get("pages") or []))} for p_ in auto]), hide_index=True, use_container_width=True)
        o1, o2, o3 = st.columns([1.2, 1.2, 1])
        use_os = o1.checkbox("OpenSanctions (sanctions / PEP)", value=bool(os_key), disabled=not os_key,
                             help="Needs an OpenSanctions API key in the sidebar. Sends party names to api.opensanctions.org.")
        use_web = o2.checkbox("Adverse-media search", value=True, help="Google News search for each key party with fraud / default / ED / CBI / SEBI / NCLT terms.")
        if o3.button("🔎 Run screening", type="primary", use_container_width=True, disabled=not ss.company):
            with st.spinner("Screening..."):
                hits, summ = WL.screen(auto, entries, WL.distinctive(ss.company))
                online = False
                if use_os and os_key:
                    try:
                        hits += WL.opensanctions(auto, os_key)
                        online = True
                    except Exception as e:
                        st.warning(f"OpenSanctions lookup failed: {e}")
                web = []
                if use_web:
                    key_parties = [p_ for p_ in auto if p_["role"] in ("Borrower",) or p_["role"].startswith(("Director", "Guarantor", "Group", "Related"))][:8]
                    for p_ in key_parties:
                        q_ = f'"{p_["name"]}" (fraud OR "wilful defaulter" OR CBI OR "Enforcement Directorate" OR SEBI OR NCLT OR insolvency OR raid)'
                        try:
                            for it in NW.google_news(q_, days=1825, limit=8):
                                it["party"] = p_["name"]
                                web.append(it)
                        except Exception:
                            pass
                order = {"High": 0, "Medium": 1, "Low": 2}
                hits.sort(key=lambda h: (order.get(h["severity"], 3), -h["score"]))
                summ.update({"hits": len(hits), "high": sum(1 for h in hits if h["severity"] == "High")})
                ss.screening = {"hits": hits, "summary": summ, "parties": [{k_: p_[k_] for k_ in ("name", "role")} for p_ in auto],
                                "online": online, "web": web}
                DB.log(USER["username"], "watchlist_screen", f"{ss.company}: {len(hits)} hits")
            st.rerun()
        if not entries:
            st.info("No lists loaded yet - " + ("load them on the right." if IS_ADMIN else "ask your administrator to load the bank's lists."))

        if scr:
            st.markdown("**2 · Results**")
            hits = scr.get("hits") or []
            if not hits:
                st.success(f"No matches for {scr['summary']['parties']} parties against {scr['summary']['entries']:,} list entries.")
            else:
                st.dataframe(pd.DataFrame([{"": SEV_ICON.get(h["severity"], ""), "Party": h["party"], "Role": h["role"], "Listed as": h["listed_name"],
                                            "List": h["list"], "Match": h["match"], "Score": h["score"], "Reason": h["reason"], "Listed on": h["list_date"]}
                                           for h in hits]), hide_index=True, use_container_width=True)
                st.caption("Each hit also appears as a red flag in 'Forensic & hidden items', where you can record your disposition "
                           "(e.g. 'Resolved - not the same entity' after checking the CIN / DIN).")
            web = scr.get("web") or []
            if web:
                st.markdown(f"**Adverse-media results ({len(web)})** - read and verify; a headline is not a finding")
                for it in web[:30]:
                    st.markdown(f"- **{it['party']}** · [{it['title']}]({it['url']}) · {it.get('source', '')} {it.get('date', '')}")
            elif "web" in scr:
                st.caption("Adverse-media search returned no articles.")

    with right:
        st.markdown("**Lists in the central database**")
        if lists_:
            st.dataframe(pd.DataFrame(lists_), hide_index=True, use_container_width=True)
        else:
            st.caption("No lists loaded.")
        with st.expander("Where to get the lists"):
            for a_, b2, u in WL_SOURCES:
                st.markdown(f"- **{a_}** - {b2}" + (f" ([link]({u}))" if u else ""))
            st.caption("Export each search / list to CSV or Excel and import it here. Refresh at least monthly; record the 'as on' date.")
        if IS_ADMIN:
            st.markdown("**Import a list** (admin)")
            up = st.file_uploader("CSV or Excel", type=["csv", "xlsx", "xls"], key="wl_up")
            lt = st.selectbox("List type", WL.LIST_TYPES, key="wl_type")
            src = st.text_input("Source / as-on date", placeholder="e.g. CIBIL suit-filed search, as on 30-Sep-2026", key="wl_src")
            if up is not None:
                try:
                    df_ = pd.read_csv(up) if up.name.lower().endswith(".csv") else pd.read_excel(up)
                    gm = WL.guess_columns(df_.columns)
                    cols_ = ["(none)"] + list(df_.columns)
                    c1, c2 = st.columns(2)
                    mp = {}
                    for i_, (fld, lab) in enumerate([("name", "Name column *"), ("identifier", "CIN / DIN / PAN column"), ("reason", "Reason column"),
                                                     ("list_date", "Date column"), ("directors", "Directors column"), ("amount", "Amount column")]):
                        v_ = (c1 if i_ % 2 == 0 else c2).selectbox(lab, cols_, index=cols_.index(gm[fld]) if gm.get(fld) in cols_ else 0, key=f"wl_m_{fld}")
                        mp[fld] = None if v_ == "(none)" else v_
                    st.caption(f"{len(df_):,} rows found. Preview:")
                    st.dataframe(df_.head(5), use_container_width=True, hide_index=True)
                    if st.button("Import", type="primary", disabled=not mp.get("name")):
                        n_ = DB.wl_add(WL.rows_from_df(df_, mp, lt, src or up.name), USER["username"])
                        DB.log(USER["username"], "watchlist_import", f"{lt}: {n_} rows from {up.name}")
                        st.success(f"Imported {n_:,} entries into '{lt}'.")
                        st.rerun()
                except Exception as e:
                    st.error(f"Could not read the file: {e}")
            st.download_button("⬇ Blank template (CSV)", WL.template_csv(), "watchlist_template.csv", use_container_width=True)
            sample_wl = os.path.join(HERE, "data", "watchlists", "SAMPLE_fictional_watchlist.csv")
            if os.path.exists(sample_wl) and st.button("Load the fictional sample list (for testing)", use_container_width=True):
                sdf = pd.read_csv(sample_wl).fillna("")
                rows_ = []
                for lt_, grp in sdf.groupby("list"):
                    rows_ += WL.rows_from_df(grp, {"name": "name", "identifier": "identifier", "reason": "reason", "list_date": "date",
                                                   "directors": "directors", "amount": "amount"}, lt_, "SAMPLE - fictional test list")
                DB.wl_add(rows_, USER["username"])
                st.rerun()
            if lists_:
                c1, c2 = st.columns([2, 1])
                dl = c1.selectbox("Remove a list", [f"{l_['list_name']} | {l_['source']}" for l_ in lists_], key="wl_del")
                if c2.button("Remove", use_container_width=True):
                    ln, sr = dl.split(" | ", 1)
                    DB.wl_delete(ln, sr)
                    DB.log(USER["username"], "watchlist_delete", dl)
                    st.rerun()
