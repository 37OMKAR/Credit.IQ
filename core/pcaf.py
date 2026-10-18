"""PCAF financed emissions (Global GHG Accounting & Reporting Standard for the Financial Industry).

Business loans & unlisted equity : AF = outstanding / (total equity + total debt)      [book values]
Listed equity & corporate bonds  : AF = outstanding / EVIC  (EVIC = market cap + total debt + minority interest)
Financed emissions               = AF x company emissions (Scope 1+2; Scope 3 reported separately)

Data quality score (PCAF Table 5-3, business loans):
 1 = reported emissions, verified (assured)
 2 = reported emissions, unverified
 3 = physical-activity based estimate (energy / production x emission factor)
 4 = economic-activity based: revenue x sector emission factor
 5 = economic-activity based: asset x asset-turnover x sector emission factor
"""
import csv
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EF_FILE = os.path.join(HERE, "data", "emission_factors.csv")


def load_factors(path=EF_FILE):
    rows = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    r["tco2e_per_inr_cr_revenue"] = float(r["tco2e_per_inr_cr_revenue"])
                    rows.append(r)
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        pass
    return rows


def calculate(outstanding_cr, asset_class, total_equity, total_debt, minority=0.0, market_cap=None,
              scope1=None, scope2=None, scope3=None, verified=False, revenue=None, total_assets=None,
              sector_ef=None, sector_name=None, physical_estimate=None):
    res = {"inputs": dict(outstanding_cr=outstanding_cr, asset_class=asset_class, total_equity=total_equity,
                          total_debt=total_debt, minority=minority, market_cap=market_cap, scope1=scope1, scope2=scope2,
                          scope3=scope3, verified=verified, revenue=revenue, sector_ef=sector_ef, sector=sector_name)}
    listed = asset_class.startswith("Listed")
    if listed and market_cap:
        denom = market_cap + (total_debt or 0) + (minority or 0)
        res["denominator_name"] = "EVIC (market cap + total debt + minority interest)"
    else:
        denom = (total_equity or 0) + (total_debt or 0)
        res["denominator_name"] = "Total equity + total debt (book value)"
        if listed:
            res["warning"] = "Listed asset class chosen but no market cap given - fell back to book equity + debt."
    res["denominator"] = denom
    af = (outstanding_cr / denom) if denom else None
    if af is not None and af > 1:
        res["warning"] = "Attribution factor capped at 100% (exposure exceeds company's capital base)."
        af = 1.0
    res["attribution_factor"] = af

    s12 = None
    method = None
    if scope1 is not None or scope2 is not None:
        s12 = (scope1 or 0) + (scope2 or 0)
        method = "Reported emissions (BRSR)"
        dq = 1 if verified else 2
    elif physical_estimate:
        s12 = physical_estimate
        method = "Physical-activity estimate"
        dq = 3
    elif sector_ef and revenue:
        s12 = sector_ef * revenue
        method = f"Revenue x sector factor ({sector_name or 'sector'}: {sector_ef} tCO2e/INR Cr)"
        dq = 4
    elif sector_ef and total_assets:
        s12 = sector_ef * total_assets  # asset-based proxy (asset turnover assumed 1)
        method = f"Assets x sector factor (asset-turnover proxy) ({sector_name or 'sector'})"
        dq = 5
    else:
        dq = None
    res["company_scope12"] = s12
    res["method"] = method
    res["data_quality_score"] = dq
    res["financed_scope12"] = (af * s12) if (af is not None and s12 is not None) else None
    res["financed_scope3"] = (af * scope3) if (af is not None and scope3) else None
    res["financed_intensity_per_cr"] = (res["financed_scope12"] / outstanding_cr) if (res["financed_scope12"] is not None and outstanding_cr) else None
    res["economic_intensity"] = (s12 / revenue) if (s12 is not None and revenue) else None
    return res
