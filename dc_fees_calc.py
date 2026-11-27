"""
dc_fees_calc.py — Shared deterministic calculator & OFA colour-ramp helpers
for Ontario Municipal Development Charges (DC) applying to Agricultural Buildings.

Covers all 4 farm building sub-types across Rural (Unserviced) and Urban (Serviced) areas:
  1. typical_farm : Typical Farm Buildings (livestock barns, drive sheds, grain storage) — default 10,000 ft²
  2. greenhouse   : Commercial Greenhouses — default 1 acre (43,560 ft²)
  3. cannabis     : Cannabis Production Facilities — default 10,000 ft²
  4. bunkhouse    : Bunkhouses / Seasonal Agricultural Worker Housing (SAWP) — default 10 beds / 2,000 ft²

Supports Upper-Tier + Lower-Tier stacking cleanly without double-counting Single-Tier municipalities.
Zero heuristic guessing: returns None whenever a sub-type is unverified, silent/ambiguous,
or not published online; returns 0.0 ONLY when verified Exempt or No DC By-law.
"""

from __future__ import annotations

import json
import math
from typing import Any

SQFT_PER_SQM = 10.763910416709722

STANDARD_DC_BENCHMARKS = {
    "typical_farm": {"sqft": 10000.0, "beds": 0, "units": 1, "label": "Typical Farm Building (10,000 ft²)"},
    "greenhouse":   {"sqft": 43560.0, "beds": 0, "units": 1, "label": "Commercial Greenhouse (1 acre / 43,560 ft²)"},
    "cannabis":     {"sqft": 10000.0, "beds": 0, "units": 1, "label": "Cannabis Production Facility (10,000 ft²)"},
    "bunkhouse":    {"sqft": 2000.0,  "beds": 10, "units": 1, "label": "Bunkhouse / Worker Housing (10 beds / 2,000 ft²)"},
}


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if val != val:
            return None
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in ("none", "nan", "n/a", "—", "-"):
        return None
    try:
        return float(s.replace("$", "").replace(",", ""))
    except ValueError:
        return None


def parse_dc_calc_spec(raw: Any) -> dict | None:
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


