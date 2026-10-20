"""Self-test: proves the logic checker and the web-source checker catch what they must.

Run from the project folder:   python tools/selftest.py
Uses only the fictional sample annual report and a tiny local test website (no internet, no real borrower data).

It checks that
  1. the sample analysis passes every logic check and all 8 report types build;
  2. deliberately broken figures / ratio engine / grading are caught (the checker must FAIL them);
  3. an invented figure in AI text is removed while real figures stay;
  4. a lenient AI recommendation is overridden by the policy rule;
  5. web results are rejected when the link was never returned by the search engine, the page is about another
     company, the headline's claim is not on the page, a rating grade differs, or a number is not next to its label.
"""
import copy
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from core import checker as CK  # noqa: E402
from core import extractor as EX  # noqa: E402
from core import pdf_reader as PR  # noqa: E402
from core import pipeline as PL  # noqa: E402
from core import ratios as R  # noqa: E402
from core import report_types as RT  # noqa: E402
from core import verify as V  # noqa: E402

FAILS = []


def ok(cond, msg):
    print(("  PASS  " if cond else "  FAIL  ") + msg)
    if not cond:
        FAILS.append(msg)


def results(checks):
    return {c["check"]: c["result"] for c in checks}


def sample_bundle():
    pdf = os.path.join(HERE, "samples", "Sample_Annual_Report_DeccanPolyfab_FY25.pdf")
    pages = PR.read_pdf(open(pdf, "rb").read())
    loc = PR.locate_sections(pages)
    r = EX.heuristic_extract(pages, loc)
    return PL.analyse(r["data"], r["years"], "Deccan Polyfab Industries Ltd", notes=EX.heuristic_notes_review(pages, loc)), r


print("1. Sample analysis")
b, raw = sample_bundle()
narr = PL.write_narrative(b)
_, chk = CK.run(b, narr)
fails = [c for c in chk if c["result"] == "FAIL"]
ok(not fails, f"sample passes all logic checks ({len(chk)} checks)" + (f" - failed: {[c['check'] for c in fails]}" if fails else ""))
for name in RT.REPORT_TYPES:
    out = RT.build(name, copy.deepcopy(b), narr, "Self test", "HO")
    ok(len(out) > 5000, f"report builds: {name}")

print("2. Deliberate errors must be caught")
d2 = copy.deepcopy(raw["data"])
y0 = raw["years"][0]
d2[y0]["total_assets"] = (d2[y0]["total_assets"] or 0) * 1.3
b2 = PL.analyse(d2, raw["years"], "Broken Co")
ok(results(CK.run(b2, PL.write_narrative(b2))[1]).get(f"Balance sheet tallies - {y0}") == "FAIL", "balance sheet that does not tally -> FAIL")

d3 = copy.deepcopy(raw["data"])
d3[y0]["revenue"] = None
b3 = PL.analyse(d3, raw["years"], "Missing Co")
ok(results(CK.run(b3, PL.write_narrative(b3))[1]).get("Core statement lines read") == "FAIL" and b3["forensics"]["grade"].startswith("NR"),
   "missing revenue -> FAIL and not rated")

b4 = copy.deepcopy(b)
b4["ratios"][y0]["current_ratio"] = (b4["ratios"][y0]["current_ratio"] or 1) * 1.5  # simulate a bug in the ratio engine
r4 = results(CK.run(b4, narr)[1])
ok("FAIL" in (r4.get("Key ratios recomputed independently agree with the ratio engine"),
              r4.get("TOL/TNW, ROCE, asset turnover, interest cover and current ratio recomputed for every year")), "wrong ratio from the engine -> FAIL")

b5 = copy.deepcopy(b)
b5["forensics"]["grade"] = "CI-1 - Very low risk"  # simulate a grading bug
ok(results(CK.run(b5, narr)[1]).get("Grade matches the score band") == "FAIL", "grade that does not match the score -> FAIL")

b6 = copy.deepcopy(b)
b6["ratios"][y0]["icr"] = 999.0
b6["data"][y0]["finance_cost"] = 0.0
ok(results(CK.run(b6, narr)[1]).get("Not-meaningful ratios are suppressed (shown as n.a. / n.m.)") == "FAIL",
   "interest cover shown on nil interest -> FAIL")

print("3. AI text")
rev = b["data"][y0]["revenue"]
ai = {"_source": "AI", "recommendation": narr["recommendation"],
      "executive_summary": f"Revenue was INR {rev:,.2f} Crore. The order book stands at INR 4,321.9 Crore. Margins are under pressure."}
clean, chk7 = CK.run(b, ai)
ok("4,321.9" not in clean["executive_summary"] and f"{rev:,.2f}" in clean["executive_summary"], "invented figure removed, real figure kept")

print("4. Policy rule beats a lenient AI recommendation")
clean8, _ = CK.run(b, dict(narr, recommendation="Approve"))
ok(clean8["recommendation"] == "Refer / further diligence" if (b["forensics"]["score"] < 55) else True, "AI 'Approve' overridden when the rule requires Refer")

print("5. Web sources (local test site)")
site = tempfile.mkdtemp()
open(os.path.join(site, "real.html"), "w").write("<h1>Deccan Polyfab Industries wins export order from Kenya</h1><p>Deccan Polyfab Industries Ltd said ... "
                                                  "Rated CARE A-/Stable. Scope 1 emissions 2,345.6 tCO2e. Revenue from operations 1,350.00 crore.</p>")
open(os.path.join(site, "other.html"), "w").write("<h1>Deccan Plastics Ltd results</h1><p>Deccan Plastics Ltd posts revenue of 2,345.6 crore</p>")
port = 8771
srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port)], cwd=site, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.2)
try:
    B = f"http://localhost:{port}/"
    co = "Deccan Polyfab Industries Ltd"
    cites = [{"url": B + "real.html"}, {"url": B + "other.html"}]
    good, bad = V.verify_news([
        {"title": "Deccan Polyfab Industries wins export order from Kenya", "url": B + "real.html"},
        {"title": "Deccan Polyfab Industries raided by Enforcement Directorate", "url": B + "real.html"},
        {"title": "Deccan Polyfab results", "url": B + "other.html"},
        {"title": "Deccan Polyfab fraud", "url": B + "invented.html"}], co, None, cites)
    ok(len(good) == 1 and len(bad) == 3, "news: real story kept; unsupported claim, other company and invented link rejected")
    ok(V.verify_rating({"agency": "CARE", "rating": "A-", "url": B + "real.html"}, co, None, cites)[0] is not None, "rating written on the page -> kept")
    ok(V.verify_rating({"agency": "CARE", "rating": "AA", "url": B + "real.html"}, co, None, cites)[0] is None, "different rating grade -> rejected")
    w = V.verify_web_pcaf({"scope1_tco2e": 2345.6, "revenue_inr_cr": 2345.6, "scope3_tco2e": 777.7, "sources": [{"url": B + "real.html"}],
                           "_citations": cites}, co, None)
    ok(w["scope1_tco2e"] == 2345.6, "emission figure next to 'Scope 1' on the company's page -> kept")
    ok(w["revenue_inr_cr"] is None, "same number but not next to 'revenue' -> rejected")
    ok(w["scope3_tco2e"] is None, "number not on any page -> rejected")
finally:
    srv.terminate()

print()
if FAILS:
    print(f"SELF-TEST FAILED: {len(FAILS)} problem(s)")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("SELF-TEST PASSED - every check behaved as required.")
