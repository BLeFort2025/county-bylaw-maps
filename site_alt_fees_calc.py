"""
site_alt_fees_calc.py — Shared deterministic calculator & OFA colour-ramp helpers
for Ontario Municipal Site Alteration & Excess Soil Permit Fees (SITE_ALT).

Mirrors bldg_fees_calc.py so farm topsoil/fill permit costs can be computed
deterministically across:
  - Database imports & Admin recalculation
  - pages/1_Lower_Tier_Map.py & pages/2_Upper_Tier_Map.py (live Topsoil Import Cost Estimator)
  - pages/3_📋_Data_Browser.py & report_generator.py
"""

from __future__ import annotations

import json
from typing import Any

STANDARD_BENCHMARK_VOLUMES_M3 = (500.0, 5000.0, 15000.0)


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if val != val:  # NaN check
            return None
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in ("none", "nan", "n/a", "—", "-"):
        return None
    try:
        return float(s.replace("$", "").replace(",", ""))
    except ValueError:
        return None


def parse_fee_calc_spec(raw: Any) -> dict | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    s = str(raw).strip()
    if not s or s.lower() in ("none", "nan"):
        return None
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _eval_spec(spec: dict, volume_m3: float) -> float | None:
    stype = str(spec.get("type", "")).strip().lower()
    vol = float(volume_m3)

    if stype in ("exempt", "exempt_zero", "waiver_zero_app"):
        return 0.0

    if stype in ("area_based", "per_hectare", "not_published", "no_bylaw", "pending", "cost_recovery_only"):
        return None

    if stype == "exempt_up_to_cap":
        cap = _to_float(spec.get("exempt_cap_m3")) or 0.0
        excl = bool(spec.get("exclusive_upper", False))
        if (vol < cap) if excl else (vol <= cap):
            return 0.0
        above = spec.get("above_cap")
        if not isinstance(above, dict):
            return None
        charge_basis = str(spec.get("charge_basis", "full")).strip().lower()
        eval_vol = max(0.0, vol - cap) if charge_basis == "excess" else vol
        return _eval_spec(above, eval_vol)

    if stype == "flat":
        fee = _to_float(spec.get("flat_fee"))
        return round(fee, 2) if fee is not None else None

    if stype == "base_plus_m3":
        base = _to_float(spec.get("base")) or 0.0
        rate = _to_float(spec.get("per_m3"))
        if rate is None:
            return None
        mn = _to_float(spec.get("min_fee")) or 0.0
        mx = _to_float(spec.get("max_fee"))
        thresh = _to_float(spec.get("threshold_m3")) or 0.0
        val = max(mn, base + max(0.0, vol - thresh) * rate)
        if mx is not None:
            val = min(mx, val)
        return round(val, 2)

    if stype == "tiered_volume":
        # Whole-volume bracket lookup:
        # brackets: [{"up_to_m3": 100, "exclusive_upper": true, "base": 250, "per_m3": 0}, ...]
        # Supports optional `threshold_m3`, `min_fee`, `max_fee`, `flat_fee`, and `exclusive_upper`
        # (so e.g. Clarington "< 100 m³" vs "100–500 m³" vs "> 500 m³" is exact).
        brackets = spec.get("brackets") or []
        for b in brackets:
            cap = _to_float(b.get("up_to_m3"))
            excl = bool(b.get("exclusive_upper", False))
            in_bracket = (cap is None) or (vol < cap if excl else vol <= cap)
            if in_bracket:
                if b.get("exempt"):
                    return 0.0
                if b.get("area_based") or b.get("not_published") or b.get("unpriced"):
                    return None
                if b.get("flat_fee") is not None:
                    return round(float(_to_float(b.get("flat_fee")) or 0.0), 2)
                base = _to_float(b.get("base")) or 0.0
                rate = _to_float(b.get("per_m3")) or 0.0
                thresh = _to_float(b.get("threshold_m3")) or 0.0
                mn = _to_float(b.get("min_fee")) or 0.0
                mx = _to_float(b.get("max_fee"))
                val = max(mn, base + max(0.0, vol - thresh) * rate)
                if mx is not None:
                    val = min(mx, val)
                return round(val, 2)
        return None

    if stype == "tiered_marginal":
        brackets = spec.get("brackets") or []
        base = _to_float(spec.get("base")) or 0.0
        mn = _to_float(spec.get("min_fee")) or 0.0
        mx = _to_float(spec.get("max_fee"))
        remaining = vol
        prev_cap = 0.0
        total = base
        for b in brackets:
            cap = _to_float(b.get("up_to_m3"))
            rate = _to_float(b.get("per_m3")) or 0.0
            if cap is None:
                total += max(0.0, remaining) * rate
                remaining = 0.0
                break
            span = max(0.0, cap - prev_cap)
            take = min(remaining, span)
            total += take * rate
            remaining -= take
            prev_cap = cap
            if remaining <= 0:
                break
        val = max(mn, total)
        if mx is not None:
            val = min(mx, val)
        return round(val, 2)

    return None