def _eval_sub_spec(spec: dict | None, sqft: float, beds: int = 10, units: int = 1) -> float | None:
    """Evaluate a single sub-type formula spec dict deterministically."""
    if not isinstance(spec, dict):
        return None
    stype = str(spec.get("type", "")).strip().lower()

    if stype in ("exempt", "no_dc", "no_bylaw", "zero", "waived"):
        return 0.0

    if stype in ("not_published", "pending", "unknown", "silent", "silent_unknown", "site_specific", "deferred_unknown"):
        return None

    discount_mult = 1.0
    disc_pct = _to_float(spec.get("discount_pct"))
    if disc_pct is not None:
        discount_mult = max(0.0, 1.0 - disc_pct / 100.0)

    mn = _to_float(spec.get("min_fee")) or 0.0
    mx = _to_float(spec.get("max_fee"))

    if stype == "flat":
        fee = _to_float(spec.get("flat_fee"))
        if fee is None:
            return None
        val = fee * discount_mult
    elif stype == "per_sqft":
        rate = _to_float(spec.get("rate"))
        if rate is None:
            return None
        base = _to_float(spec.get("base")) or 0.0
        thresh = _to_float(spec.get("exempt_up_to_sqft")) or 0.0
        charge_basis = str(spec.get("charge_basis", "excess")).strip().lower()
        if sqft <= thresh and thresh > 0:
            return 0.0
        eff_sqft = max(0.0, float(sqft) - thresh) if (thresh > 0 and charge_basis == "excess") else float(sqft)
        val = (base + eff_sqft * rate) * discount_mult
    elif stype == "per_sqm":
        rate_sqm = _to_float(spec.get("rate_sqm"))
        if rate_sqm is None:
            return None
        base = _to_float(spec.get("base")) or 0.0
        sqm = float(sqft) / SQFT_PER_SQM
        thresh_sqm = _to_float(spec.get("exempt_up_to_sqm")) or 0.0
        charge_basis = str(spec.get("charge_basis", "excess")).strip().lower()
        if sqm <= thresh_sqm and thresh_sqm > 0:
            return 0.0
        eff_sqm = max(0.0, sqm - thresh_sqm) if (thresh_sqm > 0 and charge_basis == "excess") else sqm
        val = (base + eff_sqm * rate_sqm) * discount_mult
    elif stype == "per_bed":
        rate_bed = _to_float(spec.get("rate"))
        if rate_bed is None:
            return None
        base = _to_float(spec.get("base")) or 0.0
        val = (base + max(0, int(beds)) * rate_bed) * discount_mult
    elif stype == "per_unit":
        rate_unit = _to_float(spec.get("rate"))
        if rate_unit is None:
            return None
        base = _to_float(spec.get("base")) or 0.0
        val = (base + max(1, int(units)) * rate_unit) * discount_mult
    elif stype == "tiered_area":
        # Whole-footprint bracket lookup in sq.ft. (or sq.m. if unit='sqm')
        unit = str(spec.get("unit", "sqft")).strip().lower()
        area = float(sqft) / SQFT_PER_SQM if unit == "sqm" else float(sqft)
        brackets = spec.get("brackets") or []
        val = None
        for b in brackets:
            cap = _to_float(b.get("up_to"))
            excl = bool(b.get("exclusive_upper", False))
            if cap is None or (area < cap if excl else area <= cap):
                if b.get("exempt"):
                    return 0.0
                if b.get("flat_fee") is not None:
                    val = float(_to_float(b.get("flat_fee")) or 0.0) * discount_mult
                else:
                    base = _to_float(b.get("base")) or 0.0
                    rate = _to_float(b.get("rate")) or 0.0
                    thresh = _to_float(b.get("threshold")) or 0.0
                    val = (base + max(0.0, area - thresh) * rate) * discount_mult
                break
        if val is None:
            return None
    elif stype == "tiered_marginal":
        unit = str(spec.get("unit", "sqft")).strip().lower()
        area = float(sqft) / SQFT_PER_SQM if unit == "sqm" else float(sqft)
        brackets = spec.get("brackets") or []
        remaining = area
        prev_cap = 0.0
        total = _to_float(spec.get("base")) or 0.0
        for b in brackets:
            cap = _to_float(b.get("up_to"))
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
        val = total * discount_mult
    else:
        return None

    val = max(mn, val)
    if mx is not None:
        val = min(mx, val)
    return round(val, 2)


def evaluate_dc_fee(
    row: dict | Any,
    building_type: str = "typical_farm",
    service_area: str = "rural",
    sqft: float | None = None,
    beds: int | None = None,
    units: int = 1,
) -> float | None:
    """Evaluate the municipal Development Charge ($) for a single municipality row.

    Args:
        row: Dict or pandas Series containing `dc_calc_spec_json` (and optionally `has_dc`).
        building_type: One of 'typical_farm', 'greenhouse', 'cannabis', 'bunkhouse'.
        service_area: 'rural' (unserviced primary benchmark) or 'urban' (full services).
        sqft: Building area in sq.ft. Defaults to STANDARD_DC_BENCHMARKS[building_type]['sqft'].
        beds: Worker bed count (for 'bunkhouse'). Defaults to 10.
        units: Number of residential dwelling units (for per-unit bunkhouses). Defaults to 1.

    Returns:
        Dollar amount (float, rounded to 2 decimals), 0.0 if verified Exempt / No DC By-law,
        or None if unverified / silent / not published online.
    """
    btype = str(building_type).strip().lower()
    if btype not in STANDARD_DC_BENCHMARKS:
        raise ValueError(f"Unknown DC building_type: {building_type}")
    sarea = str(service_area).strip().lower()
    if sarea not in ("rural", "urban"):
        raise ValueError(f"service_area must be 'rural' or 'urban', got {service_area}")

    bm = STANDARD_DC_BENCHMARKS[btype]
    eff_sqft = float(bm["sqft"] if sqft is None else sqft)
    eff_beds = int(bm["beds"] if beds is None else beds)
    eff_units = int(units)

    getter = row.get if hasattr(row, "get") else lambda k, d=None: getattr(row, k, d)
    has_dc = str(getter("has_dc", "") or "").strip().lower()
    if has_dc in ("2", "no"):
        return 0.0

    spec = parse_dc_calc_spec(getter("dc_calc_spec_json"))
    if not spec:
        return None

    sub = spec.get(btype)
    if not isinstance(sub, dict):
        return None

    # Support either {rural: {...}, urban: {...}} OR a single uniform spec dict (when rural == urban)
    if "rural" in sub or "urban" in sub:
        branch = sub.get(sarea)
        # If urban is omitted and rural is marked uniform, allow explicit fallback only if "uniform": True
        if branch is None and sarea == "urban" and sub.get("uniform"):
            branch = sub.get("rural")
    else:
        branch = sub

    return _eval_sub_spec(branch, sqft=eff_sqft, beds=eff_beds, units=eff_units)


