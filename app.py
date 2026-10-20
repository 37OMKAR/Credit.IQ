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
from html import escape as E  # every document-, AI- or user-supplied string rendered as HTML goes through E()

from core import analyst as AN
from core import credit_tools as CT
from core import checker as CK
from core import dashboard as DSH
from core import report_types as RT
from core import brsr as BR
from core import db as DB
from core import webfetch as WF
from core import verify as VF
from core import dualread as DR
from core import watchlist as WL
from core import websearch as WS
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
C1, C2, C3, C4 = "#F26522", "#1C1917", "#2a78d6", "#B8A897"
GOOD, WARN, SERIOUS, CRIT = "#0ca30c", "#fab219", "#ec835a", "#d03b3b"
SEV_COLOR = {"High": CRIT, "Medium": WARN, "Low": GOOD}
SEV_ICON = {"High": "🔴", "Medium": "🟠", "Low": "🟢"}
DOC_TYPES = ["pdf", "png", "jpg", "jpeg", "tif", "tiff"]
SUPPORT_TYPES = DOC_TYPES + ["docx", "xlsx", "csv", "txt"]
COMMENT_TOPICS = ["General", "Financials", "Management / promoters", "Collateral & security", "Site visit / inspection",
                  "Conduct of account", "Market feedback", "Instruction to AI"]

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Plus+Jakarta+Sans:wght@500;600;700;800&display=swap');
html, body, [class*="css"], .stApp, button, input, textarea, select {font-family: 'Inter', system-ui, sans-serif;}
.stApp {background: #F7F3EE;}
.block-container {padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1560px;}
header[data-testid="stHeader"] {background: transparent; height: 2.2rem;}
[data-testid="stAppDeployButton"], [data-testid="stMainMenu"] {display: none;}
/* ---------- left menu (dark rail, like the reference dashboards) ---------- */
section[data-testid="stSidebar"] {background: #1C1917; border-right: 1px solid #292524; min-width: 270px !important; max-width: 270px !important;}
section[data-testid="stSidebar"] * {color: #E7E0D6;}
section[data-testid="stSidebar"] .block-container, section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {padding-top: .6rem;}
section[data-testid="stSidebar"] .stButton {margin-bottom: -12px;}
section[data-testid="stSidebar"] .stButton button {justify-content: flex-start; text-align: left; border: none; border-radius: 10px;
    padding: .42rem .8rem; min-height: 0; background: transparent; font-size: .88rem; letter-spacing: .01em; color: #CFC5B8; box-shadow: none;}
section[data-testid="stSidebar"] .stButton button p {text-align: left; width: 100%; font-weight: 500;}
section[data-testid="stSidebar"] .stButton button > div, section[data-testid="stSidebar"] .stButton button [data-testid="stMarkdownContainer"] {
    justify-content: flex-start !important; text-align: left !important; width: 100%;}
section[data-testid="stSidebar"] .stButton button:hover {background: #292524; color: #fff;}
section[data-testid="stSidebar"] .stButton button[kind="primary"], section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
    background: #F26522 !important; color: #1C1917 !important; box-shadow: none;}
section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] p {color: #1C1917 !important; font-weight: 700;}
.brand {font-weight: 800; font-size: 1.55rem; letter-spacing: .06em; color: #fff !important; margin: 6px 0 0 6px;}
.brand span {color: #F26522 !important;}
.brand-sub {font-size: .72rem; color: #A39889 !important; margin: 0 0 14px 7px; letter-spacing: .03em;}
.navgrp {font-size: .66rem; letter-spacing: .14em; color: #A39889 !important; margin: 16px 0 6px 10px; font-weight: 600;}
.navcase {font-size: .82rem; color: #e5e7eb !important; margin: 0 0 8px 10px; font-weight: 600;}
.navuser {display: flex; gap: 10px; align-items: center; margin: 22px 4px 6px; padding: 10px; border-radius: 12px; background: #292524;}
.navuser .av {width: 34px; height: 34px; border-radius: 50%; background: #F26522; color: #1C1917 !important; display: flex; align-items: center;
    justify-content: center; font-weight: 800;}
.navuser b {color: #fff !important; font-size: .86rem;} .navuser span {font-size: .72rem; color: #A39889 !important;}
.navai {font-size: .72rem; color: #A39889 !important; margin: 4px 0 4px 10px;}
/* ---------- page header ---------- */
.topbar {display: flex; justify-content: space-between; align-items: flex-end; margin: 0 0 16px; padding-bottom: 12px; border-bottom: 1px solid #E9E2D9;}
.topbar .ttl {font-size: 1.65rem; font-weight: 800; letter-spacing: .02em; color: #1C1917;}
.topbar .tsub {font-size: .86rem; color: #6B6259; margin-top: 2px;}
.hpill {display: inline-block; margin-left: 8px; padding: 6px 13px; border: 1px solid #E2D8CC; border-radius: 999px; background: #fff;
    font-size: .8rem; font-weight: 600; color: #1C1917;}
.crumb {font-size: .82rem; color: #6B6259; margin: -6px 0 10px;}
/* ---------- cards ---------- */
[class*="st-key-card_"], [data-testid="stForm"] {background: #fff; border-radius: 18px !important; border: 1px solid #ECE4DA !important;
    box-shadow: 0 1px 2px rgba(60,40,20,.05); padding: 16px 18px !important;}
.stPlotlyChart {background: #fff; border: 1px solid #ECE4DA; border-radius: 18px; padding: 6px 8px; box-shadow: 0 1px 2px rgba(60,40,20,.05);}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {background: #fff; border-radius: 12px; border: 1px solid #ECE4DA; padding: 2px;}
[data-testid="stExpander"] details {background: #fff; border-radius: 12px; border-color: #ECE4DA;}
[data-testid="stFileUploaderDropzone"] {background: #fff; border: 1.5px dashed #E0B79C; border-radius: 12px;}
.kpi, .kc, .mini, .cmt, .flag {background: #fff; border: 1px solid #ECE4DA; box-shadow: 0 1px 2px rgba(60,40,20,.05);}
.kpi {border-radius: 18px; padding: 13px 15px; height: 100%;}
.kpi .l {font-size: .72rem; letter-spacing: .06em; text-transform: uppercase; color: #6B6259; margin-bottom: 3px;}
.kpi .v {font-size: 1.45rem; font-weight: 700; line-height: 1.2; color: #1C1917;}
.kpi .s {font-size: .74rem; color: #6B6259;}
.kc {border-radius: 18px; padding: 13px 15px 4px; height: 100%;}
.kc .kl, .mini .kl {font-size: .7rem; letter-spacing: .07em; text-transform: uppercase; color: #6B6259; font-weight: 600;}
.kc .kv {font-size: 1.6rem; font-weight: 700; margin-top: 3px; color: #1C1917;}
.kc .kd {font-size: .74rem; font-weight: 600; min-height: 1.1em;}
.kc .spark {width: 100%; height: 34px; display: block; margin-top: 4px;}
.mini {border-radius: 12px; padding: 10px 13px; margin-bottom: 10px;}
.mini .mv {font-size: 1.35rem; font-weight: 700; color: #1C1917;} .mini .ms {font-size: .72rem; color: #6B6259;}
.flag {border-left: 4px solid; padding: 8px 12px; margin: 7px 0; border-radius: 10px;}
/* dashboard */
.dcrumb {font-size: .8rem; color: #6B6259; margin: -6px 0 10px;}
.dband {display: grid; grid-template-columns: 1.6fr 1.15fr .9fr 1fr .9fr; background: #fff; border: 1px solid #E6DDD2; border-radius: 12px; margin-bottom: 22px;}
.dcell {padding: 14px 16px; border-left: 1px solid #EFE8DF;} .dcell:first-child {border-left: 0;}
.dl {font-size: .68rem; letter-spacing: .07em; text-transform: uppercase; color: #6B6259; font-weight: 600;}
.dv {font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-size: 1.3rem; font-weight: 700; color: #1C1917; margin-top: 2px; line-height: 1.25;}
.dv.dsm {font-size: 1.02rem;}
.ds {font-size: .76rem; color: #6B6259; margin-top: 3px; line-height: 1.35;}
.dsec {font-family: 'Plus Jakarta Sans', 'Inter', sans-serif; font-weight: 700; font-size: 1rem; color: #1C1917; margin: 4px 0 8px;}
.dsec .cnt {font-family: 'Inter', sans-serif; font-weight: 500; font-size: .78rem; color: #6B6259; margin-left: 6px;}
.dtab {width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #E6DDD2; border-radius: 12px; overflow: hidden; font-size: .86rem;}
.dtab th {text-align: left; font-size: .7rem; letter-spacing: .05em; text-transform: uppercase; color: #6B6259; font-weight: 600;
          padding: 9px 12px; border-bottom: 1px solid #E6DDD2; background: #FBF8F4;}
.dtab td {padding: 7px 12px; border-bottom: 1px solid #F3EDE5; color: #1C1917; vertical-align: top;}
.dtab tr:last-child td {border-bottom: 0;}
.dtab .n {text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap;}
.dtab .neg {color: #B91C1C;} .dtab .mut {color: #6B6259;} .dtab .u {font-size: .7rem; color: #8A817A;}
.dtab .na {color: #8A817A;} .dtab .why {font-size: .72rem; color: #8A817A; white-space: normal; max-width: 220px; margin-left: auto;}
.dtab td .why {text-align: left;} .dtab .n .why {text-align: right;}
.dtab tr.g td {font-size: .68rem; letter-spacing: .07em; text-transform: uppercase; color: #8A817A; font-weight: 600; background: #FBF8F4; padding: 5px 12px;}
.dtab.dq td:first-child {white-space: nowrap; width: 42%;}
.dtab .ev {font-size: .74rem; color: #6B6259; margin-top: 2px; line-height: 1.4;}
.dnote {font-size: .74rem; color: #8A817A; margin: 6px 2px 18px;}
.doi {background: #fff; border: 1px solid #E6DDD2; border-radius: 10px; padding: 8px 12px;}
.doi .t {font-weight: 600; font-size: .86rem; color: #1C1917;} .doi .d {font-size: .76rem; color: #6B6259; margin-top: 2px;}
.doi .lv {font-size: .68rem; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; margin-left: 4px;}
.dempty {background: #fff; border: 1px dashed #D9CFC3; border-radius: 12px; padding: 16px; min-height: 180px; margin-top: 8px;}
.dempty b {display: block; font-size: 1.05rem; margin: 6px 0 4px; color: #1C1917;}
@media (max-width: 900px) {.dband {grid-template-columns: 1fr 1fr;} .dcell {border-left: 0; border-top: 1px solid #EFE8DF;}}
.cmt {border-radius: 10px; padding: 9px 13px; margin: 6px 0;} .cmt .m {font-size: .74rem; color: #6B6259;}
.insight {display: flex; gap: 14px; align-items: flex-start; background: #FFF1E8; border: 1px solid #FBD5BC; border-radius: 18px;
    padding: 13px 18px; margin: 16px 0 8px; font-size: .9rem; color: #1C1917;}
.insight .ava {font-size: 1.4rem; background: #fff; border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center;
    justify-content: center; flex-shrink: 0; box-shadow: 0 1px 2px rgba(0,0,0,.08);}
.insight .im {font-size: .74rem; color: #6B6259; margin-bottom: 2px;} .insight .ia {color: #3F3A36; margin-top: 3px;}
.step {font-size: .72rem; font-weight: 700; letter-spacing: .1em; color: #6B6259; text-transform: uppercase; margin: 8px 0 4px;}
.sub {color: #6B6259; margin-top: 0;}
/* ---------- form fields: visible on white cards and on the grey page ---------- */
[data-testid="stMain"] [data-baseweb="input"], [data-testid="stMain"] [data-baseweb="select"] > div,
[data-testid="stMain"] [data-baseweb="textarea"] {background: #FFFCF8 !important; border: 1px solid #E5DCD1 !important; border-radius: 9px !important;}
[data-testid="stMain"] [data-baseweb="input"] input, [data-testid="stMain"] [data-baseweb="base-input"], [data-testid="stMain"] textarea {background: transparent !important;}
[data-testid="stMain"] [data-testid="stNumberInputContainer"] {background: #FFFCF8; border-radius: 9px;}
[data-testid="stMain"] [data-testid="stTextInputRootElement"], [data-testid="stMain"] [data-testid="stTextAreaRootElement"] {background: #FFFCF8 !important;
    border: 1px solid #E5DCD1 !important; border-radius: 9px !important;}
[data-testid="stMain"] [data-baseweb="input"]:focus-within, [data-testid="stMain"] [data-baseweb="select"] > div:focus-within {border-color: #F26522 !important;
    box-shadow: 0 0 0 3px rgba(242,101,34,.18);}
.jobhead {font-size: .95rem; margin: 6px 0 4px;}
.jsteps {background: #fff; border: 1px solid #ECE4DA; border-radius: 18px; padding: 8px 14px; margin: 8px 0;}
.jstep {display: flex; gap: 12px; padding: 7px 0; border-bottom: 1px solid #F3EDE5; align-items: flex-start;}
.jstep:last-child {border-bottom: none;} .jstep span {font-size: 1.05rem; width: 22px;}
.jstep.pending {opacity: .5;} .jstep.running b {color: #1C1917;} .jstep .jd {font-size: .78rem; color: #6B6259;}
/* ---------- tabs inside pages: underline style ---------- */
.stTabs [data-baseweb="tab-list"] {gap: 22px; border-bottom: 1px solid #E9E2D9;}
.stTabs [data-baseweb="tab"] {font-size: .78rem; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: #6B6259; padding: 8px 0;}
.stTabs [aria-selected="true"] {color: #1C1917;}
.stTabs [data-baseweb="tab-highlight"] {background: #F26522; height: 3px;}
/* ---------- buttons ---------- */
.main .stButton button[kind="primary"], [data-testid="stMain"] [data-testid="stBaseButton-primary"] {background: #F26522; border-color: #F26522; color: #1C1917;}
[data-testid="stMain"] [data-testid="stBaseButton-primary"] p {color: #1C1917; font-weight: 700;}
[data-testid="stMain"] [data-testid="stBaseButton-primary"]:hover {background: #E0561B; border-color: #E0561B;}
[data-testid="stMain"] [data-testid="stBaseButton-secondary"] {background: #fff; border-color: #E2D8CC;}
h1, h2, h3, h4, h5, .topbar .ttl, .brand, .kpi .v, .kc .kv, .mini .mv {font-family: 'Plus Jakarta Sans', 'Inter', sans-serif !important;}
h1, h2, h3, h4, h5 {color: #1C1917; letter-spacing: -.02em;}
.topbar .ttl {font-weight: 800; letter-spacing: -.02em !important;}
.brand {letter-spacing: .01em !important;}
.brand.brand-login {color: #1C1917 !important;}
[data-testid="stAlertContainer"]:has([data-testid="stAlertContentInfo"]) {background: #FFF1E8 !important; border: 1px solid #FBD5BC;}
[data-testid="stAlertContentInfo"], [data-testid="stAlertContentInfo"] p {color: #7C2D12 !important;}
[data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"] {background: #F26522; border-color: #F26522;}
[data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"] p {color: #1C1917; font-weight: 700;}
[data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"]:hover {background: #E0561B; border-color: #E0561B;}
.navuser .av {color: #1C1917 !important;}
[data-testid="stProgress"] [role="progressbar"] > div > div {background: #F26522 !important;}
.insight {border-left: 4px solid #F26522;}
</style>""", unsafe_allow_html=True)

import sys
import threading as _thr


class _RawState:
    """Session state used by the background analysis thread: talks to the session's state directly, without
    Streamlit's rerun 'yield point' (which would stop the job whenever the officer clicks another page)."""

    def __init__(self, safe):
        object.__setattr__(self, "_safe", safe)

    def __getitem__(self, k):
        with self._safe._lock:
            return self._safe._state[k]

    def __setitem__(self, k, v):
        with self._safe._lock:
            self._safe._state[k] = v

    def __delitem__(self, k):
        with self._safe._lock:
            del self._safe._state[k]

    def __contains__(self, k):
        with self._safe._lock:
            return k in self._safe._state

    def get(self, k, default=None):
        try:
            return self[k]
        except KeyError:
            return default

    def setdefault(self, k, v):
        if k not in self:
            self[k] = v
        return self[k]

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


class _SSProxy:
    """`ss` = st.session_state in the page; the raw session state inside the background job thread."""

    def _t(self):
        return getattr(_thr.current_thread(), "ci_state", None) or st.session_state

    def __getattr__(self, k):
        return getattr(self._t(), k)

    def __setattr__(self, k, v):
        setattr(self._t(), k, v)

    def __getitem__(self, k):
        return self._t()[k]

    def __setitem__(self, k, v):
        self._t()[k] = v

    def __delitem__(self, k):
        del self._t()[k]

    def __contains__(self, k):
        return k in self._t()

    def get(self, k, default=None):
        return self._t().get(k, default)

    def setdefault(self, k, v):
        return self._t().setdefault(k, v)

    def keys(self):
        return st.session_state.keys()


ss = _SSProxy()
CASE_KEYS = ["ext", "notes", "brsr", "news", "brief", "narr", "pcaf_in", "company", "statement_type", "method",
             "source_file", "cin", "comments", "flag_remarks", "support", "case", "aliases", "web_pcaf", "case_uid", "parties", "screening", "attest", "doc_people", "dual", "statement_type_used"]
for k, v in {"pages": {}, "located": {}, "ext": None, "notes": None, "brsr": None, "news": [], "brief": None, "narr": None,
             "pcaf_in": None, "company": "", "statement_type": "standalone", "method": "", "source_file": "", "cin": None,
             "xcheck": None, "web_pcaf": None, "case_uid": None, "comments": [], "flag_remarks": {}, "support": {}, "case": {}, "aliases": "", "_out": None,
             "parties": [], "screening": None, "attest": {}, "dual": None}.items():
    ss.setdefault(k, v)


# ------------------------------------------------------------------ accounts / login
DB.init()
FX = float(os.getenv("USD_INR", "88"))
DEMO = os.getenv("CREDITINTEL_DEMO", "").strip() in ("1", "true", "yes")
if not ss.get("user"):
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("<div style='height:8vh'></div><div class='brand brand-login' style='font-size:2.1rem;margin:0'>CREDIT<span>·IQ</span></div>"
                    "<div class='tsub' style='color:#6B6259;margin:2px 0 18px'>Credit Intelligence Workbench - sign in to continue</div>",
                    unsafe_allow_html=True)
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
                    lock_ = DB.login_locked(u)
                    if user:
                        ss.user = user
                        st.rerun()
                    elif lock_:
                        st.error(f"Too many failed sign-ins for this username. Try again in {lock_} minute(s), or ask the administrator "
                                 "to reset the password.")
                    else:
                        st.error("Wrong username or password, or the account is disabled.")
    st.stop()
USER = ss.user
IS_ADMIN = USER["role"] == "admin"
if not ss.get("case_uid"):
    ss.case_uid = f"{USER['username']}-{dt.datetime.now():%Y%m%d%H%M%S%f}"


# ------------------------------------------------------------------ settings (kept in session; edited on the ⚙ Settings page)
SET_DEFAULTS = {
    "k_ds": os.getenv("DEEPSEEK_API_KEY", ""), "k_or": os.getenv("OPENROUTER_API_KEY", ""), "k_lc": os.getenv("LONGCAT_API_KEY", ""),
    "m_ds": os.getenv("DEEPSEEK_MODEL", PROVIDERS["DeepSeek"]["model"]), "m_or": os.getenv("OPENROUTER_MODEL", PROVIDERS["OpenRouter"]["model"]),
    "m_lc": (os.getenv("LONGCAT_MODEL") or "").strip() if (os.getenv("LONGCAT_MODEL") or "").strip() not in ("", "LongCat-2.0", "LongCat-Flash-Chat")
            else PROVIDERS["LongCat"]["model"],  # old defaults move to the newer model automatically
    "oth": "-", "k_ot": "", "m_ot": "", "b_ot": "",
    "mode": "Cheapest", "ocr_mode": "auto", "max_pages": 450, "newsapi_key": os.getenv("NEWSAPI_KEY", ""),
    "gnews_key": os.getenv("GNEWS_KEY", ""), "os_key": os.getenv("OPENSANCTIONS_API_KEY", ""),
    "officer": USER.get("name") or USER["username"], "branch": USER.get("branch") or os.getenv("BRANCH_NAME", ""),
    "bank_name": os.getenv("BANK_NAME", ""),
    "dual": os.getenv("DUAL_READ", "1").strip().lower() not in ("0", "false", "no", "off"),
    "cloud_ocr": os.getenv("CLOUD_OCR", "1").strip().lower() not in ("0", "false", "no", "off"),
    "m_vis": os.getenv("VISION_MODEL", DR.DEFAULT_VISION_MODEL),
}
for _k, _v in SET_DEFAULTS.items():  # re-assigning keeps widget values alive while their page is not shown
    ss[f"set_{_k}"] = ss.get(f"set_{_k}", _v)
for _k in [k_ for k_ in list(ss.keys()) if str(k_).startswith("route_")] + ["statement_type"]:
    ss[_k] = ss[_k]
S = lambda k_: ss[f"set_{k_}"]
k_ds, k_or, k_lc, m_ds, m_or, m_lc = S("k_ds"), S("k_or"), S("k_lc"), S("m_ds"), S("m_or"), S("m_lc")
oth, k_ot, m_ot, b_ot = S("oth"), S("k_ot"), S("m_ot"), S("b_ot")
mode, ocr_mode, max_pages = S("mode"), S("ocr_mode"), S("max_pages")
newsapi_key, gnews_key, os_key, officer, branch = S("newsapi_key"), S("gnews_key"), S("os_key"), S("officer"), S("branch")
if S("bank_name"):
    os.environ["BANK_NAME"] = S("bank_name")
if oth != "-" and not m_ot:
    m_ot, b_ot = PROVIDERS[oth]["model"], PROVIDERS[oth]["base_url"]
llms = {
    "DeepSeek": LLM("DeepSeek", api_key=k_ds or None, model=m_ds) if k_ds else None,
    "OpenRouter": LLM("OpenRouter", api_key=k_or or None, model=m_or) if k_or else None,
    "LongCat": LLM("LongCat", api_key=k_lc or None, model=m_lc) if k_lc else None,
}
if oth != "-" and (k_ot or "Ollama" in oth):
    llms[oth] = LLM(oth, api_key=k_ot or None, model=m_ot or None, base_url=b_ot or None)
ready_names = [n for n, l in llms.items() if l is not None and l.ready]


def _pick(order):
    return next((n for n in order if n in ready_names), ready_names[0] if ready_names else None)


cheap_order = ["DeepSeek", "OpenRouter", "LongCat"] + ready_names
heavy_order = ["LongCat", "DeepSeek", "OpenRouter"] + ready_names
defaults = {t: (_pick(heavy_order) if (mode == "Best quality" or t == "narrative") else _pick(cheap_order)) for t in TASKS}
assignment = {t: (ss.get(f"route_{t}") if ss.get(f"route_{t}") in ready_names else defaults[t]) for t in TASKS}
for _l in llms.values():
    if _l is not None:
        _l.case_id = ss.case_uid
router = Router(llms, assignment, mode.lower())

# ------------------------------------------------------------------ navigation (left menu)
NAV = [
    (None, [("desk", "🏠  Officer desk"), ("dash", "📊  Dashboard")]),
    ("ANALYSIS", [("spread", "🧾  Spread review"), ("ratios", "📐  Ratios"), ("proposal", "🏦  Proposal & what-if")]),
    ("RISK", [("forensic", "🔍  Forensic & hidden items"), ("ews", "🚨  Early warning"), ("fraud", "🕵  Fraud screening"),
              ("market", "🌐  Market intelligence"), ("brsr", "🌱  BRSR & PCAF")]),
    ("OUTPUT", [("reports", "📑  Report centre"), ("ask", "💬  Ask the documents")]),
    ("MANAGE", [("portfolio", "📈  Portfolio"), ("history", "🗂  History & cases"), ("settings", "⚙  Settings & AI keys")]
     + ([("admin", "🛡  Admin")] if IS_ADMIN else [])),
]
PAGE_TITLES = {k_: l_.split("  ", 1)[1] for _, items in NAV for k_, l_ in items}
ss.setdefault("page", "desk")
if ss.page not in PAGE_TITLES:
    ss.page = "desk"


def _go(k_):
    ss.page = k_


with st.sidebar:
    st.markdown("<div class='brand'>CREDIT<span>·IQ</span></div><div class='brand-sub'>Credit Intelligence Workbench</div>", unsafe_allow_html=True)
    for grp, items in NAV:
        if grp:
            st.markdown(f"<div class='navgrp'>{grp}</div>", unsafe_allow_html=True)
        for k_, l_ in items:
            st.button(l_, key=f"nav_{k_}", use_container_width=True, on_click=_go, args=(k_,),
                      type="primary" if ss.page == k_ else "tertiary")
    st.markdown("<div class='navgrp'>CASE</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='navcase'>{E(ss.company or 'No case open')}</div>", unsafe_allow_html=True)
    if st.button("＋  New case", use_container_width=True, key="nav_new"):
        keep = {k_: ss[k_] for k_ in list(ss.keys()) if k_ == "user" or str(k_).startswith(("set_", "route_"))}
        for k_ in list(ss.keys()):
            del ss[k_]
        for k_, v_ in keep.items():
            ss[k_] = v_
        st.rerun()
    st.markdown(f"<div class='navuser'><div class='av'>{E((USER.get('name') or USER['username'])[:1].upper())}</div><div><b>{E(USER.get('name') or USER['username'])}</b>"
                f"<br><span>{E(USER['role'])}{' · ' + E(USER['branch']) if USER.get('branch') else ''}</span></div></div>", unsafe_allow_html=True)
    st.markdown(f"<div class='navai'>{'🟢 AI: ' + ', '.join(ready_names) if ready_names else '⚪ Rule-based mode (no AI key)'}</div>", unsafe_allow_html=True)
    if st.button("Sign out", use_container_width=True, key="nav_out", type="tertiary"):
        DB.log(USER["username"], "logout")
        for k in list(ss.keys()):
            del ss[k]
        st.rerun()
PAGE = ss.page


def render_settings():
    sa, sb = st.columns([3, 1])
    sa.caption("Changes apply immediately for this session. Click **Save** to keep them after a restart (written to the .env file on this PC).")
    if sb.button("💾 Save settings", type="primary", use_container_width=True):
        try:
            st.success(f"Saved to {save_env()}")
            DB.log(USER["username"], "settings_saved")
        except Exception as e:
            st.error(f"Could not save: {e}")
    a, b = st.columns(2, gap="large")
    with a:
        with card():
            st.markdown("**AI keys**")
            st.text_input("DeepSeek API key", type="password", key="set_k_ds")
            st.text_input("OpenRouter API key", type="password", key="set_k_or")
            st.text_input("LongCat API key", type="password", key="set_k_lc")
            c1, c2, c3 = st.columns(3)
            c1.text_input("DeepSeek model", key="set_m_ds")
            c2.text_input("OpenRouter model", key="set_m_or", help="Any OpenRouter model id, e.g. deepseek/deepseek-chat, google/gemini-2.5-flash")
            c3.text_input("LongCat model", key="set_m_lc", help="Model id exactly as shown on your LongCat API platform page.")
            if st.button("Show the models my keys can use"):
                from core.llm import list_models
                for prov_, key_ in (("DeepSeek", S("k_ds")), ("OpenRouter", S("k_or")), ("LongCat", S("k_lc"))):
                    if not key_:
                        continue
                    try:
                        ids_ = list_models(prov_, key_)
                        if prov_ == "OpenRouter":
                            ids_ = [i_ for i_ in ids_ if i_.startswith(("deepseek/", "google/gemini", "openai/gpt-4o-mini", "qwen/", "meituan/"))]
                        st.markdown(f"**{prov_}** ({len(ids_)}): " + ", ".join(f"`{i_}`" for i_ in ids_[:60]))
                    except Exception as e_:
                        st.warning(f"{prov_}: could not list models - {e_}")
                st.caption("Copy the exact id into the model box above, then click Save.")
            st.selectbox("Other provider (optional)", ["-"] + [p_ for p_ in PROVIDERS if p_ not in ("DeepSeek", "OpenRouter", "LongCat")], key="set_oth")
            if S("oth") != "-":
                c1, c2, c3 = st.columns(3)
                c1.text_input(f"{S('oth')} API key", type="password", key="set_k_ot")
                c2.text_input("Model", key="set_m_ot", placeholder=PROVIDERS[S('oth')]["model"])
                c3.text_input("Base URL", key="set_b_ot", placeholder=PROVIDERS[S('oth')]["base_url"])
            if S("k_or") and st.button("OpenRouter account - usage & balance"):
                from core.llm import openrouter_account
                acc = openrouter_account(S("k_or"))
                kd, cd = acc.get("key") or {}, acc.get("credits") or {}
                if kd or cd:
                    st.success("OpenRouter: " + " · ".join(x for x in [
                        f"key usage ${kd['usage']:,.4f}" if isinstance(kd.get("usage"), (int, float)) else "",
                        f"limit ${kd['limit']:,.2f}" if isinstance(kd.get("limit"), (int, float)) else ("no limit set" if "limit" in kd else ""),
                        f"remaining ${kd['limit_remaining']:,.4f}" if isinstance(kd.get("limit_remaining"), (int, float)) else "",
                        f"credits ${cd['total_credits']:,.2f}, used ${cd['total_usage']:,.4f}" if isinstance(cd.get("total_credits"), (int, float)) else ""] if x))
                for k_, v_ in acc.items():
                    if k_.endswith("_error"):
                        st.caption(f"{k_[:-6]}: {v_}")
            if ready_names and st.button("Test all keys"):
                for n_ in ready_names:
                    try:
                        st.success(f"{n_}: {llms[n_].test()[:12]}")
                    except Exception as e:
                        st.error(f"{n_}: {str(e)[:200]}")
        with card():
            st.markdown("**Cost mode & routing**")
            st.radio("Cost mode", ["Cheapest", "Balanced", "Best quality"], horizontal=True, key="set_mode",
                     help="Cheapest: rule-based reader first, AI only where needed, cheap model for reading, heavy model only for the final report.")
            if ready_names:
                for t_, lbl in TASKS.items():
                    if ss.get(f"route_{t_}") not in ready_names:
                        ss[f"route_{t_}"] = assignment[t_]
                    st.selectbox(lbl, ready_names, key=f"route_{t_}")
            else:
                st.caption("Add a key to choose which AI does which job. Without a key everything runs rule-based.")
    with b:
        with card():
            st.markdown("**Extraction**")
            st.radio("Statements to analyse", ["standalone", "consolidated"], horizontal=True, key="statement_type")
            c1, c2 = st.columns(2)
            c1.selectbox("OCR for scanned pages", ["auto", "force", "off"], key="set_ocr_mode", help="auto = OCR only pages without a text layer")
            c2.number_input("Max pages to read per PDF", 20, 1000, step=10, key="set_max_pages")
            st.checkbox("Second reading from page images (Gemini / Mistral via OpenRouter)", key="set_dual",
                        help="Sends images of the 4-14 statement pages (never the whole report) to a vision model for an independent second "
                             "reading; lines that differ go to Mistral OCR as tie-breaker. About Rs 1-2 per borrower. Needs the OpenRouter key. "
                             "Switch off if page images must not leave the bank.")
            st.checkbox("Document OCR (Mistral OCR) for scanned statement pages", key="set_cloud_ocr",
                        help="Scanned balance sheet / P&L / cash-flow pages are also read by Mistral OCR, which keeps table columns; the "
                             "reading whose totals add up best is used. About Rs 0.5-1 per borrower. Needs the OpenRouter key. "
                             "Switch off if page images must not leave the bank.")
            st.text_input("Vision model for the second reading", key="set_m_vis", help="OpenRouter model id; default google/gemini-2.5-flash")
        with card():
            st.markdown("**News & screening keys (optional)**")
            st.text_input("NewsAPI.org key", type="password", key="set_newsapi_key")
            st.text_input("GNews.io key", type="password", key="set_gnews_key")
            st.text_input("OpenSanctions API key (sanctions / PEP)", type="password", key="set_os_key")
            st.caption("Google News works without a key.")
        with card():
            st.markdown("**Report signature**")
            c1, c2, c3 = st.columns(3)
            c1.text_input("Your name", key="set_officer")
            c2.text_input("Branch / unit", key="set_branch")
            c3.text_input("Bank name (letters, term sheets)", key="set_bank_name")


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
        dcol = "#15803D" if good else "#B91C1C"
        arrow = "▲" if delta >= 0 else "▼"
        if unit == "%":
            dtxt = f"{arrow} {abs(delta):.1%} YoY"
        elif unit == "pp":
            dtxt = f"{arrow} {abs(delta) * 100:.1f} pp YoY"
        elif unit == "d":
            dtxt = f"{arrow} {abs(delta):.0f} days YoY"
        else:
            dtxt = f"{arrow} {abs(delta):.2f}x YoY"
    col.markdown(f"<div class='kc'><div class='kl'>{E(str(label))}</div><div class='kv'>{E(str(value))}</div>"
                 f"<div class='kd' style='color:{dcol}'>{E(str(dtxt))}</div>{_spark(series or [], dcol if delta is not None else '#F26522')}</div>",
                 unsafe_allow_html=True)


def mini(col, label, value, sub="", color=None):
    col.markdown(f"<div class='mini' style='border-left:4px solid {color or '#F26522'}'><div class='kl'>{E(str(label))}</div>"
                 f"<div class='mv'>{E(str(value))}</div><div class='ms'>{E(str(sub))}</div></div>", unsafe_allow_html=True)


_CARD = [0]


def card():
    """Bordered white card (the key gives a CSS hook)."""
    _CARD[0] += 1
    return st.container(border=True, key=f"card_{_CARD[0]}")


def kpi(col, label, value, sub="", color=None):
    style = f"border-left: 5px solid {color};" if color else ""
    col.markdown(f'<div class="kpi" style="{style}"><div class="l">{E(str(label))}</div><div class="v">{E(str(value))}</div><div class="s">{E(str(sub))}</div></div>',
                 unsafe_allow_html=True)


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
    data, derived, prov = {}, {}, {}
    da_, db_ = base.get("derived") or {}, new.get("derived") or {}
    pa_, pb_ = base.get("provenance") or {}, new.get("provenance") or {}
    for y in years:
        a, b = base["data"].get(y), new["data"].get(y)
        if a is None:
            data[y], derived[y], prov[y] = b, dict(db_.get(y) or {}), dict(pb_.get(y) or {})
        elif b is None:
            data[y], derived[y], prov[y] = a, dict(da_.get(y) or {}), dict(pa_.get(y) or {})
        else:
            data[y], derived[y], prov[y] = {}, {}, {}
            for k in schema.KEYS:
                a_der, b_der = k in (da_.get(y) or {}), k in (db_.get(y) or {})
                # a figure printed in one document beats one derived from components in the other
                use_b = a.get(k) is None or (a_der and b.get(k) is not None and not b_der)
                data[y][k] = b.get(k) if use_b else a.get(k)
                if (use_b and b_der and b.get(k) is not None) or (not use_b and a_der):
                    derived[y][k] = (db_ if use_b else da_)[y][k]
                src_p = ((pb_ if use_b else pa_).get(y) or {}).get(k)
                if src_p:
                    prov[y][k] = src_p
    out = dict(base)
    if (new.get("currency") or {}).get("code"):
        out["currency"] = new["currency"]  # any document in a non-INR currency marks the case
    if out.get("unit_status") == "NOT STATED" and new.get("unit_status") not in (None, "NOT STATED"):
        out["unit_status"] = new["unit_status"]
    out.update(years=years[:4], data={y: data[y] for y in years[:4]}, derived={y: derived.get(y) or {} for y in years[:4]},
               provenance={y: prov.get(y) or {} for y in years[:4]},
               extraction_notes=list(base.get("extraction_notes") or []) + list(new.get("extraction_notes") or []))
    return out


def chart_layout(fig, title, h=320, yfmt=None):
    """One consistent chart style: clean white card, readable title, legend top-left, value labels on small bar charts."""
    fig.update_layout(template="plotly_white", font=dict(color="#3F3A36", family="Inter, sans-serif", size=12),
                      title=dict(text=f"<b>{title}</b>", x=0.01, y=0.97, yanchor="top", font=dict(size=14, color="#1C1917")),
                      height=h, margin=dict(l=8, r=12, t=74, b=8), paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
                      hovermode="x unified", hoverlabel=dict(bgcolor="#1C1917", font=dict(color="#fff", size=12), bordercolor="#1C1917"),
                      legend=dict(orientation="h", y=1.02, x=0, xanchor="left", yanchor="bottom", font=dict(size=11), bgcolor="rgba(0,0,0,0)"),
                      bargap=0.32, bargroupgap=0.1, barcornerradius=5, uniformtext=dict(minsize=9, mode="hide"))
    fig.update_xaxes(showgrid=False, type="category", linecolor="#E2D8CC", tickfont=dict(color="#6B6259"))
    fig.update_yaxes(gridcolor="#F3EDE5", zerolinecolor="#c9ced6", tickformat=yfmt, tickfont=dict(color="#6B6259"), rangemode="tozero")
    stacked = fig.layout.barmode == "stack"
    for tr in fig.data:
        if tr.type == "bar" and tr.orientation != "h" and not stacked and tr.text is None and tr.y is not None and len(tr.y) <= 8:
            tr.update(texttemplate="%{y:,.0f}" if not yfmt else "%{y:" + yfmt + "}", textposition="outside", cliponaxis=False,
                      textfont=dict(size=10, color="#57504A"))
        if tr.type == "scatter" and (tr.mode or "").find("markers") >= 0:
            tr.update(marker=dict(size=8, line=dict(width=2, color="#fff")))
    return fig


def case_stem():
    return re.sub(r"[^A-Za-z0-9]+", "_", ss.company or "case").strip("_")[:40]


def save_case(stem=None):
    payload = {k: ss.get(k) for k in CASE_KEYS}
    return DB.save_local(USER["username"], payload, stem or f"{dt.date.today():%Y%m%d}_{case_stem()}")


# ------------------------------------------------------------------ background analysis job (survives page changes)
import threading
import traceback
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

STEPS = [("read", "Reading the financial statements (OCR if scanned)"), ("read2", "Second, independent reading from the page images"),
         ("notes", "Auditor's report, CARO & notes"),
         ("brsr", "BRSR filing (uploaded)"), ("support", "Supporting documents"), ("news", "Market intelligence (news + web search)"),
         ("brsr_web", "BRSR / emissions / market cap - web check"), ("screen", "Fraud, defaulter & regulatory screening"),
         ("score", "Ratios, forensic tests & credit score"), ("report", "Credit memorandum (Word) & workbook (Excel)")]


@st.cache_resource
def _job_registry():
    return {}


def current_job():
    return getattr(threading.current_thread(), "ci_job", None)


class _Bar:
    def __init__(self, job, text):
        self.job = job
        if job:
            job["sub"] = (0.0, text)

    def progress(self, v, text=""):
        if self.job:
            self.job["sub"] = (float(v), text)

    def empty(self):
        pass


class UI:
    """Processing code reports through UI.* so it works both in the page and in the background job."""
    @staticmethod
    def _log(level, msg):
        j = current_job()
        if j is not None:
            j["log"].append((dt.datetime.now().strftime("%H:%M:%S"), level, str(msg)))
            if level in ("warning", "error"):
                j["warnings"].append(str(msg))
            return True
        # never draw on the page from the background thread (Streamlit would stop the thread)
        return getattr(threading.current_thread(), "ci_state", None) is not None

    @staticmethod
    def write(msg):
        if not UI._log("info", msg):
            st.write(msg)

    @staticmethod
    def info(msg):
        if not UI._log("info", msg):
            st.info(msg)

    @staticmethod
    def warning(msg):
        if not UI._log("warning", msg):
            st.warning(msg)

    @staticmethod
    def progress(v, text=""):
        j = current_job()
        return _Bar(j, text) if j is not None else st.progress(v, text=text)


def _step(job, key, state, detail=""):
    for s_ in job["steps"]:
        if s_["key"] == key:
            s_["state"], s_["detail"] = state, detail or s_.get("detail", "")
            if state == "running":
                s_["t0"] = dt.datetime.now()
                job["sub"] = (0.0, "")
            if state in ("done", "skipped", "failed") and s_.get("t0"):
                s_["secs"] = (dt.datetime.now() - s_["t0"]).total_seconds()
    n_done = sum(1 for s_ in job["steps"] if s_["state"] in ("done", "skipped", "failed"))
    job["pct"] = n_done / len(job["steps"])


def run_second_reading(job, log):
    """Reader 2 (page images) + tie-breaker; writes back only values two readers agree on."""
    ss.dual = None
    if not (S("dual") and k_or):
        _step(job, "read2", "skipped", "switched off in Settings" if not S("dual") else "needs the OpenRouter key (⚙ Settings)")
        return
    name = next((n_ for n_, l_ in (ss.located or {}).items() if (l_ or {}).get("balance_sheet")), None)
    if not (ss.ext and name and name in (ss.pdf_bytes or {})):
        _step(job, "read2", "skipped", "statement pages not located")
        return
    _step(job, "read2", "running")
    try:
        res = DR.run(k_or, ss.pdf_bytes[name], ss.located[name], ss.ext, PR.detect_unit, statement_pref=ss.get("statement_type_used") or ss.statement_type,
                     model=S("m_vis") or DR.DEFAULT_VISION_MODEL, case_id=ss.case_uid, log=log)
        res["document"] = name
        n0_ = len((ss.ext or {}).get("changes") or [])
        res["corrections"] = [] if res["summary"].get("unit_mismatch") else DR.apply_corrections(ss.ext, res)
        new_ = (ss.ext.get("changes") or [])[n0_:]
        if new_:
            try:
                DB.add_figure_changes(ss.case_uid, ss.company, "system", new_, "second reading + tie-breaker agree", source="Second reading")
            except Exception:  # noqa: BLE001 - the trail is also kept with the case
                pass
        ss.dual = res
        log(res["summary"]["text"] + (" · corrected: " + "; ".join(res["corrections"]) if res["corrections"] else ""))
        _step(job, "read2", "done", res["summary"]["text"][:160])
    except Exception as e:
        UI.warning(f"Second reading failed: {e} - figures rest on one reading only")
        _step(job, "read2", "failed", str(e)[:120])


def _run_job(job, prm):
    th = threading.current_thread()
    th.ci_job = job
    log = UI.write
    try:
        srcs, brsr_src, sup = prm["srcs"], prm["brsr_src"], prm["sup"]
        if srcs:
            _step(job, "read", "running")
            process_reports(srcs, log)
            _step(job, "read", "done", f"{len(ss.ext['years']) if ss.ext else 0} year(s) spread · {ss.method}")
            run_second_reading(job, log)
            _np = len(EX.people_to_parties(ss.get("doc_people") or {}))
            _step(job, "notes", "done", f"auditor: {(ss.notes or {}).get('auditor_name') or 'n.a.'} · {(ss.notes or {}).get('method', 'AI')}"
                  + (f" · {_np} directors / promoters / group entities identified" if _np else ""))
        else:
            _step(job, "read", "skipped", "using the spread already in this case")
            _step(job, "read2", "skipped", "spread not re-read")
            _step(job, "notes", "skipped")
        job["company"] = ss.company
        if brsr_src:
            _step(job, "brsr", "running")
            process_brsr(*brsr_src, log)
            _step(job, "brsr", "done")
        else:
            _step(job, "brsr", "skipped", "no BRSR uploaded - web check below")
        if sup:
            _step(job, "support", "running")
            process_support(sup, log)
            _step(job, "support", "done", f"{len(sup)} file(s)")
        else:
            _step(job, "support", "skipped", "none uploaded")
        pcaf_from_case()
        # --- start the slow web / AI look-ups now, all at once; the steps below just collect the results
        from concurrent.futures import ThreadPoolExecutor
        pool_ = ThreadPoolExecutor(max_workers=4)
        pre_ = {}
        if clean_company():
            _comp, _auto, _kp = screening_parties()
            if prm["want_news"]:
                pre_["screen_news"] = pool_.submit(screen_news_call, _kp, clean_company())
            if k_or:
                pre_["web_news"] = pool_.submit(web_news_call, web_search_client("news"), clean_company(), ss.cin, ss.aliases) if prm["want_news"] else None
                pre_["brsr_web"] = pool_.submit(WF.fetch_pcaf_inputs, web_search_client("brsr_web"), clean_company(), ss.cin)
                if _kp:
                    pre_["screen_ai"] = pool_.submit(screen_ai_call, web_search_client("screening"), _comp, _kp)
        pool_.shutdown(wait=False)
        if prm["want_news"] and clean_company():
            _step(job, "news", "running")
            n_g = n_w = 0
            try:
                process_news(prm["days"], log)
                n_g = len(ss.news or [])
            except Exception as e:
                UI.warning(f"Google News failed: {e}")
            if k_or:
                try:
                    n_w = process_web_news(log, data=pre_["web_news"].result() if pre_.get("web_news") else None)
                except Exception as e:
                    UI.warning(f"Web search for news failed: {e}")
            _step(job, "news", "done", f"{n_g} news + {n_w} web items" + ("" if k_or else " (add the OpenRouter key for web search)"))
        else:
            _step(job, "news", "skipped", "news switched off" if not prm["want_news"] else "company name not found - type it on the desk")
        if k_or and clean_company():
            _step(job, "brsr_web", "running")
            try:
                ss.web_pcaf = VF.verify_web_pcaf(pre_["brsr_web"].result() if pre_.get("brsr_web") else
                                                 WF.fetch_pcaf_inputs(web_search_client("brsr_web"), clean_company(), ss.cin), clean_company(), ss.cin)
                w_ = ss.web_pcaf or {}
                _step(job, "brsr_web", "done", ("BRSR filed" if w_.get("brsr_filed") else "no BRSR found") + (" · emissions declared" if w_.get("emissions_declared") else ""))
            except Exception as e:
                UI.warning(f"BRSR web check failed: {e}")
                _step(job, "brsr_web", "failed", str(e)[:120])
        else:
            _step(job, "brsr_web", "skipped", "needs the OpenRouter key (⚙ Settings)" if not k_or else "company name not found")
        _step(job, "screen", "running")
        try:
            run_screening(use_os=bool(os_key), use_news=prm["want_news"], use_ai=bool(k_or), log=log,
                          pre={"news": pre_.get("screen_news"), "ai": pre_.get("screen_ai")})
            sm_ = (ss.screening or {}).get("summary") or {}
            _step(job, "screen", "done", f"{sm_.get('parties', 0)} parties · {sm_.get('hits', 0)} potential match(es) · {sm_.get('entries', 0)} list entries")
        except Exception as e:
            UI.warning(f"Screening failed: {e}")
            _step(job, "screen", "failed", str(e)[:120])
        _step(job, "score", "running")
        bundle_ = get_bundle()
        if bundle_ is None:
            _step(job, "score", "failed", "no figures could be read - open Spread review to enter them")
            raise RuntimeError("Could not read any financial figures - open 'Spread review' to enter them manually.")
        _step(job, "score", "done", f"score {FZ.score_text(bundle_['forensics'])} · {bundle_['forensics']['grade']}")
        _step(job, "report", "running")
        make_outputs(bundle_)
        _step(job, "report", "done", f"cost ≈ ₹{case_cost(ss.case_uid, FX)['inr']:,.2f}")
        job["status"] = "done"
    except BaseException as e:  # incl. Streamlit's StopException - the job must never stay "running"
        job["status"] = "error"
        job["error"] = str(e) or type(e).__name__
        job["trace"] = traceback.format_exc()[-2000:]
        print("[analysis job failed]", traceback.format_exc(), file=sys.stderr)
        for s_ in job["steps"]:
            if s_["state"] == "running":
                s_["state"] = "failed"
        DB.log(USER["username"], "analysis_error", str(e)[:300])
    job["finished"] = dt.datetime.now()


CASE_STATE = ["ext", "notes", "brsr", "news", "brief", "narr", "pcaf_in", "statement_type_used", "method", "source_file", "cin", "xcheck",
              "web_pcaf", "screening", "support", "flag_remarks", "qa", "rt_out", "_out", "pages", "located", "pdf_bytes", "attest", "parties", "doc_people", "checks", "dual", "integrity"]


def reset_case_state(keep_company=True):
    """A new document = a new case: clear everything derived from the previous borrower."""
    for k_ in CASE_STATE:
        if k_ in ss:
            ss[k_] = {} if k_ in ("pages", "located", "flag_remarks", "support", "pdf_bytes", "attest") else ([] if k_ in ("news", "qa", "parties") else None)
    if not keep_company or ss.get("company_auto"):
        ss.company = ""
    ss.case_uid = f"{USER['username']}-{dt.datetime.now():%Y%m%d%H%M%S%f}"
    for _l in llms.values():
        if _l is not None:
            _l.case_id = ss.case_uid


def start_job(prm):
    reg = _job_registry()
    jid = f"{USER['username']}-{dt.datetime.now():%Y%m%d%H%M%S%f}"
    job = {"id": jid, "status": "running", "started": dt.datetime.now(), "finished": None, "pct": 0.0, "sub": (0.0, ""),
           "steps": [{"key": k_, "name": n_, "state": "pending", "detail": ""} for k_, n_ in STEPS], "log": [], "warnings": [],
           "company": ss.company, "error": None}
    reg[jid] = job
    ss.job_id = jid
    t = threading.Thread(target=_run_job, args=(job, prm), daemon=True)
    ctx_ = get_script_run_ctx()
    add_script_run_ctx(t, ctx_)
    t.ci_state = _RawState(ctx_.session_state)
    t.ci_job = job
    t.start()
    return job


def get_job():
    return _job_registry().get(ss.get("job_id")) if ss.get("job_id") else None


ICON = {"pending": "⚪", "running": "⏳", "done": "✅", "skipped": "➖", "failed": "❌"}


def render_job(job, full=True):
    el = (job.get("finished") or dt.datetime.now()) - job["started"]
    head = {"running": "Running full credit analysis", "done": "Analysis complete", "error": "Analysis stopped"}[job["status"]]
    cur = next((s_ for s_ in job["steps"] if s_["state"] == "running"), None)
    sub_v, sub_t = job.get("sub", (0.0, ""))
    pct = job["pct"] + (sub_v / len(job["steps"]) if cur else 0)
    st.markdown(f"<div class='jobhead'><b>{head}</b> · {E(job.get('company') or '')} · {int(el.total_seconds()) // 60}m {int(el.total_seconds()) % 60}s</div>",
                unsafe_allow_html=True)
    st.progress(min(pct, 1.0), text=(f"Step {job['steps'].index(cur) + 1} of {len(job['steps'])}: {cur['name']}" + (f" - {sub_t}" if sub_t else ""))
                if cur else f"{int(min(pct, 1.0) * 100)}%")
    if full:
        rows = "".join(f"<div class='jstep {s_['state']}'><span>{ICON[s_['state']]}</span><div><b>{i + 1}. {s_['name']}</b>"
                       f"<div class='jd'>{E(str(s_.get('detail') or ''))}{(' · ' + str(int(s_['secs'])) + 's') if s_.get('secs') else ''}</div></div></div>"
                       for i, s_ in enumerate(job["steps"]))
        st.markdown(f"<div class='jsteps'>{rows}</div>", unsafe_allow_html=True)
        if job["warnings"]:
            with st.expander(f"⚠ {len(job['warnings'])} warning(s)"):
                for w_ in job["warnings"]:
                    st.write("• " + w_)
        with st.expander("Activity log"):
            st.code("\n".join(f"{t_} {m_}" for t_, _, m_ in job["log"][-80:]) or "-", language=None)
    if job["status"] == "error":
        st.error(job.get("error"))


@st.fragment(run_every=1.5)
def job_monitor(full=True):
    job = get_job()
    if not job:
        return
    if job["status"] == "running":
        render_job(job, full)
    else:
        if not ss.get(f"_seen_{job['id']}"):
            ss[f"_seen_{job['id']}"] = True
            st.rerun(scope="app")
        if full:
            render_job(job, full)


def clean_company():
    return (ss.company or "").replace("(fictional sample)", "").strip()


def guess_company(pages_by_doc):
    """Most frequent 'XYZ LIMITED' style name on the first pages of the annual report."""
    from collections import Counter
    cnt = Counter()
    for pgs in (pages_by_doc or {}).values():
        for p_ in pgs[:8]:
            for m_ in re.finditer(r"\b([A-Z][A-Z0-9&.,'()\- ]{3,80}?(?:PRIVATE LIMITED|LIMITED|LTD\.?|LLP))\b", p_.get("text") or ""):
                nm = re.sub(r"\s+", " ", m_.group(1)).strip(" ,.-")
                if 2 <= len(nm.split()) <= 9 and not re.search(r"\b(AUDIT|REPORT|NOTES|ANNEXURE|BANK|MEMBERS|STATEMENT)\b", nm):
                    cnt[nm] += 1
    if not cnt:  # names printed in normal capitalisation: 'Bridge & Roof Co. (India) Ltd.'
        rx_ = re.compile(r"\b((?:(?:\([A-Za-z0-9&.'\-]+\)|[A-Z][A-Za-z0-9&.'\-]*)\)?|of|and|the|&)(?:\s+(?:\(?[A-Za-z0-9&.'\-]+\)?|of|and|the|&)){1,8}?\s+"
                         r"(?:Private Limited|Pvt\.?\s*Ltd\.?|Limited|Ltd\.?|LLP|Corporation|Foundation|Trust|Society))\b", re.I)
        for pgs in (pages_by_doc or {}).values():
            for p_ in pgs[:8]:
                for m_ in rx_.finditer(p_.get("text") or ""):
                    nm = re.sub(r"\s+", " ", m_.group(1)).strip(" ,.-")
                    if nm.split()[0].lower() in ("of", "and", "the", "&", "for") or re.search(r"\b(Audit|Report|Notes|Annexure|Bank|Members|Statement|Directors?)\b", nm, re.I):
                        continue
                    cnt[nm] += 1
    if not cnt:
        return ""
    top = cnt.most_common(1)[0][0]
    return re.sub(r"\bLtd\b", "Ltd", top.title(), flags=re.I).replace(" Of ", " of ").replace(" And ", " and ").replace("(India)", "(India)")


def name_from_file(fname):
    """'Uniq-Facility-Services-Private-Limited.pdf' -> 'Uniq Facility Services Private Limited' (only if it looks like a company)."""
    base = re.sub(r"\.(pdf|png|jpe?g|tiff?)$", "", os.path.basename(fname or ""), flags=re.I)
    base = re.sub(r"(?i)\b(annual[ _-]?report|audited|financials?|balance[ _-]?sheet|fy\s?\d{2,4}|20\d\d(-\d\d)?|scanned|sample|final|signed)\b", " ", base)
    words = [w for w in re.split(r"[\s_\-]+", base) if w and not w.isdigit()]
    if len(words) >= 2 and re.search(r"(?i)\b(limited|ltd|llp|private|pvt|industries|corporation|company)\b", " ".join(words)):
        return " ".join(w if w.isupper() and len(w) <= 4 else w.capitalize() for w in words)
    return ""


def web_search_client(task="web"):
    return WS.WebSearch(k_or, m_or, max_results=8, case_id=ss.case_uid, task=task) if k_or else None


def web_news_call(ws, company, cin, aliases):
    """The web-search request itself (no page/session access - safe to run in a worker thread)."""
    extra = (f"\nCIN: {cin}" if cin else "") + (f"\nAlso known as: {aliases}" if aliases else "")
    return ws.chat_json(WS.NEWS_SYS, WS.NEWS_PROMPT.format(company=company, extra=extra), max_tokens=3500)


def process_web_news(log, data=None):
    """Cheap web search (OpenRouter + Parallel) for news, rating actions, litigation; merged with Google News.
    `data` = result fetched in advance (the full analysis starts it early, in parallel with other steps)."""
    if data is None:
        ws = web_search_client("news")
        if not ws or not clean_company():
            return 0
        data = web_news_call(ws, clean_company(), ss.cin, ss.aliases)
    items = []
    for it in data.get("items") or []:
        if it.get("url") and it.get("title"):
            items.append({"date": it.get("date") or "", "title": it["title"], "source": it.get("source") or "web", "url": it["url"],
                          "summary": it.get("summary") or "", "category": it.get("category") or "Other",
                          "sentiment": it.get("sentiment") or "Neutral", "severity": it.get("severity") or "Low", "query": "web search"})
    cites = data.get("_citations") or []
    items, rejected = VF.verify_news(items, clean_company(), ss.cin, cites)  # only items whose page really carries the story
    seen = {(n_.get("url") or n_.get("title")) for n_ in (ss.news or [])}
    ss.news = (ss.news or []) + [i_ for i_ in items if i_["url"] not in seen and i_["title"] not in seen]
    wb = data.get("brief") or {}
    br = dict(ss.brief or {})
    br["unverified_web"] = rejected
    if wb.get("overview") and items and (not br.get("overview") or "keyword rules" in br.get("overview", "") or br.get("overview", "").startswith("No news")):
        br["overview"] = wb["overview"]
        br["overview_source"] = "AI summary of web search - only the items listed with sources were verified"
    elif not items:
        br["overview"] = (br.get("overview") or "") + (f" Web search ran: {len(data.get('items') or [])} item(s) returned, "
                                                       f"{len(rejected)} rejected because the source page did not show the company and the story.")
    for k_ in ("key_positives", "key_concerns", "regulatory_legal", "management_governance", "items_needing_verification"):
        br[k_] = list(dict.fromkeys((br.get(k_) or []) + (wb.get(k_) or [])))
    ok_r, bad_r = VF.verify_rating(data.get("credit_rating") or {}, clean_company(), ss.cin, cites)
    br.pop("credit_rating", None)
    if ok_r:
        br["credit_rating"] = ok_r
    if bad_r:
        br["credit_rating_unverified"] = bad_r
    VF.fetch_many([c_.get("url") for c_ in cites])
    br["web_sources"] = [c_ for c_ in cites if VF.fetch_text(c_.get("url"))[0] and VF.mentions_company(VF.fetch_text(c_.get("url"))[0], clean_company(), ss.cin)]
    ss.brief = br
    log(f"Web search: {len(items)} items verified on their source page, {len(rejected)} rejected (page missing / does not match)" + (f", rating {br['credit_rating'].get('agency')} {br['credit_rating'].get('rating')}" if br.get("credit_rating") else ""))
    return len(items)


def screening_parties():
    """(company, all parties found, key parties for web checks) - in priority order."""
    comp = ss.company or (bundle_hdr or {}).get("company") or ""
    auto = WL.parties_for({"company": comp, "cin": ss.cin, "notes": ss.notes},
                          list(ss.parties or []) + EX.people_to_parties(ss.get("doc_people") or {}), ss.get("pages"))
    _prio = ("Borrower", "Promoter", "Director", "Guarantor", "Group", "Related", "Key", "Statutory auditor")
    key_parties = sorted([p_ for p_ in auto if p_["role"].startswith(_prio)],
                         key=lambda p_: next(i_ for i_, r_ in enumerate(_prio) if p_["role"].startswith(r_)))[:18]
    return comp, auto, key_parties


def screen_ai_call(ws, comp, key_parties):
    """AI web screening request (worker-thread safe)."""
    plist = "\n".join(f"- {p_['name']} ({p_['role']}{', ' + p_['id'] if p_.get('id') else ''})" for p_ in key_parties)
    return ws.chat_json(WS.SCREEN_SYS, WS.SCREEN_PROMPT.format(company=comp, parties=plist), max_tokens=3000)


def screen_news_call(key_parties, borrower_name):
    """Adverse-news lookups for the key parties, 8 at a time (worker-thread safe)."""
    from concurrent.futures import ThreadPoolExecutor

    def one(p_):
        q_ = f'"{WL.norm(p_["name"]) if p_["role"] != "Borrower" else borrower_name or p_["name"]}" (fraud OR "wilful defaulter" OR CBI OR "Enforcement Directorate" OR SEBI OR NCLT OR insolvency OR raid)'
        try:
            its = NW.google_news(q_, days=1825, limit=8)
        except Exception:
            return []
        for it in its:
            it["party"] = p_["name"]
        return its
    with ThreadPoolExecutor(max_workers=8) as pool:
        return [it for lst in pool.map(one, key_parties[:8]) for it in lst]


def run_screening(use_os=True, use_news=True, use_ai=True, log=None, pre=None):
    """pre = {"ai": future, "news": future} started earlier by the full analysis (optional)."""
    pre = pre or {}
    entries = [e for e in DB.wl_entries() if DEMO or not str(e.get("source", "")).startswith("SAMPLE")]  # test lists never count in production
    comp, auto, key_parties = screening_parties()
    hits, summ = WL.screen(auto, entries, WL.distinctive(comp)) if entries else ([], {"parties": len(auto), "lists": 0, "entries": 0,
                                                                                     "when": dt.datetime.now().strftime("%d-%b-%Y %H:%M")})
    online = False
    if use_os and os_key:
        try:
            hits += WL.opensanctions(auto, os_key)
            online = True
        except Exception as e:
            UI.warning(f"OpenSanctions lookup failed: {e}")
    web = []
    if use_news:
        try:
            web = pre["news"].result() if pre.get("news") else screen_news_call(key_parties, clean_company())
        except Exception:
            web = []
    ai_web = None
    if use_ai and k_or and key_parties:
        try:
            ai_web = pre["ai"].result() if pre.get("ai") else screen_ai_call(web_search_client("screening"), comp, key_parties)
            _ok_f, _bad_f = VF.verify_findings([f_ for f_ in (ai_web.get("findings") or []) if f_.get("url")], comp, ss.cin, ai_web.get("_citations") or [])
            ai_web["findings"], ai_web["unverified"] = _ok_f, _bad_f  # unverified results are leads to check, never hits
            _clear = re.compile(r"\bno (adverse|negative|relevant)|\bnot found\b|\bnothing (adverse|found)|\bno (record|evidence|match)|\bclean\b|\bnone found", re.I)
            for f_ in ai_web.get("findings") or []:
                if not f_.get("url"):
                    continue
                if _clear.search(f_.get("finding") or "") and not f_.get("list_or_action"):
                    ai_web.setdefault("clear_parties", []).append(f_.get("party") or comp)  # a 'nothing found' result is a clearance, not a hit
                    continue
                conf = f_.get("same_party_confidence") or "Low"
                sev = f_.get("severity") if conf == "High" else ("Medium" if conf == "Medium" else "Low")
                hits.append({"party": f_.get("party") or comp, "role": "Web finding", "party_id": "", "pages": [],
                             "listed_name": f_.get("party") or "", "list": f"Web: {f_.get('list_or_action') or 'adverse finding'}",
                             "listed_id": "", "reason": f_.get("finding") or "", "list_date": f_.get("date") or "",
                             "score": {"High": 95, "Medium": 80, "Low": 60}.get(conf, 60),
                             "match": f"Web search finding (same-party confidence {conf}) - verify", "severity": sev or "Medium", "source": f_["url"]})
        except Exception as e:
            UI.warning(f"Web screening failed: {e}")
    order = {"High": 0, "Medium": 1, "Low": 2}
    hits.sort(key=lambda h: (order.get(h["severity"], 3), -h["score"]))
    summ.update({"hits": len(hits), "high": sum(1 for h in hits if h["severity"] == "High"), "parties": len(auto)})
    ss.screening = {"hits": hits, "summary": summ, "parties": [{k_: p_[k_] for k_ in ("name", "role")} for p_ in auto],
                    "online": online or bool(ai_web), "web": web, "ai_web": ai_web}
    DB.log(USER["username"], "watchlist_screen", f"{comp}: {len(hits)} hits")
    if log:
        log(f"Screening: {len(auto)} parties, {len(hits)} potential match(es)")


ENV_MAP = {"DEEPSEEK_API_KEY": "k_ds", "OPENROUTER_API_KEY": "k_or", "LONGCAT_API_KEY": "k_lc", "DEEPSEEK_MODEL": "m_ds",
           "OPENROUTER_MODEL": "m_or", "LONGCAT_MODEL": "m_lc", "NEWSAPI_KEY": "newsapi_key", "GNEWS_KEY": "gnews_key",
           "OPENSANCTIONS_API_KEY": "os_key", "BRANCH_NAME": "branch", "BANK_NAME": "bank_name",
           "DUAL_READ": "dual", "VISION_MODEL": "m_vis", "CLOUD_OCR": "cloud_ocr"}


def save_env():
    """Write the Settings values into .env next to app.py (keeps other lines)."""
    path = os.path.join(HERE, ".env")
    lines = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
    done = set()
    out = []
    for ln in lines:
        k_ = ln.split("=", 1)[0].strip().lstrip("# ").strip()
        if k_ in ENV_MAP and ("=" in ln):
            out.append(f"{k_}={S(ENV_MAP[k_])}")
            done.add(k_)
        else:
            out.append(ln)
    for k_, v_ in ENV_MAP.items():
        if k_ not in done and S(v_):
            out.append(f"{k_}={S(v_)}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    for k_, v_ in ENV_MAP.items():
        os.environ[k_] = str(S(v_) or "")
    return path


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
        bar = UI.progress(0.0, text=f"Reading {name}")
        pages = PR.read_pdf(data, ocr_mode=ocr_mode, max_pages=int(max_pages), progress=lambda p, t: bar.progress(min(p, 1.0), text=t))
        prof = PR.doc_profile(pages)
        if prof["ocr_pages"] and PR.OCR_AVAILABLE is False:
            UI.warning("Scanned pages found but the OCR engine is not installed - run setup.bat again (installs rapidocr).")
        loc = PR.locate_sections(pages, prefer=ss.statement_type)
        ss.pages[name], ss.located[name] = pages, loc
        if not ss.company:
            ss.company = guess_company({name: pages}) or name_from_file(name)
            ss.company_auto = bool(ss.company)
            if ss.company:
                UI.info(f"Company name read from the document: {ss.company}")
        ss.cin = prof["cin"] or ss.cin
        log(f"**{name}** - {prof['pages']} pages ({prof['ocr_pages']} via OCR). {loc.get('basis', '').title()} statements: balance sheet "
            f"p.{loc['balance_sheet']}, P&L p.{loc['profit_loss']}, cash flow p.{loc['cash_flow']}")
        ss.statement_type_used = loc.get("basis") or ss.statement_type
        if loc.get("basis_note"):
            UI.warning(loc["basis_note"])
        heur = EX.heuristic_extract(pages, loc)
        # scanned statement pages: also read them with a document-OCR engine and keep whichever reading adds up better
        st_pages_ = sorted({n_ for k_ in ("balance_sheet", "profit_loss", "cash_flow") for n_ in loc.get(k_, [])})
        kor_ = S("k_or")
        if kor_ and S("cloud_ocr") and st_pages_ and any(p_.get("ocr") for p_ in pages if p_["page"] in st_pages_):
            try:
                log(f"Document OCR (Mistral OCR) of scanned statement pages {st_pages_} ...")
                txt_ = DR.cloud_ocr_pages(kor_, data, st_pages_, model=S("m_vis") or DR.DEFAULT_VISION_MODEL, case_id=ss.case_uid)
                if txt_:
                    alt_ = [dict(p_, text=txt_[p_["page"]], text_local=p_["text"], ocr_engine="mistral-ocr") if p_["page"] in txt_ else p_
                            for p_ in pages]
                    heur2 = EX.heuristic_extract(alt_, loc)
                    s1_, s2_ = CK.reading_score(heur), CK.reading_score(heur2)
                    log(f"Local OCR reading scores {s1_}, document OCR {s2_} (totals that add up, core lines read)")
                    if s2_ > s1_:
                        pages, heur = alt_, heur2
                        ss.pages[name] = pages
                        heur.setdefault("extraction_notes", []).append(f"Scanned statement pages {sorted(txt_)} read with Mistral OCR "
                                                                       f"(its totals added up better than the local OCR: {s2_} vs {s1_}).")
            except Exception as e_:  # noqa: BLE001 - the local OCR reading stays in use
                log(f"Document OCR not used ({str(e_)[:120]}); local OCR kept")
        ext = heur
        llm = router.get("extract")
        good, why = rule_spread_ok(heur)
        if llm and router.mode == "cheapest" and good:
            log(f"Rule-based spread passed checks ({why}) - AI extraction skipped, cost ₹0")
        elif llm:
            try:
                log(f"AI extraction with {llm.label} ...")
                ext = EX.llm_extract_financials(llm, pages, loc, loc.get("basis") or ss.statement_type)
                diffs = []
                for y in ext["years"]:
                    if y not in heur["data"]:
                        continue
                    for k in schema.KEYS:
                        a, b = ext["data"][y].get(k), heur["data"][y].get(k)
                        if a is not None and b is not None and abs(a - b) > max(0.01 * abs(a), 0.05):
                            diffs.append({"Year": y, "Item": schema.LABELS[k], "AI": a, "Rule-based": b})
                ss.xcheck = diffs
                if ext.get("company_name") and (not ss.company or ss.get("company_auto")):
                    ss.company = ext["company_name"]
                    ss.company_auto = True
            except Exception as e:
                UI.warning(f"AI extraction failed ({e}); using the rule-based reader.")
                ext = heur
        methods.append(ext.get("method", "rule-based"))
        cur_doc = PR.detect_currency("\n".join(p_["text"] for p_ in pages[:40]))  # the whole report, not only the statement pages
        if cur_doc[0] and not (ext.get("currency") or {}).get("code"):
            ext["currency"] = {"code": cur_doc[0], "evidence": cur_doc[1]}
        ss.ext = merge_ext(ss.ext, ext)
    if pdfs and not ss.company and router.get("extract"):
        try:  # tiny AI call (≈₹0.01) to read the company name when OCR text has no spaces
            first = "\n".join(p_["text"] for p_ in ss.pages[pdfs[0][0]][:3])[:4000]
            nm_ = router.get("extract").chat("Return only the legal name of the company whose financial statements these are. No other words.",
                                             first, max_tokens=40).strip().strip('"').splitlines()[0][:120]
            if nm_ and len(nm_) > 3 and "unknown" not in nm_.lower():
                ss.company, ss.company_auto = nm_, True
                UI.info(f"Company name (AI): {nm_}")
        except Exception as e:
            UI.warning(f"Could not read the company name: {e}")
    if pdfs:
        name0 = pdfs[0][0]
        llm = router.get("notes")
        if llm:
            try:
                log(f"AI review ({llm.label}) of auditor's report, CARO, related-party and contingent-liability notes ...")
                ss.notes = EX.llm_review_notes(llm, ss.pages[name0], ss.located[name0], unit_fallback=(ss.ext or {}).get("unit_multiplier"))
            except Exception as e:
                UI.warning(f"AI notes review failed ({e}); using keyword scan.")
                ss.notes = EX.heuristic_notes_review(ss.pages[name0], ss.located[name0])
        else:
            ss.notes = EX.heuristic_notes_review(ss.pages[name0], ss.located[name0])
        # ICAI UDIN Compliance Audit
        try:
            from core import udin as udin_mod
            all_pages = [p for p_list in (ss.pages or {}).values() for p in p_list]
            ss.udin_info = udin_mod.audit_udin_compliance(all_pages, (ss.ext or {}).get("years", []), notes=ss.notes)
            if ss.udin_info.get("has_udin"):
                log(f"ICAI UDIN detected: {ss.udin_info.get('primary_udin', {}).get('udin')} (Status: {ss.udin_info.get('status')})")
            elif ss.udin_info.get("is_mandatory"):
                log(f"⚠️ ICAI UDIN not found on audited statement (mandatory since 01-Jul-2019)")
        except Exception as _ue:
            UI.warning(f"UDIN check encountered an issue: {_ue}")
            ss.udin_info = None
    ss.doc_people = {}
    if pdfs and router.get("notes"):
        try:
            UI.write("Identifying directors, KMP, promoters, group companies and auditor for screening ...")
            ss.doc_people = EX.llm_extract_people(router.get("notes"), ss.pages[pdfs[0][0]])
            n_ = len(EX.people_to_parties(ss.doc_people))
            UI.write(f"{n_} directors / KMP / promoters / group entities found")
        except Exception as e:
            UI.warning(f"People extraction failed ({e}); using names found by pattern only.")
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
            UI.warning(f"AI BRSR extraction failed ({e}); using pattern scan.")
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
            UI.warning(f"AI review of supporting documents failed ({e}); keyword scan used.")
    ss.support = sup


def process_news(days, log):
    bar = UI.progress(0.0, text="Searching news ...")
    raw, errs = NW.fetch_news(clean_company(), [x.strip() for x in (ss.aliases or "").split(",")], days=days,
                              newsapi_key=newsapi_key or None, gnews_key=gnews_key or None,
                              progress=lambda p, t: bar.progress(min(p, 1.0), text=t))
    for e in errs[:2]:
        UI.warning(e)
    log(f"{len(raw)} news items found")
    llm = router.get("news")
    if llm and raw:
        ss.news = NW.classify_news(llm, clean_company(), raw)
        try:
            ss.brief = NW.intelligence_brief(llm, clean_company(), ss.news, "")
        except Exception as e:
            UI.warning(f"News brief failed: {e}")
    else:
        ss.news = NW.keyword_classify(raw)
        ss.brief = {"overview": (f"No news articles were found for '{clean_company()}' in the last {days} days (Google News"
                                 + (", NewsAPI" if newsapi_key else "") + (", GNews" if gnews_key else "") + ")." if not raw else
                                 f"{len(raw)} articles scanned with keyword rules" + ("" if llm else " (add an AI key for a written brief)") + ".")
                                + (" Sources that failed: " + "; ".join(errs[:2]) if errs else "")}


def pcaf_from_case():
    c = ss.case or {}
    if not c.get("exposure"):
        return
    br = ss.brsr or {}
    factors = PC.load_factors()
    sec = next((f for f in factors if f["sector"] == c.get("sector") and f.get("approved")), None)  # placeholder factors are never used
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
    all_pages = [p for p_list in (ss.pages or {}).values() for p in p_list]
    return pipeline.analyse(ss.ext["data"], years, ss.company or "Company", notes=ss.notes, news=ss.news, brief=ss.brief,
                            brsr=ss.brsr, pcaf_inputs=ss.pcaf_in, statement_type=ss.get("statement_type_used") or ss.statement_type, source_file=ss.source_file,
                            method=ss.method, cin=ss.cin, comments=ss.comments, flag_remarks=ss.flag_remarks, support=ss.support,
                            screening={**(ss.get("screening") or {}), "attest": ss.get("attest") or {}},
                            proposal={"facility": c.get("facility"), "amount": c.get("amount", 0), **(c.get("prop") or {})},
                            udin=ss.get("udin_info"),
                            meta={"sector": (ss.case or {}).get("sector") if (ss.case or {}).get("sector") not in (None, "-") else None,
                                  "pages": all_pages,
                                  "located": {k_: {s_: v_ for s_, v_ in l_.items() if isinstance(v_, list)} for k_, l_ in (ss.located or {}).items()},
                                  "basis_notes": [l_.get("basis_note") for l_ in (ss.located or {}).values() if l_.get("basis_note")],
                                  "extraction_notes": (ss.ext or {}).get("extraction_notes"),
                                  "figure_changes": (ss.ext or {}).get("changes") or [],
                                  "derived_fields": (ss.ext or {}).get("derived") or {},
                                  "provenance": (ss.ext or {}).get("provenance") or {},
                                  "unit_status": (ss.ext or {}).get("unit_status"), "currency": (ss.ext or {}).get("currency"),
                                  "model": "; ".join(f"{t}: {v}" for t, v in router.describe().items()) if router.ready else "none (rule-based only)",
                                  "newsapi": bool(newsapi_key), "web_esg": ss.get("web_pcaf"),
                                  "dual": {k_: v_ for k_, v_ in (ss.get("dual") or {}).items() if k_ != "images"} or None,
                                  "dual_enabled": bool(S("dual") and k_or)})


def make_outputs(bundle):
    ss.narr = pipeline.check(bundle, pipeline.write_narrative(bundle, router.get("narrative")))  # AI sentences with untraceable figures removed
    ss.checks = bundle.get("checks")
    ss.integrity = bundle.get("integrity")
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
    ss.narr = bundle.get("final_narrative") or ss.narr  # the narrative exactly as printed
    summ_ = pipeline.case_summary(bundle)
    DB.add_case(USER["username"], bundle["company"], summ_,
                cc["inr"], cc["usd"], cc["calls"], paths["docx"], paths["xlsx"], jpath, ss.source_file,
                metrics={**portfolio_metrics(bundle), "integrity": summ_["integrity"]})
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
        a.markdown(f'<div class="cmt"><div class="m">{E(str(c.get("when", "")))} · {E(c.get("author") or "Officer")} · {E(c.get("topic", "General"))}</div>'
                   f'{E(str(c.get("text", "")))}</div>', unsafe_allow_html=True)
        if allow_delete and b.button("🗑", key=f"{prefix}_del_{i}", help="Delete this comment"):
            ss.comments.pop(i)
            st.rerun()


def top_flags(container, fz, n=6):
    for f in sorted(fz["flags"], key=lambda f: {"High": 0, "Medium": 1, "Low": 2}.get(f["severity"], 3))[:n]:
        container.markdown(f'<div class="flag" style="border-left-color:{SEV_COLOR.get(f["severity"], "#999")}">{SEV_ICON.get(f["severity"], "")} '
                           f'<b>{E(f["severity"])}</b> · {E(f["title"])}<br><span style="opacity:.8;font-size:.88rem">{E(str(f["evidence"]))}</span></div>',
                           unsafe_allow_html=True)


# ------------------------------------------------------------------ page header
def page_header(title, sub=""):
    fzh = None
    try:
        fzh = bundle_hdr["forensics"] if bundle_hdr else None
    except Exception:
        pass
    pills = ""
    if ss.company:
        pills += f"<span class='hpill'>🏢 {E(ss.company[:42])}</span>"
    if fzh:
        blk_ = (bundle_hdr.get("integrity") or {}).get("status") == "BLOCKED"
        gcol = "#8A817A" if (blk_ or str(fzh.get("grade") or "").startswith("NR")) else "#16935f" if fzh["score"] >= 60 else ("#d48806" if fzh["score"] >= 40 else "#d03b3b")
        pills += f"<span class='hpill' style='color:{gcol};border-color:{gcol}55'>● {fzh['grade'].split(' - ')[0]} · {FZ.score_text(fzh)}{' · provisional' if blk_ else ''}</span>"
    st.markdown(f"<div class='topbar'><div><div class='ttl'>{title.upper()}</div><div class='tsub'>{sub}</div></div><div>{pills}</div></div>",
                unsafe_allow_html=True)


PAGE_SUBS = {"desk": "Upload the borrower's documents, add your observations and run the full analysis.",
             "dash": "Snapshot of the borrower - performance, risk and repayment capacity at a glance.",
             "spread": "Check and correct every extracted figure against the source page.",
             "ratios": "Every ratio with benchmark, trend and what it means.",
             "proposal": "Structure the facility and test repayment capacity, security and pricing.",
             "forensic": "Hidden items, fund diversion tests and your disposition on each flag.",
             "ews": "RBI early-warning signals and earnings quality.",
             "fraud": "Borrower, promoters and related parties against defaulter, fraud and regulatory lists.",
             "market": "News and market intelligence on the borrower.", "brsr": "BRSR disclosures and PCAF financed emissions.",
             "reports": "Generate the memorandum, workbook and the other credit reports.", "ask": "Ask questions of the uploaded documents.",
             "portfolio": "All borrowers - risk mix, watch-list and peer comparison.", "history": "Every report generated, with cost - and your saved cases.",
             "settings": "AI keys, cost mode, extraction and report signature.", "admin": "Users, AI spend and activity."}

try:
    bundle_hdr = get_bundle()
    if bundle_hdr is not None and "integrity" not in bundle_hdr:  # case status for the header, from the current figures
        import copy as _cp
        CK.run(bundle_hdr, _cp.deepcopy(ss.narr) if ss.narr else pipeline.write_narrative(bundle_hdr))
except Exception:
    bundle_hdr = None
page_header(PAGE_TITLES[PAGE], PAGE_SUBS.get(PAGE, ""))
if PAGE != "desk" and get_job() and get_job()["status"] == "running":
    job_monitor(False)

# ================================================================== OFFICER DESK
if PAGE == "desk":
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown('<p class="step">Step 1 · Case details</p>', unsafe_allow_html=True)
        c = dict(ss.case or {})
        a, b = st.columns(2)
        _cn = a.text_input("Borrower / company name", value=ss.company or "", placeholder="Read automatically from the annual report - or type it",
                           help="Leave blank and the name is read from the document. Typing a name here overrides it.")
        if _cn != (ss.company or ""):
            ss.company, ss.company_auto = _cn, False
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
    _jr = get_job()
    run_all = o1.button("⏳  Analysis running ..." if (_jr and _jr["status"] == "running") else "▶  Run full credit analysis", type="primary",
                        use_container_width=True, disabled=not can_run or bool(_jr and _jr["status"] == "running"),
                        help="Reads every document, spreads the financials, runs ratios & forensic checks, pulls news, BRSR & PCAF, and writes the Word + Excel.")
    if not can_run:
        st.caption("Upload at least the annual report / balance sheet (or tick the sample) to run.")

    job_ = get_job()
    if run_all and not (job_ and job_["status"] == "running"):
        if use_sample:
            srcs = [(os.path.basename(sample), open(sample, "rb").read())]
            bs = os.path.join(HERE, "samples", "Sample_BRSR_DeccanPolyfab_FY25.pdf")
            brsr_src = (os.path.basename(bs), open(bs, "rb").read()) if os.path.exists(bs) else None
        else:
            srcs = [(f.name, f.getvalue()) for f in ar_files] if ar_files else []
            brsr_src = (brsr_file.name, brsr_file.getvalue()) if brsr_file else None
        if srcs:  # a fresh document = a fresh case (no data from the previous borrower)
            reset_case_state(keep_company=True)
        if use_sample:
            ss.company = ss.company or "Deccan Polyfab Industries Ltd (fictional sample)"
        DB.log(USER["username"], "analysis_run", ss.company or (srcs[0][0] if srcs else ""))
        start_job({"srcs": srcs, "brsr_src": brsr_src, "sup": [(f.name, f.getvalue()) for f in sup_files] if sup_files else [],
                   "want_news": want_news, "days": days})
        st.rerun()
    if get_job():
        job_monitor(True)
        if get_job()["status"] == "running":
            st.caption("You can open other pages while this runs - the progress bar stays at the top of every page.")

    bundle_d = get_bundle()
    if bundle_d:
        st.divider()
        fz = bundle_d["forensics"]
        y0 = bundle_d["years"][0]
        r0 = bundle_d["ratios"][y0]
        nh = sum(1 for f in fz["flags"] if f["severity"] == "High")
        st.markdown(f"#### Result · {E(bundle_d['company'])} · {y0}")
        if "integrity" not in bundle_d:
            import copy as _cp2
            CK.run(bundle_d, _cp2.deepcopy(ss.narr) if ss.narr else pipeline.write_narrative(bundle_d))
        ig_d = bundle_d.get("integrity") or {}
        blk_d = ig_d.get("status") == "BLOCKED"
        if blk_d:
            st.error(f"**Case BLOCKED - do not rely on these figures.** {ig_d.get('detail', '')}. Open the Dashboard for what to fix.")
            if "Figures confirmed by a second, independent reading" in (ig_d.get("failed_checks") or []):
                dual_ = ss.get("dual") or {}
                core_keys = {"revenue", "pat", "pbt", "total_equity", "total_assets", "total_current_assets", "total_current_liabilities", "finance_cost",
                             "long_term_borrowings", "short_term_borrowings", "trade_receivables", "inventories", "cfo"}
                open_core = [r_ for r_ in (dual_.get("rows") or []) if r_["status"].startswith("Disputed") and r_["key"] in core_keys]
                if open_core:
                    with st.expander(f"🔍 Action Required: Confirm {len(open_core)} Disputed Key Figure(s) to Unblock Case", expanded=True):
                        st.markdown("Reader 1 (PDF text parser) and Reader 2 (Vision AI) read different numbers for these core lines. "
                                    "Review the audited PDF and click to confirm the authoritative number:")
                        for ix_, r_ in enumerate(open_core):
                            dc1, dc2, dc3 = st.columns([4, 2, 2])
                            v1_str = "—" if r_["r1"] is None else f"{r_['r1']} Cr"
                            v2_str = "—" if r_["r2"] is None else f"{r_['r2']} Cr"
                            dc1.markdown(f"**{r_['label']} ({r_['year']})** · Current spread uses: `{r_['final']}` Cr")
                            if dc2.button(f"Confirm Reader 1 ({v1_str})", key=f"dsk_r1_{ix_}_{r_['key']}_{r_['year']}", use_container_width=True):
                                r_["final"] = r_["r1"]
                                r_["status"] = "Confirmed by officer"
                                if ss.ext and r_["year"] in ss.ext.get("data", {}):
                                    ss.ext["data"][r_["year"]][r_["key"]] = r_["r1"]
                                dual_["summary"] = DR.summary(dual_["rows"])
                                ss.dual = dual_
                                b_ = get_bundle()
                                if b_:
                                    make_outputs(b_)
                                save_case()
                                st.success(f"Confirmed {r_['label']} = {r_['r1']} Cr")
                                st.rerun()
                            if r_["r2"] is not None and dc3.button(f"Confirm Reader 2 ({v2_str})", key=f"dsk_r2_{ix_}_{r_['key']}_{r_['year']}", use_container_width=True):
                                r_["final"] = r_["r2"]
                                r_["status"] = "Confirmed by officer"
                                if ss.ext and r_["year"] in ss.ext.get("data", {}):
                                    ss.ext["data"][r_["year"]][r_["key"]] = r_["r2"]
                                dual_["summary"] = DR.summary(dual_["rows"])
                                ss.dual = dual_
                                b_ = get_bundle()
                                if b_:
                                    make_outputs(b_)
                                save_case()
                                st.success(f"Confirmed {r_['label']} = {r_['r2']} Cr")
                                st.rerun()
                        if st.button("Accept all Used / Reader 1 figures as verified from PDF", type="primary", key="dsk_all_r1", use_container_width=True):
                            for r_ in (dual_.get("rows") or []):
                                if r_["status"].startswith("Disputed"):
                                    r_["status"] = "Confirmed by officer"
                                    r_["final"] = r_["r1"]
                                    if ss.ext and r_["year"] in ss.ext.get("data", {}):
                                        ss.ext["data"][r_["year"]][r_["key"]] = r_["r1"]
                            dual_["summary"] = DR.summary(dual_["rows"])
                            ss.dual = dual_
                            b_ = get_bundle()
                            if b_:
                                make_outputs(b_)
                            save_case()
                            st.success("All disputed figures confirmed from PDF. Case unblocked!")
                            st.rerun()
        k = st.columns(5)
        kpi(k[0], "Internal credit score", FZ.score_text(fz) + (" (provisional)" if blk_d else ""), fz["grade"],
            "#8A817A" if blk_d else GOOD if fz["score"] >= 60 else (WARN if fz["score"] >= 40 else CRIT))
        kpi(k[1], "Recommendation", (ss.narr or {}).get("recommendation", "—"), "run analysis to refresh" if not ss.narr else (ss.narr.get("_source") or ""))
        kpi(k[2], "Red flags", len(fz["flags"]), f"{nh} high severity", CRIT if nh else GOOD)
        rv_ = bundle_d["data"][y0].get("revenue")
        kpi(k[3], "Revenue (₹ Cr)", "not read" if rv_ is None else (f"{rv_:,.1f}" + (" - unit check failed" if blk_d and abs(rv_) > 2e6 else "")),
            f"EBITDA margin {R.fmt('ebitda_margin', r0.get('ebitda_margin'))}")
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
                st.markdown(f"**💰 Cost of this report:** **₹{cc['inr']:,.2f}** (${cc['usd']:,.4f}) · {cc['calls']} AI calls, "
                            f"{cc['cached']} from cache (free) · basis: **{cc['basis']}**" + ("  ·  ₹0 - rule-based only" if not cc["calls"] else ""))
                with st.expander("Cost by model"):
                    st.dataframe(pd.DataFrame(cost_rows).rename(columns={"in": "input tokens", "out": "output tokens", "usd": "USD (est.)"}),
                                 hide_index=True, use_container_width=True)
                    st.caption(f"USD→INR {FX}. OpenRouter calls use the amount OpenRouter actually billed (usage.cost); other providers "
                               "(DeepSeek direct, LongCat) don't report cost, so their tokens are priced from Admin › Bank parameters › llm_prices.csv.")
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
def show_dual_panel(dual_):
    if dual_.get("rows"):
        sm_ = dual_["summary"]
        (st.error if sm_.get("unit_mismatch") or sm_["disputed"] else st.success)(
            f"Second reading ({dual_.get('model')}, pages {', '.join(str(p_) for p_ in dual_.get('pages') or [])}): {sm_['text']}")
        if dual_.get("corrections"):
            st.info("Corrected because the tie-breaker agreed with the second reading: " + "; ".join(dual_["corrections"]))
        open_ = [r_ for r_ in dual_["rows"] if not r_["status"].startswith(("Confirmed", "Corrected"))]
        with st.expander(f"Line-by-line comparison - {len(open_)} line(s) need your check", expanded=bool(open_)):
            st.dataframe(pd.DataFrame([{"Line": r_["label"], "Year": r_["year"], "Reader 1": r_["r1"], "Reader 2 (image)": r_["r2"],
                                        "Tie-breaker": r_["r3"], "Used": r_["final"], "Status": r_["status"]}
                                       for r_ in sorted(dual_["rows"], key=lambda r_: r_["status"].startswith("Confirmed"))]),
                         hide_index=True, use_container_width=True)
            if open_ and dual_.get("document") in (ss.pdf_bytes or {}):
                pg_ = st.selectbox("Open a statement page to check", dual_.get("pages") or [], key="dual_pg")
                try:
                    st.image(DR.page_images(ss.pdf_bytes[dual_["document"]], [pg_], dpi=110)[0][1], use_container_width=True)
                except Exception as e_:
                    st.caption(f"Page preview not available: {e_}")
            if open_:
                st.markdown("---")
                st.markdown("**Confirm disputed figures to unblock case:**")
                for ix_, r_ in enumerate(open_):
                    c1, c2, c3 = st.columns([4, 2, 2])
                    c1.markdown(f"**{r_['label']} ({r_['year']})** · Current spread uses: `{r_['final']}` Cr")
                    v1 = "—" if r_["r1"] is None else f"{r_['r1']} Cr"
                    v2 = "—" if r_["r2"] is None else f"{r_['r2']} Cr"
                    if c2.button(f"Confirm Reader 1 ({v1})", key=f"pnl_r1_{ix_}_{r_['key']}_{r_['year']}", use_container_width=True):
                        r_["final"] = r_["r1"]
                        r_["status"] = "Confirmed by officer"
                        if ss.ext and r_["year"] in ss.ext.get("data", {}):
                            ss.ext["data"][r_["year"]][r_["key"]] = r_["r1"]
                        dual_["summary"] = DR.summary(dual_["rows"])
                        ss.dual = dual_
                        b_ = get_bundle()
                        if b_:
                            make_outputs(b_)
                        save_case()
                        st.success(f"Confirmed {r_['label']} ({r_['year']}) = {r_['r1']} Cr")
                        st.rerun()
                    if r_["r2"] is not None and c3.button(f"Confirm Reader 2 ({v2})", key=f"pnl_r2_{ix_}_{r_['key']}_{r_['year']}", use_container_width=True):
                        r_["final"] = r_["r2"]
                        r_["status"] = "Confirmed by officer"
                        if ss.ext and r_["year"] in ss.ext.get("data", {}):
                            ss.ext["data"][r_["year"]][r_["key"]] = r_["r2"]
                        dual_["summary"] = DR.summary(dual_["rows"])
                        ss.dual = dual_
                        b_ = get_bundle()
                        if b_:
                            make_outputs(b_)
                        save_case()
                        st.success(f"Confirmed {r_['label']} ({r_['year']}) = {r_['r2']} Cr")
                        st.rerun()
                if st.button("Accept all Used / Reader 1 figures as verified from PDF", type="primary", key="pnl_all_r1", use_container_width=True):
                    for r_ in open_:
                        r_["status"] = "Confirmed by officer"
                        r_["final"] = r_["r1"]
                        if ss.ext and r_["year"] in ss.ext.get("data", {}):
                            ss.ext["data"][r_["year"]][r_["key"]] = r_["r1"]
                    dual_["summary"] = DR.summary(dual_["rows"])
                    ss.dual = dual_
                    b_ = get_bundle()
                    if b_:
                        make_outputs(b_)
                    save_case()
                    st.success("All disputed figures confirmed from PDF. Case unblocked!")
                    st.rerun()
    elif ss.ext and S("dual") and not k_or:
        st.warning("Figures rest on one reading only - add the OpenRouter key in ⚙ Settings to get an independent second reading.")


if PAGE == "spread":
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
        dual_ = ss.get("dual") or {}
        try:
            show_dual_panel(dual_)
        except Exception as e_:
            st.warning(f"Second-reading panel could not be shown: {e_}")
        if ss.xcheck:
            with st.expander(f"⚠ {len(ss.xcheck)} items where the AI and the rule-based reader disagree - check these against the PDF"):
                st.dataframe(pd.DataFrame(ss.xcheck), use_container_width=True, hide_index=True)
        if ss.ext.get("extraction_notes"):
            with st.expander(f"ℹ {len(ss.ext['extraction_notes'])} extraction notes (OCR repairs, ambiguities) - please verify"):
                for n_ in ss.ext["extraction_notes"]:
                    st.write("• " + str(n_))
        # ---- unit and currency of the document: never assumed silently
        cur_ = (ss.ext.get("currency") or {})
        if cur_.get("code") and cur_["code"] != "INR":
            st.error(f"**These statements appear to be in {cur_['code']}, not Indian rupees** ({cur_.get('evidence', '')}). Every ratio, norm, limit "
                     "and report in this app assumes INR - do not use the analysis for an INR exposure without converting the figures.")
        UNITS_ = {"Crore": 1.0, "Lakh": 0.01, "Million": 0.1, "Thousand": 0.0001, "Hundred": 0.00001, "Rupees (whole)": 1e-7, "Billion": 100.0}
        um_ = ss.ext.get("unit_multiplier") or 1.0
        cur_name_ = next((k_ for k_, v_ in UNITS_.items() if abs(v_ - um_) < 1e-12), None)
        us_ = ss.ext.get("unit_status")
        with st.expander("Document unit - " + (f"read as {cur_name_} from \"{us_[:60]}\"" if us_ and us_ != "NOT STATED" else
                                                "NOT STATED in the document - set it here"), expanded=(us_ == "NOT STATED")):
            ua_, ub_, uc_ = st.columns([1, 2, 1])
            new_u_ = ua_.selectbox("The figures in the PDF are in", list(UNITS_), index=list(UNITS_).index(cur_name_) if cur_name_ else 0, key="unit_pick")
            why_u_ = ub_.text_input("Reason (required)", key="unit_why", placeholder="e.g. 'Amounts in Rupees' printed on p.24 under the title")
            if uc_.button("Apply unit", disabled=not why_u_.strip() or (UNITS_[new_u_] == um_ and us_ != "NOT STATED"), use_container_width=True):
                f_ = UNITS_[new_u_] / um_
                chg_u_ = []
                for y_ in ss.ext["years"]:
                    for k_ in schema.KEYS:
                        v_ = ss.ext["data"][y_].get(k_)
                        if v_ is not None and k_ != "promoter_pledge_pct":
                            ss.ext["data"][y_][k_] = round(v_ * f_, 6)
                            chg_u_.append({"year": y_, "key": k_, "line": schema.LABELS.get(k_, k_), "old": v_, "new": ss.ext["data"][y_][k_]})
                ss.ext["unit_multiplier"], ss.ext["unit_status"] = UNITS_[new_u_], f"set by {USER['username']}: {new_u_} - {why_u_.strip()}"
                now_ = dt.datetime.now().isoformat(timespec="seconds")
                ss.ext.setdefault("changes", []).append({"year": "all", "key": "unit", "line": f"Document unit {cur_name_ or 'not stated'} -> {new_u_}",
                                                         "old": um_, "new": UNITS_[new_u_], "user": USER["username"], "ts": now_, "reason": why_u_.strip()})
                try:
                    DB.add_figure_changes(ss.case_uid, ss.company, USER["username"],
                                          [{"year": "all", "key": "unit", "line": f"Document unit -> {new_u_}", "old": um_, "new": UNITS_[new_u_]}],
                                          why_u_.strip())
                except Exception as e_:  # noqa: BLE001
                    st.warning(f"Unit applied; central audit log not written: {e_}")
                ss.ed_v = ss.get("ed_v", 0) + 1
                st.rerun()
        df = ext_to_df(ss.ext)
        stmt = st.radio("Show", ["Balance Sheet", "Profit & Loss", "Cash Flow", "Disclosures", "All"], horizontal=True)
        view = df if stmt == "All" else df[df["Statement"] == stmt]
        edited = st.data_editor(view, hide_index=True, use_container_width=True, height=min(38 * (len(view) + 1), 900),
                                disabled=["key", "Statement", "Section", "Particulars"],
                                column_config={"key": None, "Statement": None,
                                               **{y: st.column_config.NumberColumn(y, format="%.2f") for y in ss.ext["years"]}},
                                key=f"ed_{stmt}_{ss.get('ed_v', 0)}")
        yrs_ = ss.ext["years"]
        if not edited[yrs_].equals(view[yrs_]):
            # every change needs a reason and goes into the audit trail before it touches the analysis
            chg_ = []
            for ix_ in edited.index:
                for y_ in yrs_:
                    o_, n_ = view.at[ix_, y_], edited.at[ix_, y_]
                    o_ = None if pd.isna(o_) else float(o_)
                    n_ = None if pd.isna(n_) else float(n_)
                    if o_ != n_:
                        chg_.append({"year": y_, "key": view.at[ix_, "key"], "line": view.at[ix_, "Particulars"], "old": o_, "new": n_})
            st.markdown(f"**{len(chg_)} change(s) not yet applied**")
            st.dataframe(pd.DataFrame([{"Line": c_["line"], "Year": c_["year"], "Was": c_["old"], "Now": c_["new"]} for c_ in chg_]),
                         hide_index=True, use_container_width=True)
            why_ = st.text_input("Reason (required - e.g. 'per audited balance sheet p.42, OCR misread 1,35O as 135')", key=f"why_{ss.get('ed_v', 0)}")
            ca_, cb_ = st.columns([1, 1])
            if ca_.button("Apply changes", type="primary", disabled=not why_.strip(), use_container_width=True):
                df.loc[edited.index, yrs_] = edited[yrs_].astype("float64")
                ss.ext["data"] = df_to_ext(df, ss.ext["years"])
                now_ = dt.datetime.now().isoformat(timespec="seconds")
                ss.ext.setdefault("changes", []).extend({**c_, "user": USER["username"], "ts": now_, "reason": why_.strip()} for c_ in chg_)
                for c_ in chg_:  # a figure the officer entered is no longer 'derived'; its provenance becomes the officer's entry
                    ((ss.ext.get("derived") or {}).get(c_["year"]) or {}).pop(c_["key"], None)
                    ss.ext.setdefault("provenance", {}).setdefault(c_["year"], {})[c_["key"]] = [
                        {"token": "" if c_["new"] is None else str(c_["new"]), "kind": "entered by officer" if c_["new"] is not None else "cleared by officer",
                         "page": None, "label": why_.strip()[:60]}]
                for y_, dk_ in (ss.ext.get("derived") or {}).items():  # rebuild derived totals from the corrected lines
                    if y_ in ss.ext["data"] and dk_:
                        for k_ in list(dk_):
                            ss.ext["data"][y_][k_] = None
                        dk_.clear()
                        schema.fill_derived(ss.ext["data"][y_], dk_)
                DB.add_figure_changes(ss.case_uid, ss.company, USER["username"], chg_, why_.strip())
                ss.ed_v = ss.get("ed_v", 0) + 1
                st.rerun()
            if cb_.button("Discard", use_container_width=True):
                ss.ed_v = ss.get("ed_v", 0) + 1
                st.rerun()
        odd_ = [{"Line": schema.LABELS.get(k_, k_), "Year": y_, "Printed": e_.get("token"), "Read as": e_.get("kind"), "Page": e_.get("page")}
                for y_, pk_ in ((ss.ext or {}).get("provenance") or {}).items() for k_, lst_ in (pk_ or {}).items() for e_ in (lst_ or [])
                if e_.get("kind") not in ("value", "AI reading", "entered by officer")]
        if odd_:
            with st.expander(f"How {len(odd_)} cell(s) were read - dashes, zeros, unreadable or repaired figures (confirm against the PDF)",
                             expanded=any(str(o_["Read as"]).startswith(("UNRESOLVED", "unreadable")) for o_ in odd_)):
                st.dataframe(pd.DataFrame(odd_), hide_index=True, use_container_width=True)
        unres_ = [(y_, k_) for y_, pk_ in ((ss.ext or {}).get("provenance") or {}).items() for k_, lst_ in (pk_ or {}).items()
                  if any(str(e_.get("kind", "")).startswith("UNRESOLVED") for e_ in (lst_ or [])) and ss.ext["data"].get(y_, {}).get(k_) is None]
        if unres_:
            st.warning(f"**{len(unres_)} cell(s) show '-' or nothing in the document**: "
                       + ", ".join(f"{schema.LABELS.get(k_, k_)} {y_}" for y_, k_ in unres_[:10])
                       + ". If you have checked the PDF and they are nil, confirm them here - they are then used as 0 (recorded in the audit trail).")
            nc1_, nc2_ = st.columns([3, 1])
            why_n_ = nc1_.text_input("Reason (required)", key=f"nil_why_{ss.get('ed_v', 0)}", placeholder="e.g. 'checked p.12: Grant income FY2020 printed as -'")
            if nc2_.button("Confirm as nil (0)", disabled=not why_n_.strip(), use_container_width=True, key="nil_ok"):
                now_ = dt.datetime.now().isoformat(timespec="seconds")
                rows_n_ = [{"year": y_, "key": k_, "line": schema.LABELS.get(k_, k_), "old": None, "new": 0.0} for y_, k_ in unres_]
                for y_, k_ in unres_:
                    ss.ext["data"][y_][k_] = 0.0
                    ss.ext.setdefault("provenance", {}).setdefault(y_, {})[k_] = [{"token": "-", "kind": "confirmed nil by officer",
                                                                                     "page": None, "label": why_n_.strip()[:60]}]
                ss.ext.setdefault("changes", []).extend({**r_, "user": USER["username"], "ts": now_, "reason": why_n_.strip()} for r_ in rows_n_)
                try:
                    DB.add_figure_changes(ss.case_uid, ss.company, USER["username"], rows_n_, why_n_.strip())
                except Exception as e_:  # noqa: BLE001
                    st.warning(f"Confirmed; central audit log not written: {e_}")
                for y_ in {y_ for y_, _k in unres_}:  # rebuild derived totals with the confirmed lines
                    dk_ = (ss.ext.setdefault("derived", {})).setdefault(y_, {})
                    for k_ in list(dk_):
                        ss.ext["data"][y_][k_] = None
                    dk_.clear()
                    schema.fill_derived(ss.ext["data"][y_], dk_)
                ss.ed_v = ss.get("ed_v", 0) + 1
                st.rerun()
        der_ = [(y_, k_, h_) for y_, dk_ in ((ss.ext or {}).get("derived") or {}).items() for k_, h_ in (dk_ or {}).items()]
        if der_:
            st.warning("**Derived, not read from the document** - confirm these against the PDF (the checker cannot verify a tie-out "
                       "built on them):\n\n" + "\n".join(f"- {schema.LABELS.get(k_, k_)} {y_}: {h_}" for y_, k_, h_ in der_[:12]))
        if (ss.ext or {}).get("changes"):
            with st.expander(f"Audit trail - {len(ss.ext['changes'])} figure change(s) on this case"):
                st.dataframe(pd.DataFrame([{"When": c_["ts"].replace("T", " "), "By": c_["user"], "Line": c_["line"], "Year": c_["year"],
                                            "Was": c_["old"], "Now": c_["new"], "Reason": c_["reason"]} for c_ in ss.ext["changes"]]),
                             hide_index=True, use_container_width=True)
                st.caption("Kept with the case, in the central database and in Annexure D of the memorandum. Entries are never edited or removed.")
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
        u_info = bundle.get("udin") if bundle else ss.get("udin_info")
        if (ss.notes and ss.notes.get("available")) or u_info:
            with st.expander("Auditor's report, CA Signatures & ICAI UDIN Check"):
                if u_info:
                    stat = u_info.get("status", "UNASSESSED")
                    stat_color = "green" if stat == "VALID" else ("orange" if stat == "MISSING_MANDATORY" else "red")
                    st.markdown(f"**ICAI UDIN Status:** :{stat_color}[{stat}]")
                    st.info(u_info.get("message"))
                    st.markdown(f"🔗 [Verify on Official ICAI UDIN Portal]({u_info.get('portal_url', 'https://udin.icai.org/search-udin')})")
                    if u_info.get("ca_signatures"):
                        st.caption("Extracted Auditor Signatures:")
                        for sig in u_info["ca_signatures"]:
                            st.write(f"- **{sig.get('ca_name') or 'CA'}** · M.No: `{sig.get('membership_no')}` · Firm: {sig.get('firm_name') or '-'} (FRN: `{sig.get('frn') or '-'}`)")
                if ss.notes and ss.notes.get("available"):
                    n = ss.notes
                    st.write(f"**Opinion:** {(n.get('auditor_opinion') or '-').title()}  ·  **Auditor:** {n.get('auditor_name') or '-'}  ·  "
                             f"**Going-concern doubt:** {'Yes' if n.get('going_concern_uncertainty') else 'No'}  ·  method: {n.get('method', 'AI')}")
                    for f in n.get("red_flags") or []:
                        st.markdown(f"{SEV_ICON.get(f.get('severity'), '⚪')} **{f.get('title')}** - {f.get('evidence', '')[:400]} {'(p.' + str(f['page']) + ')' if f.get('page') else ''}")

# ================================================================== DASHBOARD
if PAGE == "dash":
    if not bundle:
        need_data()
    else:
        import copy as _copy
        import html as _html
        y = bundle["years"]
        y0 = y[0]
        fz = bundle["forensics"]
        # live checks on the current figures (a stored log would be stale after a spread edit)
        dnarr_, dchk_ = CK.run(bundle, _copy.deepcopy(ss.narr) if ss.narr else pipeline.write_narrative(bundle))
        ig_ = bundle.get("integrity") or {}
        cnt_ = DSH.check_counts(dchk_)
        items_ = DSH.open_items(bundle, dchk_, dnarr_)
        esc = _html.escape
        STAT = {"READY": ("●", "Ready for decision", GOOD), "READY_WITH_WARNINGS": ("▲", "Ready with warnings", "#B26B00"),
                "BLOCKED": ("■", "Blocked", CRIT)}
        sym_, slab_, scol_ = STAT.get(ig_.get("status"), ("▲", "Not checked", "#B26B00"))
        nsev_ = {s_: sum(1 for f_ in fz["flags"] if f_["severity"] == s_) for s_ in ("High", "Medium", "Low")}
        nopen_ = sum(1 for f_ in fz["flags"] if (f_.get("status") or "Open") == "Open")
        grade_ = str(fz.get("grade") or "")
        gcode_, gdesc_ = (grade_.split(" - ", 1) + [""])[:2]
        rec_ = (dnarr_ or {}).get("recommendation") or "-"
        st.markdown(
            f"<div class='dcrumb'>{esc(bundle['company'])} · {esc(str(bundle.get('statement_type') or ss.statement_type or ''))} statements · "
            f"{' / '.join(reversed(y))} · ₹ crore unless stated</div>"
            "<div class='dband'>"
            f"<div class='dcell dmain'><div class='dl'>Case status</div><div class='dv' style='color:{scol_}'>{sym_} {slab_}</div>"
            f"<div class='ds'>{esc(ig_.get('detail') or '')}</div></div>"
            f"<div class='dcell'><div class='dl'>Recommendation</div><div class='dv dsm'>{esc(rec_)}</div>"
            f"<div class='ds'>{'AI draft checked by the rules' if (ss.narr or {}).get('_source') == 'AI' else 'rule-based'}</div></div>"
            f"<div class='dcell'><div class='dl'>Internal rating</div><div class='dv'>{esc(gcode_)}</div>"
            f"<div class='ds'>{'<b>Provisional</b> - the figures failed checks · ' if ig_.get('status') == 'BLOCKED' else ''}"
            f"{esc(gdesc_[:70])} · score {FZ.score_text(fz)}</div></div>"
            f"<div class='dcell'><div class='dl'>Red flags</div><div class='dv'>{len(fz['flags'])}</div>"
            f"<div class='ds'>{nsev_['High']} high · {nsev_['Medium']} medium · {nsev_['Low']} low · {nopen_} without disposition</div></div>"
            f"<div class='dcell'><div class='dl'>Checks</div><div class='dv'>{cnt_['FAIL']} failed</div>"
            f"<div class='ds'>{cnt_['WARN']} warnings · {cnt_['PASS']} passed</div></div>"
            "</div>", unsafe_allow_html=True)

        left_, right_ = st.columns([1.65, 1], gap="large")
        with left_:
            cols_, mrows_ = DSH.metric_rows(bundle)
            head_ = "".join(f"<th class='n'>{esc(c_)}</th>" for c_ in cols_)
            body_, grp_ = "", None
            AMARK = {"Within norm": ("●", GOOD), "Watch": ("▲", "#B26B00"), "Outside norm": ("■", CRIT)}
            for m_ in mrows_:
                if m_["group"] != grp_:
                    grp_ = m_["group"]
                    body_ += f"<tr class='g'><td colspan='{len(cols_) + 4}'>{esc(grp_)}</td></tr>"
                cells_ = ""
                for v_ in m_["values"]:
                    if v_["raw"] is None:
                        cells_ += f"<td class='n na'>n.a.<div class='why'>{esc(v_['note'])}</div></td>"
                    else:
                        neg_ = " neg" if v_["raw"] < 0 else ""
                        cells_ += f"<td class='n{neg_}'>{esc(v_['text'])}</td>"
                mk_, mc_ = AMARK.get(m_["assess"], ("", ""))
                assess_ = f"<span style='color:{mc_}'>{mk_}</span> {esc(m_['assess'])}" if m_["assess"] else ""
                body_ += (f"<tr><td>{esc(m_['label'])}{' <span class=u>₹ Cr</span>' if m_['src'] == 'd' else ''}</td>{cells_}"
                          f"<td class='n mut'>{esc(m_['change'])}</td><td class='n mut'>{esc(m_['norm'])}</td><td>{assess_}</td></tr>")
            st.markdown("<div class='dsec'>Key figures</div>"
                        f"<table class='dtab'><thead><tr><th>Measure</th>{head_}<th class='n'>Change</th><th class='n'>Norm</th><th>Latest year</th></tr></thead>"
                        f"<tbody>{body_}</tbody></table>"
                        "<div class='dnote'>Norms are the generic bank benchmarks in the ratio engine - replace with the bank's sector norms in "
                        "Admin › Bank parameters. n.a. cells say why the figure is missing; nothing is filled with zero.</div>",
                        unsafe_allow_html=True)
        with right_:
            nblk_ = sum(1 for i_ in items_ if i_["level"] == "block")
            st.markdown(f"<div class='dsec'>Before a decision <span class='cnt'>{len(items_)} open"
                        + (f" · {nblk_} blocking" if nblk_ else "") + "</span></div>", unsafe_allow_html=True)
            LV = {"block": ("■", CRIT, "Blocking"), "warn": ("▲", "#B26B00", "Resolve or explain"), "todo": ("○", "#6B6259", "Your input")}
            if not items_:
                st.markdown("<div class='doi'><b>Nothing open.</b> Every check passed and every input is in.</div>", unsafe_allow_html=True)
            for i_, it_ in enumerate(items_[:9]):
                mk_, mc_, ml_ = LV[it_["level"]]
                a_, b_ = st.columns([2.6, 1.4], vertical_alignment="center")
                det_ = it_["detail"] if len(it_["detail"]) <= 130 else it_["detail"][:127].rsplit(" ", 1)[0] + " ..."
                a_.markdown(f"<div class='doi'><div class='t'><span style='color:{mc_}'>{mk_}</span> {esc(DSH.short_title(it_['title']))}"
                            + (f" <span class='lv' style='color:{mc_}'>{ml_}</span>" if it_["level"] == "block" else "")
                            + f"</div><div class='d'>{esc(det_)}</div></div>", unsafe_allow_html=True)
                b_.button(DSH.PAGE_SHORT.get(it_["page"], "Open") + " →", key=f"dgo_{i_}", on_click=_go, args=(it_["page"],),
                          use_container_width=True, help=f"Open {PAGE_TITLES[it_['page']]}")
            if len(items_) > 9:
                st.caption(f"{len(items_) - 9} more in the verification log (Report centre).")

        # ---- charts: one measure family per chart, single axis, norms drawn as reference lines
        cy_ = list(reversed(y))
        S1, S2 = "#2a78d6", "#eb6834"

        def _ref(fig_, v_, txt_):
            # norm line labelled at the left edge (clear of the bar value labels), with headroom above the tallest bar
            fig_.add_hline(y=v_, line=dict(color="#8A817A", width=1.5, dash="dash"),
                           annotation=dict(text=txt_, font=dict(size=11, color="#57504A"), xanchor="left", x=0, yanchor="bottom",
                                           bgcolor="rgba(255,255,255,.85)"))
            vals_ = [v for tr_ in fig_.data for v in (tr_.y or []) if v is not None] + [v_]
            fig_.update_yaxes(range=[min(0, min(vals_)) * 1.15, max(vals_) * 1.22])

        def _gaps(keys_, src_="d"):
            out_ = []
            for k_, lab_ in keys_:
                for yy_ in cy_:
                    v_ = bundle["data"][yy_].get(k_) if src_ == "d" else bundle["ratios"][yy_].get(k_)
                    if v_ is None:
                        out_.append(f"{lab_} {yy_}: {DSH.na_reason(bundle, k_, yy_, src_)}")
            return out_

        c1_, c2_, c3_ = st.columns(3, gap="medium")
        with c1_:
            fig = go.Figure()
            fig.add_bar(x=cy_, y=[bundle["data"][yy_].get("pat") for yy_ in cy_], name="Profit after tax", marker_color=S1,
                        hovertemplate="PAT %{y:,.1f} Cr<extra></extra>")
            fig.add_bar(x=cy_, y=[bundle["data"][yy_].get("cfo") for yy_ in cy_], name="Cash from operations", marker_color=S2,
                        hovertemplate="CFO %{y:,.1f} Cr<extra></extra>")
            fig.update_layout(hovermode="closest")
            st.plotly_chart(chart_layout(fig, "Do profits turn into cash? (₹ Cr)", h=300), use_container_width=True)
            g_ = _gaps([("pat", "PAT"), ("cfo", "CFO")])
            if g_:
                st.caption("Not shown - " + "; ".join(g_))
        with c2_:
            fig = go.Figure()
            fig.add_bar(x=cy_, y=[bundle["ratios"][yy_].get("tol_tnw") for yy_ in cy_], name="TOL / TNW", marker_color=S1,
                        hovertemplate="TOL/TNW %{y:.2f}x<extra></extra>")
            fig.add_bar(x=cy_, y=[bundle["ratios"][yy_].get("debt_ebitda") for yy_ in cy_], name="Debt / EBITDA", marker_color=S2,
                        hovertemplate="Debt/EBITDA %{y:.2f}x<extra></extra>")
            _ref(fig, 3.0, "norm ≤ 3.0x (both)")
            fig.update_layout(hovermode="closest")
            st.plotly_chart(chart_layout(fig, "Leverage (x)", h=300, yfmt=".2f"), use_container_width=True)
            g_ = _gaps([("tol_tnw", "TOL/TNW"), ("debt_ebitda", "Debt/EBITDA")], "r")
            if g_:
                st.caption("Not shown - " + "; ".join(g_))
        with c3_:
            prow_, pa_ = CT.projections(bundle, CT.proposal(bundle))
            if pa_.get("status") == "NOT COMPUTED" or not prow_:
                st.markdown("<div class='dempty'><div class='dl'>Projected DSCR</div><b>Not computed</b><div class='ds'>"
                            f"{esc(str(pa_.get('reason') or 'no projection'))}. Enter the growth rate or the missing lines; "
                            "no default growth is assumed.</div></div>", unsafe_allow_html=True)
                st.button("Open Proposal & what-if", key="dgo_prop", on_click=_go, args=("proposal",))
            else:
                ds_ = [r_["dscr"] for r_ in prow_]
                if all(v_ is None for v_ in ds_):
                    st.markdown("<div class='dempty'><div class='dl'>Projected DSCR</div><b>No term debt to service</b><div class='ds'>"
                                "No existing or proposed term loan, so DSCR does not apply. Enter the facility on Proposal & what-if."
                                "</div></div>", unsafe_allow_html=True)
                else:
                    psm_ = CT.dscr_summary(prow_)
                    fig = go.Figure()
                    fig.add_bar(x=[r_["year"] for r_ in prow_], y=ds_, name="DSCR", marker_color=S1, hovertemplate="DSCR %{y:.2f}x<extra></extra>")
                    _ref(fig, 1.10, "minimum 1.10x")
                    fig.update_layout(hovermode="closest", showlegend=False)
                    st.plotly_chart(chart_layout(fig, f"Projected DSCR (x) · average {psm_['avg']:.2f}x" if psm_.get("avg") else "Projected DSCR (x)",
                                                 h=300, yfmt=".2f"), use_container_width=True)
                    nd_ = [r_["year"] for r_ in prow_ if r_["dscr"] is None]
                    if nd_:
                        st.caption(f"{', '.join(nd_)}: no term-loan repayment due, so DSCR does not apply.")
                    if pa_.get("approximations"):
                        st.caption("Uses defaults not yet reviewed: " + ", ".join(pa_["approximations"]) + " - see the assumption register.")

        # ---- risk and data quality
        r1_, r2_ = st.columns([1.65, 1], gap="large")
        with r1_:
            st.markdown("<div class='dsec'>Red flags <span class='cnt'>most severe first</span></div>", unsafe_allow_html=True)
            SV = {"High": ("■", CRIT), "Medium": ("▲", "#B26B00"), "Low": ("○", "#6B6259")}
            fl_ = sorted(fz["flags"], key=lambda f_: {"High": 0, "Medium": 1, "Low": 2}.get(f_["severity"], 3))
            if not fl_:
                st.markdown("<div class='doi'>No red flags were raised by the tests that could run - see the not-assessed tests on the right.</div>",
                            unsafe_allow_html=True)
            rows_ = ""
            for f_ in fl_[:6]:
                mk_, mc_ = SV.get(f_["severity"], ("", ""))
                rows_ += (f"<tr><td style='white-space:nowrap'><span style='color:{mc_}'>{mk_}</span> {f_['severity']}</td>"
                          f"<td><b>{esc(f_['title'])}</b><div class='ev'>{esc(str(f_.get('evidence') or '')[:160])}</div></td>"
                          f"<td class='mut'>{esc(f_.get('status') or 'Open')}</td></tr>")
            if rows_:
                st.markdown(f"<table class='dtab'><thead><tr><th>Severity</th><th>Observation</th><th>Your disposition</th></tr></thead>"
                            f"<tbody>{rows_}</tbody></table>", unsafe_allow_html=True)
            if len(fl_) > 6:
                st.button(f"All {len(fl_)} flags - Forensic & hidden items", key="dgo_fz", on_click=_go, args=("forensic",))
        with r2_:
            st.markdown("<div class='dsec'>Data quality</div>", unsafe_allow_html=True)
            res_ = {c_["check"]: c_ for c_ in dchk_}

            def _q(check_, label_):
                c_ = res_.get(check_)
                if not c_:
                    return ""
                mk_, mc_ = {"PASS": ("●", GOOD), "WARN": ("▲", "#B26B00"), "FAIL": ("■", CRIT)}[c_["result"]]
                return (f"<tr><td><span style='color:{mc_}'>{mk_}</span> {esc(label_)}</td>"
                        f"<td class='mut'>{esc((c_['detail'] or {'PASS': 'ok'}.get(c_['result'], ''))[:110])}</td></tr>")

            mods_ = fz.get("models") or {}
            modtxt_ = ", ".join(f"{k_.split(' ')[0]} {v_['status'].lower()}" for k_, v_ in mods_.items())
            q_ = (_q("Figures confirmed by a second, independent reading", "Second reading")
                  + _q("Size plausible for the unit read (rupees / thousands / lakhs / crore)", "Unit")
                  + _q(f"Balance sheet tallies - {y0}", "Balance sheet tallies")
                  + _q("Audit opinion read from the auditor's report itself", "Audit opinion")
                  + _q("Latest statements are recent", "Statement date")
                  + _q("Every forensic test had the figures it needs", "Forensic coverage")
                  + _q("Borrowings consistent with finance cost", "Borrowings captured")
                  + (f"<tr><td><span style='color:{GOOD if all(v_['status'] == 'CALCULATED' for v_ in mods_.values()) else '#B26B00'}'>"
                     f"{'●' if all(v_['status'] == 'CALCULATED' for v_ in mods_.values()) else '▲'}</span> Statistical models</td>"
                     f"<td class='mut'>{esc(modtxt_)}</td></tr>" if mods_ else ""))
            st.markdown(f"<table class='dtab dq'><tbody>{q_}</tbody></table>", unsafe_allow_html=True)

        with st.expander("Detailed analysis - sector comparison, line-item swings, horizontal and vertical analysis, fund flow"):
            sec_ = (ss.case or {}).get("sector")
            comp_ = AN.sector_comparison(bundle, sec_) if sec_ and sec_ != "-" else None
            an_ = AN.anomalies(bundle)
            cA_, cB_ = st.columns(2)
            with cA_:
                st.markdown("**Sector comparison**" + (f" - {sec_}" if comp_ else ""))
                if comp_:
                    st.dataframe(pd.DataFrame(comp_, columns=["Measure", "Company", "Sector norm", "Position"]), hide_index=True, use_container_width=True)
                else:
                    st.caption("No approved norms for this sector yet - pick the sector on the desk; the admin enters norms in Admin › Bank parameters.")
            with cB_:
                st.markdown("**Line-item swings**")
                if an_:
                    st.dataframe(pd.DataFrame(an_, columns=["Line item", "Prior", "Latest", "Change", "Materiality"]), hide_index=True, use_container_width=True)
                else:
                    st.caption("No material line-item swings (>50% and >2% of assets/revenue).")
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
if PAGE == "ratios":
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
if PAGE == "forensic":
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
        if fz.get("not_assessed"):
            st.warning(f"{len(fz['not_assessed'])} forensic test(s) NOT ASSESSED - the figures they need were not read, so no flag here "
                       "is not a clean result. Enter the missing lines on Spread review.")
            st.dataframe(pd.DataFrame([[t["test"], ", ".join(t["missing"])] for t in fz["not_assessed"]], columns=["Test", "Inputs not read"]),
                         hide_index=True, use_container_width=True)
        if fz.get("models"):
            st.markdown("**Statistical models** - indicators of risk, not proof")
            st.dataframe(pd.DataFrame([[m_, v_["status"], (v_.get("note") or "") + (": " + ", ".join(v_["missing"]) if v_.get("missing") else "")]
                                       for m_, v_ in fz["models"].items()], columns=["Model", "Status", "Note"]), hide_index=True, use_container_width=True)
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
if PAGE == "market":
    if not ss.company and bundle_hdr:
        ss.company = bundle_hdr.get("company") or ""
    a0, b0 = st.columns([2, 1])
    ss.company = a0.text_input("Company to research", value=ss.company or "", placeholder="Name as on the annual report")
    ss.aliases = b0.text_input("Other names / brand / ticker", value=ss.aliases or "")
    if not ss.company:
        st.info("Enter the company name (or run an analysis - the name is read from the annual report).")
    else:
        a, b, c3 = st.columns([1, 1.4, 1.4])
        days_t = a.selectbox("Look-back", [90, 180, 365, 730], index=2, format_func=lambda x: f"{x} days", key="news_days")
        use_ws = b.checkbox("Add web search (OpenRouter, ≈₹0.10-0.50)", value=bool(k_or), disabled=not k_or,
                            help="Parallel 'fast' search engine via OpenRouter - USD 0.001 per search plus model tokens. Finds rating actions, "
                                 "litigation and filings that Google News misses.")
        if c3.button("🌐 Run market intelligence", type="primary", use_container_width=True):
            with st.status("Researching the company ...", expanded=True) as stt:
                try:
                    process_news(days_t, st.write)
                except Exception as e:
                    st.warning(f"Google News failed: {e}")
                if use_ws:
                    try:
                        process_web_news(st.write)
                    except Exception as e:
                        st.warning(f"Web search failed: {e}")
                stt.update(label=f"Done - {len(ss.news or [])} items", state="complete")
            st.rerun()
        cr_ = (ss.brief or {}).get("credit_rating")
        if cr_:
            st.success(f"Credit rating found: **{cr_.get('agency')} {cr_.get('rating')}** {cr_.get('outlook') or ''} {('(' + cr_['date'] + ')') if cr_.get('date') else ''}"
                       + (f" - [source]({cr_['url']})" if cr_.get("url") else ""))
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
            if (ss.brief or {}).get("web_sources"):
                with st.expander(f"Web sources used ({len(ss.brief['web_sources'])})"):
                    for c_ in ss.brief["web_sources"]:
                        st.markdown(f"- [{c_.get('title')}]({c_.get('url')})")
        else:
            st.caption("No news pulled yet - click 'Run market intelligence'.")

# ================================================================== BRSR & PCAF
if PAGE == "brsr":
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
        wl = web_search_client("brsr_web")
        c1_, c2_ = st.columns([2, 1])
        c1_.caption("Pull market cap, reported Scope 1/2/3 (BRSR) and sector from the internet, then calculate.")
        if c2_.button("🌐 Fetch from web", type="primary", use_container_width=True, disabled=not (wl and (ss.company or bundle_hdr)),
                      help="Needs the OpenRouter key (web search, Parallel engine). Costs about ₹0.10-0.50 per fetch."):
            with st.spinner("Searching the web (BRSR, annual report, NSE/BSE) ..."):
                try:
                    ss.web_pcaf = VF.verify_web_pcaf(WF.fetch_pcaf_inputs(wl, clean_company() or bundle_hdr.get("company"), ss.cin),
                                                     clean_company() or bundle_hdr.get("company"), ss.cin)
                    DB.log(USER["username"], "web_fetch_pcaf", ss.company)
                except Exception as e:
                    st.error(f"Web fetch failed: {e}")
        if not wl:
            st.caption("Add the OpenRouter key in ⚙ Settings to enable web fetch.")
        w = ss.web_pcaf or {}
        if w:
            filed = w.get("brsr_filed")
            (st.success if filed else st.warning)(
                ("✅ BRSR filed" if filed else "⚠ No BRSR found on the web") + (f" - years: {', '.join(w.get('brsr_years_filed') or [])}" if w.get("brsr_years_filed") else "")
                + (f" · applicability: {w.get('brsr_applicable')}" if w.get("brsr_applicable") else "")
                + (f" · [latest BRSR]({w['brsr_latest_url']})" if w.get("brsr_latest_url") else ""))
            wt = pd.DataFrame([
                ["Market capitalisation (₹ Cr)", w.get("market_cap_inr_cr"), w.get("market_cap_date")],
                ["Scope 1 (tCO2e)", w.get("scope1_tco2e"), w.get("financial_year")],
                ["Scope 2 (tCO2e)", w.get("scope2_tco2e"), w.get("financial_year")],
                ["Scope 3 (tCO2e)", w.get("scope3_tco2e"), w.get("financial_year")],
                ["Emissions declared?", "Yes" if w.get("emissions_declared") else "No", w.get("ghg_assurance")],
                ["Sector", w.get("sector"), w.get("nic_or_industry")],
                ["Listed", "Yes" if w.get("listed") else "No", w.get("exchange_symbol")],
                ["BRSR Core assured", {True: "Yes", False: "No"}.get(w.get("brsr_core_assured"), "n.a."), ""],
                ["Energy (GJ) / renewable share", w.get("energy_gj"), w.get("renewable_share_pct")],
                ["Water (kL)", w.get("water_kl"), ""], ["Net-zero target", w.get("net_zero_target"), ""],
            ], columns=["Field (from web)", "Value", "As of / detail"]).astype(str)
            st.dataframe(wt, hide_index=True, use_container_width=True)
            if w.get("_verification"):
                st.markdown("**Source check** - a web figure is used only if it is printed on a page that names the company")
                st.dataframe(pd.DataFrame([[k_.replace("_", " "), str(v_.get("value")), v_.get("status"), v_.get("url") or "-"]
                                           for k_, v_ in w["_verification"].items()], columns=["Field", "AI said", "Check", "Page"]),
                             hide_index=True, use_container_width=True)
            for c_ in (w.get("_citations") or [])[:8]:
                w.setdefault("sources", []).append({"field": "web", "url": c_.get("url"), "note": c_.get("title")})
            if w.get("sources"):
                with st.expander(f"Sources ({len(w['sources'])}) - verify before use"):
                    for src in w["sources"]:
                        st.markdown(f"- **{src.get('field', '')}**: [{src.get('url', '')}]({src.get('url', '')}) {src.get('note', '')}")
        br = dict(ss.brsr or {})
        for kk_ in ("scope1_tco2e", "scope2_tco2e", "scope3_tco2e"):
            if br.get(kk_) is None and w.get(kk_) is not None:  # a reported 0 is kept, never replaced
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
            # blank = not reported / not known; 0 = reported as zero. The two are never merged.
            _kn = lambda *v_: next((float(x_) for x_ in v_ if x_ is not None and x_ != ""), None)
            mc = st.number_input("Market capitalisation (INR Cr, listed only - blank if not known)", 0.0, 1e8, _kn(prev.get("market_cap")), 10.0)
            s1 = st.number_input("Scope 1 (tCO2e - blank if not reported)", 0.0, 1e10, _kn(prev.get("scope1"), br.get("scope1_tco2e")))
            s2 = st.number_input("Scope 2 (tCO2e - blank if not reported)", 0.0, 1e10, _kn(prev.get("scope2"), br.get("scope2_tco2e")))
            s3 = st.number_input("Scope 3 (tCO2e, optional - blank if not reported)", 0.0, 1e11, _kn(prev.get("scope3"), br.get("scope3_tco2e")))
            ver = st.checkbox("GHG data is third-party assured", value=bool(prev.get("verified", br.get("ghg_assurance") in ("reasonable", "limited"))))
            names = [f["sector"] for f in factors]
            _ws = (w.get("sector") or "").lower()
            _guess = next((n_ for n_ in names if _ws and (n_.lower().split(" ")[0] in _ws or _ws.split(" ")[0] in n_.lower())), None)
            sec_i = names.index(prev.get("sector_name")) if prev.get("sector_name") in names else (names.index(_guess) if _guess else 0)
            sec = st.selectbox("Sector (fallback when no reported emissions)", names, index=sec_i)
            _appr = next((f["tco2e_per_inr_cr_revenue"] for f in factors if f["sector"] == sec and f.get("approved")), None)
            ef = st.number_input("Sector emission factor (tCO2e / INR Cr revenue - blank if none approved)", 0.0, 1e5, _kn(prev.get("sector_ef"), _appr))
            st.caption("Only bank-approved factors (Admin › Bank parameters) are pre-filled; enter a sourced factor here otherwise. "
                       "Reported Scope 1 & 2 always take precedence.")
            if st.form_submit_button("Calculate", type="primary"):
                ss.pcaf_in = dict(outstanding_cr=out_cr, asset_class=ac, market_cap=mc or None, scope1=s1, scope2=s2,
                                  scope3=s3, verified=ver, sector_ef=ef or None, sector_name=sec)
                st.rerun()
        if bundle and bundle.get("pcaf"):
            p = bundle["pcaf"]
            k = st.columns(3)
            kpi(k[0], "Attribution factor", "n.a." if p["attribution_factor"] is None else f"{p['attribution_factor']:.3%}", p["denominator_name"])
            kpi(k[1], "Financed Scope 1+2", "n.a." if p["financed_scope12"] is None else f"{p['financed_scope12']:,.0f} t", "tCO2e")
            kpi(k[2], "PCAF data quality", p["data_quality_score"] if p["data_quality_score"] is not None else "n.a.", "1 best · 5 worst")
            st.caption(f"Method: {p['method']}" + (f" · ⚠ {p['warning']}" if p.get("warning") else ""))
        elif not bundle:
            st.caption("Extract financials first - the denominator uses the balance sheet.")

# ================================================================== REPORTS & COMMENTS
if PAGE == "reports":
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
            chk_ = ss.get("checks") or []
            ig_ = ss.get("integrity") or {}
            if ig_:
                msg_ = f"**Case status: {ig_['status'].replace('_', ' ')}** - {ig_.get('detail', '')}"
                if ig_["status"] == "BLOCKED":
                    st.error(msg_ + " · no credit recommendation may be acted on.")
                elif ig_["status"] == "READY_WITH_WARNINGS":
                    st.warning(msg_)
                else:
                    st.success(msg_)
            if chk_:
                nf_ = sum(1 for c_ in chk_ if c_["result"] == "FAIL")
                nw_ = sum(1 for c_ in chk_ if c_["result"] == "WARN")
                (st.error if nf_ else st.warning if nw_ else st.success)(
                    f"Logic & source checks: {len(chk_) - nf_ - nw_} passed · {nw_} warning(s) · {nf_} failed"
                    + (" - the report is marked DRAFT until the failed checks are fixed." if nf_ else ""))
                with st.expander("Verification log (also Annexure D of the memorandum and the 'Checks' sheet of the workbook)", expanded=bool(nf_)):
                    st.dataframe(pd.DataFrame(chk_).rename(columns={"area": "Area", "check": "Check", "result": "Result", "detail": "Detail"}),
                                 hide_index=True, use_container_width=True)
                    rem_ = (ss.get("narr") or {}).get("_removed_sentences") or []
                    if rem_:
                        st.markdown("**AI sentences removed - their figures could not be traced to the statements**")
                        st.dataframe(pd.DataFrame(rem_), hide_index=True, use_container_width=True)
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
if PAGE == "ask":
    st.caption("Ask anything about the uploaded statements, notes and auditor's report. Answers cite page numbers - check them in Spread review › source page.")
    qa_llm = router.get("notes")
    if not ss.get("pages") and not k_or:
        st.info("Run an analysis first so the documents are loaded.")
    elif not qa_llm and not k_or:
        st.info("Add an AI key in ⚙ Settings to ask questions.")
    else:
        use_web_q = st.toggle("🌐 Also search the web (OpenRouter + Parallel search, ≈₹0.10 per question)", value=bool(k_or), disabled=not k_or)
        ss.setdefault("qa", [])
        for qa in ss.qa:
            st.chat_message("user").write(qa["q"])
            st.chat_message("assistant").write(qa["a"])
            if qa.get("cites"):
                st.caption("Web sources: " + " · ".join(f"[{c_['title'][:60]}]({c_['url']})" for c_ in qa["cites"][:8]))
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
            cites = []
            with st.spinner("Reading the documents" + (" and searching the web ..." if use_web_q else " ...")):
                try:
                    if use_web_q:
                        ans, cites = web_search_client("ask").chat(WS.ASK_SYS, f"Company: {clean_company()}\nQuestion: {q}\n\nDOCUMENT PAGES:\n=== "
                                                                   + "\n=== ".join(ranked)[:40000], max_tokens=1500)
                    else:
                        ans = qa_llm.chat("You answer questions about a company's financial documents for a bank credit officer. Answer only from the "
                                      "pages given, quote figures exactly, and cite pages as (document, p.N). If not found, say so. End with a line "
                                      "'Confidence: High / Medium / Low - <reason>' (Low when the pages only partly answer the question).",
                                          f"Question: {q}\n\nPAGES:\n=== " + "\n=== ".join(ranked)[:60000], max_tokens=1200)
                except Exception as e:
                    ans = f"Error: {e}"
            ss.qa.append({"q": q, "a": ans, "cites": cites})
            DB.log(USER["username"], "ask", q[:200])
            st.rerun()

# ================================================================== HISTORY
if PAGE == "history":
    _known = {os.path.normcase(os.path.abspath(r_.get("docx_path") or "")) for r_ in DB.cases()}
    _extra = []
    for root_, _, fs_ in os.walk(REPORTS):
        for f_ in fs_:
            fp_ = os.path.join(root_, f_)
            if f_.lower().endswith((".docx", ".xlsx")) and os.path.normcase(os.path.abspath(fp_)) not in _known:
                if IS_ADMIN or os.path.basename(root_) == USER["username"]:
                    _extra.append(fp_)
    if _extra:
        with st.expander(f"📁 {len(_extra)} other report file(s) on this PC (older runs, extra reports) - nothing is deleted"):
            for i_, fp_ in enumerate(sorted(_extra, key=os.path.getmtime, reverse=True)[:60]):
                c1_, c2_ = st.columns([4, 1])
                c1_.write(f"{os.path.relpath(fp_, REPORTS)} · {dt.datetime.fromtimestamp(os.path.getmtime(fp_)):%d-%b-%Y %H:%M}")
                with open(fp_, "rb") as fh_:
                    c2_.download_button("⬇", fh_.read(), os.path.basename(fp_), key=f"xf_{i_}")
    with st.expander("📂 Open one of my saved cases (stored on this PC)"):
        mydir = DB.officer_dir(USER["username"])
        files = sorted([f for f in os.listdir(mydir) if f.endswith(".json")], reverse=True)
        pick = st.selectbox("Saved case", ["-"] + files)
        if pick != "-" and st.button("Load case"):
            with open(os.path.join(mydir, pick), encoding="utf-8") as f:
                c = json.load(f)
            for k in CASE_KEYS:
                if k in c:
                    ss[k] = c.get(k)
            ss.screening = WL.drop_clearances(ss.get("screening"))
            ss._out = None
            ss.rt_out = None
            ss.page = "dash"
            st.rerun()
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
        if not DB.can_access(USER, row["username"]):
            st.error("This case belongs to another officer.")
            st.stop()
        c1, c2, c3 = st.columns(3)
        for col, key_, lbl, mime in [(c1, "docx_path", "⬇ Word report", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
                                     (c2, "xlsx_path", "⬇ Excel workbook", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]:
            p_ = row[key_]
            if p_ and not DB.can_access(USER, row["username"], p_, REPORTS):
                col.caption("File is outside the reports folder - not opened")
            elif p_ and os.path.exists(p_):
                with open(p_, "rb") as fh:
                    col.download_button(lbl, fh.read(), os.path.basename(p_), mime=mime, use_container_width=True, key=f"h_{key_}_{pick_id}")
            else:
                col.caption("File not found on this PC")
        if c3.button("Re-open this case", use_container_width=True) and row["case_json_path"] and os.path.exists(row["case_json_path"]) \
                and DB.can_access(USER, row["username"], row["case_json_path"], CASES):
            with open(row["case_json_path"], encoding="utf-8") as f:
                cj = json.load(f)
            for k_ in CASE_KEYS:
                if k_ in cj:
                    ss[k_] = cj.get(k_)
            ss.screening = WL.drop_clearances(ss.get("screening"))
            ss._out = None
            st.rerun()

# ================================================================== ADMIN
if IS_ADMIN:
    if PAGE == "admin":
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
        st.markdown("#### 📐 Bank parameters")
        st.caption("These tables drive benchmarks, emissions, default probabilities and AI cost. The shipped values are illustrative - replace them "
                   "with your bank's approved figures here. Every report shows which values were used.")
        for fname_, lbl_, why_ in [("sector_benchmarks.csv", "Sector norms (dashboard & memorandum sector comparison)", "Bank's sector-wise ratio norms"),
                                   ("emission_factors.csv", "PCAF emission factors (when the borrower has no reported emissions)", "PCAF database / bank-approved factors"),
                                   ("pd_scale.csv", "PD master scale by internal grade (pricing, expected loss, RAROC)", "Bank's validated rating model"),
                                   ("llm_prices.csv", "AI model prices in USD per million tokens (cost meter)", "Provider pricing pages")]:
            with st.expander(f"{lbl_} - data/{fname_}"):
                fp_ = os.path.join(HERE, "data", fname_)
                try:
                    df_ = pd.read_csv(fp_)
                except Exception:
                    df_ = pd.DataFrame()
                st.caption(f"Source to use: {why_}.")
                ed_ = st.data_editor(df_, num_rows="dynamic", use_container_width=True, key=f"bp_{fname_}")
                if st.button("Save", key=f"bp_save_{fname_}"):
                    ed_.to_csv(fp_, index=False)
                    DB.log(USER["username"], "parameters_saved", fname_)
                    st.success(f"Saved {fname_}")


# ================================================================== PROPOSAL & WHAT-IF
def _pct_in(col, label, key, val, lo=0.0, hi=30.0, step=0.05, help=None):
    return col.number_input(label, lo, hi, float(round(val * 100, 2)), step, key=key, help=help) / 100


if PAGE == "proposal":
    if not bundle:
        need_data()
    else:
        c = dict(ss.case or {})
        P0 = CT.proposal({**bundle, "proposal": {"facility": c.get("facility"), "amount": c.get("amount", 0), **(c.get("prop") or {})}})
        st.caption("Structure the facilities, then move the sliders - DSCR, scenarios, drawing power, security cover and pricing recalculate instantly. "
                   "Everything here flows into the memorandum, committee note, term sheet and the Excel 'Projections & DSCR' tab.")
        P = dict(P0)
        with card():
            st.markdown("**Facility structure**")
            a, b_, c_, d_ = st.columns(4)
            P["tl_amount"] = a.number_input("Term loan (₹ Cr)", 0.0, 1e6, float(P0["tl_amount"]), 1.0, key="pp_tl")
            P["tl_tenor_years"] = b_.number_input("Tenor (years)", 1, 20, int(P0["tl_tenor_years"]), key="pp_ten")
            P["tl_moratorium_months"] = c_.number_input("Moratorium (months)", 0, 60, int(P0["tl_moratorium_months"]), 3, key="pp_mor")
            P["tl_rate"] = _pct_in(d_, "TL rate (% p.a.)", "pp_tlr", P0["tl_rate"])
            a, b_, c_, d_ = st.columns(4)
            P["cc_amount"] = a.number_input("Cash credit / WC (₹ Cr) - blank = not specified, 0 = no CC limit", 0.0, 1e6,
                                            None if P0.get("cc_amount") is None else float(P0["cc_amount"]), 1.0, key="pp_cc")
            P["cc_rate"] = _pct_in(b_, "CC rate (% p.a.)", "pp_ccr", P0["cc_rate"])
            P["nfb_amount"] = c_.number_input("BG / LC non-fund (₹ Cr)", 0.0, 1e6, float(P0["nfb_amount"]), 1.0, key="pp_nfb")
            P["takeover_amount"] = d_.number_input("Existing debt taken over (₹ Cr)", 0.0, 1e6, float(P0.get("takeover_amount") or 0.0), 1.0, key="pp_to",
                                                   help="Existing borrowings repaid out of this loan - excluded from 'other lenders' when computing security cover.")
            a, b_ = st.columns([2, 1])
            P["purpose"] = a.text_input("Purpose", P0.get("purpose") or "", key="pp_purp", placeholder="e.g. Capacity expansion - new extrusion line")
            P["tl_capex"] = b_.checkbox("Term loan funds new fixed assets", value=bool(P0.get("tl_capex", True)), key="pp_capex")
        with card():
            st.markdown("**Security**")
            a, b_, c_ = st.columns([1, 1, 2])
            P["collateral_value"] = a.number_input("Collateral market value (₹ Cr)", 0.0, 1e6, float(P0["collateral_value"]), 1.0, key="pp_coll")
            P["collateral_type"] = b_.text_input("Collateral type", P0["collateral_type"], key="pp_ctype")
            P["guarantee"] = c_.text_input("Guarantee", P0["guarantee"], key="pp_guar")
            P["primary_security"] = st.text_input("Primary security", P0["primary_security"], key="pp_prim")
        with card():
            st.markdown("**What-if assumptions**")
            a, b_, c_, d_ = st.columns(4)
            base_g = CT._hist_growth(bundle)
            # blank = use the historical CAGR (shown in the assumption register); a value typed here is the officer's own assumption
            _gin = a.number_input("Revenue growth % p.a. (blank = history)", -30.0, 40.0,
                                  None if P0.get("growth") is None else float(round(P0["growth"] * 100, 1)), 0.5, key="pp_g",
                                  help="History-based: " + (f"{base_g:.1%}" if base_g is not None else "not derivable - enter a rate"))
            P["growth"] = None if _gin is None else _gin / 100
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
            st.caption("PD by grade: " + ", ".join(f"{k} {v:.2%}" for k, v in CT.load_pd().items()) + " - the admin sets the bank's master scale in 🛡 Admin › Bank parameters.")
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
        # store only what the officer actually set (or set before): untouched bank-policy defaults stay 'default - not reviewed'
        _prev = c.get("prop") or {}
        c["prop"] = {k: v for k, v in P.items() if k in CT.PROPOSAL_DEFAULTS and (k in _prev or v != CT.PROPOSAL_DEFAULTS[k])}
        ss.case = c
        bp = {**bundle, "proposal": {**(bundle.get("proposal") or {}), **c["prop"]}}

        rows_, asm = CT.projections(bp, P)
        sm = CT.dscr_summary(rows_)
        be = CT.breakeven(bp, P)
        if asm.get("status") == "NOT COMPUTED":
            st.error(f"Projections NOT COMPUTED - input required: {asm.get('reason')}.")
        elif asm.get("approximations"):
            st.warning("The projection uses approximations or unreviewed bank-policy defaults for: " + ", ".join(asm["approximations"])
                       + ". Confirm them below before relying on the DSCR.")
        if asm.get("register"):
            with st.expander("Assumption register - every input of the projection and where it comes from", expanded=bool(asm.get("approximations"))):
                st.dataframe(pd.DataFrame(asm["register"], columns=["Input", "Value used", "Source"]), hide_index=True, use_container_width=True)
        sc = CT.security_cover(bp, P)
        rp = CT.risk_pricing(bp, P)
        k = st.columns(6)
        kpi(k[0], "Average DSCR", ("n.a." if sm["avg"] is None else f"{sm['avg']:.2f}x"), "norm ≥ 1.25x",
            GOOD if (sm["avg"] or 0) >= 1.25 else CRIT)
        kpi(k[1], "Minimum DSCR", "n.a." if sm["min"] is None else f"{sm['min']:.2f}x", sm.get("min_year") or "", GOOD if (sm["min"] or 0) >= 1.10 else CRIT)
        kpi(k[2], "EBITDA cushion", "n.a." if be is None else f"{be:.0%}", "fall before min DSCR < 1.0x", GOOD if (be or 0) >= 0.2 else WARN if (be or 0) > 0 else CRIT)
        kpi(k[3], "Security cover", "n.a." if sc["cover"] is None else f"{sc['cover']:.2f}x", "FACR " + ("n.a." if sc["facr"] is None else f"{sc['facr']:.2f}x"))
        if rp.get("configured"):
            kpi(k[4], "Minimum price", f"{rp['floor']:.2%}", f"proposed {rp['proposed']:.2%}", GOOD if rp["proposed"] >= rp["floor"] else CRIT)
        else:
            kpi(k[4], "Minimum price", "not set", "admin: configure PD scale", WARN)
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
            b_.dataframe(pd.DataFrame([[a_, None if v is None else round(v, 2)] for a_, v in dp_["rows"]], columns=["Drawing power", "₹ Cr"]), hide_index=True, use_container_width=True)
        with t5:
            a, b_ = st.columns(2)
            a.dataframe(pd.DataFrame([[a_, None if v is None else round(v, 2)] for a_, v in sc["rows"]], columns=["Security", "₹ Cr"]), hide_index=True, use_container_width=True)
            a.write(f"Security cover **{fmt_(sc['cover'], 'x')}** · FACR **{fmt_(sc['facr'], 'x')}** · LTV {fmt_(sc['ltv'], '%')}")
            b_.dataframe(pd.DataFrame(rp["rows"], columns=["Pricing", "Value"]), hide_index=True, use_container_width=True, height=36 * (len(rp["rows"]) + 1))
            st.markdown("**Regulatory checks**")
            st.dataframe(pd.DataFrame(CT.regulatory(bp, P), columns=["Check", "Position", "Result"]), hide_index=True, use_container_width=True)

# ================================================================== EARLY WARNING
if PAGE == "ews":
    if not bundle:
        need_data()
    else:
        P = CT.proposal(bundle)
        ews_rows, n_trig = CT.rbi_ews(bundle, P)
        st.caption("Tested against the EWS indicators in the RBI framework for fraud risk management. 'Bank data needed' items depend on account "
                   "conduct, bank statements or registry searches - record them under Proposal › Account conduct.")
        k = st.columns(4)
        kpi(k[0], "Signals triggered", n_trig, f"of {len(ews_rows)} tested", CRIT if n_trig >= 4 else WARN if n_trig >= 2 else GOOD)
        kpi(k[1], "No indication", sum(1 for e in ews_rows if e[1] == "No indication"))
        kpi(k[2], "Not assessed / bank data", sum(1 for e in ews_rows if e[1] in ("Bank data needed", "Not assessed")))
        kpi(k[3], "Account status", CT.sma_status(P.get("dpd")).split(" (")[0].split(" -")[0])
        (st.error if n_trig >= 4 else st.warning if n_trig >= 1 else st.success)(CT.ews_action(n_trig))
        icon = {"Triggered": "🔴", "No indication": "🟢", "Not assessed": "🟡", "Bank data needed": "🟡"}
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
if PAGE == "portfolio":
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
        watch = pf[(pf["grade_code"].isin(["CI-5", "CI-6", "CI-7", "NR"])) | (pf["ews"].fillna(0) >= 2) | (pf["flags_high"].fillna(0) >= 3)]
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
            fig = chart_layout(fig, "Exposure by sector (₹ Cr)", h=300)
            fig.update_xaxes(type="linear", range=[0, max(float(sg.max()), 1) * 1.15], showgrid=True)
            fig.update_yaxes(type="category")
            b_.plotly_chart(fig, use_container_width=True)
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

if PAGE == "fraud":
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
        auto = WL.parties_for({"company": ss.company, "cin": ss.cin, "notes": ss.notes},
                              list(ss.parties or []) + EX.people_to_parties(ss.get("doc_people") or {}), ss.get("pages"))
        with st.expander(f"All {len(auto)} parties that will be screened (incl. those found in the documents)"):
            st.dataframe(pd.DataFrame([{"Name": p_["name"], "Role": p_["role"], "Identifier": p_.get("id", ""),
                                        "Pages": ", ".join(map(str, p_.get("pages") or []))} for p_ in auto]), hide_index=True, use_container_width=True)
        o1, o2, o3 = st.columns([1.2, 1.2, 1])
        use_os = o1.checkbox("OpenSanctions (sanctions / PEP)", value=bool(os_key), disabled=not os_key,
                             help="Needs an OpenSanctions API key in the sidebar. Sends party names to api.opensanctions.org.")
        use_web = o2.checkbox("Adverse-media search", value=True, help="Google News search for each key party with fraud / default / ED / CBI / SEBI / NCLT terms.")
        use_ai = st.checkbox("AI web screening of each party (OpenRouter + Parallel search, ≈₹0.20-0.60)", value=bool(k_or), disabled=not k_or,
                             help="Searches the web for wilful-defaulter listings, SEBI / RBI / MCA / ED / CBI / NCLT actions on each party, with source links.")
        if o3.button("🔎 Run screening", type="primary", use_container_width=True):
            with st.spinner("Screening..."):
                run_screening(use_os, use_web, use_ai)
            st.rerun()
        if not entries:
            st.info("No watch-lists loaded - screening still runs the web checks (adverse media" + (", AI web search" if k_or else "")
                    + "). For list matching, " + ("import the lists on the right." if IS_ADMIN else "ask your administrator to load the bank's lists."))

        st.markdown("**2 · Required regulatory checks** - CFR, wilful-defaulter & defaulter lists, CRILC, MCA, SEBI, IBBI")
        st.caption("Each source must show a result before sanction. Lists you import are screened automatically; bank-login sources "
                   "(RBI CFR, CRILC, non-suit-filed CIC data) can't be queried by this system - search them and record the result here.")
        cov_ = WL.coverage([e for e in entries if DEMO or not str(e.get("source", "")).startswith("SAMPLE")], scr or None, ss.attest)
        att_df = pd.DataFrame([{"key": r_["key"], "Source": r_["source"], "How to check": r_["how"], "Link": r_["url"] or None,
                                "Automated list": r_["list"], "List result": r_["auto"],
                                "Officer check": (ss.attest.get(r_["key"]) or {}).get("status", "Not checked"),
                                "Checked on": (ss.attest.get(r_["key"]) or {}).get("date", ""),
                                "Reference / remarks": (ss.attest.get(r_["key"]) or {}).get("ref", ""), "Status": r_["overall"]} for r_ in cov_])
        att_ed = st.data_editor(att_df, hide_index=True, use_container_width=True, key="attest_ed",
                                disabled=["Source", "How to check", "Link", "Automated list", "List result", "Status"],
                                column_config={"key": None, "Link": st.column_config.LinkColumn("Link", display_text="open"),
                                               "Officer check": st.column_config.SelectboxColumn("Officer check", options=WL.ATTEST_STATUS, required=True),
                                               "Checked on": st.column_config.TextColumn("Checked on", help="dd-mm-yyyy"),
                                               "Reference / remarks": st.column_config.TextColumn("Reference / remarks", width="medium")})
        new_att = {r_["key"]: {"status": r_["Officer check"], "date": r_["Checked on"], "ref": r_["Reference / remarks"], "by": officer}
                   for r_ in att_ed.to_dict("records") if r_["Officer check"] != "Not checked" or r_["Checked on"] or r_["Reference / remarks"]}
        if new_att != {k_: v_ for k_, v_ in (ss.attest or {}).items()}:
            ss.attest = new_att
            DB.log(USER["username"], "screening_attested", f"{ss.company}: " + ", ".join(f"{k_}={v_['status']}" for k_, v_ in new_att.items()))
            st.rerun()
        n_nc = sum(1 for r_ in cov_ if r_["overall"] == "NOT CHECKED")
        (st.warning if n_nc else st.success)(f"{n_nc} of {len(cov_)} required sources not yet checked." if n_nc else "All required sources checked.")

        if scr:
            st.markdown("**3 · Results**")
            hits = scr.get("hits") or []
            if not hits:
                st.success(f"No matches for {scr['summary']['parties']} parties against {scr['summary']['entries']:,} list entries.")
            else:
                st.dataframe(pd.DataFrame([{"": SEV_ICON.get(h["severity"], ""), "Party": h["party"], "Role": h["role"], "Listed as": h["listed_name"],
                                            "List": h["list"], "Match": h["match"], "Score": h["score"], "Reason": h["reason"], "Listed on": h["list_date"],
                                            "Source": h.get("source") if str(h.get("source", "")).startswith("http") else None}
                                           for h in hits]), hide_index=True, use_container_width=True,
                             column_config={"Source": st.column_config.LinkColumn("Source", display_text="open")})
            if (scr.get("ai_web") or {}).get("clear_parties"):
                st.caption("Web check found nothing adverse for: " + ", ".join(dict.fromkeys(scr["ai_web"]["clear_parties"])))
            if (scr.get("ai_web") or {}).get("unverified"):
                st.warning(f"{len(scr['ai_web']['unverified'])} web result(s) could not be confirmed on their source page - they are NOT treated as "
                           "findings. Open the link and check by hand:")
                st.dataframe(pd.DataFrame([{"Party": f_.get("party"), "AI said": f_.get("finding"), "Why not confirmed": f_.get("verification"),
                                            "Link": f_.get("url")} for f_ in scr["ai_web"]["unverified"]]), hide_index=True, use_container_width=True,
                             column_config={"Link": st.column_config.LinkColumn("Link", display_text="open")})
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
            if DEMO and os.path.exists(sample_wl) and st.button("Load the fictional sample list (demo mode only)", use_container_width=True):
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


# ================================================================== SETTINGS
if PAGE == "settings":
    render_settings()
