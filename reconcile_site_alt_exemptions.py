# -*- coding: utf-8 -*-
"""
reconcile_site_alt_exemptions.py — Reconcile legacy Site Alteration
`farm_exemption` / `bylaw_exemptions.exemption_status` discrepancies uncovered
during the Wave 1 + Wave 2 primary-source province-wide fee & bylaw audits.

Approved reconciliation package (42 municipalities):
  - Group A (3):  Legacy Yes -> No (No NFP Exemption):
      Caledon, Kingsville, Orangeville
  - Group B (11): Legacy Yes -> Partial (Statutory Topsoil / Narrow Carve-Out / NFPPB-Gated):
      Grand Valley, Vaughan, Innisfil, Essa, Newmarket, Oakville,
      Richmond Hill, St. Marys, Lakeshore, Deseronto, Malahide
  - Group C (4):  Legacy Yes -> Partial (Volume-Capped Ag Fill Imports — matches all 15 existing Partial caps):
      Burlington, Oro-Medonte, Kawartha Lakes, East Gwillimbury
  - Group D (5):  Legacy No / Partial -> Yes (Full NFP / Fill & Grading verified):
      Kingston, Penetanguishene, Ramara, Clearview, Loyalist
  - Group E (5):  Legacy No -> Partial (Verified Statutory Drainage / Topsoil Removal carve-outs):
      Barrie, Gravenhurst, Orillia, Welland, Niagara Falls
  - Group F (3):  Proven Cross-Contaminated / Zoning Misclassifications -> NO BY-LAW IN PLACE (N/A):
      Dawn-Euphemia (held King's By-law 2021-039), Newbury (Zoning 692), South Huron (Zoning 69-2018)
  - Group G (3):  Unverified Legacy Records (broken links, 0 fees in 2026) -> NOT KNOWN (COMMUNICATION NEEDED):
      Marmora and Lake, West Grey, Thunder Bay
  - Group H (8):  Metadata Hygiene (backfill nfp_exemption_scope, links & dates on 7 verified Yes + The Archipelago progress fix):
      Amherstburg, London, Niagara-on-the-Lake, Southwold, Timmins, Uxbridge,
      Whitchurch-Stouffville, The Archipelago

All updates keep `bylaw_exemptions.exemption_status` and `details_site_alt.farm_exemption`
in 100% lockstep and log every modified field to `audit_log`.

Usage:
    python reconcile_site_alt_exemptions.py
"""

from __future__ import annotations

import datetime
import os
import sqlite3
from collections import Counter

from import_site_alt_fees_wave1 import export_qa_workbook

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB = os.path.join(HERE, "bylaws.db")
AUDIT_USER = "site_alt_exemption_reconciliation"
TODAY_STR = "2026-11-27"


# ── Helpers for clean canonical No-Bylaw resets ──────────────────────────────
NO_BYLAW_CLEAR_DETAILS = {
    "farm_exemption": None,
    "special_provision": None,
    "guidelines_wording": None,
    "exception_wording": None,
    "nfp_exemption_scope": None,
    "drainage_act_exempt": None,
    "excess_soil_reg_406_19": None,
    "fill_captures_ag_materials": None,
    "fee_verification_status": "N/A (No Bylaw)",
    "fee_year": None,
    "fees_bylaw_name": None,
    "fees_bylaw_link": None,
    "ag_import_fee_status": "No Bylaw",
    "ag_exempt_volume_cap_m3": None,
    "out_of_muni_fill_ban": None,
    "fee_pricing_model": None,
    "base_fee_small": None,
    "base_fee_large": None,
    "per_m3_rate": None,
    "fee_calc_spec_json": None,
    "est_fee_500_m3": None,
    "est_fee_5000_m3": None,
    "est_fee_15000_m3": None,
    "security_deposit_terms": None,
    "peer_review_recovery": None,
    "fee_formula_notes": None,
}


