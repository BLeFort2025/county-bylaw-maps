# -*- coding: utf-8 -*-
"""
import_site_alt_fees_wave1.py — Ingest primary-source verified Wave 1 Site
Alteration & Excess Soil permit fee schedules (81 municipalities) into local
bylaws.db (SQLite) without altering any existing farm exemption statuses, and
export the OFA-branded Wave 1 QA workbook (`wave1_site_alt_fees_qa.xlsx`).

Usage:
    python import_site_alt_fees_wave1.py
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
from collections import Counter

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from site_alt_fees_calc import compute_site_alt_benchmarks, evaluate_site_alt_fee

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB = os.path.join(HERE, "bylaws.db")
WAVE1_JSON = os.path.join(HERE, "wave1_site_alt_fees_verified.json")
QA_XLSX = os.path.join(HERE, "wave1_site_alt_fees_qa.xlsx")

FEE_COLUMNS = [
    "fee_verification_status",
    "fee_year",
    "fees_bylaw_name",
    "fees_bylaw_link",
    "ag_import_fee_status",
    "ag_exempt_volume_cap_m3",
    "out_of_muni_fill_ban",
    "fee_pricing_model",
    "base_fee_small",
    "base_fee_large",
    "per_m3_rate",
    "fee_calc_spec_json",
    "est_fee_500_m3",
    "est_fee_5000_m3",
    "est_fee_15000_m3",
    "security_deposit_terms",
    "peer_review_recovery",
    "fee_formula_notes",
]


def get_exemption_counts(cur: sqlite3.Cursor) -> dict:
    rows = cur.execute(
        """
        SELECT COALESCE(d.farm_exemption, 'N/A'), COUNT(*)
        FROM municipalities m
        LEFT JOIN bylaws b ON b.municipality_id = m.id AND b.category = 'SITE_ALT'
        LEFT JOIN details_site_alt d ON d.bylaw_id = b.id
        GROUP BY COALESCE(d.farm_exemption, 'N/A')
        """
    ).fetchall()
    return {k: v for k, v in rows}


def ingest_wave1(conn: sqlite3.Connection) -> tuple[int, int]:
    cur = conn.cursor()
    before_counts = get_exemption_counts(cur)
    print("Baseline SITE_ALT farm_exemption counts:", before_counts)

    with open(WAVE1_JSON, "r", encoding="utf-8") as fh:
        records = json.load(fh)

    now_iso = datetime.datetime.now().isoformat(timespec="seconds")
    munis_updated = 0
    fields_updated = 0

    for rec in records:
        muni_name = rec["municipality"]
        fields = dict(rec["fields"])
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
            raise ValueError(f"Municipality not found in SITE_ALT details: {muni_name}")

        detail_id = row["detail_id"]
        old_row = dict(cur.execute("SELECT * FROM details_site_alt WHERE id = ?", (detail_id,)).fetchone())

        row_changes = 0
        for col in FEE_COLUMNS:
            if col not in fields:
                continue
            new_val = fields[col]
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
                        "site_alt_fees_wave1",
                        "details_site_alt",
                        detail_id,
                        col,
                        str(old_val) if old_val is not None else None,
                        str(new_val) if new_val is not None else None,
                    ),
                )
                row_changes += 1
                fields_updated += 1

        if row_changes > 0:
            munis_updated += 1

    # Also refresh pilot benchmarks deterministically (in case calculator rules improved)
    pilot_rows = cur.execute(
        """
        SELECT d.id, m.name, d.*
        FROM municipalities m
        JOIN bylaws b ON b.municipality_id = m.id AND b.category = 'SITE_ALT'
        JOIN details_site_alt d ON d.bylaw_id = b.id
        WHERE d.fee_verification_status LIKE 'Verified%'
        """
    ).fetchall()
    for prow in pilot_rows:
        d = dict(prow)
        bm = compute_site_alt_benchmarks(d)
        for col, new_val in bm.items():
            if d.get(col) != new_val:
                cur.execute(f'UPDATE details_site_alt SET "{col}" = ? WHERE id = ?', (new_val, d["id"]))
                cur.execute(
                    """
                    INSERT INTO audit_log (timestamp, user_name, table_name, record_id, field_name, old_value, new_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        now_iso,
                        "site_alt_fees_wave1",
                        "details_site_alt",
                        d["id"],
                        col,
                        str(d.get(col)) if d.get(col) is not None else None,
                        str(new_val) if new_val is not None else None,
                    ),
                )
                fields_updated += 1

    after_counts = get_exemption_counts(cur)
    assert before_counts == after_counts, f"Exemption counts changed! {before_counts} -> {after_counts}"
    conn.commit()
    print(f"Ingested {len(records)} Wave 1 records ({munis_updated} updated, {fields_updated} field writes).")
    print("Verified unchanged SITE_ALT farm_exemption counts:", after_counts)
    return munis_updated, fields_updated


