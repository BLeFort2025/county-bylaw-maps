"""
fee_charts.py — Publication-grade OFA-branded Altair chart helpers for
Farm Building Permit Fees (BLDG_FEES) and Site Alteration / Excess Soil Fees (SITE_ALT).

Follows OFA Brand Guide 2025-26 palette & executive visual hierarchy:
  - Focal accent: OFA Crimson (#D7182A)
  - Structural/benchmark ink: Pickled Bluewood (#334B58)
  - Inflection/cap accent: OFA Tulip Tree (#ECA842)
  - Farm Exempt ($0): Soft Sage Green (#2E8B57)
  - Muted peer context: Neutral Slate (#CBD5E1)
  - Typography: Arial, explicit #FFFFFF surface for light/dark theme safety
  - Zero gridlines, zero legend clutter, whole-dollar direct bar labels
"""

from __future__ import annotations

import altair as alt
import pandas as pd

from bldg_fees_calc import evaluate_bldg_fee, OBC_LARGE_FARM_SQFT
from site_alt_fees_calc import evaluate_site_alt_fee

# Official OFA Brand Guide 2025-26 Palette
OFA_CRIMSON = "#D7182A"
OFA_BLUEWOOD = "#334B58"
OFA_GOLD = "#ECA842"
OFA_CHAMPAGNE = "#EDE6DE"
OFA_SAGE = "#2E8B57"
PEER_GRAY = "#CBD5E1"
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
        subtitle=subtitle if subtitle else None,
        anchor="start",
        font="Arial",
        fontSize=15,
        fontWeight="bold",
        color=OFA_BLUEWOOD,
        subtitleFont="Arial",
        subtitleFontSize=12,
        subtitleColor=TEXT_MUTED,
        offset=22,
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
