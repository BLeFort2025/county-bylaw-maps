# -*- coding: utf-8 -*-
"""
seed_site_alt_fees_pilot.py — Seed primary-source verified Site Alteration &
Excess Soil permit fee records into local bylaws.db (SQLite) without modifying
any existing farm exemption statuses.

Every record below is verified directly against enacted municipal bylaws,
consolidated 2025/2026 User Fee / Fees & Charges schedules, or official
municipal Site Alteration Guidelines.
"""

import datetime
import json
import os
import sqlite3

from site_alt_fees_calc import compute_site_alt_benchmarks

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB = os.path.join(HERE, "bylaws.db")

VERIFIED_RECORDS = [
    {
        "municipality": "Clarington",
        "fields": {
            "fee_verification_status": "Verified",
            "fee_year": 2025,
            "fees_bylaw_name": "User Fee By-law 2025-021 (and Site Alteration Agricultural Guide)",
            "fees_bylaw_link": "https://www.clarington.net/homes-and-property/site-alteration-grading-and-drainage/",
            "ag_import_fee_status": "Standard Commercial Rate",
            "ag_exempt_volume_cap_m3": None,
            "out_of_muni_fill_ban": "Yes",
            "fee_pricing_model": "Tiered Volume + Per m³",
            "base_fee_small": 1000.0,
            "base_fee_large": 2000.0,
            "per_m3_rate": 2.00,
            "fee_calc_spec_json": json.dumps({
                "type": "tiered_volume",
                "brackets": [
                    {"up_to_m3": 100, "exclusive_upper": True, "flat_fee": 250.0},
                    {"up_to_m3": 500, "base": 1000.0, "per_m3": 2.00},
                    {"up_to_m3": None, "base": 2000.0, "per_m3": 2.00},
                ],
            }),
            "security_deposit_terms": (
                "$1,000 certified cheque + 100% of approved works/ESC/road-cleaning estimate "
                "(+ 10% contingency + 5% admin + 13% HST) + haul-route road damage deposit"
            ),
            "peer_review_recovery": (
                "O. Reg. 406/19 Qualified Person soil analysis, Soils Management Plan, Grading Plan "
                "(2%–5% grades), ESC & Dust Plans; RPRA Excess Soil Registry required >10,000 m³"
            ),
            "fee_formula_notes": (
                "User Fee By-law 2025-021 (CPI-indexed Jan 1 by Treasurer): Minor Fill (<100 m³) $250 flat "
                "(renewal $125); Small Fill (100–500 m³) $1,000 + $2.00/m³ (renewal $500 + $2/m³); "
                "Large Fill (>500 m³) $2,000 + $2.00/m³ (renewal $1,000 + $2/m³). Deputy CAO may waive fees "
                "in the public interest (By-law 2024-017). No fill may be imported from outside Clarington. "
                "Ag Guide: https://media-003-ca.cdn.govstack.com/clarington-018-ca/media/ibgpmzr1/sitealteration-agriculture-aoda.pdf"
            ),
        },
    },
    {
        "municipality": "Brock",
        "fields": {
            "fee_verification_status": "Verified",
            "fee_year": 2026,
            "fees_bylaw_name": "Consolidated 2026 Fees By-law 3382-2025 (Schedule G, p. 12)",
            "fees_bylaw_link": "https://media-002-ca.cdn.govstack.com/townshipofbrock-011-ca/media/1a2fc2ms/consolidated-2026-fees-bylaw-3382-2025-nov-24-2025-final.pdf",
            "ag_import_fee_status": "Exempt up to Volume Cap",
            "ag_exempt_volume_cap_m3": 1000.0,
            "out_of_muni_fill_ban": "Unknown",
            "fee_pricing_model": "Tiered Volume + Per m³",
            "base_fee_small": 584.23,
            "base_fee_large": 2976.96,
            "per_m3_rate": 3.08,
            "fee_calc_spec_json": json.dumps({
                "type": "exempt_up_to_cap",
                "exempt_cap_m3": 1000.0,
                "charge_basis": "full",
                "above_cap": {
                    "type": "tiered_volume",
                    "brackets": [
                        {"up_to_m3": 500, "base": 584.23, "per_m3": 2.05},
                        {"up_to_m3": None, "base": 2976.96, "per_m3": 3.08},
                    ],
                },
            }),
            "security_deposit_terms": (
                "Min $5,000 (≤500 m³) or $10,000 (>500 m³) breach security + highway/roads security TBD by Director"
            ),
            "peer_review_recovery": (
                "Fill quality testing actual cost + 10% admin; pre-consultation $110–$360 + consultant cost + 10% admin; "
                "Site Alt Agreement $368.44–$789.51; compliance inspection $319.92"
            ),
            "fee_formula_notes": (
                "By-law 3426-2026 s. 7.1 grants an NFP Permit Waiver for active FBRN-registered farms up to 1,000 m³ "
                "in any 12-month period ($0). Above cap (2026 Fees By-law 3382-2025 Sched G, HST exempt): "
                "≤500 m³ = $584.23 + $2.05/m³; >500 m³ = $2,976.96 + $3.08/m³ (plus $789.51 agreement & $319.92 inspection). "
                "Overfill / unpermitted fill: $10.00/m³ and double application fees."
            ),
        },
    },
    {
        "municipality": "Scugog",
        "fields": {
            "fee_verification_status": "Verified (Ag Exempt - $0)",
            "fee_year": 2026,
            "fees_bylaw_name": "2026 Fees and Charges By-law 42-25 (Schedule C, pp. 8–10)",
            "fees_bylaw_link": "https://www.scugog.ca/media/tvbj0dpz/schedule-c-development-services-department.pdf",
            "ag_import_fee_status": "Exempt ($0)",
            "ag_exempt_volume_cap_m3": None,
            "out_of_muni_fill_ban": "Unknown",
            "fee_pricing_model": "Exempt ($0)",
            "base_fee_small": 555.0,
            "base_fee_large": 3249.0,
            "per_m3_rate": 0.0,
            "fee_calc_spec_json": json.dumps({"type": "exempt"}),
            "security_deposit_terms": (
                "Security for agreement breach and highway maintenance TBD by Director (when a permit is required)"
            ),
            "peer_review_recovery": (
                "Peer engineer cost for pre-consultation; fill quality testing actual costs + 25% admin; "
                "external legal/consulting reimbursed on case-by-case basis (when permit applies)"
            ),
            "fee_formula_notes": (
                "By-law 27-26 (passed May 25, 2026) s. 5.2(c) exempts Site Alteration directly related to a Normal Farm "
                "Practice for active FBRN-registered farms in good standing ($0). Additionally, 2026 Fees Schedule C "
                "(By-law 42-25, p. 9) provides a dedicated Agricultural Site Alteration Permit (up to 10,000 m³ of topsoil) "
                "at a flat $555.00 application fee ($0/m³ volumetric fee; $222 extension). By contrast, non-ag commercial "
                "rates are $650 + $2.00/m³ (≤500 m³) and $3,249 + $4.00/m³ (>500–10,000 m³); overfill penalty $32.00/m³."
            ),
        },
    },
    {
        "municipality": "Ajax",
        "fields": {
            "fee_verification_status": "Verified",
            "fee_year": 2021,
            "fees_bylaw_name": "In Sediment & Erosion Control By-law 38-2021 (Schedule A)",
            "fees_bylaw_link": "https://ajax.ca/wp-content/uploads/2026/06/Sediment-and-Erosion-Control-By-law-38-2021-Accessible.pdf",
            "ag_import_fee_status": "Standard Commercial Rate",
            "ag_exempt_volume_cap_m3": None,
            "out_of_muni_fill_ban": "Unknown",
            "fee_pricing_model": "Base + Per Hectare",
            "base_fee_small": 2012.10,
            "base_fee_large": 2074.50,
            "per_m3_rate": None,
            "fee_calc_spec_json": json.dumps({
                "type": "area_based",
                "minor_flat": 2012.10,
                "major_base": 2074.50,
                "per_hectare": 942.40,
            }),
            "security_deposit_terms": (
                "Irrevocable Letter of Credit or cash for 100% of estimated cost of site control & mud-tracking measures"
            ),
            "peer_review_recovery": None,
            "fee_formula_notes": (
                "Schedule A of By-law 38-2021 (area-based, not $/m³): Minor Sediment & Erosion Control Permit = "
                "$2,012.10 flat; Major Permit = $2,074.50 + $942.40/hectare. Permit valid 365 days; 100% LOC security. "
                "Note: 2026 Town User Fees schedule should be cross-checked for any CPI updates since 2021."
            ),
        },
    },
    {
        "municipality": "Whitby",
        "fields": {
            # Base flat application fee sits in Whitby's Consolidated Fees & Charges By-law 7220-17 engineering schedule
            # (not printed inside Guideline v16), so keep status Pending so benchmarks are not understated,
            # while storing the verified 2026 $2.30/m³ Road/Inspection fee and Appendix B security schedule.
            "fee_verification_status": "Pending",
            "fee_year": 2026,
            "fees_bylaw_name": "Guideline to Site Alteration v16 (Jan 2026) & Consolidated Fees By-law 7220-17",
            "fees_bylaw_link": "https://www.whitby.ca/media/hupld54u/2026-01-23-guideline-to-site-alteration-v16.pdf",
            "ag_import_fee_status": "Standard Commercial Rate",
            "ag_exempt_volume_cap_m3": None,
            "out_of_muni_fill_ban": "Unknown",
            "fee_pricing_model": "Tiered Volume + Per m³",
            "base_fee_small": None,
            "base_fee_large": None,
            "per_m3_rate": 2.30,
            "fee_calc_spec_json": None,
            "security_deposit_terms": (
                "Cat 3 (≥500 m³): Engineer's ESC estimate + 30% contingency + HST; $5,212 immediate road damage; "
                "15% of Road/Inspection fee overfill security; $2,000 signage; $10,000 soil testing/peer review "
                "(+ $10,000 per additional 50,000 m³)"
            ),
            "peer_review_recovery": (
                "Applicant-retained Qualified Person (O. Reg. 406/19), P.Eng. drawings, Registered Agrology Practitioner "
                "letter justifying topsoil import, and $10,000+ soil testing / peer review security"
            ),
            "fee_formula_notes": (
                "2026 Guideline v16 (p. 43 & Appendix B): Category 3 Large Site Alteration (≥500 m³) charges a "
                "$2.30/m³ Road Damage Contribution / Inspection Fee (2026 rate; sliding-scale 1×/2×/4× overfill penalties) "
                "PLUS flat Application Fee per Consolidated Fees & Charges By-law 7220-17 (base application fee pending "
                "verification from Engineering fee schedule, so total benchmark estimates are intentionally left blank)."
            ),
        },
    },
    {
        "municipality": "Puslinch",
        "fields": {
            "fee_verification_status": "Verified (Ag Tier)",
            "fee_year": 2026,
            "fees_bylaw_name": "In Site Alteration By-law 2023-057 (s. 5.1 NFP Waiver, consolidated Oct 2026)",
            "fees_bylaw_link": "https://puslinch.ca/bylaws/site-alteration/",
            "ag_import_fee_status": "Waiver Available ($0 App Fee)",
            "ag_exempt_volume_cap_m3": None,
            "out_of_muni_fill_ban": "Unknown",
            "fee_pricing_model": "Waiver ($0 App Fee)",
            "base_fee_small": 0.0,
            "base_fee_large": 0.0,
            "per_m3_rate": 0.0,
            "fee_calc_spec_json": json.dumps({"type": "waiver_zero_app"}),
            "security_deposit_terms": "Financial security required per Schedule C of By-law 2023-057 for NFP Waiver",
            "peer_review_recovery": (
                "No application fee for NFP Waiver, but Owner pays all third-party external review costs & recoveries "
                "+ Qualified Person NFP justification report, lab soil testing, Control Plan & haul route agreement"
            ),
            "fee_formula_notes": (
                "By-law 2023-057 (consolidated Oct 7, 2026) s. 5.1(b)(ii): Normal Farm Practice Site Alteration Waiver "
                "carries $0 application fee, but requires a Qualified Person report, O. Reg. 406/19 lab testing, "
                "Schedule C financial security, haul route agreement, and full third-party external review cost recovery."
            ),
        },
    },
]


