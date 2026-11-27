"""
bldg_fees_calc.py — Shared deterministic calculator & OFA colour-ramp helpers
for Ontario Municipal Farm Building Permit Fees (BLDG_FEES).

Used across:
  - Database import & Admin recalculation
  - pages/1_Lower_Tier_Map.py & pages/2_Upper_Tier_Map.py (live Permit Cost Estimator)
  - pages/3_📋_Data_Browser.py & report_generator.py
"""

from __future__ import annotations

import json
import math
from typing import Any

SQFT_PER_M2 = 10.7639104
OBC_LARGE_FARM_SQFT = 6458.35  # 600 m² threshold under 2024 OBC Group G


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


def parse_calc_spec(raw: Any) -> dict | None:
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


def _eval_spec(
    spec: dict,
    row: dict | Any,
    getter,
    sqft: float,
    is_livestock: bool,
    assumed_cost_per_sqft: float | None,
) -> float | None:
    stype = str(spec.get("type", "")).strip().lower()
    if stype in ("urban_no_farm", "missing", "upper_local_jurisdiction"):
        return None

    if stype == "split_spec":
        # Allows completely different calculation models for livestock vs. non-livestock
        # e.g., Chatham-Kent (livestock = valuation, pole barn = $0.28/ft²)
        sub = spec.get("livestock" if is_livestock else "other_farm")
        if isinstance(sub, dict):
            return _eval_spec(sub, row, getter, sqft, is_livestock, assumed_cost_per_sqft)
        return None

    if stype == "standard":
        branch = spec.get("livestock" if is_livestock else "other_farm") or spec
        base = _to_float(branch.get("base")) or 0.0
        rate = _to_float(branch.get("rate"))
        mn = _to_float(branch.get("min_fee")) or 0.0
        if rate is None:
            return None
        return round(max(mn, base + float(sqft) * rate), 2)

    if stype == "flat":
        fee = _to_float(spec.get("flat_fee"))
        return round(fee, 2) if fee is not None else None

    if stype == "flat_split":
        # Different flat fees for livestock vs. non-livestock (e.g., Brooke-Alvinston, Warwick)
        fee = _to_float(spec.get("livestock_flat" if is_livestock else "other_farm_flat"))
        return round(fee, 2) if fee is not None else None

    if stype == "capped_area":
        # Base + rate * sqft with min_fee floor and optional max_fee cap (e.g., St. Clair $100 + $0.10/ft², $1,000 max)
        branch = spec.get("livestock" if is_livestock else "other_farm") or spec
        base = _to_float(branch.get("base")) or 0.0
        rate = _to_float(branch.get("rate")) or 0.0
        mn = _to_float(branch.get("min_fee")) or 0.0
        mx = _to_float(branch.get("max_fee"))
        val = max(mn, base + float(sqft) * rate)
        if mx is not None:
            val = min(mx, val)
        return round(val, 2)

    if stype == "excess_over":
        # e.g. Norwich / Plympton-Wyoming: base + rate * max(0, sqft - threshold)
        # Optional `step_sqft` rounds excess up to whole increments ("or part thereof", e.g. Calvin per 10 m², Emo per 200 ft²)
        # Optional `max_fee` caps the total fee (e.g. Emo $2,000 maximum building permit fee)
        branch = spec.get("livestock" if is_livestock else "other_farm") or spec
        base = _to_float(branch.get("base")) or 0.0
        thresh = _to_float(branch.get("threshold_sqft")) or 0.0
        rate = _to_float(branch.get("rate")) or 0.0
        step = _to_float(branch.get("step_sqft"))
        mn = _to_float(branch.get("min_fee")) or 0.0
        mx = _to_float(branch.get("max_fee"))
        excess = max(0.0, float(sqft) - thresh)
        if step is not None and step > 0:
            val = base + math.ceil(round(excess / step, 9)) * rate
        else:
            val = base + excess * rate
        val = max(mn, val)
        if mx is not None:
            val = min(mx, val)
        return round(val, 2)

    if stype == "tiered_marginal":
        # e.g. West Perth / West Grey / Adelaide-Metcalfe: base + marginal brackets [(up_to_sqft, rate), ...]
        branch = spec.get("livestock" if is_livestock else "other_farm") or spec
        brackets = branch.get("brackets") or []
        base = _to_float(branch.get("base")) or 0.0
        mn = _to_float(branch.get("min_fee")) or 0.0
        remaining = float(sqft)
        prev_cap = 0.0
        total = base
        for b in brackets:
            cap = _to_float(b.get("up_to_sqft"))
            rate = _to_float(b.get("rate")) or 0.0
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
        return round(max(mn, total), 2)

    if stype == "tiered_total":
        # Whole-building bracket lookup (e.g. Arran-Elderslie, Kingsville, Halton Hills,
        # Middlesex Centre, Lucan Biddulph, Strathroy-Caradoc, West Lincoln, Enniskillen).
        # Each bracket supports optional `threshold_sqft` (for base + rate * max(0, sqft - threshold)),
        # optional `over_cap_sqft` + `over_rate` (second marginal rate inside that bracket, e.g. Middlesex Centre >30,000 ft²),
        # and `min_fee`.
        branch = spec.get("livestock" if is_livestock else "other_farm") or spec
        brackets = branch.get("brackets") or []
        for b in brackets:
            cap = _to_float(b.get("up_to_sqft"))
            if cap is None or float(sqft) <= cap:
                base = _to_float(b.get("base")) or 0.0
                thresh = _to_float(b.get("threshold_sqft")) or 0.0
                rate = _to_float(b.get("rate")) or 0.0
                over_cap = _to_float(b.get("over_cap_sqft"))
                over_rate = _to_float(b.get("over_rate"))
                mn = _to_float(b.get("min_fee")) or 0.0
                mx = _to_float(b.get("max_fee"))
                if over_cap is not None and over_rate is not None and float(sqft) > over_cap:
                    val = base + max(0.0, over_cap - thresh) * rate + (float(sqft) - over_cap) * over_rate
                else:
                    val = base + max(0.0, float(sqft) - thresh) * rate
                val = max(mn, val)
                if mx is not None:
                    val = min(mx, val)
                return round(val, 2)
        return None

    if stype == "valuation":
        val_rate = _to_float(spec.get("value_rate_per_1000")) or _to_float(getter("value_rate_per_1000"))
        if val_rate is None or assumed_cost_per_sqft is None or assumed_cost_per_sqft <= 0:
            return None
        base = _to_float(spec.get("base")) or _to_float(getter("base_fee")) or 0.0
        mn = _to_float(spec.get("min_fee")) or _to_float(getter("min_fee")) or 0.0
        est_val = float(sqft) * float(assumed_cost_per_sqft)
        return round(max(mn, base + (est_val / 1000.0) * val_rate), 2)

    return None