def export_qa_workbook(
    conn: sqlite3.Connection,
    out_path: str | None = None,
    title_label: str | None = None,
) -> None:
    """Export OFA-branded Site Alteration & Excess Soil Fees QA Workbook."""
    target_xlsx = out_path or QA_XLSX
    cur = conn.cursor()
    rows = [
        dict(r)
        for r in cur.execute(
            """
            SELECT m.geographic_area, m.name AS municipality, m.municipal_status,
                   b.bylaw_name AS sa_bylaw_name, b.bylaw_link AS sa_bylaw_link,
                   d.*
            FROM municipalities m
            JOIN bylaws b ON b.municipality_id = m.id AND b.category = 'SITE_ALT'
            JOIN details_site_alt d ON d.bylaw_id = b.id
            ORDER BY m.geographic_area, m.name
            """
        ).fetchall()
    ]

    audited = [r for r in rows if (r.get("fee_verification_status") or "") not in ("Pending", "N/A (No Bylaw)")]
    pending_yes = [r for r in rows if (r.get("fee_verification_status") or "") == "Pending"]
    no_bylaw_cnt = sum(1 for r in rows if (r.get("fee_verification_status") or "") == "N/A (No Bylaw)")
    active_sa_cnt = len(rows) - no_bylaw_cnt

    # OFA Brand Guide 2025-26 Palette
    OFA_RED = "D7182A"
    OFA_SLATE = "334B58"
    OFA_GOLD = "ECA842"
    OFA_CHAMPAGNE = "EDE6DE"
    OFA_SAGE = "2E8B57"
    OFA_LIGHT_RED = "FDE8EA"
    OFA_LIGHT_GREEN = "E6F4EC"
    OFA_LIGHT_GOLD = "FDF4E3"
    OFA_DARK_TEXT = "1F2937"
    WHITE = "FFFFFF"

    thin = Side(border_style="thin", color="D1D5DB")
    border_cell = Border(left=thin, right=thin, top=thin, bottom=thin)

    fill_red = PatternFill("solid", fgColor=OFA_RED)
    fill_slate = PatternFill("solid", fgColor=OFA_SLATE)
    fill_champ = PatternFill("solid", fgColor=OFA_CHAMPAGNE)
    fill_white = PatternFill("solid", fgColor=WHITE)
    fill_zebra = PatternFill("solid", fgColor="F9F8F6")
    fill_lred = PatternFill("solid", fgColor=OFA_LIGHT_RED)
    fill_lgrn = PatternFill("solid", fgColor=OFA_LIGHT_GREEN)
    fill_lgld = PatternFill("solid", fgColor=OFA_LIGHT_GOLD)

    f_title = Font(name="Arial", size=14, bold=True, color=WHITE)
    f_sub = Font(name="Arial", size=9.5, italic=False, color=WHITE)
    f_sec = Font(name="Arial", size=11, bold=True, color=OFA_SLATE)
    f_th = Font(name="Arial", size=9.5, bold=True, color=WHITE)
    f_td = Font(name="Arial", size=9, color=OFA_DARK_TEXT)
    f_td_b = Font(name="Arial", size=9, bold=True, color=OFA_DARK_TEXT)
    f_link = Font(name="Arial", size=9, color="1D4ED8", underline="single")

    wb = openpyxl.Workbook()

    # ── Sheet 1: Executive Summary & Durham Focus ────────────────────────────
    ws = wb.active
    ws.title = "Executive Summary & Durham"
    ws.views.sheetView[0].showGridLines = True

    today_str = datetime.date.today().isoformat()
    ws.merge_cells("A1:J1")
    ws["A1"] = title_label or "OFA Municipal Site Alteration & Excess Topsoil Permit Fees — Province-Wide QA Workbook"
    ws["A1"].font = f_title
    ws["A1"].fill = fill_red
    ws["A1"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 28

    ws.merge_cells("A2:J2")
    ws["A2"] = (
        f"Province-Wide Audit of Ontario Site Alteration & Excess Soil By-laws | "
        f"{len(audited)} of {active_sa_cnt} Active Site Alteration Municipalities Audited ({len(rows)} Total Ontario Municipalities) | Primary Enacted Sources Only | Generated {today_str}"
    )
    ws["A2"].font = f_sub
    ws["A2"].fill = fill_slate
    ws["A2"].alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 20

    # Summary KPI block
    ws["A4"] = "Province-Wide Audit & Coverage Summary"
    ws["A4"].font = f_sec

    fvs_counts = Counter(r["fee_verification_status"] for r in audited)
    ags_counts = Counter(r["ag_import_fee_status"] for r in audited)
    pm_counts = Counter(r["fee_pricing_model"] for r in audited)
    ban_counts = Counter(r["out_of_muni_fill_ban"] for r in audited)

    verified_cnt = sum(v for k, v in fvs_counts.items() if k.startswith("Verified"))
    not_pub_cnt = fvs_counts.get("Not Published Online", 0)
    vol_15k = sorted(r["est_fee_15000_m3"] for r in audited if r.get("est_fee_15000_m3") is not None)
    nonzero_15k = [v for v in vol_15k if v > 0]
    if vol_15k:
        mid = len(vol_15k) // 2
        med_15k = vol_15k[mid] if len(vol_15k) % 2 == 1 else (vol_15k[mid - 1] + vol_15k[mid]) / 2.0
    else:
        med_15k = 0.0

    strict_ban_names = sorted(r["municipality"] for r in audited if r.get("out_of_muni_fill_ban") == "Yes")
    restricted_names = sorted(r["municipality"] for r in audited if r.get("out_of_muni_fill_ban") == "Restricted")
    fe_counts = Counter((r.get("farm_exemption") or "Unknown") for r in audited)

    kpis = [
        ("Total Ontario Municipalities in Database", len(rows), f"{active_sa_cnt} with Active Site Alteration By-laws; {no_bylaw_cnt} N/A (No By-law)"),
        ("Province-Wide Fee Audit Coverage (Active Site Alteration By-laws)", f"{len(audited)} / {active_sa_cnt}", f"{verified_cnt} Primary-Source Verified ({verified_cnt/len(audited)*100:.1f}%); {not_pub_cnt} Not Published Online; {len(pending_yes)} Pending"),
        ("Reconciled DB Farm Exemption Breakdown (Active Site Alt By-laws)", f"{fe_counts['Yes']} Yes / {fe_counts['Partial']} Partial", f"Yes (Full NFP): {fe_counts['Yes']} | Partial (Statutory/Capped): {fe_counts['Partial']} | No: {fe_counts['No']} | NOT KNOWN: {fe_counts['NOT KNOWN']}"),
        ("Ag Clean-Topsoil Import: Exempt ($0) or $0 App Waiver", ags_counts["Exempt ($0)"] + ags_counts["Waiver Available ($0 App Fee)"], f"{ags_counts['Exempt ($0)']} Exempt ($0), {ags_counts['Waiver Available ($0 App Fee)']} Waiver ($0 App Fee)"),
        ("Ag Clean-Topsoil Import: Exempt up to Cap / Reduced Farm Tier", ags_counts["Exempt up to Volume Cap"] + ags_counts["Reduced Farm Tier"], f"{ags_counts['Exempt up to Volume Cap']} Volume-Capped Exemption, {ags_counts['Reduced Farm Tier']} Reduced Farm Tier"),
        ("Ag Clean-Topsoil Import: Standard Commercial Rate", ags_counts["Standard Commercial Rate"], "No farm-specific fee relief (flat, area-based, or volumetric $/m³)"),
        ("Volumetric $/m³ Fee Schedules (Base/Tiered + $/m³)", pm_counts["Tiered Volume + Per m³"] + pm_counts["Base + Per m³"] + pm_counts["Per m³ Only"], "Directly escalate total cost with cubic metres of clean topsoil imported"),
        ("Flat-Fee or Reduced Farm Flat-Fee Schedules ($0/m³)", pm_counts["Flat Fee"] + pm_counts["Reduced Farm Flat Fee"], "Predictable permit fee regardless of clean topsoil volume"),
        ("Area-Based ($/ha) Schedules", pm_counts["Base + Per Hectare"], "Priced per disturbed hectare rather than cubic metres (m³ benchmarks left blank)"),
        ("Strict Out-of-Municipality Fill Ban / Local-Source Restriction", ban_counts["Yes"] + ban_counts["Restricted"], f"Strict Ban ({ban_counts['Yes']}): {', '.join(strict_ban_names)}; Origin Restricted ({ban_counts['Restricted']}): {', '.join(restricted_names)}"),
        ("Median Estimated Permit Fee at 15,000 m³ (Across Volumetric/Flat/Exempt Munis)", f"${med_15k:,.2f}", f"Range: $0.00 to ${max(nonzero_15k):,.2f} across {len(vol_15k)} comparable municipalities"),
    ]

    for idx, (label, val, note) in enumerate(kpis, start=5):
        ws.cell(idx, 1, label).font = f_td_b
        c_val = ws.cell(idx, 4, val)
        c_val.font = f_td_b
        c_val.alignment = Alignment(horizontal="right")
        ws.merge_cells(start_row=idx, start_column=1, end_row=idx, end_column=3)
        ws.merge_cells(start_row=idx, start_column=5, end_row=idx, end_column=10)
        ws.cell(idx, 5, note).font = f_td
        row_fill = fill_champ if idx % 2 == 1 else fill_white
        for c in range(1, 11):
            ws.cell(idx, c).fill = row_fill
            ws.cell(idx, c).border = border_cell

    # ── Durham Region Focus Table (Willowtree Farms / Clarington Benchmark) ──
    d_start = 18
    ws.cell(d_start, 1, "Durham Region Clean-Topsoil Permit Fee Comparison (100% Verified — Incl. 14,000 m³ Willowtree Farms Scenario)").font = f_sec
    d_hdrs = [
        "Municipality", "Fee Year", "Ag Import Status", "Pricing Model",
        "Per m³ Rate", "Est. 500 m³", "Est. 5,000 m³", "Est. 14,000 m³*",
        "Est. 15,000 m³", "Out-of-Muni Ban & Key Notes",
    ]
    for ci, h in enumerate(d_hdrs, 1):
        cell = ws.cell(d_start + 1, ci, h)
        cell.font = f_th
        cell.fill = fill_slate
        cell.alignment = Alignment(horizontal="center" if ci >= 2 and ci <= 9 else "left", vertical="center", wrap_text=True)
        cell.border = border_cell
    ws.row_dimensions[d_start + 1].height = 24

    durham = [r for r in audited if r["geographic_area"] == "Durham"]
    durham.sort(key=lambda r: (r["est_fee_15000_m3"] is None, -(r["est_fee_15000_m3"] or -1), r["municipality"]))

    for idx, r in enumerate(durham, start=d_start + 2):
        e14 = evaluate_site_alt_fee(r, 14000.0)
        vals = [
            r["municipality"],
            r["fee_year"],
            r["ag_import_fee_status"],
            r["fee_pricing_model"],
            r["per_m3_rate"],
            r["est_fee_500_m3"],
            r["est_fee_5000_m3"],
            e14,
            r["est_fee_15000_m3"],
            f"Ban: {r['out_of_muni_fill_ban']} | {(r['fees_bylaw_name'] or '')}",
        ]
        is_clar = r["municipality"] == "Clarington"
        is_free = (r["est_fee_15000_m3"] == 0.0)
        rfill = fill_lred if is_clar else (fill_lgrn if is_free else (fill_zebra if idx % 2 == 0 else fill_white))
        for ci, v in enumerate(vals, 1):
            c = ws.cell(idx, ci, v if v is not None else ("Area ($/ha)" if "Hectare" in (r["fee_pricing_model"] or "") else "—"))
            c.font = f_td_b if (is_clar or ci == 1) else f_td
            c.fill = rfill
            c.border = border_cell
            if ci == 5 and isinstance(v, (int, float)):
                c.number_format = "$#,##0.00"
                c.alignment = Alignment(horizontal="right")
            elif ci in (6, 7, 8, 9) and isinstance(v, (int, float)):
                c.number_format = "$#,##0.00"
                c.alignment = Alignment(horizontal="right")
            elif ci == 2:
                c.alignment = Alignment(horizontal="center")
            elif ci == 10:
                c.alignment = Alignment(wrap_text=True)

    fn_row = d_start + 2 + len(durham)
    ws.merge_cells(start_row=fn_row, start_column=1, end_row=fn_row, end_column=10)
    ws.cell(fn_row, 1, "*14,000 m³ corresponds to Jordan MacKay / Willowtree Farms' ~$30,000 Clarington estimate ($2,000 large base + 14,000 m³ × $2.00/m³ = $30,000; note Clarington also bans out-of-municipality fill).").font = Font(name="Arial", size=8.5, italic=True, color="4B5563")

    # ── Top 15 Highest-Cost Municipalities Across Ontario (15,000 m³) ────────
    t_start = fn_row + 2
    ws.cell(t_start, 1, "Top 15 Highest-Cost Audited Ontario Municipalities for Clean-Topsoil Import (Ranked by 15,000 m³ Estimate)").font = f_sec
    t_hdrs = [
        "Rank", "Municipality", "County / Region", "Ag Import Status", "Pricing Model",
        "Base (Large)", "Per m³ Rate", "Est. 500 m³", "Est. 5,000 m³", "Est. 15,000 m³",
    ]
    for ci, h in enumerate(t_hdrs, 1):
        cell = ws.cell(t_start + 1, ci, h)
        cell.font = f_th
        cell.fill = fill_red
        cell.alignment = Alignment(horizontal="center" if ci != 2 and ci != 3 else "left", vertical="center", wrap_text=True)
        cell.border = border_cell
    ws.row_dimensions[t_start + 1].height = 24

    ranked = sorted(
        [r for r in audited if (r.get("est_fee_15000_m3") or 0) > 0],
        key=lambda r: -r["est_fee_15000_m3"],
    )[:15]
    for rank, r in enumerate(ranked, 1):
        rr = t_start + 1 + rank
        vals = [
            rank, r["municipality"], r["geographic_area"], r["ag_import_fee_status"],
            r["fee_pricing_model"], r["base_fee_large"], r["per_m3_rate"],
            r["est_fee_500_m3"], r["est_fee_5000_m3"], r["est_fee_15000_m3"],
        ]
        is_clar = r["municipality"] == "Clarington"
        rfill = fill_lred if is_clar else (fill_zebra if rank % 2 == 0 else fill_white)
        for ci, v in enumerate(vals, 1):
            c = ws.cell(rr, ci, v if v is not None else "—")
            c.font = f_td_b if (is_clar or ci in (1, 2, 10)) else f_td
            c.fill = rfill
            c.border = border_cell
            if ci in (6, 7, 8, 9, 10) and isinstance(v, (int, float)):
                c.number_format = "$#,##0.00"
                c.alignment = Alignment(horizontal="right")
            elif ci == 1:
                c.alignment = Alignment(horizontal="center")

    col_widths_s1 = [22, 14, 22, 24, 14, 14, 14, 15, 15, 42]
    for ci, w in enumerate(col_widths_s1, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w

    # ── Sheet 2: All Audited Schedules (86) ──────────────────────────────────
    ws2 = wb.create_sheet(title=f"All Audited Schedules ({len(audited)})")
    s2_hdrs = [
        "Geographic Area", "Municipality", "Tier", "DB Farm Exemption",
        "Fee Audit Status", "Fee Year", "Ag Import Fee Status", "Ag Exempt Cap (m³)",
        "Out-of-Muni Fill Ban", "Pricing Model", "Base Small ($)", "Base Large ($)",
        "Per m³ Rate ($/m³)", "Est. 500 m³ ($)", "Est. 5,000 m³ ($)", "Est. 15,000 m³ ($)",
        "Fees By-law / Source Name", "Primary Source URL",
        "Security Deposit Terms", "Peer Review / Cost Recovery", "Verified Formula Notes",
    ]
    for ci, h in enumerate(s2_hdrs, 1):
        c = ws2.cell(1, ci, h)
        c.font = f_th
        c.fill = fill_slate
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border_cell
    ws2.row_dimensions[1].height = 28
    ws2.freeze_panes = "C2"
    ws2.auto_filter.ref = f"A1:{get_column_letter(len(s2_hdrs))}{len(audited)+1}"

    audited_sorted = sorted(
        audited,
        key=lambda r: (
            0 if r["geographic_area"] == "Durham" else 1,
            r["geographic_area"] or "",
            r["municipality"] or "",
        ),
    )

    for ri, r in enumerate(audited_sorted, start=2):
        vals = [
            r["geographic_area"], r["municipality"], r["municipal_status"], r["farm_exemption"],
            r["fee_verification_status"], r["fee_year"], r["ag_import_fee_status"],
            r["ag_exempt_volume_cap_m3"], r["out_of_muni_fill_ban"], r["fee_pricing_model"],
            r["base_fee_small"], r["base_fee_large"], r["per_m3_rate"],
            r["est_fee_500_m3"], r["est_fee_5000_m3"], r["est_fee_15000_m3"],
            r["fees_bylaw_name"], r["fees_bylaw_link"],
            r["security_deposit_terms"], r["peer_review_recovery"], r["fee_formula_notes"],
        ]
        status_str = r["fee_verification_status"] or ""
        if status_str == "Not Published Online":
            rfill = fill_lgld
        elif (r.get("est_fee_15000_m3") or 0) >= 25000:
            rfill = fill_lred
        elif r.get("est_fee_15000_m3") == 0.0:
            rfill = fill_lgrn
        else:
            rfill = fill_zebra if ri % 2 == 0 else fill_white

        for ci, v in enumerate(vals, 1):
            c = ws2.cell(ri, ci, v)
            c.font = f_td_b if ci == 2 else f_td
            c.fill = rfill
            c.border = border_cell
            if ci in (11, 12, 13, 14, 15, 16) and isinstance(v, (int, float)):
                c.number_format = "$#,##0.00"
                c.alignment = Alignment(horizontal="right", vertical="top")
            elif ci == 8 and isinstance(v, (int, float)):
                c.number_format = "#,##0"
                c.alignment = Alignment(horizontal="right", vertical="top")
            elif ci in (4, 6, 9):
                c.alignment = Alignment(horizontal="center", vertical="top")
            elif ci == 18 and isinstance(v, str) and v.startswith("http"):
                c.hyperlink = v
                c.font = f_link
                c.alignment = Alignment(vertical="top")
            else:
                c.alignment = Alignment(vertical="top", wrap_text=(ci >= 17))

    s2_widths = [18, 24, 12, 13, 22, 9, 22, 14, 13, 21, 13, 13, 13, 14, 14, 15, 36, 38, 38, 38, 56]
    for ci, w in enumerate(s2_widths, 1):
        ws2.column_dimensions[get_column_letter(ci)].width = w

    # ── Sheet 3: Gaps, Caps & Transparency Log ───────────────────────────────
    ws3_title = "Gaps, Caps & Clerk Queue" if not pending_yes else "Gaps, Caps & Wave 2 Queue"
    ws3 = wb.create_sheet(title=ws3_title)
    ws3["A1"] = "Audit Transparency Log — Not Published Online & Capped / Non-Volumetric Schedules"
    ws3.merge_cells("A1:G1")
    ws3["A1"].font = f_title
    ws3["A1"].fill = fill_slate
    ws3.row_dimensions[1].height = 26

    ws3["A3"] = "1. Audited Schedules with Not Published Fees or Capped / Non-Volumetric Limits (No Extrapolation Applied)"
    ws3["A3"].font = f_sec
    g_hdrs = ["Geographic Area", "Municipality", "Fee Audit Status", "Pricing Model", "Est. 500 m³", "Est. 5,000 m³", "Audit Finding / Reason for Blank Benchmark(s)"]
    for ci, h in enumerate(g_hdrs, 1):
        c = ws3.cell(4, ci, h)
        c.font = f_th
        c.fill = fill_red
        c.border = border_cell

    special = [
        r for r in audited
        if r["fee_verification_status"] == "Not Published Online"
        or (r["est_fee_15000_m3"] is None and "Hectare" not in (r["fee_pricing_model"] or ""))
    ]
    for idx, r in enumerate(special, start=5):
        vals = [
            r["geographic_area"], r["municipality"], r["fee_verification_status"],
            r["fee_pricing_model"], r["est_fee_500_m3"], r["est_fee_5000_m3"], r["fee_formula_notes"],
        ]
        for ci, v in enumerate(vals, 1):
            c = ws3.cell(idx, ci, v if v is not None else "—")
            c.font = f_td
            c.fill = fill_lgld if r["fee_verification_status"] == "Not Published Online" else fill_champ
            c.border = border_cell
            if ci in (5, 6) and isinstance(v, (int, float)):
                c.number_format = "$#,##0.00"
            c.alignment = Alignment(vertical="top", wrap_text=(ci == 7))

    if pending_yes:
        w2_start = 5 + len(special) + 2
        ws3.cell(w2_start, 1, f"2. Wave 2 Queue — Remaining {len(pending_yes)} Municipalities Already Flagged 'Farm Exempt = Yes' in DB").font = f_sec
        w2_hdrs = ["Geographic Area", "Municipality", "Tier", "DB Farm Exemption", "Site Alteration By-law", "By-law Link", "Wave 2 Status"]
        for ci, h in enumerate(w2_hdrs, 1):
            c = ws3.cell(w2_start + 1, ci, h)
            c.font = f_th
            c.fill = fill_slate
            c.border = border_cell
        for idx, r in enumerate(pending_yes, start=w2_start + 2):
            vals = [
                r["geographic_area"], r["municipality"], r["municipal_status"],
                r["farm_exemption"], r["sa_bylaw_name"], r["sa_bylaw_link"], "Pending Wave 2 Audit",
            ]
            for ci, v in enumerate(vals, 1):
                c = ws3.cell(idx, ci, v)
                c.font = f_td
                c.fill = fill_zebra if idx % 2 == 0 else fill_white
                c.border = border_cell
                if ci == 6 and isinstance(v, str) and v.startswith("http"):
                    c.hyperlink = v
                    c.font = f_link

    for ci, w in enumerate([18, 24, 22, 22, 16, 26, 68], 1):
        ws3.column_dimensions[get_column_letter(ci)].width = w

    wb.save(target_xlsx)
    print(f"Exported OFA-branded QA workbook: {target_xlsx} ({os.path.getsize(target_xlsx):,} bytes)")


def main() -> None:
    conn = sqlite3.connect(LOCAL_DB)
    conn.row_factory = sqlite3.Row
    try:
        ingest_wave1(conn)
        export_qa_workbook(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