def evaluate_site_alt_fee(row: dict | Any, volume_m3: float) -> float | None:
    """Calculate the estimated municipal Site Alteration permit fee ($) for importing
    `volume_m3` cubic metres of clean topsoil/fill onto agricultural land.

    Returns None when the schedule is unverified/pending, not published online,
    area-based (per hectare), cost-recovery-only, or where no bylaw exists,
    so incompatible or missing fee structures are never silently reported as $0.
    """
    if volume_m3 is None or volume_m3 <= 0:
        return None

    getter = row.get if hasattr(row, "get") else lambda k, d=None: getattr(row, k, d)

    vs = str(getter("fee_verification_status", "") or "").strip().lower()
    if vs in ("pending", "not published online", "n/a (no bylaw)"):
        return None

    ag_status = str(getter("ag_import_fee_status", "") or "").strip().lower()
    if ag_status in ("no bylaw", "pending"):
        return None

    # 1. Explicit JSON formula takes priority (handles brackets, caps — including exempt-below-cap
    #    with area-based above-cap — and dedicated farm tiers deterministically)
    spec = parse_fee_calc_spec(getter("fee_calc_spec_json", None))
    if spec:
        return _eval_spec(spec, float(volume_m3))

    pm = str(getter("fee_pricing_model", "") or "").strip().lower()
    if any(k in pm for k in ("hectare", "not published", "cost recovery only")):
        return None

    # 2. Full farm exemption or $0 application waiver
    if ag_status in ("exempt ($0)", "waiver available ($0 app fee)"):
        return 0.0

    # 3. Volume-capped exemption fallback using structured numeric columns
    cap = _to_float(getter("ag_exempt_volume_cap_m3"))
    if ag_status == "exempt up to volume cap" and cap is not None and float(volume_m3) <= cap:
        return 0.0

    # 4. Structured numeric fallback (base_fee_small / base_fee_large + per_m3_rate)
    rate = _to_float(getter("per_m3_rate"))
    base_small = _to_float(getter("base_fee_small"))
    base_large = _to_float(getter("base_fee_large"))

    if rate is not None:
        base = base_large if (float(volume_m3) > 500.0 and base_large is not None) else (base_small or base_large or 0.0)
        return round(base + float(volume_m3) * rate, 2)

    if pm in ("flat fee", "reduced farm flat fee"):
        flat = base_large if (float(volume_m3) > 500.0 and base_large is not None) else base_small
        return round(flat, 2) if flat is not None else None

    return None


def compute_site_alt_benchmarks(row: dict) -> dict[str, float | None]:
    """Compute all 3 standardized OFA clean-topsoil import benchmarks deterministically."""
    return {
        "est_fee_500_m3": evaluate_site_alt_fee(row, 500.0),
        "est_fee_5000_m3": evaluate_site_alt_fee(row, 5000.0),
        "est_fee_15000_m3": evaluate_site_alt_fee(row, 15000.0),
    }


def site_alt_fee_tier_rgba(
    fee: float | None,
    volume_m3: float = 15000.0,
    verification_status: str = "",
    ag_import_fee_status: str = "",
    pricing_model: str = "",
) -> tuple[list[int], str]:
    """Return (RGBA color, cost_tier_label) following OFA Brand Identity Guidelines.

    Thresholds scale with `volume_m3` relative to effective $/m³:
      - Exempt / $0 App Fee:           Soft Sage Green   [46, 139, 87, 175]
      - Low (< $1.00/m³ eff.):         OFA Bluewood-Teal [72, 128, 148, 175]
      - Moderate ($1.00–$2.00/m³):     OFA Tulip Tree    [236, 168, 66, 190]
      - High (>= $2.00/m³):            OFA Crimson       [215, 24, 42, 195]
      - Area-Based ($/ha) / Special:   Deep Slate        [51, 75, 88, 175]
      - No Site Alt Bylaw:             Muted Warm Gray   [186, 182, 176, 120]
      - Not Published / Pending:       Champagne Neutral [222, 214, 205, 115]
    """
    vs = str(verification_status or "").strip().lower()
    ags = str(ag_import_fee_status or "").strip().lower()
    pm = str(pricing_model or "").strip().lower()

    if "no bylaw" in vs or "no bylaw" in ags:
        return [186, 182, 176, 120], "No Site Alt. By-law"

    if fee is not None and volume_m3 > 0:
        if fee <= 0.0:
            lbl = "Waiver ($0 App Fee)" if "waiver" in ags else "Farm Exempt ($0)"
            return [46, 139, 87, 175], lbl
        eff = float(fee) / float(volume_m3)
        if eff < 1.00:
            return [72, 128, 148, 175], "Low (< $1.00/m³)"
        if eff < 2.00:
            return [236, 168, 66, 190], "Moderate ($1.00–$1.99/m³)"
        return [215, 24, 42, 195], "High (≥ $2.00/m³)"

    if "hectare" in pm:
        return [51, 75, 88, 175], "Area-Based ($/ha)"
    if "cost recovery" in pm:
        return [51, 75, 88, 175], "Cost Recovery Only"
    if "not published" in vs or "not published" in pm:
        return [180, 140, 100, 150], "Not Published Online"
    if "verified" in vs:
        return [51, 75, 88, 175], "Capped / Non-Volumetric"
    return [222, 214, 205, 115], "Pending Fee Audit"