def evaluate_bldg_fee(
    row: dict | Any,
    sqft: float,
    is_livestock: bool = True,
    assumed_cost_per_sqft: float | None = None,
) -> float | None:
    """Calculate the estimated building permit fee ($) for a farm structure of `sqft` sq ft.

    Parameters
    ----------
    row : dict or pandas Series
        Must contain details_bldg_fees fields (or mapped equivalents).
    sqft : float
        Gross floor area in square feet (e.g. 2500, 10000, 20000).
    is_livestock : bool
        True for Livestock Barn; False for Equipment / Drive Shed / Non-Livestock storage.
    assumed_cost_per_sqft : float | None
        Optional assumed construction cost ($/ft²) used ONLY when a municipality charges
        exclusively per $1,000 of construction value (`value_rate_per_1000`). If None,
        valuation-only schedules return None so incompatible scales are never silently mixed.
    """
    if sqft is None or sqft <= 0:
        return None

    getter = row.get if hasattr(row, "get") else lambda k, d=None: getattr(row, k, d)

    has_farm = str(getter("has_farm_tier", "") or "").strip().lower()
    if has_farm.startswith("no") or has_farm in ("n/a", "not verified", "unknown"):
        return None

    spec = parse_calc_spec(getter("calc_spec_json", None))
    if spec:
        return _eval_spec(spec, row, getter, sqft, is_livestock, assumed_cost_per_sqft)

    # Default fallback using standard structured columns
    flat_fee = _to_float(getter("flat_fee"))
    if flat_fee is not None and flat_fee > 0:
        return round(flat_fee, 2)

    rate_live = _to_float(getter("rate_per_sqft_livestock"))
    rate_other = _to_float(getter("rate_per_sqft_other_farm"))
    rate = (rate_live if is_livestock else rate_other)
    if rate is None:
        rate = rate_live if rate_live is not None else rate_other

    if rate is not None:
        base = _to_float(getter("base_fee")) or 0.0
        mn = _to_float(getter("min_fee")) or 0.0
        return round(max(mn, base + float(sqft) * rate), 2)

    val_rate = _to_float(getter("value_rate_per_1000"))
    if val_rate is not None and assumed_cost_per_sqft is not None and assumed_cost_per_sqft > 0:
        base = _to_float(getter("base_fee")) or 0.0
        mn = _to_float(getter("min_fee")) or 0.0
        est_val = float(sqft) * float(assumed_cost_per_sqft)
        return round(max(mn, base + (est_val / 1000.0) * val_rate), 2)

    return None


