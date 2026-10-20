<div align="center">

# 🏦 Credit Intelligence Workbench

**From a scanned balance sheet to a sanction-ready credit file in minutes.**

Upload an annual report (digital or scanned), add your observations, and get back a full credit appraisal:
spread financials, 40+ ratios, forensic red flags, fraud & defaulter screening, RBI early-warning signals,
loan structuring with DSCR what-ifs, market intelligence, BRSR + PCAF financed emissions, and eight
ready-to-file Word reports plus a live-formula Excel workbook.

![Python](https://img.shields.io/badge/Python-3.11%E2%80%933.13-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-dashboard-FF4B4B?logo=streamlit&logoColor=white)
![Runs offline](https://img.shields.io/badge/works%20without%20AI-rule--based%20mode-1baf7a)
![Cost](https://img.shields.io/badge/AI%20cost-~%E2%82%B94%20per%20borrower-4c8dff)
![Made for](https://img.shields.io/badge/made%20for-Indian%20bank%20credit%20officers-eb6834)

<img src="docs/screenshots/03_dashboard.png" width="95%" alt="Dashboard"/>

</div>

---

## Contents
- [Why](#why)
- [What it does](#what-it-does)
- [Screens](#screens)
- [How it works (flow)](#how-it-works)
- [Reports you get](#reports-you-get)
- [Fraud & watch-list screening](#fraud--watch-list-screening)
- [Cost of running it](#cost-of-running-it)
- [Install & run (Windows)](#install--run-windows)
- [Configuration](#configuration)
- [Project structure](#project-structure)
- [Checks: what you can rely on](#checks-what-you-can-rely-on)
- [Accuracy, limits & data privacy](#accuracy-limits--data-privacy)

---

## Why

A credit officer spends most of an appraisal **re-typing numbers** from a 300-page annual report into a CMA / spreading
sheet, and very little time on the questions that matter: *Is the money going where they say? Can they repay? Who are we
really lending to?*  This workbench does the mechanical part and puts the judgement calls in front of the officer, with
every figure traceable to its source page.

## What it does

| Area | What you get |
|---|---|
| 📄 **Reading** | Digital PDFs, **scanned PDFs and phone photos** (built-in OCR, no Tesseract), Word / Excel / CSV supporting documents. Finds the balance sheet, P&L, cash flow, auditor's report, CARO and notes inside long annual reports. |
| 🧮 **Spreading** | Schedule III / Ind-AS spread with AI + rule-based cross-check, OCR decimal repair, tie-out checks, editable grid and a **source-page viewer** to check any figure. |
| 📊 **Analysis** | 40+ ratios (TOL/TNW, DSCR, ICR, MPBF, working-capital days, cash-flow quality), horizontal & vertical analysis, DuPont, sources & uses of funds, line-item anomalies, sector comparison, Beneish M, Piotroski F, Altman Z''. |
| 🕵️ **Forensics** | End-use gap, loans & advances to group entities, cash-rich-yet-borrowing, low yield on cash, receivables outrunning sales, CWIP stuck, capital advances, contingent liabilities, related-party trading, pledge, auditor qualifications / CARO / defaults. |
| 🚩 **Fraud screening** | Borrower, directors, guarantors, auditor and every company named in the documents screened against **wilful-defaulter, suit-filed, SEBI, MCA, RBI, IBBI and the bank's own fraud lists** - identifier, fuzzy-name, shared-director and group-name pattern matching. Optional OpenSanctions + adverse-media. |
| 🚨 **RBI early warning** | 20 EWS indicators from the RBI fraud-risk framework, each *Triggered / Not observed / Bank data needed*, with the RFA escalation call. |
| 🏦 **Structuring & what-if** | Term loan / CC / BG structure, quarterly repayment schedule, 3-10 year projections, yearly DSCR, 4 scenarios, **EBITDA break-even cushion**, Tandon I & II + turnover method, drawing power, security cover & FACR, PD / LGD / expected loss, risk-based price and RAROC, exposure-norm and SMA / NPA checks. |
| 🌐 **Market intelligence** | Live news (Google News; NewsAPI / GNews optional), AI-tagged for fraud, default, regulatory and rating signals, plus a written brief. |
| 🌱 **ESG** | BRSR scan (Scope 1/2/3, energy, water, waste, assurance) and **PCAF financed emissions** with a web "Fetch" for market cap & emissions. |
| 📑 **Outputs** | 8 Word reports + a 10-tab Excel workbook with live formulas (change an assumption, DSCR recalculates). |
| ✅ **Checks** | A logic checker (tie-outs, independent ratio recomputation, plausibility, rating/recommendation consistency, AI figures traced to the data) and a web source checker (page opens, names the company, shows the figure) run before every report - see [Checks](#checks-what-you-can-rely-on). |
| 🖥️ **Interface** | Warm near-black menu with an orange accent, cream work area with white cards, KPI cards with YoY change and sparklines, an analyst-update banner, and every chart on its own card. Fonts: Plus Jakarta Sans + Inter (Open Font License). |
| 👥 **Team** | Admin + officer accounts, central SQLite database, per-officer case store, history, portfolio view, activity log, **₹ cost meter per report**. |
| 💬 **Ask the documents** | Q&A over the uploaded reports with page citations and a confidence rating. |

## Screens

| Officer desk - upload, comment, run | Dashboard - snapshot, analyst update, actual vs projected |
|---|---|
| <img src="docs/screenshots/01_officer_desk.png"/> | <img src="docs/screenshots/03_dashboard.png"/> |

| Proposal & what-if - DSCR, cushion, pricing | Scenarios |
|---|---|
| <img src="docs/screenshots/05_proposal_whatif.png"/> | <img src="docs/screenshots/06_scenarios.png"/> |

| Fraud & watch-list screening | RBI early-warning signals |
|---|---|
| <img src="docs/screenshots/08_fraud_screening.png"/> | <img src="docs/screenshots/07_early_warning.png"/> |

| Forensic & hidden items | Spread review with source-page viewer |
|---|---|
| <img src="docs/screenshots/09_forensic.png"/> | <img src="docs/screenshots/10_spread_review.png"/> |

| Report centre - with the verification log | Portfolio view |
|---|---|
| <img src="docs/screenshots/12_report_centre.png"/> | <img src="docs/screenshots/13_portfolio.png"/> |

| BRSR & PCAF | Risk & analysis view |
|---|---|
| <img src="docs/screenshots/11_brsr_pcaf.png"/> | <img src="docs/screenshots/04_dashboard_risk.png"/> |

| History & cost per report | Admin - users, AI spend, activity |
|---|---|
| <img src="docs/screenshots/14_history.png"/> | <img src="docs/screenshots/15_admin.png"/> |

| Settings & AI keys | Analysis result on the desk |
|---|---|
| <img src="docs/screenshots/16_settings.png"/> | <img src="docs/screenshots/02_desk_results.png"/> |

| Ratios - n.a. / n.m. where a ratio is not meaningful | |
|---|---|
| <img src="docs/screenshots/17_ratios.png"/> | |

> Screenshots use the bundled **fictional** company *Deccan Polyfab Industries Ltd* and a **fictional** watch-list.

## How it works

```mermaid
flowchart LR
    subgraph IN[Inputs]
        A1[Annual report / balance sheet<br/>PDF, scanned PDF, photos]
        A2[BRSR filing]
        A3[CMA, stock statement,<br/>rating rationale, visit notes]
        A4[Officer comments &<br/>proposal structure]
        A5[Watch-lists<br/>CIBIL, SEBI, MCA, RBI, IBBI, internal]
    end
    subgraph READ[Read]
        B1[Text layer / OCR] --> B2[Locate statements,<br/>auditor report, notes]
        B2 --> B3[Spread: AI + rule-based<br/>cross-check, tie-outs]
    end
    subgraph ANALYSE[Analyse - deterministic]
        C1[Ratios & scores]
        C2[Forensic tests]
        C3[Projections, DSCR,<br/>scenarios, pricing]
        C4[RBI EWS]
        C5[Watch-list screening]
        C6[PCAF]
    end
    subgraph WEB[Online - optional]
        D1[News & adverse media]
        D2[OpenSanctions]
        D3[Web fetch: market cap,<br/>Scope 1 & 2]
    end
    subgraph OUT[Outputs]
        E1[Dashboard]
        E2[8 Word reports]
        E3[10-tab Excel]
        E4[Central DB, history,<br/>portfolio, cost meter]
    end
    A1 & A3 --> B1
    A2 --> C6
    B3 --> C1 --> C2 --> C4
    A4 --> C3
    C1 --> C3
    A5 --> C5
    D1 --> C2
    D2 --> C5
    D3 --> C6
    C1 & C2 & C3 & C4 & C5 & C6 --> F[AI narrative<br/>optional] --> E2
    C1 & C2 & C3 & C4 & C5 & C6 --> E1 & E3 & E4
```

**Officer journey**

```mermaid
sequenceDiagram
    actor O as Credit officer
    participant App as Workbench
    participant AI as AI model (optional)
    O->>App: Upload annual report + BRSR + supporting docs, add comments
    App->>App: OCR, locate statements, rule-based spread
    App->>AI: Extract / review notes (only if rule-based spread does not tie out)
    App-->>O: Spread with tie-outs and source pages
    O->>App: Correct figures, enter facility structure
    App-->>O: Ratios, forensic flags, EWS, DSCR what-if, pricing
    O->>App: Run watch-list screening, record flag dispositions
    App->>AI: Write memorandum narrative (one call)
    App-->>O: Word reports + Excel + cost in ₹, saved to central DB
```

Numbers are **never** produced by the AI: ratios, scores, projections, pricing and screening are computed in Python
(and as live Excel formulas). AI only reads documents and drafts prose.

## Reports you get

| Report | Pages | Use |
|---|---|---|
| **Credit Appraisal Memorandum** | ~20 | Full file: executive summary, data validation, financial analysis, ratios, DuPont, working-capital methods & drawing power, projections & DSCR, scenarios, stress test, forensic review, **RBI EWS**, **watch-list screening**, auditor & notes, market intelligence, ESG / PCAF, risk matrix, security, pricing, regulatory checks, covenants, due-diligence checklist, annexures. |
| **Credit Committee Note** | 2-3 | Summary for the sanctioning committee with sign-off block. |
| **Annual Review / Renewal Note** | 3 | Actuals vs last year and vs projections, rating migration, covenants, account conduct, EWS, renew / tighten / exit call. |
| **Early-Warning & Fraud-Risk Report** | 2-3 | EWS, watch-list hits, forensic findings, fund flow, statistical scores, actions incl. RFA / forensic audit trigger. |
| **Query Letter to Borrower** | 2 | Ready-to-send letter of clarifications and documents required (internal scores left out). |
| **Indicative Term Sheet** | 2 | Facilities, pricing, security, margins, covenants, conditions precedent & subsequent. |
| **Covenant Compliance Report** | 1-2 | Covenants on actuals plus projected headroom year by year. |
| **ESG & Financed Emissions Note** | 1-2 | BRSR indicators, emission intensity, PCAF calculation, transition risk. |

**Excel workbook:** `Balance Sheet` · `Ratios` · `PCAF Financed Emissions` · `Projections & DSCR` (yellow input cells drive
everything) · `Repayment Schedule` · `Scenarios` · `WC Assessment & DP` · `Security & Pricing` · `RBI EWS & Regulatory` ·
`CMA Analysis` (Forms II, III, IV, VI).

Sample outputs: [`samples/Sample_Output_CreditIntel_Report.docx`](samples/Sample_Output_CreditIntel_Report.docx) ·
[`samples/Sample_Output_CreditIntel_Workbook.xlsx`](samples/Sample_Output_CreditIntel_Workbook.xlsx)

## Fraud & watch-list screening

Lists are loaded once by the admin into the central database (CSV / Excel, any column layout - columns are mapped on
import) and shared by every officer:

| List | Where it comes from |
|---|---|
| Wilful defaulters & suit-filed accounts | [TransUnion CIBIL suit-filed search](https://transunioncibil.com/suit-filed-cases/overview) (RBI directs banks to report these to credit bureaus) |
| SEBI debarred entities | SEBI enforcement orders |
| MCA disqualified directors / struck-off companies | MCA21 |
| RBI Alert List, IBBI insolvency / liquidation, NFRA orders | Regulator websites |
| Fraud (FMR) / Red-Flagged Accounts / internal negative list | The bank's own systems |
| Sanctions & PEPs (optional, online) | [OpenSanctions match API](https://www.opensanctions.org/docs/api/) |

**Who is screened:** borrower (name + CIN), directors / promoters / guarantors entered by the officer (with DIN / PAN),
the statutory auditor, related parties from the notes, and every company / director (with DIN) **found automatically in
the documents**.

**How a match is decided**

| Pattern | Result |
|---|---|
| Same CIN / DIN / PAN / LLPIN | 🔴 High - confirmed identifier match |
| Name similarity ≥ 92 (after removing Pvt / Ltd / Mr / Shri…) | 🔴 High - probable match |
| Name similarity 85-92 | 🟠 Medium - possible match, verify identity |
| A screened person is a director of a listed entity | 🔴 High - shared director |
| A listed entity shares a distinctive name with the borrower or a related party | 🟠 Medium - possible group connection |
| Same party on two or more lists | escalated to High |
| Initials-only person name without DIN / PAN | capped at Medium |

Hits become red flags (with officer disposition), drive the RBI EWS indicator and appear in the memorandum and the EWS
report. Matching runs **locally**; names leave the PC only if you switch on OpenSanctions or adverse-media search.

## Cost of running it

The app works **with no AI key at all** (rule-based extraction, keyword notes review, template narrative). With a key, the
router sends cheap tasks to the cheapest model, caches every call (re-runs are free) and, in *Cheapest* mode, skips AI
extraction when the rule-based spread already ties out.

Estimated AI cost for one borrower (annual report ~300 pages, 2 years, BRSR, news, full memorandum - about
128k input + 22k output tokens), USD/INR 88:

| Model | Per borrower | 100 borrowers / month |
|---|---|---|
| DeepSeek `deepseek-chat` (direct API) | **≈ ₹4** | ≈ ₹400 |
| OpenRouter `deepseek/deepseek-chat` | ≈ ₹5 | ≈ ₹510 |
| OpenAI `gpt-4o-mini` | ≈ ₹3 | ≈ ₹280 |
| Google `gemini-2.5-flash` | ≈ ₹8 | ≈ ₹810 |
| LongCat (free daily quota) | ₹0 within quota | - |
| No key (rule-based) | ₹0 | ₹0 |

| Optional extra | Cost |
|---|---|
| Ask-the-documents question | ≈ ₹0.25-0.60 each |
| PCAF web fetch (OpenRouter `:online`) | ≈ ₹2 per company |
| Google News, watch-list screening | free |
| OpenSanctions API | per OpenSanctions plan |

Prices are **estimates** from `data/llm_prices.csv` - edit that file with your provider's current prices. The app shows
the **actual** cost of every report in ₹ (desk, history and admin pages), from real token counts.

## Install & run (Windows)

1. Install **Python 3.13** (or 3.12 / 3.11) from python.org - tick *Add python.exe to PATH*.
2. Double-click **`setup.bat`** - creates a virtual environment and installs everything (retries on flaky networks).
3. Copy `.env.example` to `.env` and add the keys you have (all optional).
4. Double-click **`run_app.bat`** - the browser opens at <http://localhost:8501>.
5. First run: create the **admin** account, then create officer accounts in 🛡 Admin.
6. Tick *Use the fictional sample* on the desk to see the whole flow without a real document.

**Office network:** run `run_app_network.bat` on one PC; colleagues open `http://<that-pc-name>:8501`. Everyone's work
lands in the central database on that PC.

**Linux / macOS:**
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-ocr.txt
streamlit run app.py
```

## Configuration

| Setting | Where |
|---|---|
| AI keys - DeepSeek, OpenRouter, LongCat, OpenAI, Gemini, Anthropic, Groq, Ollama (offline), custom | `.env` or the sidebar |
| Which model does which job + cost mode (Cheapest / Balanced / Best quality) | sidebar → *Which AI does which job* |
| News keys (NewsAPI, GNews), OpenSanctions key | `.env` or sidebar |
| Bank policy: benchmark rate, cost of funds, capital ratio, haircuts, margins, Tier-1 capital | Proposal tab → *Bank policy parameters* |
| PD master scale by grade | `core/credit_tools.py` → `PD_BY_GRADE` |
| Sector norms | `data/sector_benchmarks.csv` |
| Emission factors (PCAF) | `data/emission_factors.csv` |
| Model prices / USD-INR | `data/llm_prices.csv`, `USD_INR` in `.env` |
| Database location | `CREDITINTEL_DB` in `.env` (default `data/central.db`) |

## Project structure

```
app.py                      Streamlit UI (desk, dashboard, proposal, EWS, fraud screening, reports, portfolio, admin)
core/
  pdf_reader.py, docs.py    PDF / image / Office reading, OCR, statement locator
  extractor.py, schema.py   Spreading (AI + rule-based), canonical line items
  ratios.py, analyst.py     Ratios (one formula set for app + Excel), analytical commentary
  forensics.py              Red flags, Beneish / Piotroski / Altman, credit score & grade
  credit_tools.py           Projections, DSCR, scenarios, WC methods, DP, security, pricing, RBI EWS, regulatory
  watchlist.py              Fraud / defaulter / sanctions screening and party extraction
  news.py, webfetch.py      Market intelligence, web fetch for PCAF inputs
  brsr.py, pcaf.py          ESG extraction, financed emissions
  narrative.py, llm.py      AI narrative, provider router, cache, cost ledger
  report_word.py, report_sections.py, report_types.py     Word memorandum + 7 other reports
  report_excel.py, report_excel_extra.py                  Excel workbook (10 tabs, live formulas)
  db.py                     Users, cases, activity, watch-lists (SQLite)
data/                       Price list, sector norms, emission factors, sample watch-list (fictional)
samples/                    Fictional annual report, BRSR, scanned copy and sample outputs
docs/screenshots/           README images
```

## Checks: what you can rely on

Every analysis goes through two automated checkers **before any report is written**. Their log is printed as
**Annexure D** of the memorandum, the **Checks** sheet of the workbook and the **Verification log** on the Report centre page.
A report with a failed check is stamped **DRAFT**.

**1. Logic checker (`core/checker.py`)**

| Check | Result if it fails |
|---|---|
| Balance sheet tallies; PBT − tax = PAT; no negative assets or revenue | FAIL - report marked DRAFT |
| Ten key ratios (current ratio, TOL/TNW, debt/equity, ROCE, interest cover, EBITDA & PAT margin, debtor days, asset turnover ...) recomputed for every year by separate code must equal the ratio engine | FAIL |
| No ratio shown where it is meaningless (interest cover on nil interest, debt/EBITDA on negative EBITDA, tax rate in a loss year) | FAIL |
| Core lines read (revenue, PAT, net worth, current assets / liabilities, total assets) | FAIL; the borrower is shown **NR - Not rated** instead of a score |
| Year-on-year jump above 4x (usual sign of a lakh/crore or wrong-year misread) | WARN - confirm against the PDF |
| Size plausible for the unit read (figures in rupees read as crore would give an impossible balance sheet) | FAIL |
| Grade matches the score band; rating, open high-severity flags and recommendation agree | FAIL |
| Policy rule: score below 55 or two or more open high-severity flags can never say "Approve" | an AI "Approve" is **overridden** to "Refer / further diligence" and logged |
| **Every figure in an AI-written sentence must trace to the statements, ratios or scores - by unit** (a "₹ crore" figure must be an amount, a "%" a percentage, "days" a day count, within rounding only) | the sentence is **removed** and listed in Annexure D |
| Every red flag shows its evidence; mandatory regulatory checks (CFR, CRILC, wilful defaulters ...) recorded | WARN until done |
| **A missing core line is never treated as zero** (revenue, current assets / liabilities, net worth, PBT, PAT, CFO, receivables): every ratio, NWC / MPBF, projection, scenario, stress test and CMA line that needs it shows *n.a. - input missing* (app, Word and live Excel formulas) | withheld |
| Statement basis: the document's own titles decide standalone / consolidated; a consolidated-only PDF is analysed and **labelled consolidated** | noted in section 2.2 |
| Each line is read only from its own statement (a cash-flow "interest on loan" can never become the P&L finance cost); balance sheets running over 2-3 pages are read in full | - |
| Audit opinion is reported only if the auditor's report itself is in the documents; otherwise *not verified* | WARN |
| Statements older than 18 months; large movements in PPE, CWIP, borrowings, investments, loans (reconcile before relying) | WARN |
| **Recommendation fails closed**: any FAIL -> "Not ready for decision"; an approval also needs a verified audit opinion, recent statements and recorded regulatory checks; AI sentences recommending approval are removed when the recommendation is not an approval | enforced |
| **Case status** - one authoritative status on the cover, Annexure D, the workbook's Checks sheet and the Report centre: **READY**, **READY WITH WARNINGS** or **BLOCKED** (a required line not read or any FAIL), with the missing lines, the decision metrics not computed and the failed checks listed | BLOCKED -> no recommendation may be acted on |
| **Every input has a required/optional status.** Only lines that can genuinely be nil (goodwill, CWIP, leases, borrowings, inventories ...) may default to zero; a printed dash on a required line stays blank for the officer, never zero | withheld |
| **No silent defaults in projections**: growth comes from two read years of revenue or the officer - otherwise projections, DSCR and scenarios are *NOT COMPUTED*; every other assumption is listed in an assumption register with its source (spread / officer / default) | NOT COMPUTED / WARN |
| **Forensic tests declare their inputs**: a test whose figures were not read is reported *NOT ASSESSED* (it is not a clean result) and can never raise a flag on a zero; Beneish, Piotroski and Altman carry a status - CALCULATED / PARTIAL / NOT COMPUTED - and are presented as risk indicators, not proof | WARN |
| Free cash flow, drawing power, security cover, stress test and the narrative are withheld when their inputs (capex, receivables, payables, fixed assets, EBITDA) were not read - never "₹0.00 Cr" | withheld |
| Interest cost with no borrowings read (or interest above 30% of year-end borrowings) - borrowings may have been missed, which would flatter leverage | WARN |
| Fund-flow (sources and uses): lines read for only one year are excluded, and the statement must reconcile | noted in the report |
| Early-warning signals: *Triggered*, *No indication* (documents only - not a clearance), *Not assessed* (inputs missing / no list loaded), *Bank data needed* | - |

**2. Second, independent reading (`core/dualread.py`)** - the statement pages (only those, found locally for free) are read
again **from the page images** by a vision model (default Gemini 2.5 Flash-Lite via OpenRouter, about ₹0.07 a page). Every
figure is compared line by line with the first reading. Lines that differ go to a third reader (Mistral OCR via OpenRouter,
about ₹0.18 a page) as tie-breaker. A figure is **confirmed** when two readers agree; a figure the tie-breaker cannot settle is
**disputed** and shown to the officer with the page image. A disputed key line, or readers disagreeing on the unit
(lakh vs crore), fails the check and marks the report DRAFT. Switch: *Settings › Second reading from page images*
(turn off if page images must not leave the bank). Typical extra cost ₹1-2 per borrower.

**3. Web source checker (`core/verify.py`)** - nothing found by an AI web search is used unless:
1. the link was actually returned by the search engine and the page really opens (links the AI invented fail here),
2. the page names the company - its CIN, or **every word of its name** ("Deccan Plastics" is not "Deccan Polyfab"),
3. every number taken from it (emissions, market cap, revenue) is printed on that page **next to its own label** (a Scope 1 figure cannot confirm revenue),
4. a rating is used only if the exact grade (A+ is not A) and the agency are on the page,
5. a news item is used only if the page carries the story - most of the headline's words, and every adverse claim in it (raid, fraud, default, insolvency ...).

What fails is kept aside as an *unverified lead* for the officer to open by hand - it never reaches ratios, PCAF,
red flags or the report's conclusions.

**4. Self-test (`tools/selftest.py`)** - run `python tools/selftest.py` after any change. It deliberately breaks the
figures, the ratio engine and the grading, plants an invented figure in AI text, serves fake web pages (invented links,
another company, unsupported headline, wrong rating grade, misplaced numbers) and simulates second readers that misread a
figure or the unit, and runs the regression cases from an external audit on a consolidated test document, and checks that missing inputs are never read as zero - and fails unless every one is caught (54 checks).

**Where each part of the analysis comes from**

| Part | Basis |
|---|---|
| Ratios, Tandon I / II, turnover method, drawing power, DSCR | Standard published formulas (Tandon / Nayak committees, RBI guidance) |
| Beneish M-score, Piotroski F-score, Altman Z'' (emerging markets) | Original published models and coefficients |
| RBI early-warning signals | RBI Master Directions on Fraud Risk Management (2024) EWS list |
| Internal 0-100 score, CI-1…CI-7 grades, automatic recommendation | **This tool's own screening model** - a consistent first view, not the bank's rating model |
| Benchmarks (e.g. current ratio ≥ 1.33, TOL/TNW ≤ 3) | Generic Indian bank norms - replace with the bank's sector norms in Admin › Bank parameters |
| Risk-based pricing (PD / LGD / RAROC) | Switched off until the bank enters its own PD master scale - no placeholder values are used |
| Ratios that are not meaningful (nil interest, negative EBITDA, loss year, service business) | Shown as *n.a. / n.m.* with the reason, in the report and as live formulas in the workbook |
| EBITDA | PBT − exceptional items − share of JV / associate profit + finance cost + depreciation − other income (operating EBITDA) |
| Free cash flow | CFO − all capital expenditure in investing activities (PPE, intangibles, CWIP, capital advances) |
| End-use test | Reconciles new borrowing against fixed-asset additions (cash-flow capex or the balance-sheet build-up incl. CWIP), working capital, capital advances and cash / deposits / current investments before flagging a gap |
| Security | Book values of current and fixed assets are shown as **indicative book-asset coverage**, not confirmed security, until the charge, its ranking and valuation are verified |
| Drawing power | Lower of DP and the sanctioned limit; no limit entered = no DP available |

## Accuracy, limits & data privacy

- **Decision support, not a decision.** Verify material figures against the audited statements; the memorandum says so.
- The biggest remaining risk is **reading the PDF**: if a figure is misread, every ratio built on it is wrong. The tie-out
  and plausibility checks catch most misreads; always compare *Spread review* with the source page for material figures.
- Bank-login sources (RBI CFR, CRILC, CIBIL suit-filed / non-suit-filed data) cannot be queried by any outside tool - the
  officer checks them and records the result on the Fraud screening page; the report shows each as checked / not checked.
- Sector norms, emission factors and the PD scale are only used once the administrator marks them as the bank's approved values.
- A watch-list **name match is not a finding** until identity is confirmed by CIN / DIN / PAN.
- Documents, cases and the database stay on the PC that runs the app. Text is sent only to the AI provider you configure
  (or none - use Ollama for fully offline AI). `.env`, `data/central.db`, `cases/` and `reports/` are git-ignored.
- RBI references: Master Directions on Fraud Risk Management (2024) EWS / RFA framework, Large Exposures Framework,
  IRACP norms, Tandon / Nayak committee methods.

---

<div align="center">Built for credit officers who would rather think than type.</div>
