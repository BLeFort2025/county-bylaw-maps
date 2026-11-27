"""
fee_charts.py — Publication-grade OFA-branded Altair chart helpers for
Farm Building Permit Fees (BLDG_FEES), Agricultural Development Charges (DC),
and Site Alteration / Excess Soil Fees (SITE_ALT).

Follows OFA Brand Guide 2025-26 palette & executive visual hierarchy:
  - Focal accent: OFA Crimson (#D7182A)
  - Structural/benchmark ink: Pickled Bluewood (#334B58)
  - Inflection/cap/upper-tier accent: OFA Tulip Tree (#ECA842)
  - Farm Exempt ($0): Soft Sage Green (#2E8B57)
  - Muted peer context: Neutral Slate (#CBD5E1) / Upper-Tier Slate (#7C93A0)
  - Typography: Arial, explicit #FFFFFF surface for light/dark theme safety
  - Zero gridlines, zero legend clutter, whole-dollar direct bar labels
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from bldg_fees_calc import evaluate_bldg_fee, OBC_LARGE_FARM_SQFT
from dc_fees_calc import compute_stacked_dc, evaluate_dc_fee
from site_alt_fees_calc import evaluate_site_alt_fee

# Official OFA Brand Guide 2025-26 Palette
OFA_CRIMSON = "#D7182A"
OFA_BLUEWOOD = "#334B58"
OFA_GOLD = "#ECA842"
OFA_CHAMPAGNE = "#EDE6DE"
OFA_SAGE = "#2E8B57"
PEER_GRAY = "#CBD5E1"
PEER_UPPER_SLATE = "#7C93A0"
TEXT_DARK = "#1E293B"
TEXT_MUTED = "#475569"
SURFACE_WHITE = "#FFFFFF"


def _fmt_dollars(val: float | None) -> str:
    if val is None or pd.isna(val):
        return "—"
    return f"${round(float(val)):,}"


def build_peer_bar_chart(
    df: pd.DataFrame,
    focus_muni: str,
    title: str,
    subtitle: str = "",
    median_val: float | None = None,
    median_label: str = "Ontario Median",
    exempt_zero_highlight: bool = False,
    height: int | None = None,
) -> alt.Chart:
    """Build a clean horizontal ranked peer benchmark bar chart.

    Expected columns in `df`:
      - `Municipality` (str)
      - `Fee` (float, non-null)
      - Optional `Detail` (str, for hover tooltip)
      - Optional `IsEstimate` (bool, appends ' (Est.)' to label when True)
    """
    plot_df = df.copy()
    plot_df["Fee"] = pd.to_numeric(plot_df["Fee"], errors="coerce")
    plot_df = plot_df[plot_df["Fee"].notna()].copy()
    plot_df = plot_df.sort_values(["Fee", "Municipality"], ascending=[False, True]).reset_index(drop=True)

    if plot_df.empty:
        return alt.Chart(pd.DataFrame({"msg": ["No comparable numeric schedules in this selection."]})).mark_text(
            font="Arial", fontSize=13, color=TEXT_MUTED
        ).encode(text="msg:N").properties(height=90, background=SURFACE_WHITE)

    def _role(row) -> str:
        if str(row["Municipality"]) == str(focus_muni):
            return "Selected"
        if exempt_zero_highlight and float(row["Fee"]) <= 0.0:
            return "Exempt"
        return "Peer"

    def _bar_label(row) -> str:
        val = float(row["Fee"])
        if exempt_zero_highlight and val <= 0.0:
            return "$0 (Exempt)"
        est_tag = " (Est.)" if bool(row.get("IsEstimate", False)) else ""
        return f"${round(val):,}{est_tag}"

    plot_df["Role"] = plot_df.apply(_role, axis=1)
    plot_df["Label"] = plot_df.apply(_bar_label, axis=1)
    if "Detail" not in plot_df.columns:
        plot_df["Detail"] = ""

    max_fee = float(plot_df["Fee"].max())
    if median_val is not None and pd.notna(median_val):
        max_fee = max(max_fee, float(median_val))
    x_upper = max(max_fee * 1.24, 500.0)

    muni_order = plot_df["Municipality"].tolist()
    chart_h = height if height is not None else max(230, min(720, len(plot_df) * 36 + 76))

    color_scale = alt.Scale(
        domain=["Selected", "Exempt", "Peer"],
        range=[OFA_CRIMSON, OFA_SAGE, PEER_GRAY],
    )

    bars = (
        alt.Chart(plot_df)
        .mark_bar(cornerRadiusEnd=3, size=22)
        .encode(
            y=alt.Y(
                "Municipality:N",
                sort=muni_order,
                title=None,
                axis=alt.Axis(
                    labelFont="Arial",
                    labelFontSize=12,
                    labelColor=TEXT_DARK,
                    labelLimit=220,
                    labelOverlap=False,
                    ticks=False,
                    domain=False,
                    labelPadding=10,
                ),
            ),
            x=alt.X(
                "Fee:Q",
                title=None,
                scale=alt.Scale(domain=[0, x_upper]),
                axis=alt.Axis(
                    format="$,.0f",
                    tickCount=4,
                    grid=False,
                    domainColor="#CBD5E1",
                    labelFont="Arial",
                    labelFontSize=11,
                    labelColor=TEXT_MUTED,
                ),
            ),
            color=alt.Color("Role:N", scale=color_scale, legend=None),
            tooltip=[
                alt.Tooltip("Municipality:N", title="Municipality"),
                alt.Tooltip("Label:N", title="Estimated Fee"),
                alt.Tooltip("Detail:N", title="Pricing Model / Notes"),
            ],
        )
    )

    label_color_scale = alt.Scale(
        domain=["Selected", "Exempt", "Peer"],
        range=[OFA_CRIMSON, OFA_SAGE, TEXT_DARK],
    )

    labels_halo = (
        alt.Chart(plot_df)
        .mark_text(
            align="left",
            baseline="middle",
            dx=6,
            font="Arial",
            fontSize=11.5,
            fontWeight="bold",
            stroke=SURFACE_WHITE,
            strokeWidth=3.5,
            fill=SURFACE_WHITE,
        )
        .encode(
            y=alt.Y("Municipality:N", sort=muni_order),
            x=alt.X("Fee:Q"),
            text=alt.Text("Label:N"),
        )
    )

    labels = (
        alt.Chart(plot_df)
        .mark_text(align="left", baseline="middle", dx=6, font="Arial", fontSize=11.5, fontWeight="bold")
        .encode(
            y=alt.Y("Municipality:N", sort=muni_order),
            x=alt.X("Fee:Q"),
            text=alt.Text("Label:N"),
            color=alt.Color("Role:N", scale=label_color_scale, legend=None),
        )
    )

    layers = []

    if median_val is not None and pd.notna(median_val) and float(median_val) >= 0:
        med_df = pd.DataFrame([{"med": float(median_val), "txt": f"{median_label}: {_fmt_dollars(median_val)}"}])
        rule = (
            alt.Chart(med_df)
            .mark_rule(color=OFA_BLUEWOOD, strokeDash=[5, 4], strokeWidth=1.5, opacity=0.65)
            .encode(x="med:Q")
        )
        _med_align = "right" if float(median_val) > x_upper * 0.72 else "left"
        _med_dx = -5 if _med_align == "right" else 5
        rule_txt = (
            alt.Chart(med_df)
            .mark_text(
                align=_med_align,
                dx=_med_dx,
                dy=-6,
                font="Arial",
                fontSize=11,
                fontWeight="bold",
                color=OFA_BLUEWOOD,
            )
            .encode(x="med:Q", y=alt.value(-4), text="txt:N")
        )
        # Put rule BEHIND bars and labels so it never cuts across dollar text
        layers.extend([rule, bars, labels_halo, labels, rule_txt])
    else:
        layers.extend([bars, labels_halo, labels])

    title_params = alt.TitleParams(
        text=title,
        anchor="start",
        font="Arial",
        fontSize=15,
        fontWeight="bold",
        color=OFA_BLUEWOOD,
        subtitleFont="Arial",
        subtitleFontSize=12,
        subtitleColor=TEXT_MUTED,
        offset=22,
        **({"subtitle": subtitle} if subtitle else {}),
    )

    return (
        alt.layer(*layers)
        .resolve_scale(color="independent")
        .properties(
            title=title_params,
            height=chart_h,
            background=SURFACE_WHITE,
            padding={"top": 14, "left": 8, "right": 18, "bottom": 8},
        )
        .configure_view(strokeWidth=0)
        .configure_axis(grid=False)
    )


def build_bldg_scaling_chart(
    spec_payload: dict,
    muni_name: str,
    is_livestock: bool = True,
    assumed_cost: float | None = None,
    highlight_sqft: int = 10000,
    show_obc_marker: bool = True,
) -> alt.Chart | None:
    """Build a building-size scaling curve from 1,500 to 30,000 sq. ft."""
    points = []
    for sq in range(1500, 30500, 500):
        val = evaluate_bldg_fee(spec_payload, float(sq), is_livestock=is_livestock, assumed_cost_per_sqft=assumed_cost)
        if val is not None:
            points.append({"SqFt": sq, "Fee": float(val), "FeeLabel": _fmt_dollars(val)})

    if not points:
        return None

    curve_df = pd.DataFrame(points)
    max_fee = float(curve_df["Fee"].max())
    y_upper = max(max_fee * 1.18, 500.0)
    struct_lbl = "Livestock Barn" if is_livestock else "Equipment / Drive Shed"

    line = (
        alt.Chart(curve_df)
        .mark_line(color=OFA_CRIMSON, strokeWidth=2.8)
        .encode(
            x=alt.X(
                "SqFt:Q",
                title="Building Footprint (sq. ft.)",
                axis=alt.Axis(
                    format=",.0f",
                    tickCount=5,
                    grid=False,
                    labelFont="Arial",
                    titleFont="Arial",
                    labelColor=TEXT_MUTED,
                    titleColor=TEXT_DARK,
                ),
            ),
            y=alt.Y(
                "Fee:Q",
                title=None,
                scale=alt.Scale(domain=[0, y_upper]),
                axis=alt.Axis(
                    format="$,.0f",
                    tickCount=4,
                    grid=False,
                    labelFont="Arial",
                    labelColor=TEXT_MUTED,
                ),
            ),
            tooltip=[
                alt.Tooltip("SqFt:Q", title="Footprint (ft²)", format=",.0f"),
                alt.Tooltip("FeeLabel:N", title="Estimated Permit Fee"),
            ],
        )
    )

    layers = [line]

    if show_obc_marker:
        obc_df = pd.DataFrame([{"x": OBC_LARGE_FARM_SQFT, "lbl": "OBC 600 m² (6,458 ft²)"}])
        layers.append(
            alt.Chart(obc_df)
            .mark_rule(color=OFA_GOLD, strokeDash=[4, 4], strokeWidth=1.6)
            .encode(x="x:Q")
        )
        layers.append(
            alt.Chart(obc_df)
            .mark_text(align="left", dx=5, dy=12, font="Arial", fontSize=10.5, fontWeight="bold", color="#9A6700")
            .encode(x="x:Q", y=alt.value(10), text="lbl:N")
        )

    hi_val = evaluate_bldg_fee(spec_payload, float(highlight_sqft), is_livestock=is_livestock, assumed_cost_per_sqft=assumed_cost)
    if hi_val is not None:
        hi_df = pd.DataFrame([{"SqFt": int(highlight_sqft), "Fee": float(hi_val), "lbl": f"{int(highlight_sqft):,} ft²: {_fmt_dollars(hi_val)}"}])
        # Place callout in open upper-left space above rising curve (or upper-right near left edge)
        _align = "right" if highlight_sqft >= 7000 else "left"
        _dx = -10 if _align == "right" else 10
        layers.append(
            alt.Chart(hi_df)
            .mark_point(color=OFA_CRIMSON, fill=SURFACE_WHITE, size=90, strokeWidth=2.6)
            .encode(x="SqFt:Q", y="Fee:Q")
        )
        layers.append(
            alt.Chart(hi_df)
            .mark_text(
                align=_align,
                dx=_dx,
                dy=-12,
                font="Arial",
                fontSize=11.5,
                fontWeight="bold",
                stroke=SURFACE_WHITE,
                strokeWidth=4,
                fill=SURFACE_WHITE,
            )
            .encode(x="SqFt:Q", y="Fee:Q", text="lbl:N")
        )
        layers.append(
            alt.Chart(hi_df)
            .mark_text(
                align=_align,
                dx=_dx,
                dy=-12,
                font="Arial",
                fontSize=11.5,
                fontWeight="bold",
                color=OFA_CRIMSON,
            )
            .encode(x="SqFt:Q", y="Fee:Q", text="lbl:N")
        )

    return (
        alt.layer(*layers)
        .properties(
            title=alt.TitleParams(
                text=f"How {muni_name} Permit Fees Scale by Size ({struct_lbl})",
                subtitle="Highlights minimum permit floors, stepped thresholds, and 2024 OBC Group G splits",
                anchor="start",
                font="Arial",
                fontSize=14,
                fontWeight="bold",
                color=OFA_BLUEWOOD,
                subtitleFont="Arial",
                subtitleFontSize=11.5,
                subtitleColor=TEXT_MUTED,
            ),
            height=260,
            background=SURFACE_WHITE,
        )
        .configure_view(strokeWidth=0)
        .configure_axis(grid=False)
    )


def build_site_alt_scaling_chart(
    spec_payload: dict,
    muni_name: str,
    highlight_vol: int = 15000,
    exempt_cap_m3: float | None = None,
) -> alt.Chart | None:
    """Build a clean-topsoil volume scaling curve from 500 to 25,000 m³."""
    vols = sorted(set(list(range(500, 25500, 500)) + [int(highlight_vol)]))
    if exempt_cap_m3 is not None and pd.notna(exempt_cap_m3) and 50 <= float(exempt_cap_m3) <= 25000:
        cap_i = int(round(float(exempt_cap_m3)))
        vols = sorted(set(vols + [max(50, cap_i), min(25000, cap_i + 1)]))

    points = []
    for v in vols:
        val = evaluate_site_alt_fee(spec_payload, float(v))
        if val is not None:
            points.append({
                "Volume": v,
                "Loads": f"~{v // 10:,} loads",
                "Fee": float(val),
                "FeeLabel": _fmt_dollars(val),
            })

    if not points:
        return None

    curve_df = pd.DataFrame(points)
    max_fee = float(curve_df["Fee"].max())
    y_upper = max(max_fee * 1.18, 500.0)

    line = (
        alt.Chart(curve_df)
        .mark_line(color=OFA_CRIMSON, strokeWidth=2.8)
        .encode(
            x=alt.X(
                "Volume:Q",
                title="Imported Clean Topsoil / Fill Volume (m³ · ~10 m³ per tri-axle load)",
                axis=alt.Axis(
                    format=",.0f",
                    tickCount=5,
                    grid=False,
                    labelFont="Arial",
                    titleFont="Arial",
                    labelColor=TEXT_MUTED,
                    titleColor=TEXT_DARK,
                ),
            ),
            y=alt.Y(
                "Fee:Q",
                title=None,
                scale=alt.Scale(domain=[0, y_upper]),
                axis=alt.Axis(
                    format="$,.0f",
                    tickCount=4,
                    grid=False,
                    labelFont="Arial",
                    labelColor=TEXT_MUTED,
                ),
            ),
            tooltip=[
                alt.Tooltip("Volume:Q", title="Volume (m³)", format=",.0f"),
                alt.Tooltip("Loads:N", title="Approx. Truckloads"),
                alt.Tooltip("FeeLabel:N", title="Estimated Permit Fee"),
            ],
        )
    )

    layers = [line]

    if exempt_cap_m3 is not None and pd.notna(exempt_cap_m3) and 50 <= float(exempt_cap_m3) <= 24500:
        cap_v = float(exempt_cap_m3)
        cap_df = pd.DataFrame([{"x": cap_v, "lbl": f"Ag Exempt Cap: {round(cap_v):,} m³"}])
        layers.append(
            alt.Chart(cap_df)
            .mark_rule(color=OFA_GOLD, strokeDash=[4, 4], strokeWidth=1.8)
            .encode(x="x:Q")
        )
        layers.append(
            alt.Chart(cap_df)
            .mark_text(align="left", dx=5, dy=12, font="Arial", fontSize=10.5, fontWeight="bold", color="#9A6700")
            .encode(x="x:Q", y=alt.value(10), text="lbl:N")
        )

    hi_val = evaluate_site_alt_fee(spec_payload, float(highlight_vol))
    if hi_val is not None:
        hi_df = pd.DataFrame([{"Volume": int(highlight_vol), "Fee": float(hi_val), "lbl": f"{int(highlight_vol):,} m³: {_fmt_dollars(hi_val)}"}])
        _align = "right" if highlight_vol >= 6000 else "left"
        _dx = -10 if _align == "right" else 10
        layers.append(
            alt.Chart(hi_df)
            .mark_point(color=OFA_CRIMSON, fill=SURFACE_WHITE, size=90, strokeWidth=2.6)
            .encode(x="Volume:Q", y="Fee:Q")
        )
        layers.append(
            alt.Chart(hi_df)
            .mark_text(
                align=_align,
                dx=_dx,
                dy=-12,
                font="Arial",
                fontSize=11.5,
                fontWeight="bold",
                stroke=SURFACE_WHITE,
                strokeWidth=4,
                fill=SURFACE_WHITE,
            )
            .encode(x="Volume:Q", y="Fee:Q", text="lbl:N")
        )
        layers.append(
            alt.Chart(hi_df)
            .mark_text(
                align=_align,
                dx=_dx,
                dy=-12,
                font="Arial",
                fontSize=11.5,
                fontWeight="bold",
                color=OFA_CRIMSON,
            )
            .encode(x="Volume:Q", y="Fee:Q", text="lbl:N")
        )

    return (
        alt.layer(*layers)
        .properties(
            title=alt.TitleParams(
                text=f"How {muni_name} Excess Soil Permit Fees Scale by Volume",
                subtitle="Non-refundable permit fee only — refundable securities and peer-review retainers are shown separately in Stack B above",
                anchor="start",
                font="Arial",
                fontSize=14,
                fontWeight="bold",
                color=OFA_BLUEWOOD,
                subtitleFont="Arial",
                subtitleFontSize=11.5,
                subtitleColor=TEXT_MUTED,
            ),
            height=260,
            background=SURFACE_WHITE,
        )
        .configure_view(strokeWidth=0)
        .configure_axis(grid=False)
    )


def build_dc_stacked_peer_chart(
    df: pd.DataFrame,
    focus_muni: str,
    title: str,
    subtitle: str = "",
    median_val: float | None = None,
    median_label: str = "Ontario Charged Median",
    stacked: bool = True,
    height: int | None = None,
) -> alt.Chart:
    """Build a horizontal stacked Lower/Single-Tier + Upper-Tier DC peer comparison bar chart.

    Expected columns in `df`:
      - `Municipality` (str)
      - `LowerFee` (float, >= 0)
      - `UpperFee` (float, >= 0)
      - `TotalFee` (float, non-null)
      - Optional `UpperName` (str)
      - Optional `Detail` (str)
    """
    plot_df = df.copy()
    plot_df["LowerFee"] = pd.to_numeric(plot_df["LowerFee"], errors="coerce").fillna(0.0)
    plot_df["UpperFee"] = pd.to_numeric(plot_df["UpperFee"], errors="coerce").fillna(0.0)
    plot_df["TotalFee"] = pd.to_numeric(plot_df["TotalFee"], errors="coerce")
    plot_df = plot_df[plot_df["TotalFee"].notna()].copy()
    plot_df = plot_df.sort_values(["TotalFee", "Municipality"], ascending=[False, True]).reset_index(drop=True)

    if plot_df.empty:
        return (
            alt.Chart(pd.DataFrame({"msg": ["No comparable priced DC schedules in this selection."]}))
            .mark_text(font="Arial", fontSize=13, color=TEXT_MUTED)
            .encode(text="msg:N")
            .properties(height=90, background=SURFACE_WHITE)
        )

    if "UpperName" not in plot_df.columns:
        plot_df["UpperName"] = "—"
    if "Detail" not in plot_df.columns:
        plot_df["Detail"] = ""
    if "PartialSilent" not in plot_df.columns:
        plot_df["PartialSilent"] = False
    if "SilentWhich" not in plot_df.columns:
        plot_df["SilentWhich"] = ""

    has_upper_stack = bool(stacked and (plot_df["UpperFee"] > 0.0).any())
    muni_order = plot_df["Municipality"].tolist()
    chart_h = height if height is not None else max(230, min(720, len(plot_df) * 36 + 76))

    max_fee = float(plot_df["TotalFee"].max())
    if median_val is not None and pd.notna(median_val):
        max_fee = max(max_fee, float(median_val))
    x_upper = max(max_fee * 1.26, 5000.0)

    # Build explicit horizontal bar segments so Lower-Tier always draws left of Upper-Tier
    seg_rows = []
    for _, r in plot_df.iterrows():
        muni = str(r["Municipality"])
        is_f = muni == str(focus_muni)
        lt = float(r["LowerFee"])
        ut = float(r["UpperFee"]) if has_upper_stack else 0.0
        tot = float(r["TotalFee"])
        partial = bool(r["PartialSilent"])
        swhich = str(r["SilentWhich"] or "")
        uname = str(r["UpperName"] or "—")
        det = str(r["Detail"] or "")
        lt_txt = "Silent / Confirm" if (partial and swhich == "lower") else _fmt_dollars(lt)
        if partial and swhich == "upper":
            ut_txt = f"Silent / Confirm ({uname})" if uname not in ("", "—") else "Silent / Confirm"
        else:
            ut_txt = f"{_fmt_dollars(ut)} ({uname})" if ut > 0 and uname not in ("", "—") else _fmt_dollars(ut)
        tot_txt = "$0 (Exempt)" if (tot <= 0 and not partial) else f"{_fmt_dollars(tot)}{'+' if partial else ''}"

        if tot <= 0:
            # Tiny hairline placeholder not drawn; label alone conveys $0 (Exempt)
            seg_rows.append(
                {
                    "Municipality": muni,
                    "x0": 0.0,
                    "x1": 0.0,
                    "SegRole": "SelectedLower" if is_f else "Exempt",
                    "TierLabel": "Exempt ($0)",
                    "LowerTxt": "$0",
                    "UpperTxt": "$0",
                    "TotalTxt": tot_txt,
                    "Detail": det,
                }
            )
            continue

        if lt > 0:
            seg_rows.append(
                {
                    "Municipality": muni,
                    "x0": 0.0,
                    "x1": lt,
                    "SegRole": "SelectedLower" if is_f else "PeerLower",
                    "TierLabel": "Lower / Single-Tier DC (Upper Tier Silent)" if (partial and swhich == "upper") else "Lower / Single-Tier DC",
                    "LowerTxt": lt_txt,
                    "UpperTxt": ut_txt,
                    "TotalTxt": tot_txt,
                    "Detail": det,
                }
            )
        if ut > 0:
            seg_rows.append(
                {
                    "Municipality": muni,
                    "x0": lt,
                    "x1": lt + ut,
                    "SegRole": "SelectedUpper" if is_f else "PeerUpper",
                    "TierLabel": f"Upper-Tier DC ({uname})" if uname not in ("", "—") else "Upper-Tier DC",
                    "LowerTxt": lt_txt,
                    "UpperTxt": ut_txt,
                    "TotalTxt": tot_txt,
                    "Detail": det,
                }
            )

    seg_df = pd.DataFrame(seg_rows)

    def _lbl_role(row) -> str:
        if str(row["Municipality"]) == str(focus_muni):
            return "Selected"
        if float(row["TotalFee"]) <= 0.0 and not bool(row["PartialSilent"]):
            return "Exempt"
        return "Peer"

    def _end_label(row) -> str:
        tot = float(row["TotalFee"])
        partial = bool(row["PartialSilent"])
        if tot <= 0.0 and not partial:
            return "$0 (Exempt)"
        return f"{_fmt_dollars(tot)}+" if partial else _fmt_dollars(tot)

    plot_df["Role"] = plot_df.apply(_lbl_role, axis=1)
    plot_df["Label"] = plot_df.apply(_end_label, axis=1)

    seg_color_scale = alt.Scale(
        domain=["SelectedLower", "SelectedUpper", "PeerLower", "PeerUpper", "Exempt"],
        range=[OFA_CRIMSON, OFA_GOLD, PEER_GRAY, PEER_UPPER_SLATE, OFA_SAGE],
    )

    bars = (
        alt.Chart(seg_df)
        .mark_bar(cornerRadiusEnd=3, size=22)
        .encode(
            y=alt.Y(
                "Municipality:N",
                sort=muni_order,
                title=None,
                axis=alt.Axis(
                    labelFont="Arial",
                    labelFontSize=12,
                    labelColor=TEXT_DARK,
                    labelLimit=220,
                    labelOverlap=False,
                    ticks=False,
                    domain=False,
                    labelPadding=10,
                ),
            ),
            x=alt.X(
                "x0:Q",
                title=None,
                scale=alt.Scale(domain=[0, x_upper]),
                axis=alt.Axis(
                    format="$,.0f",
                    tickCount=4,
                    grid=False,
                    domainColor="#CBD5E1",
                    labelFont="Arial",
                    labelFontSize=11,
                    labelColor=TEXT_MUTED,
                ),
            ),
            x2="x1:Q",
            color=alt.Color("SegRole:N", scale=seg_color_scale, legend=None),
            tooltip=[
                alt.Tooltip("Municipality:N", title="Municipality"),
                alt.Tooltip("TierLabel:N", title="Segment"),
                alt.Tooltip("LowerTxt:N", title="Lower / Single-Tier DC"),
                alt.Tooltip("UpperTxt:N", title="Upper-Tier DC"),
                alt.Tooltip("TotalTxt:N", title="Total DC"),
                alt.Tooltip("Detail:N", title="Status / Notes"),
            ],
        )
    )

    label_color_scale = alt.Scale(
        domain=["Selected", "Exempt", "Peer"],
        range=[OFA_CRIMSON, OFA_SAGE, TEXT_DARK],
    )

    labels_halo = (
        alt.Chart(plot_df)
        .mark_text(
            align="left",
            baseline="middle",
            dx=6,
            font="Arial",
            fontSize=11.5,
            fontWeight="bold",
            stroke=SURFACE_WHITE,
            strokeWidth=3.5,
            fill=SURFACE_WHITE,
        )
        .encode(
            y=alt.Y("Municipality:N", sort=muni_order),
            x=alt.X("TotalFee:Q"),
            text=alt.Text("Label:N"),
        )
    )

    labels = (
        alt.Chart(plot_df)
        .mark_text(align="left", baseline="middle", dx=6, font="Arial", fontSize=11.5, fontWeight="bold")
        .encode(
            y=alt.Y("Municipality:N", sort=muni_order),
            x=alt.X("TotalFee:Q"),
            text=alt.Text("Label:N"),
            color=alt.Color("Role:N", scale=label_color_scale, legend=None),
        )
    )

    layers = []
    if median_val is not None and pd.notna(median_val) and float(median_val) > 0:
        med_df = pd.DataFrame([{"med": float(median_val), "txt": f"{median_label}: {_fmt_dollars(median_val)}"}])
        rule = (
            alt.Chart(med_df)
            .mark_rule(color=OFA_BLUEWOOD, strokeDash=[5, 4], strokeWidth=1.5, opacity=0.65)
            .encode(x="med:Q")
        )
        _med_align = "right" if float(median_val) > x_upper * 0.72 else "left"
        _med_dx = -5 if _med_align == "right" else 5
        rule_txt = (
            alt.Chart(med_df)
            .mark_text(
                align=_med_align,
                dx=_med_dx,
                dy=-6,
                font="Arial",
                fontSize=11,
                fontWeight="bold",
                color=OFA_BLUEWOOD,
            )
            .encode(x="med:Q", y=alt.value(-4), text="txt:N")
        )
        layers.extend([rule, bars, labels_halo, labels, rule_txt])
    else:
        layers.extend([bars, labels_halo, labels])

    title_params = alt.TitleParams(
        text=title,
        anchor="start",
        font="Arial",
        fontSize=15,
        fontWeight="bold",
        color=OFA_BLUEWOOD,
        subtitleFont="Arial",
        subtitleFontSize=12,
        subtitleColor=TEXT_MUTED,
        offset=22,
        **({"subtitle": subtitle} if subtitle else {}),
    )

    return (
        alt.layer(*layers)
        .resolve_scale(color="independent")
        .properties(
            title=title_params,
            height=chart_h,
            background=SURFACE_WHITE,
            padding={"top": 14, "left": 8, "right": 18, "bottom": 8},
        )
        .configure_view(strokeWidth=0)
        .configure_axis(grid=False)
    )


def build_dc_scaling_chart(
    lower_row: dict,
    upper_row: dict | None,
    muni_name: str,
    upper_name: str = "",
    building_type: str = "typical_farm",
    service_area: str = "rural",
    stacked: bool = True,
    highlight_val: float | None = None,
) -> alt.Chart | None:
    """Build a Development Charge scaling curve across project size (ft², acres, or worker beds)."""
    btype = str(building_type).strip().lower()
    ut_eff = upper_row if stacked else None

    if btype == "greenhouse":
        grid_x = [round(0.25 * i, 2) for i in range(1, 21)]  # 0.25 to 5.0 acres
        x_title = "Greenhouse Area (acres)"
        x_fmt = ",.1f"
        hi_default = 1.0
        btype_title = "Commercial Greenhouse"
    elif btype == "bunkhouse":
        grid_x = list(range(4, 42, 2))  # 4 to 40 beds
        x_title = "Seasonal Worker Capacity (beds; scaled at 200 ft²/bed)"
        x_fmt = ",.0f"
        hi_default = 10.0
        btype_title = "Bunkhouse / Worker Housing"
    elif btype == "cannabis":
        grid_x = list(range(2000, 31000, 1000))
        x_title = "Facility Area (sq. ft.)"
        x_fmt = ",.0f"
        hi_default = 10000.0
        btype_title = "Cannabis Production Facility"
    else:
        grid_x = list(range(2000, 31000, 1000))
        x_title = "Farm Building Area (sq. ft.)"
        x_fmt = ",.0f"
        hi_default = 10000.0
        btype_title = "Typical Farm Building"

    hi_x = float(hi_default if highlight_val is None else highlight_val)
    rows = []
    any_upper = False
    any_silent_tier = False
    for xv in grid_x:
        if btype == "greenhouse":
            res = compute_stacked_dc(lower_row, ut_eff, "greenhouse", service_area, sqft=float(xv) * 43560.0)
        elif btype == "bunkhouse":
            res = compute_stacked_dc(lower_row, ut_eff, "bunkhouse", service_area, sqft=float(xv) * 200.0, beds=int(xv))
        else:
            res = compute_stacked_dc(lower_row, ut_eff, btype, service_area, sqft=float(xv))

        tot = res["stacked_total"]
        is_part = False
        if tot is None and res["known_floor_total"] is not None and res["known_floor_total"] > 0:
            tot = res["known_floor_total"]
            is_part = True
            any_silent_tier = True
        lt = res["lower_or_single"]
        ut = res["upper_tier"] or 0.0
        if tot is None:
            continue
        if ut > 0:
            any_upper = True
        rows.append(
            {
                "XVal": float(xv),
                "TotalDC": float(tot),
                "LowerDC": float(lt) if lt is not None else 0.0,
                "UpperDC": float(ut),
                "TotalLbl": f"{_fmt_dollars(tot)}+" if is_part else _fmt_dollars(tot),
                "LowerLbl": "Silent / Confirm" if lt is None else _fmt_dollars(lt),
                "UpperLbl": "Silent / Confirm" if (ut_eff is not None and res["upper_tier"] is None) else _fmt_dollars(ut),
            }
        )

    if len(rows) < 2:
        return None
    df_c = pd.DataFrame(rows)
    if float(df_c["TotalDC"].max()) <= 0.0:
        return None

    y_upper = max(float(df_c["TotalDC"].max()) * 1.18, 5000.0)
    x_min, x_max = float(df_c["XVal"].min()), float(df_c["XVal"].max())

    area_fill = (
        alt.Chart(df_c)
        .mark_area(color=OFA_CHAMPAGNE, opacity=0.45)
        .encode(
            x=alt.X(
                "XVal:Q",
                title=x_title,
                axis=alt.Axis(format=x_fmt, grid=False, labelFont="Arial", titleFont="Arial", titleColor=TEXT_MUTED),
            ),
            y=alt.Y(
                "TotalDC:Q",
                title="Estimated Development Charge ($)",
                scale=alt.Scale(domain=[0, y_upper]),
                axis=alt.Axis(format="$,.0f", grid=False, labelFont="Arial", titleFont="Arial", titleColor=TEXT_MUTED),
            ),
        )
    )

    line_total = (
        alt.Chart(df_c)
        .mark_line(color=OFA_CRIMSON if any_upper else OFA_BLUEWOOD, strokeWidth=2.5)
        .encode(
            x="XVal:Q",
            y="TotalDC:Q",
            tooltip=[
                alt.Tooltip("XVal:Q", title=x_title, format=x_fmt),
                alt.Tooltip("TotalLbl:N", title="Known Minimum DC" if any_silent_tier else ("Combined DC" if any_upper else "Municipal DC")),
                alt.Tooltip("LowerLbl:N", title="Lower / Single-Tier DC"),
                alt.Tooltip("UpperLbl:N", title=f"Upper-Tier DC ({upper_name})" if upper_name else "Upper-Tier DC"),
            ],
        )
    )

    layers = [area_fill, line_total]

    if any_upper and float(df_c["LowerDC"].max()) > 0.0:
        line_lower = (
            alt.Chart(df_c)
            .mark_line(color=OFA_BLUEWOOD, strokeDash=[5, 4], strokeWidth=1.8, opacity=0.8)
            .encode(x="XVal:Q", y="LowerDC:Q")
        )
        layers.append(line_lower)

    # Highlight user's current scenario
    if btype == "greenhouse":
        hi_res = compute_stacked_dc(lower_row, ut_eff, "greenhouse", service_area, sqft=hi_x * 43560.0)
        hi_unit = f"{hi_x:g} ac"
    elif btype == "bunkhouse":
        hi_res = compute_stacked_dc(lower_row, ut_eff, "bunkhouse", service_area, sqft=hi_x * 200.0, beds=int(round(hi_x)))
        hi_unit = f"{int(round(hi_x))} beds"
    else:
        hi_res = compute_stacked_dc(lower_row, ut_eff, btype, service_area, sqft=hi_x)
        hi_unit = f"{round(hi_x):,} ft²"

    hi_tot = hi_res["stacked_total"]
    hi_part = False
    if hi_tot is None and hi_res["known_floor_total"] is not None and hi_res["known_floor_total"] > 0:
        hi_tot = hi_res["known_floor_total"]
        hi_part = True

    if hi_tot is not None and x_min <= hi_x <= x_max:
        hi_df = pd.DataFrame([{"XVal": hi_x, "TotalDC": float(hi_tot), "lbl": f"{hi_unit}: {_fmt_dollars(hi_tot)}{'+' if hi_part else ''}"}])
        _align = "right" if hi_x > x_min + (x_max - x_min) * 0.62 else "left"
        _dx = -10 if _align == "right" else 10
        layers.append(
            alt.Chart(hi_df)
            .mark_point(color=OFA_CRIMSON, size=90, filled=True)
            .encode(x="XVal:Q", y="TotalDC:Q")
        )
        layers.append(
            alt.Chart(hi_df)
            .mark_text(
                align=_align,
                dx=_dx,
                dy=-12,
                font="Arial",
                fontSize=11.5,
                fontWeight="bold",
                stroke=SURFACE_WHITE,
                strokeWidth=4,
                fill=SURFACE_WHITE,
            )
            .encode(x="XVal:Q", y="TotalDC:Q", text="lbl:N")
        )
        layers.append(
            alt.Chart(hi_df)
            .mark_text(
                align=_align,
                dx=_dx,
                dy=-12,
                font="Arial",
                fontSize=11.5,
                fontWeight="bold",
                color=OFA_CRIMSON,
            )
            .encode(x="XVal:Q", y="TotalDC:Q", text="lbl:N")
        )

    sa_lbl = "Rural Unserviced" if service_area == "rural" else "Urban Serviced"
    if any_silent_tier:
        sub_txt = f"Known Lower-Tier Minimum ({muni_name}; {upper_name or 'Upper Tier'} is silent — confirm separately) · {sa_lbl}"
    elif any_upper:
        sub_txt = f"Solid Crimson = Combined Stacked DC ({muni_name} + {upper_name}) · Dashed Slate = {muni_name} Standalone · {sa_lbl}"
    else:
        sub_txt = f"Municipal DC schedule ({sa_lbl}) · Excludes separate school-board Education Development Charges (EDCs)"

    return (
        alt.layer(*layers)
        .properties(
            title=alt.TitleParams(
                text=f"How {muni_name} {btype_title} Development Charges Scale",
                subtitle=sub_txt,
                anchor="start",
                font="Arial",
                fontSize=14,
                fontWeight="bold",
                color=OFA_BLUEWOOD,
                subtitleFont="Arial",
                subtitleFontSize=11.5,
                subtitleColor=TEXT_MUTED,
                offset=8,
            ),
            height=280,
            background=SURFACE_WHITE,
            padding={"top": 30, "left": 8, "right": 18, "bottom": 8},
        )
        .configure_view(strokeWidth=0)
        .configure_axis(grid=False)
    )