def compute_benchmarks(row: dict) -> dict[str, float | None]:
    """Compute all 4 standard OFA farm building benchmarks deterministically."""
    return {
        "est_2500_shed": evaluate_bldg_fee(row, 2500, is_livestock=False),
        "est_10000_barn": evaluate_bldg_fee(row, 10000, is_livestock=True),
        "est_10000_shed": evaluate_bldg_fee(row, 10000, is_livestock=False),
        "est_20000_barn": evaluate_bldg_fee(row, 20000, is_livestock=True),
    }


def fee_cost_tier_rgba(
    fee: float | None,
    sqft: float = 10000.0,
    verification_status: str = "",
    has_farm_tier: str = "",
    pricing_model: str = "",
) -> tuple[list[int], str]:
    """Return (RGBA color, cost_tier_label) following OFA Brand Identity Guidelines.

    Thresholds scale linearly with `sqft` relative to a 10,000 ft² reference barn:
      - Low (< $0.28/ft² eff.):        Soft Sage Green   [46, 139, 87, 175]
      - Moderate ($0.28–$0.37/ft²):    OFA Bluewood-Teal [72, 128, 148, 175]
      - High ($0.37–$0.48/ft²):        OFA Tulip Tree    [236, 168, 66, 190]
      - Very High (>= $0.48/ft²):      OFA Crimson       [215, 24, 42, 195]
      - Valuation-Based ($/$1k):       Deep Slate        [51, 75, 88, 175]
      - Urban / No Farm Tier (ICI):    Cool Steel Gray   [148, 163, 184, 155]
      - Upper Tier (Local Jurisd.):    Muted Warm Gray   [186, 182, 176, 120]
      - Not Published / Pending:       Champagne Neutral [222, 214, 205, 115]
    """
    vs = str(verification_status or "").strip().lower()
    hft = str(has_farm_tier or "").strip().lower()
    pm = str(pricing_model or "").strip().lower()

    if "upper tier" in vs or "local jurisdiction" in pm:
        return [186, 182, 176, 120], "Local Jurisdiction (Lower Tier)"

    if fee is not None and sqft > 0:
        eff_rate = float(fee) / float(sqft)
        if eff_rate < 0.28:
            return [46, 139, 87, 175], "Low (< $0.28/ft²)"
        if eff_rate < 0.37:
            return [72, 128, 148, 175], "Moderate ($0.28–$0.37/ft²)"
        if eff_rate < 0.48:
            return [236, 168, 66, 190], "High ($0.37–$0.48/ft²)"
        return [215, 24, 42, 195], "Very High (≥ $0.48/ft²)"

    if "not published" in vs:
        return [180, 140, 100, 150], "Not Published Online"
    if (
        hft == "no"
        or hft.startswith("no ")
        or hft.startswith("no(")
        or hft.startswith("no—")
        or "urban" in vs
        or "no farm tier" in vs
    ):
        return [148, 163, 184, 155], "Urban / No Farm Tier (ICI)"
    if "$1,000" in pm or "valu" in pm:
        return [51, 75, 88, 175], "Valuation-Based ($/$1k)"
    return [222, 214, 205, 115], "Pending Audit"