def build_reconciliation_specs() -> list[dict]:
    """Return all 42 verified reconciliation specifications."""
    return [
        # ════════════════════════════════════════════════════════════════════
        # GROUP A: Legacy Yes -> No (No NFP Exemption) [3]
        # ════════════════════════════════════════════════════════════════════
        {
            "group": "A: Yes -> No",
            "lookup_key": "Caledon, Tp",
            "bylaws": {
                "bylaw_link": "https://www.caledon.ca/assets/2026-07/Doc_637203057426383973%2027.pdf",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to No (No NFP Exemption). "
                "Verbatim review of enacted Fill By-law 2007-59 (Office Consolidation amended through 2022-067 & 2026-066) "
                "s. 17 confirms zero agricultural, Normal Farm Practice, Drainage Act, or topsoil-removal permit exemptions; "
                "s. 11(1)(a) requires a Fill Permit on A-1/A-2/A-3 farmland, caps imports at 10,000 m³, and triggers 2026 commercial rates ($983 + $2.05–$3.85/m³)."
            ),
            "exemptions": {
                "exemption_status": "No",
                "exemption_wording": (
                    "Fill By-law 2007-59 (consolidated through 2026-066) s. 17 contains no agricultural, Normal Farm Practice, "
                    "Drainage Act, or topsoil-removal permit exemption (exempts only <=150 mm lawn/garden dressing, demolition backfill, "
                    "underground services, and executed development grading agreements). Section 11(1)(a) requires a Fill Permit on "
                    "A-1/A-2/A-3 active agricultural lands demonstrating improved agricultural viability/productivity and prohibits permits >10,000 m³."
                ),
            },
            "details": {
                "farm_exemption": "No",
                "nfp_exemption_scope": "No NFP Exemption",
                "drainage_act_exempt": "No",
                "excess_soil_reg_406_19": "No",
                "exception_wording": (
                    "Fill By-law 2007-59 (consolidated through 2026-066) s. 17 contains no agricultural, Normal Farm Practice, "
                    "Drainage Act, or topsoil-removal permit exemption. Section 11(1)(a) requires a Fill Permit on A-1/A-2/A-3 "
                    "agricultural lands and strictly caps imported fill at 10,000 m³."
                ),
            },
        },
        {
            "group": "A: Yes -> No",
            "lookup_key": "Kingsville, Tp",
            "bylaws": {
                "bylaw_link": "https://media-003-ca.cdn.govstack.com/kingsville-ca/media/5thprv1f/combined-by-law-40-2026.pdf",
                "date_enacted": "2026-06-17",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to No (No NFP Exemption). "
                "Page-by-page visual inspection of enacted Site Alteration By-law 40-2026 (passed June 17, 2026, repealing draft 64-2025) "
                "confirms Sections 10–12 ('Permit Exemptions') contain zero agricultural, Normal Farm Practice, or Drainage Act exemptions."
            ),
            "exemptions": {
                "exemption_status": "No",
                "exemption_wording": (
                    "Enacted Site Alteration By-law No. 40-2026 (passed June 17, 2026) Sections 10–12 ('Permit Exemptions') "
                    "contain no agricultural, Normal Farm Practice, or Drainage Act permit exemption (exempting only Town/County/ERCA works, "
                    "<=10 cm lawn/flowerbed/vegetable garden dressing, and discretionary building-permit lot grading)."
                ),
            },
            "details": {
                "farm_exemption": "No",
                "nfp_exemption_scope": "No NFP Exemption",
                "drainage_act_exempt": "No",
                "excess_soil_reg_406_19": "Yes",
                "exception_wording": (
                    "Enacted Site Alteration By-law No. 40-2026 (passed June 17, 2026) Sections 10–12 contain no agricultural, "
                    "Normal Farm Practice, or Drainage Act permit exemption (s. 13(c) requires O. Reg. 153/04 & 406/19 compliance)."
                ),
            },
        },
        {
            "group": "A: Yes -> No",
            "lookup_key": "Orangeville, Tp",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to No (No NFP Exemption). "
                "By-law 2024-001 s. 3.5(a)–(g) contains zero agricultural, Normal Farm Practice, or Drainage Act permit exemptions "
                "(legacy Yes misread Schedule C s. 1(b), which exempts NFP only from the 10 m adjacent-property notification requirement)."
            ),
            "exemptions": {
                "exemption_status": "No",
                "exemption_wording": (
                    "Site Alteration By-law No. 2024-001 Section 3.5(a)–(g) contains no agricultural, Normal Farm Practice, or Drainage Act "
                    "permit exemption. Schedule C s. 1(b) exempts Normal Farm Practice only from the 10 m adjacent-property notification "
                    "requirement (s. 7 allows discretionary GMIS case-by-case waiver)."
                ),
            },
            "details": {
                "farm_exemption": "No",
                "nfp_exemption_scope": "No NFP Exemption",
                "exception_wording": (
                    "Site Alteration By-law No. 2024-001 s. 3.5(a)–(g) contains no agricultural or Normal Farm Practice permit exemption; "
                    "Schedule C s. 1(b) exempts NFP solely from the 10 m adjacent-property notification requirement."
                ),
            },
        },
        # ════════════════════════════════════════════════════════════════════
        # GROUP B: Legacy Yes -> Partial (Statutory / Narrow / NFPPB-Gated) [11]
        # ════════════════════════════════════════════════════════════════════
        {
            "group": "B: Yes -> Partial (Statutory/Narrow)",
            "lookup_key": "Grand Valley, Tp",
            "bylaws": {
                "bylaw_link": "https://www.townofgrandvalley.ca/media/matlmre1/2022-60.pdf",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial (Topsoil Removal Only). "
                "Fill By-law 2022-60 s. 3.1(m) exempts only incidental NFP topsoil removal; importing/placing fill or topsoil onto farmland requires a permit and full commercial fees."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Fill By-law 2022-60 s. 3.1(m) exempts only the removal of topsoil as an incidental part of a Normal Farm Practice "
                    "(including sod-farming, greenhouse operations, and horticultural nurseries; excluding sale, exchange, or disposition). "
                    "Importing or placing fill/topsoil on agricultural land is not exempt."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Topsoil Removal Only",
            },
        },
        {
            "group": "B: Yes -> Partial (Statutory/Narrow)",
            "lookup_key": "Vaughan, C",
            "bylaws": {
                "bylaw_link": "https://www.vaughan.ca/sites/default/files/2024-02/031-2024.pdf",
                "date_enacted": "2024-02-21",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial (Topsoil Removal Only). "
                "Enacted By-law 031-2024 repealed legacy Fill By-law 189-96's broad ag fill exemption and narrowed s. 6.0(1)(j) to "
                "removal/replacement of topsoil from agricultural lands (e.g., sod-farming/greenhouses/nurseries); general excess soil import requires a permit ($11,033 flat) and s. 5.0(4)(a) fertility proof."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Site Alteration By-law 031-2024 (eff. Feb 21, 2024, repealing Fill By-law 189-96) s. 6.0(1)(j) narrows the exemption "
                    "to 'the Removal or replacement of Topsoil from Agricultural Lands as part of Normal Farm Practice such as Sod-farming, "
                    "greenhouse operations and nurseries for horticultural productions' (excluding sale/exchange). General fill or excess soil "
                    "import onto agricultural land is not broadly exempt and requires proof of maintained/improved agricultural fertility (s. 5.0(4)(a)) and a permit."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Topsoil Removal Only",
                "exception_wording": (
                    "Site Alteration By-law 031-2024 s. 6.0(1)(j): exempts only 'the Removal or replacement of Topsoil from Agricultural Lands "
                    "as part of Normal Farm Practice such as Sod-farming, greenhouse operations and nurseries for horticultural productions' "
                    "(excludes sale/exchange; general excess soil import onto agricultural land requires a permit and s. 5.0(4)(a) fertility proof)."
                ),
            },
        },
        {
            "group": "B: Yes -> Partial (Statutory/Narrow)",
            "lookup_key": "Innisfil, Tp",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from Yes to Partial (Statutory Topsoil & Drainage Only). "
                "Site Alteration By-law 108-23 s. 1.3.3(h) grants an NFP exemption ONLY 'as so determined by the Normal Farm Practices Protection Board' "
                "(no automatic municipal exemption); otherwise farmers >100 m³ require a s. 3.3 Bona Fide Farmer Permit (survey + P.Eng. + Agrologist report, 1,000 m³/yr cap) and commercial fees ($1,061–$4,774)."
            ),
            "exemptions": {
                "exemption_status": "Partial",
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
            },
        },
        {
            "group": "B: Yes -> Partial (Statutory/Narrow)",
            "lookup_key": "Essa, Tp",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial (Topsoil Removal Only). "
                "Visually verified By-law 2019-84: s. 5.1 exempts topsoil removal only; s. 5.2 requires a Permit + survey + P.Eng. + Certified Agrologist report + "
                "$250 + $2/m³ fee with a hard 1,000 m³/yr limit for Bona Fide Farmers >100 m³, and s. 6.1.5.5 prohibits permitted site alteration on Class 1–3 farmland."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Site Alteration Fill By-law 2019-84 s. 5.1 exempts topsoil removal only. Section 5.2 & s. 7.1 are NOT permit exemptions: "
                    "a Bona Fide Farmer placing/dumping fill >100 m³ must obtain a Permit, submit a professional survey, P.Eng. submission, and "
                    "Certified Agrologist report, pay commercial fees ($250 + $2.00/m³), and adhere to a hard 1,000 m³/yr maximum; s. 6.1.5.5 "
                    "prohibits permitted site alteration on Class 1, 2, or 3 agricultural lands or specialty crop areas."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Topsoil Removal Only",
                "exception_wording": (
                    "By-law 2019-84 s. 5.1 exempts topsoil removal only. Section 5.2 requires Bona Fide Farmers (>100 m³) to obtain a Permit "
                    "with survey, P.Eng., and Certified Agrologist reports up to a hard 1,000 m³/yr ceiling; s. 6.1.5.5 bans permitted site alteration on Class 1–3 farmland."
                ),
            },
        },
        {
            "group": "B: Yes -> Partial (Statutory/Narrow)",
            "lookup_key": "Newmarket, Tp",
            "bylaws": {
                "bylaw_link": "https://www.newmarket.ca/media/file/2016-58-site-alteration-law",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial (Topsoil Removal Only). "
                "By-law 2016-58 s. 6.2 exempts routine tilling/planting/harvesting only and s. 6.12 exempts topsoil removal only; "
                "importing/placing fill >5 m³ on parcels >=0.5 ha requires a permit + s. 5.6 QP fertility certificate + $2,261 + % engineering fee."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Site Alteration By-law 2016-58 s. 6.2 exempts only routine agricultural activity such as tilling, planting, harvesting "
                    "and associated activities ('Other agricultural activities are not exempt'), and s. 6.12 exempts topsoil removal only. "
                    "Importing/placing fill or topsoil >5 m³ on parcels >=0.5 ha requires a Site Alteration Permit plus a Qualified Person fertility certificate (s. 5.6)."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Topsoil Removal Only",
            },
        },
        {
            "group": "B: Yes -> Partial (Statutory/Narrow)",
            "lookup_key": "Oakville, Tp",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial (Topsoil Removal Only). "
                "By-law 2023-047 (cons. w/ 2025-132) Schedule B Item 6 exempts incidental NAP topsoil removal only; importing/placing fill or topsoil is not exempt."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Site Alteration By-law 2023-047 (consolidated Aug 11, 2025 w/ By-law 2025-132) Schedule B Item 6 exempts only "
                    "'The removal of topsoil incidental to a normal agricultural practice including such removal as an incidental part of "
                    "sod-farming, greenhouse operations and nurseries for horticultural products' (fill/topsoil import is not exempt)."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Topsoil Removal Only",
                "exception_wording": (
                    "Schedule B Item 6: exempts only the removal of topsoil incidental to a normal agricultural practice "
                    "(sod-farming, greenhouse operations, nurseries); fill/topsoil import is not exempt."
                ),
            },
        },
        {
            "group": "B: Yes -> Partial (Statutory/Narrow)",
            "lookup_key": "Richmond Hill, C",
            "bylaws": {
                "bylaw_link": "https://www.richmondhill.ca/en/shared-content/resources/documents/Site-Alteration-Permit/47-25.pdf",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial (Topsoil Removal Only). "
                "Verified directly in enacted By-law 47-25 PDF (Ch. 967, May 14, 2025): s. 3.1(c) & Sched A #3 exempt incidental NAP topsoil removal only "
                "(no Drainage Act or O. Reg. 406/19 reference; importing/placing fill requires permit at $656 flat)."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Site Alteration By-law 47-25 (Municipal Code Ch. 967, passed May 14, 2025) s. 3.1(c) and Schedule A Item 3 exempt only "
                    "'the removal of topsoil as an incidental part of a normal agricultural practice including such removal as an incidental part "
                    "of sod-farming, greenhouse operations and nurseries for horticultural products' (excluding sale/exchange/disposition). "
                    "Importing or placing fill/topsoil on agricultural land is not exempt."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Topsoil Removal Only",
                "drainage_act_exempt": "No",
                "excess_soil_reg_406_19": "No",
                "exception_wording": (
                    "Site Alteration By-law 47-25 s. 3.1(c) & Schedule A Item 3: exempts only the removal of topsoil incidental to a normal "
                    "agricultural practice (excluding sale/exchange/disposition); fill/topsoil import is not exempt."
                ),
            },
        },
        {
            "group": "B: Yes -> Partial (Statutory/Narrow)",
            "lookup_key": "St. Marys, T",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial (Topsoil Removal Only). "
                "Clerk-obtained excerpt of Site Alteration By-law 72-2018 s. 4.1(h) exempts Removal of Soil incidental to NAP only; "
                "importing/placing clean topsoil or fill requires a permit ($279 <500 m³ / $557 >500 m³)."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Site Alteration By-law No. 72-2018 Section 4.1(h) exempts only 'the Removal of Soil as an incidental part of a normal "
                    "agricultural practice' (excluding Removal of Topsoil for sale, exchange, or other disposition). Importing/placing fill or topsoil is not exempt."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Topsoil Removal Only",
            },
        },
        {
            "group": "B: Yes -> Partial (Statutory/Narrow)",
            "lookup_key": "Lakeshore, M",
            "bylaws": {
                "date_enacted": "2020-09-01",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial (Statutory Topsoil & Drainage Only). "
                "Verbatim review of enacted Fill By-law 60-2020 (passed Sept 1, 2020) s. 11.2(g)–(h) confirms exemptions are limited to "
                "Drainage Act / Tile Drainage Act works and incidental NAP topsoil removal only; agricultural fill import requires a permit ($260 flat)."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Fill By-law No. 60-2020 Section 11.2(g)–(h) exempts only drain construction under the Drainage Act / Tile Drainage Act "
                    "and 'the removal of Topsoil as an incidental part of a normal agricultural practice' (excluding sale/exchange/disposition). "
                    "Importing or placing fill/topsoil on agricultural land is not exempt."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
                "drainage_act_exempt": "Yes",
            },
        },
        {
            "group": "B: Yes -> Partial (Statutory/Narrow)",
            "lookup_key": "Deseronto, Tp",
            "bylaws": {
                "bylaw_link": "https://www.deseronto.ca/s/Site-Alteration-By-law-47-2023.pdf",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial (Statutory Topsoil & Drainage Only) and updated link to official Town PDF. "
                "Visual inspection of all 8 pages of enacted Site Alteration By-law 47-2023 confirms s. 4(i)(g) Drainage Act and s. 4(iii) incidental NAP topsoil removal only; "
                "importing/placing fill >50 m³ requires a permit under s. 5(ii)."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Site Alteration By-law No. 47-2023 s. 4(i)(g) exempts Drainage Act / Tile Drainage Act works and s. 4(iii) exempts only "
                    "'the extent that Topsoil is removed as an incidental part of a Normal Agricultural Practice' (excluding sale/exchange/disposition). "
                    "Importing or placing fill >50 m³ requires a permit (s. 5(ii))."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
                "drainage_act_exempt": "Yes",
            },
        },
        {
            "group": "B: Yes -> Partial (Statutory/Narrow)",
            "lookup_key": "Malahide, Tp",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial (Statutory Topsoil & Drainage Only). "
                "Stored verbatim excerpts of Site Alteration By-law 08-59 confirm s. 3.1(g) Drainage Act / Tile Drainage Act and s. 3.3 incidental NAP topsoil removal only "
                "(no verified agricultural fill-import exemption)."
            ),
            "exemptions": {
                "exemption_status": "Partial",
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
                "drainage_act_exempt": "Yes",
            },
        },
        # ════════════════════════════════════════════════════════════════════
        # GROUP C: Legacy Yes -> Partial (Volume-Capped Ag Fill Imports) [4]
        # ════════════════════════════════════════════════════════════════════
        {
            "group": "C: Yes -> Partial (Volume Cap)",
            "lookup_key": "Burlington, C",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from Yes to Partial for provincial consistency with all volume-capped bylaws. "
                "By-law 064-2014 s. 3.06.02.02 caps imported agricultural fill at a one-time maximum of 500 m³; above 500 m³ triggers area-based fees (501–5,000 m³) "
                "and volumetric fees ($1,181.78 + $1.18/m³ = $18,881.78 at 15,000 m³) plus Ag Committee circulation and Site Alteration Agreement."
            ),
            "exemptions": {
                "exemption_status": "Partial",
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
            },
        },
        {
            "group": "C: Yes -> Partial (Volume Cap)",
            "lookup_key": "Oro-Medonte, Tp",
            "bylaws": {
                "bylaw_link": "https://portal.laserfiche.ca/Portal/DocView.aspx?id=43978&repo=r-000184d30821",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial for provincial consistency with all volume-capped bylaws. "
                "By-law 2016-056 as amended by 2017-046 s. 3.2.6 caps farm fill exemption at 500 m³/yr AND restricts it strictly to Township-origin fill; "
                "above 500 m³/yr or any out-of-township fill triggers $500–$750 + $0.50/m³ ($8,250 at 15,000 m³) plus Council approval & agreement on title."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Site Alteration By-law 2016-056 (as amended by By-law 2017-046 s. 2 / s. 3.2.6) exempts fill placement incidental to "
                    "normal farming practices ONLY up to 500 m³/year (s. 3.2.6.3) AND only where the fill originates within Oro-Medonte Township "
                    "(s. 3.2.6.6). Above 500 m³/year or for any out-of-township fill, a permit and volumetric fees ($500–$750 + $0.50/m³) apply."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
                "exception_wording": (
                    "By-law 2016-056 (amended by 2017-046) s. 3.2.6: exempts NFP fill placement ONLY up to 500 m³/yr AND strictly from "
                    "sources originating within Oro-Medonte Township; larger or out-of-township imports require permit + $500–$750 + $0.50/m³."
                ),
            },
        },
        {
            "group": "C: Yes -> Partial (Volume Cap)",
            "lookup_key": "Kawartha Lakes, C",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial for provincial consistency with all volume-capped bylaws. "
                "Verified in consolidated By-law 2019-105 (w/ 2024-202): external ag soil import is capped at 1,000 m³/yr (<=500 m³ exempt; 500–1,000 m³ requires Declaration); "
                ">1,000 m³/yr triggers Large Fill Permit fees ($1,050 + $1.00/m³ = $16,050 at 15,000 m³). Uncapped Sched A s. 3.3 applies only within an Agricultural Operation wholly inside Kawartha Lakes."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Site Alteration By-law 2019-105 (consolidated w/ 2024-202) caps external agricultural soil import exemptions at "
                    "1,000 m³/calendar year (<=500 m³ NFP exempt under Sched A s. 3.2; 500–1,000 m³ exempt via Agricultural Soil Placement "
                    "Declaration Statement under s. 2.17). External imports >1,000 m³/yr require a Large Fill Permit ($1,050 + $1.00/m³). "
                    "Uncapped exemption (Sched A s. 3.3) applies only to moving soil within an Agricultural Operation wholly inside Kawartha Lakes."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
                "drainage_act_exempt": "Yes",
                "excess_soil_reg_406_19": "Yes",
            },
        },
        {
            "group": "C: Yes -> Partial (Volume Cap)",
            "lookup_key": "East Gwillimbury, Tp",
            "bylaws": {
                "bylaw_link": "https://www.eastgwillimbury.ca/media/dboclmij/2026-030-fill-by-law-update.pdf",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Downgraded from legacy Yes to Partial for provincial consistency with all volume-capped bylaws. "
                "Verified in enacted Fill By-law 2026-030 (Mar 24, 2026): s. 5.1(b) caps NFP topsoil spreading at 10,000 m³ per 36 months (<=200 mm grade, active FRFOFA/FBRN); "
                ">10,000 m³ triggers Major Site fees ($2,515.80 + $2.60/m³ = $41,515.80 at 15,000 m³) plus Council approval and Site Alteration Agreement."
            ),
            "exemptions": {
                "exemption_status": "Partial",
                "exemption_wording": (
                    "Fill By-law 2026-030 (passed Mar 24, 2026, repealing 2013-066) s. 5.1(b) exempts Site Alteration directly related to "
                    "a Normal Farm Practice (no Liquid Soil), including topsoil spreading, ONLY provided grade increase <=200 mm, total fill "
                    "added <=10,000 m³ in any 36-month period, and active FRFOFA/FBRN registration is held in good standing (also exempts "
                    "Drainage Act and statutory topsoil removal). Imports >10,000 m³ require a Major Permit ($2,515.80 + $2.60/m³), Council approval, and a Site Alteration Agreement."
                ),
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
                "drainage_act_exempt": "Yes",
                "excess_soil_reg_406_19": "Yes",
                "exception_wording": (
                    "Fill By-law 2026-030 s. 5.1(b): NFP topsoil spreading exempt ONLY up to 10,000 m³ per 36-month period (<=200 mm grade "
                    "increase, no Liquid Soil, active FRFOFA/FBRN required); >10,000 m³ triggers Major Permit ($2,515.80 + $2.60/m³)."
                ),
            },
        },
        # ════════════════════════════════════════════════════════════════════
        # GROUP D: Legacy No / Partial -> Yes (Full NFP / Fill & Grading) [5]
        # ════════════════════════════════════════════════════════════════════
        {
            "group": "D: No/Partial -> Yes",
            "lookup_key": "Kingston, C",
            "bylaws": {
                "bylaw_link": "https://www.cityofkingston.ca/by-laws-and-animal-services/commonly-requested-by-laws/by-law-library/",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Upgraded from legacy No to Yes (Full NFP / Fill & Grading) and replaced broken asbestos link. "
                "Site Alteration By-law 2008-128 (cons. 2009-11) s. 4(d) verbatim exempts all Site Alteration undertaken as part of a Normal Farm Practice (incl. fill placement & grading), plus s. 5(5) Drainage Act."
            ),
            "exemptions": {
                "exemption_status": "Yes",
                "exemption_wording": (
                    "Site Alteration By-law 2008-128 (cons. 2009-11) s. 4(d) exempts Site Alteration (placing/dumping fill, grade alteration) "
                    "undertaken 'as part of a Normal Farm Practice, including, but not limited to, sod-farming, greenhouse operations, nurseries, "
                    "and Agricultural Operations, but not including the removal of topsoil for sale, exchange, or other disposition' (s. 5(5) also exempts Drainage Act works)."
                ),
            },
            "details": {
                "farm_exemption": "Yes",
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
                "drainage_act_exempt": "Yes",
                "exception_wording": (
                    "By-law 2008-128 s. 4(d): exempts all Site Alteration undertaken as part of a Normal Farm Practice (excl. topsoil removal for sale/exchange/disposition); s. 5(5) exempts Drainage Act works."
                ),
            },
        },
        {
            "group": "D: No/Partial -> Yes",
            "lookup_key": "Penetanguishene, Tp",
            "bylaws": {
                "bylaw_link": "https://penetanguishene.civicweb.net/document/172728",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Upgraded from legacy No to Yes (Full NFP / Fill & Grading). "
                "Site Alteration By-law 2012-69 (Office Consolidation) s. 5.1(c) verbatim exempts site alterations undertaken as part of a Normal Farm Practice."
            ),
            "exemptions": {
                "exemption_status": "Yes",
                "exemption_wording": (
                    "Site Alteration By-law 2012-69 (Office Consolidation) s. 5.1(c) exempts site alterations undertaken 'As part of a Normal "
                    "Farm Practice, including, but not limited to, sod-farming, greenhouse operations, nurseries, and Agricultural Operations, "
                    "but not including the removal of topsoil for sale, exchange, stockpiling of material or other disposition'."
                ),
            },
            "details": {
                "farm_exemption": "Yes",
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
                "exception_wording": (
                    "By-law 2012-69 s. 5.1(c): exempts site alterations undertaken as part of a Normal Farm Practice (excl. topsoil removal for sale/exchange/stockpiling/disposition)."
                ),
            },
        },
        {
            "group": "D: No/Partial -> Yes",
            "lookup_key": "Ramara, Tp",
            "bylaws": {
                "bylaw_name": "Site Alteration By-law No. 2026.50 (replaces By-law 2018.64)",
                "date_enacted": "2026-09-14",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Upgraded from legacy No to Yes (Full NFP / Fill & Grading) and updated bylaw record to enacted By-law 2026.50 (passed Sept 14, 2026, repealing 2018.64). "
                "Part 5 s. 5.1(i) exempts Normal Farm Practice (FFPPA), including off-site fill demonstrated necessary for bona fide agricultural use and compliant with O. Reg. 406/19."
            ),
            "exemptions": {
                "exemption_status": "Yes",
                "exemption_wording": (
                    "Site Alteration By-law 2026.50 (passed Sept 14, 2026, repealing By-law 2018.64) Part 5 s. 5.1(i) exempts Site Alteration "
                    "undertaken as part of a Normal Farm Practice (FFPPA), including off-site fill demonstrated to be necessary for bona fide "
                    "agricultural use and compliant with O. Reg. 406/19 (not for commercial fill disposal or revenue generation)."
                ),
            },
            "details": {
                "farm_exemption": "Yes",
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
                "excess_soil_reg_406_19": "Yes",
                "exception_wording": (
                    "Site Alteration By-law 2026.50 s. 5.1(i): exempts Site Alteration as part of a Normal Farm Practice (FFPPA), including "
                    "O. Reg. 406/19-compliant off-site fill necessary for bona fide agricultural use."
                ),
            },
        },
        {
            "group": "D: No/Partial -> Yes",
            "lookup_key": "Clearview, Tp",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Upgraded from Partial to Yes (Full NFP / Fill & Grading). "
                "Enacted Fill By-law 25-67 (passed Nov 24, 2025) s. 5.4(c) explicitly exempts Normal Farm Practice (full FFPPA definition in s. 1) from requiring a Site Alteration Permit ($0, uncapped)."
            ),
            "exemptions": {
                "exemption_status": "Yes",
                "exemption_wording": (
                    "Fill By-law 25-67 (passed Nov 24, 2025) s. 5.4(c) exempts Normal Farm Practice (defined in s. 1 via the full FFPPA definition) "
                    "from requiring a Site Alteration Permit (substantive O. Reg. 406/19, Beneficial Purpose s. 3.12, and no-adverse-effect rules "
                    "still apply per s. 5.5; also exempts Drainage Act and statutory topsoil removal)."
                ),
            },
            "details": {
                "farm_exemption": "Yes",
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
                "exception_wording": (
                    "Fill By-law 25-67 s. 5.4(c): exempts Normal Farm Practice (full FFPPA definition) from requiring a Site Alteration Permit "
                    "(O. Reg. 406/19, Beneficial Purpose s. 3.12, and no-adverse-effect standards still apply per s. 5.5)."
                ),
            },
        },
        {
            "group": "D: No/Partial -> Yes",
            "lookup_key": "Loyalist, Tp",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Upgraded from Partial to Yes (Full NFP / Fill & Grading). "
                "Fill By-law 2003-22 s. 2(c)(viii) verbatim exempts dumping/placing fill and grade alteration on Prime Agricultural or Rural lands "
                "as an incidental part of a commonly accepted agricultural practice (plus s. 2(c)(xvi) Drainage Act)."
            ),
            "exemptions": {
                "exemption_status": "Yes",
                "exemption_wording": (
                    "Fill By-law 2003-22 s. 2(c)(viii) exempts permit requirements where 'fill is dumped or placed on lands zoned Prime "
                    "Agricultural or Rural where there is an alteration to the grade of land as an incidental part of a commonly accepted "
                    "agricultural practice' (s. 2(c)(xvi) also exempts Drainage Act works)."
                ),
            },
            "details": {
                "farm_exemption": "Yes",
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
            },
        },
        # ════════════════════════════════════════════════════════════════════
        # GROUP E: Legacy No -> Partial (Verified Statutory Carve-Outs) [5]
        # ════════════════════════════════════════════════════════════════════
        {
            "group": "E: No -> Partial",
            "lookup_key": "Barrie, C",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Upgraded from legacy No to Partial (Statutory Topsoil & Drainage Only). "
                "Visually verified By-law 2014-100 s. 6.2.6–6.2.7 exempt Drainage Act / Tile Drainage Act works and incidental NAP topsoil removal."
            ),
            "exemptions": {
                "exemption_status": "Partial",
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
                "drainage_act_exempt": "Yes",
                "exception_wording": (
                    "Site Alteration By-law 2014-100 s. 6.2.6–6.2.7 exempt only Drainage Act / Tile Drainage Act works and incidental "
                    "normal agricultural practice topsoil removal (s. 5.7 requires a Qualified Person fertility certificate for Site Alteration on Agricultural lands)."
                ),
            },
        },
        {
            "group": "E: No -> Partial",
            "lookup_key": "Gravenhurst, Tp",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Upgraded from legacy No to Partial (Statutory Topsoil & Drainage Only). "
                "Site Alteration By-law 2014-27 s. 4(e) exempts Drainage Act works and incidental NFP topsoil removal (and s. 2 applies only to shoreline/EP/scenic corridors)."
            ),
            "exemptions": {
                "exemption_status": "Partial",
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
                "drainage_act_exempt": "Yes",
                "exception_wording": (
                    "Site Alteration By-law 2014-27 s. 4(e) exempts Drainage Act works and incidental normal farm practice topsoil removal "
                    "(excluding sale); s. 2 applies only within 60 m of lake/river OSWL, EP/floodplain zones, 45 m of Hwy 11, and listed Scenic Corridors."
                ),
            },
        },
        {
            "group": "E: No -> Partial",
            "lookup_key": "Orillia, C",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Upgraded from legacy No to Partial (Statutory Topsoil & Drainage Only). "
                "Municipal Code Ch. 373 (By-law 2019-78) s. 373.3.2(f)–(g) exempt Drainage Act / Tile Drainage Act works and incidental NAP topsoil removal; "
                "s. 373.4.12 requires a permit for agricultural topsoil replacement."
            ),
            "exemptions": {
                "exemption_status": "Partial",
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
                "drainage_act_exempt": "Yes",
                "exception_wording": (
                    "Municipal Code Chapter 373 (By-law 2019-78) s. 373.3.2(f)–(g) exempt only Drainage Act / Tile Drainage Act works and "
                    "incidental normal agricultural practice topsoil removal; s. 373.4.12 requires a permit for agricultural topsoil replacement "
                    "(capped at 0.2 m depth & 1,000 m³/yr unless GM + Council approve more)."
                ),
            },
        },
        {
            "group": "E: No -> Partial",
            "lookup_key": "Welland, C",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Upgraded from legacy No to Partial (Statutory Topsoil & Drainage Only). "
                "Site Alteration By-law 2010-81 s. 3.6–3.7 exempt Drainage Act works and incidental NFP topsoil removal."
            ),
            "exemptions": {
                "exemption_status": "Partial",
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Statutory Topsoil & Drainage Only",
                "drainage_act_exempt": "Yes",
                "exception_wording": (
                    "Site Alteration By-law 2010-81 s. 3.6–3.7 exempt only Drainage Act works and incidental normal farm practice topsoil removal; "
                    "s. 2.8 caps Agricultural Lands depth at 300 mm with a professional soil fertility report (s. 4.1.9)."
                ),
            },
        },
        {
            "group": "E: No -> Partial",
            "lookup_key": "Niagara Falls, C",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Upgraded from legacy No to Partial (Topsoil Removal Only). "
                "By-law 2007-260 (amended by 2015-08) s. 25–26 verbatim exempts incidental normal agricultural practice topsoil removal (excluding sale/exchange)."
            ),
            "exemptions": {
                "exemption_status": "Partial",
            },
            "details": {
                "farm_exemption": "Partial",
                "nfp_exemption_scope": "Topsoil Removal Only",
                "exception_wording": (
                    "Fill/Site Alteration By-law 2007-260 (amended by 2015-08) s. 25–26 exempts incidental normal agricultural practice "
                    "topsoil removal only (excluding sale, exchange, or disposition); no agricultural fill-import exemption."
                ),
            },
        },
        # ════════════════════════════════════════════════════════════════════
        # GROUP F: Proven Misclassifications -> NO BY-LAW IN PLACE (N/A) [3]
        # ════════════════════════════════════════════════════════════════════
        {
            "group": "F: Misclassified -> No Bylaw",
            "lookup_key": "Dawn-Euphemia, Tp",
            "bylaws": {
                "progress": 11,
                "progress_label": "NO BY-LAW IN PLACE",
                "bylaw_name": None,
                "bylaw_name_2": None,
                "bylaw_link": None,
                "bylaw_link_2": None,
                "date_enacted": None,
                "expiry_date": None,
                "expiry_notes": None,
                "other_notes": (
                    "Reconciled Nov 27, 2026: Reclassified to NO BY-LAW IN PLACE. Legacy entry 'Site Alteration By-Law 2021-039' "
                    "(enacted 2021-04-26, amended by 2023-050, 2024-011, 2024-034) was empirically proven to be a cross-contamination of "
                    "Township of King (York Region)'s Site Alteration By-law. Dawn-Euphemia's By-Laws directory and 2026 Fees By-law 2025-17 "
                    "contain no Site Alteration / Fill / Topsoil By-law or fees."
                ),
                "date_last_updated": TODAY_STR,
            },
            "exemptions": {
                "exemption_status": None,
                "exemption_wording": None,
            },
            "details": dict(NO_BYLAW_CLEAR_DETAILS),
        },
        {
            "group": "F: Misclassified -> No Bylaw",
            "lookup_key": "Newbury, Tp",
            "bylaws": {
                "progress": 11,
                "progress_label": "NO BY-LAW IN PLACE",
                "bylaw_name": None,
                "bylaw_name_2": None,
                "bylaw_link": None,
                "bylaw_link_2": None,
                "date_enacted": None,
                "expiry_date": None,
                "expiry_notes": None,
                "other_notes": (
                    "Reconciled Nov 27, 2026: Reclassified to NO BY-LAW IN PLACE. Legacy entry 'By-law No. 692' (1978, cons. 2017) was "
                    "strictly Newbury's Restricted Area (Zoning) By-law (A1 Agricultural Zone), not a Municipal Act s. 142 Site Alteration / Fill / Topsoil By-law. "
                    "Newbury's By-laws directory (all 9 posted by-laws) and Fees By-law 128-19 contain no Site Alteration by-law or fees."
                ),
                "date_last_updated": TODAY_STR,
            },
            "exemptions": {
                "exemption_status": None,
                "exemption_wording": None,
            },
            "details": dict(NO_BYLAW_CLEAR_DETAILS),
        },
        {
            "group": "F: Misclassified -> No Bylaw",
            "lookup_key": "South Huron, M",
            "bylaws": {
                "progress": 11,
                "progress_label": "NO BY-LAW IN PLACE",
                "bylaw_name": None,
                "bylaw_name_2": None,
                "bylaw_link": None,
                "bylaw_link_2": None,
                "date_enacted": None,
                "expiry_date": None,
                "expiry_notes": None,
                "other_notes": (
                    "Reconciled Nov 27, 2026: Reclassified to NO BY-LAW IN PLACE. Legacy entry referenced Comprehensive Zoning By-law 69-2018 "
                    "(building definition) rather than a Municipal Act s. 142 Site Alteration / Fill / Topsoil By-law. Review of South Huron's "
                    "by-laws portal and 2026 Fees & Charges By-law 77-2025 confirms no standalone Site Alteration by-law or fee exists."
                ),
                "date_last_updated": TODAY_STR,
            },
            "exemptions": {
                "exemption_status": None,
                "exemption_wording": None,
            },
            "details": dict(NO_BYLAW_CLEAR_DETAILS),
        },
        # ════════════════════════════════════════════════════════════════════
        # GROUP G: Unverified Legacy Records -> NOT KNOWN (Clerk Follow-Up) [3]
        # ════════════════════════════════════════════════════════════════════
        {
            "group": "G: Unverified -> NOT KNOWN",
            "lookup_key": "Marmora and Lake, M",
            "bylaws": {
                "progress": 3,
                "progress_label": "COMMUNICATION NEEDED",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Changed from unverified Yes to NOT KNOWN (COMMUNICATION NEEDED) pending Clerk confirmation. "
                "Stored Adobe share link to 'By-law 2003-22' is inaccessible (note 2003-22 is Loyalist Township's Fill By-law number), "
                "no Site Alteration/Topsoil by-law appears on marmoraandlake.ca/bylaw, and 2026 User Fee By-law 2026-16 contains zero Site Alteration/Fill/Topsoil fees."
            ),
            "exemptions": {
                "exemption_status": "NOT KNOWN",
            },
            "details": {
                "farm_exemption": "NOT KNOWN",
                "nfp_exemption_scope": None,
            },
        },
        {
            "group": "G: Unverified -> NOT KNOWN",
            "lookup_key": "West Grey, M",
            "bylaws": {
                "progress": 3,
                "progress_label": "COMMUNICATION NEEDED",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Changed from unverified Yes to NOT KNOWN (COMMUNICATION NEEDED) pending Clerk confirmation. "
                "Stored link points to an unrelated road-grading news post, 'By-law 120-2018' does not appear in West Grey's 39-bylaw online directory, "
                "and 2026 Fees & Charges By-law 2025-065 contains zero Site Alteration/Fill/Topsoil fees."
            ),
            "exemptions": {
                "exemption_status": "NOT KNOWN",
            },
            "details": {
                "farm_exemption": "NOT KNOWN",
                "nfp_exemption_scope": None,
            },
        },
        {
            "group": "G: Unverified -> NOT KNOWN",
            "lookup_key": "Thunder Bay, C",
            "bylaws": {
                "progress": 3,
                "progress_label": "COMMUNICATION NEEDED",
                "date_last_updated": TODAY_STR,
            },
            "append_other_notes": (
                "Reconciled Nov 27, 2026: Changed from unverified No to NOT KNOWN (COMMUNICATION NEEDED) pending Clerk confirmation. "
                "Stored link for 'By-law 135-1997' points to an unrelated water-fill-station post, no standalone Site Alteration/Fill/Topsoil by-law is "
                "published on thunderbay.ca, and all 21 2026 User Fee Schedules (A–U) contain zero Site Alteration/Fill fees."
            ),
            "exemptions": {
                "exemption_status": "NOT KNOWN",
            },
            "details": {
                "farm_exemption": "NOT KNOWN",
                "nfp_exemption_scope": None,
            },
        },
        # ════════════════════════════════════════════════════════════════════
        # GROUP H: Metadata Hygiene (7 Verified Yes Backfill + Archipelago) [8]
        # ════════════════════════════════════════════════════════════════════
        {
            "group": "H: Metadata Hygiene",
            "lookup_key": "Amherstburg, Tp",
            "bylaws": {
                "date_enacted": "2025-05-12",
                "date_last_updated": TODAY_STR,
            },
            "details": {
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
                "drainage_act_exempt": "Yes",
                "excess_soil_reg_406_19": "Yes",
                "fill_captures_ag_materials": "Sod + Compost/Manure",
            },
        },
        {
            "group": "H: Metadata Hygiene",
            "lookup_key": "London, C",
            "bylaws": {
                "date_enacted": "2024-11-26",
                "date_last_updated": TODAY_STR,
            },
            "exemptions": {
                "exemption_wording": (
                    "Site Alteration By-law No. C.P.-1591-279 (enacted Nov 26, 2024, repealing C.P.-1363-381) Part 2 s. 2.1(c) exempts "
                    "'Site alteration as an incidental part of a normal agricultural practice including such removal as an incidental part of "
                    "sod-farming, greenhouse operations and nurseries for horticultural products, but not including the removal of topsoil for "
                    "sale, exchange or other disposition' (s. 2.1(b) exempts Municipal Act s. 142(5) / Drainage Act works)."
                ),
            },
            "details": {
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
                "drainage_act_exempt": "Yes",
                "excess_soil_reg_406_19": "Yes",
                "exception_wording": (
                    "By-law C.P.-1591-279 Part 2 s. 2.1(b)–(c): exempts Site alteration as an incidental part of a normal agricultural "
                    "practice (excluding topsoil removal for sale/exchange/disposition) and Municipal Act s. 142(5) / Drainage Act works."
                ),
            },
        },
        {
            "group": "H: Metadata Hygiene",
            "lookup_key": "Niagara-on-the-Lake, Tp",
            "bylaws": {
                "bylaw_link": "https://www.notl.com/sites/default/files/2026-03/By-law%202026-007%20-%20Site%20Alteration%20By-law_0.pdf",
                "date_enacted": "2026-02-24",
                "date_last_updated": TODAY_STR,
            },
            "exemptions": {
                "exemption_wording": (
                    "Site Alteration By-law No. 2026-007 (passed Feb 24, 2026, repealing 3941-05) s. 14(g) exempts 'Any work pursuant to "
                    "Normal Farm Practice with a setback of 3.05 m (10 ft) or greater from all property lines that does not change the "
                    "direction, rate or quality of runoff that results in a detrimental effect on neighbouring properties' (subject to 48-hour "
                    "prior written notice under s. 15; s. 14(f) exempts tile drainage with 7-day notice)."
                ),
            },
            "details": {
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
                "drainage_act_exempt": "Yes",
                "excess_soil_reg_406_19": "Yes",
                "exception_wording": (
                    "By-law 2026-007 s. 14(g): exempts any work pursuant to Normal Farm Practice with >=3.05 m (10 ft) property-line setback "
                    "and no detrimental runoff change (48h notice under s. 15; no m³ cap); s. 14(f) exempts tile drainage."
                ),
            },
        },
        {
            "group": "H: Metadata Hygiene",
            "lookup_key": "Southwold, Tp",
            "bylaws": {
                "bylaw_link": "https://www.southwold.ca/living-here/by-laws/site-alteration-by-law",
                "date_last_updated": TODAY_STR,
            },
            "exemptions": {
                "exemption_wording": (
                    "Site Alteration By-law No. 2023-27 s. 2.1 limits geographic application solely to lands subject to a draft plan of "
                    "subdivision, AND s. 6.1(c) explicitly exempts 'Normal farm practices as defined in section 1.1 of the Farming and Food "
                    "Production Protection Act, 1998' (s. 6.1(d) exempts Municipal Act s. 142(5) / Drainage Act works)."
                ),
            },
            "details": {
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
                "drainage_act_exempt": "Yes",
                "exception_wording": (
                    "By-law 2023-27 s. 2.1 (draft plan of subdivision lands only) & s. 6.1(c)–(d): exempts Normal farm practices (FFPPA s. 1.1) and Municipal Act s. 142(5) / Drainage Act works."
                ),
            },
        },
        {
            "group": "H: Metadata Hygiene",
            "lookup_key": "Timmins, C",
            "bylaws": {
                "bylaw_link": "https://mattagamiregion.ca/wp-content/uploads/2020/01/2019-8343-Site-Alteration-By-Law.pdf",
                "date_last_updated": TODAY_STR,
            },
            "details": {
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
                "drainage_act_exempt": "Yes",
                "exception_wording": (
                    "Site Alteration By-law 2019-8343 s. 3.4 exempts 'the placement and/or removal of topsoil as an incidental part of a "
                    "normal agricultural practices including, sod farming, greenhouse operations and nurseries for horticultural products'; "
                    "s. 3.1.6 exempts Drainage Act / Tile Drainage Act works."
                ),
            },
        },
        {
            "group": "H: Metadata Hygiene",
            "lookup_key": "Uxbridge, Tp",
            "bylaws": {
                "date_last_updated": TODAY_STR,
            },
            "details": {
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
            },
        },
        {
            "group": "H: Metadata Hygiene",
            "lookup_key": "Whitchurch-Stouffville, Tp",
            "bylaws": {
                "bylaw_link": "https://whitchurch.civicweb.net/document/184502/",
                "date_enacted": "2024-04-24",
                "date_last_updated": TODAY_STR,
            },
            "details": {
                "nfp_exemption_scope": "Full NFP / Fill & Grading",
                "exception_wording": (
                    "Site Alteration By-law 2024-037-RE s. 3.1(n) exempts 'Site Alterations that are directly related to a Normal Farm "
                    "Practice that is legally established under the Town's Zoning By-law, including the application of Topsoil for spreading "
                    "over Agricultural Property provided that the Existing Grade of the Property is not increased by more than two hundred "
                    "(200) millimetres' (active FRFOFA/FBRN registration in good standing required; no m³ volume cap)."
                ),
            },
        },
        {
            "group": "H: Metadata Hygiene",
            "lookup_key": "The Archipelago, Tp",
            "bylaws": {
                "progress": 2,
                "progress_label": "COMPLETE",
                "date_last_updated": TODAY_STR,
            },
        },
    ]