def main():
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    now_iso = datetime.datetime.now().isoformat(timespec="seconds")

    for rec in VERIFIED_RECORDS:
        muni_name = rec["municipality"]
        fields = dict(rec["fields"])
        # Deterministically compute 500 / 5,000 / 15,000 m³ benchmarks
        benchmarks = compute_site_alt_benchmarks(fields)
        fields.update(benchmarks)

        row = cur.execute(
            """
            SELECT d.id AS detail_id, b.id AS bylaw_id, m.name
            FROM municipalities m
            JOIN bylaws b ON b.municipality_id = m.id AND b.category = 'SITE_ALT'
            JOIN details_site_alt d ON d.bylaw_id = b.id
            WHERE LOWER(m.name) = LOWER(?)
            """,
            (muni_name,),
        ).fetchone()

        if not row:
            print(f"[SKIP] Municipality not found: {muni_name}")
            continue

        detail_id = row["detail_id"]
        old_row = dict(cur.execute("SELECT * FROM details_site_alt WHERE id = ?", (detail_id,)).fetchone())

        updated_cnt = 0
        for col, new_val in fields.items():
            old_val = old_row.get(col)
            if old_val != new_val:
                cur.execute(f'UPDATE details_site_alt SET "{col}" = ? WHERE id = ?', (new_val, detail_id))
                cur.execute(
                    """
                    INSERT INTO audit_log (timestamp, user_name, table_name, record_id, field_name, old_value, new_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso,
                        "site_alt_fees_seed",
                        "details_site_alt",
                        detail_id,
                        col,
                        str(old_val) if old_val is not None else None,
                        str(new_val) if new_val is not None else None,
                    ),
                )
                updated_cnt += 1

        print(
            f"[OK] {row['name']}: updated {updated_cnt} fields | "
            f"status={fields['fee_verification_status']} | ag={fields['ag_import_fee_status']} | "
            f"500m3={fields['est_fee_500_m3']} | 5000m3={fields['est_fee_5000_m3']} | 15000m3={fields['est_fee_15000_m3']}"
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