def compute_all_dc_benchmarks(spec_dict: dict | str | None) -> dict[str, float | None]:
    """Compute all 8 standard benchmark fields (4 building types × rural/urban) from a dc_calc_spec_json."""
    row = {"dc_calc_spec_json": spec_dict}
    return {
        "est_dc_10k_barn_rural":       evaluate_dc_fee(row, "typical_farm", "rural"),
        "est_dc_10k_barn_urban":       evaluate_dc_fee(row, "typical_farm", "urban"),
        "est_dc_1ac_greenhouse_rural": evaluate_dc_fee(row, "greenhouse",   "rural"),
        "est_dc_1ac_greenhouse_urban": evaluate_dc_fee(row, "greenhouse",   "urban"),
        "est_dc_10k_cannabis_rural":   evaluate_dc_fee(row, "cannabis",     "rural"),
        "est_dc_10k_cannabis_urban":   evaluate_dc_fee(row, "cannabis",     "urban"),
        "est_dc_bunkhouse_rural":      evaluate_dc_fee(row, "bunkhouse",    "rural"),
        "est_dc_bunkhouse_urban":      evaluate_dc_fee(row, "bunkhouse",    "urban"),
    }


def compute_stacked_dc(
    lower_row: dict | Any,
    upper_row: dict | Any | None,
    building_type: str = "typical_farm",
    service_area: str = "rural",
    sqft: float | None = None,
    beds: int | None = None,
    units: int = 1,
) -> dict[str, float | None]:
    """Compute standalone Lower/Single-Tier DC, Upper-Tier DC, and Stacked Total cleanly.

    If either tier is None (unverified/silent/not published), `stacked_total` is None
    (while `known_partial_total` is returned separately so missing data is never disguised as $0).
    """
    lt_val = evaluate_dc_fee(lower_row, building_type, service_area, sqft=sqft, beds=beds, units=units)
    if upper_row is None:
        return {
            "lower_or_single": lt_val,
            "upper_tier": 0.0,
            "stacked_total": lt_val,
            "known_floor_total": lt_val,
            "has_silent_tier": False,
            "silent_tier_which": None,
            "is_stacked": False,
        }
    ut_val = evaluate_dc_fee(upper_row, building_type, service_area, sqft=sqft, beds=beds, units=units)
    if lt_val is not None and ut_val is not None:
        stacked = round(lt_val + ut_val, 2)
        return {
            "lower_or_single": lt_val,
            "upper_tier": ut_val,
            "stacked_total": stacked,
            "known_floor_total": stacked,
            "has_silent_tier": False,
            "silent_tier_which": None,
            "is_stacked": True,
        }
    if lt_val is not None and ut_val is None:
        return {
            "lower_or_single": lt_val,
            "upper_tier": None,
            "stacked_total": None,
            "known_floor_total": round(lt_val, 2),
            "has_silent_tier": True,
            "silent_tier_which": "upper",
            "is_stacked": True,
        }
    if lt_val is None and ut_val is not None:
        return {
            "lower_or_single": None,
            "upper_tier": ut_val,
            "stacked_total": None,
            "known_floor_total": round(ut_val, 2),
            "has_silent_tier": True,
            "silent_tier_which": "lower",
            "is_stacked": True,
        }
    return {
        "lower_or_single": None,
        "upper_tier": None,
        "stacked_total": None,
        "known_floor_total": None,
        "has_silent_tier": True,
        "silent_tier_which": "both",
        "is_stacked": True,
    }


def sqm_rate_to_sqft(rate_per_sqm: float) -> float:
    """Convert $/m² rate to $/ft² (rounded to 4 decimal places for display/storage)."""
    return round(float(rate_per_sqm) / SQFT_PER_SQM, 4)