def _update_row_with_audit(
    cur: sqlite3.Cursor,
    table_name: str,
    record_id: int,
    updates: dict,
    now_iso: str,
) -> int:
    if not updates:
        return 0
    old_row = dict(cur.execute(f'SELECT * FROM "{table_name}" WHERE id = ?', (record_id,)).fetchone())
    changes = 0
    for col, new_val in updates.items():
        old_val = old_row.get(col)
        if old_val != new_val:
            cur.execute(f'UPDATE "{table_name}" SET "{col}" = ? WHERE id = ?', (new_val, record_id))
            cur.execute(
                """
                INSERT INTO audit_log (timestamp, user_name, table_name, record_id, field_name, old_value, new_value)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    now_iso,
                    AUDIT_USER,
                    table_name,
                    record_id,
                    col,
                    str(old_val) if old_val is not None else None,
                    str(new_val) if new_val is not None else None,
                ),
            )
            changes += 1
    return changes


def get_status_counts(cur: sqlite3.Cursor) -> dict:
    rows = cur.execute(
        """
        SELECT COALESCE(e.exemption_status, 'N/A (No Bylaw)') AS st, COUNT(*) AS n
        FROM bylaws b
        LEFT JOIN bylaw_exemptions e ON e.bylaw_id = b.id
        WHERE b.category = 'SITE_ALT'
        GROUP BY st
        """
    ).fetchall()
    return {r["st"]: r["n"] for r in rows}


def run_reconciliation(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    before_counts = get_status_counts(cur)
    print("BEFORE SITE_ALT exemption_status counts:", before_counts)

    specs = build_reconciliation_specs()
    assert len(specs) == 42, f"Expected 42 specs, got {len(specs)}"
    keys = [s["lookup_key"] for s in specs]
    assert len(keys) == len(set(keys)), "Duplicate lookup_key in reconciliation specs!"

    now_iso = datetime.datetime.now().isoformat(timespec="seconds")
    total_fields = 0
    munis_changed = 0
    group_counts = Counter()

    for spec in specs:
        lk = spec["lookup_key"]
        row = cur.execute(
            """
            SELECT m.id AS muni_id, m.lookup_key, b.id AS bylaw_id, b.other_notes,
                   e.id AS exemption_id, d.id AS detail_id
            FROM municipalities m
            JOIN bylaws b ON b.municipality_id = m.id AND b.category = 'SITE_ALT'
            JOIN bylaw_exemptions e ON e.bylaw_id = b.id
            JOIN details_site_alt d ON d.bylaw_id = b.id
            WHERE m.lookup_key = ?
            """,
            (lk,),
        ).fetchone()
        if not row:
            raise ValueError(f"Municipality not found in SITE_ALT: {lk}")

        bylaw_updates = dict(spec.get("bylaws", {}))
        append_note = spec.get("append_other_notes")
        if append_note:
            existing_notes = (row["other_notes"] or "").strip()
            if append_note not in existing_notes:
                bylaw_updates["other_notes"] = (
                    f"{existing_notes}\n\n{append_note}" if existing_notes else append_note
                )

        c1 = _update_row_with_audit(cur, "bylaws", row["bylaw_id"], bylaw_updates, now_iso)
        c2 = _update_row_with_audit(cur, "bylaw_exemptions", row["exemption_id"], spec.get("exemptions", {}), now_iso)
        c3 = _update_row_with_audit(cur, "details_site_alt", row["detail_id"], spec.get("details", {}), now_iso)

        row_total = c1 + c2 + c3
        if row_total > 0:
            munis_changed += 1
            total_fields += row_total
        group_counts[spec["group"]] += 1

    # Integrity assertions BEFORE commit!
    mismatches = cur.execute(
        """
        SELECT m.lookup_key, e.exemption_status, d.farm_exemption
        FROM municipalities m
        JOIN bylaws b ON b.municipality_id = m.id AND b.category = 'SITE_ALT'
        JOIN bylaw_exemptions e ON e.bylaw_id = b.id
        JOIN details_site_alt d ON d.bylaw_id = b.id
        WHERE COALESCE(e.exemption_status, '') != COALESCE(d.farm_exemption, '')
        """
    ).fetchall()
    assert len(mismatches) == 0, f"Lockstep mismatch found: {[dict(r) for r in mismatches]}"

    prog_mismatches = cur.execute(
        """
        SELECT m.lookup_key, b.progress_label, d.fee_verification_status
        FROM municipalities m
        JOIN bylaws b ON b.municipality_id = m.id AND b.category = 'SITE_ALT'
        JOIN details_site_alt d ON d.bylaw_id = b.id
        WHERE (b.progress_label = 'NO BY-LAW IN PLACE' AND d.fee_verification_status != 'N/A (No Bylaw)')
           OR (b.progress_label != 'NO BY-LAW IN PLACE' AND d.fee_verification_status = 'N/A (No Bylaw)')
        """
    ).fetchall()
    assert len(prog_mismatches) == 0, f"progress_label mismatch found: {[dict(r) for r in prog_mismatches]}"

    pending_fee = cur.execute(
        """
        SELECT COUNT(*) AS n FROM details_site_alt
        WHERE COALESCE(fee_verification_status, 'Pending') = 'Pending'
        """
    ).fetchone()["n"]
    assert pending_fee == 0, f"Unexpected Pending fee_verification_status rows: {pending_fee}"

    conn.commit()
    after_counts = get_status_counts(cur)
    print(f"Reconciled {len(specs)} municipalities ({munis_changed} modified, {total_fields} field writes).")
    for grp, cnt in sorted(group_counts.items()):
        print(f"  {grp}: {cnt}")
    print("AFTER  SITE_ALT exemption_status counts:", after_counts)
    print("Lockstep & progress_label integrity checks: [PASS] (0 mismatches, 0 pending fees)")


def main() -> None:
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    try:
        run_reconciliation(conn)
        export_qa_workbook(
            conn,
            out_path=os.path.join(HERE, "province_wide_site_alt_fees_qa.xlsx"),
            title_label="OFA Municipal Site Alteration & Excess Topsoil Permit Fees — Reconciled Province-Wide QA Workbook (132 Active / 444 Total)",
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
