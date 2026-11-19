"""
county_digest_engine.py — County Federation Weekly Digest matching, full-discussion extraction,
and grounded Gemini summarization engine.

Matches each County Federation's custom keyword watchlist (positive + negative exclusions)
against the unified 444-municipality council agenda/minutes cache, extracts the full
surrounding discussion passage (agenda item / staff report / council resolution), and
produces a strictly grounded plain-English summary via Gemini (with deterministic fallback).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
from typing import Any

import pandas as pd

try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except Exception:
    pass

from shared_config import (
    apply_negative_keywords,
    build_combined_keyword_regex,
    build_keyword_regex,
    canon_name,
    classify_meeting_doc,
    extract_date_from_text,
    is_recent_date,
    is_stale_context,
    is_valid_meeting_document,
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CACHE_PATH = os.path.join(SCRIPT_DIR, "signals", "cached_portal_docs.csv")
DEFAULT_REGISTRY_PATH = os.path.join(SCRIPT_DIR, "signals", "portal_registry.csv")

# Major urban lower-tier cities excluded by default when exclude_large_cities=True
# (County Federations can still include any city explicitly via the Admin UI selector)
MAJOR_URBAN_LOWER_TIER_CITIES = {
    "MISSISSAUGA",
    "BRAMPTON",
    "BURLINGTON",
    "OAKVILLE",
    "OSHAWA",
    "PICKERING",
    "WHITBY",
    "AJAX",
    "VAUGHAN",
    "MARKHAM",
    "RICHMOND HILL",
    "KITCHENER",
    "WATERLOO, C",
    "CAMBRIDGE",
    "ST CATHARINES",
    "NIAGARA FALLS",
    "WELLAND",
    "SARNIA",
    "WOODSTOCK",
    "OWEN SOUND",
}

# Separated single-tier urban towns inside two-tier counties excluded alongside separated cities
SEPARATED_URBAN_TOWNS = {
    "ST MARYS",
    "ST. MARYS",
    "SMITHS FALLS",
    "GANANOQUE",
    "PRESCOTT",
}


def is_excluded_large_city(muni_row: pd.Series, area_df: pd.DataFrame) -> bool:
    """Return True if a municipality is a separated or large urban city inside a multi-municipality area."""
    if len(area_df) <= 1:
        # Never exclude the sole municipality in a single-municipality area (e.g. Ottawa, Hamilton, Kawartha Lakes)
        return False

    name_up = str(muni_row.get("name") or "").strip().upper()
    lk_up = str(muni_row.get("lookup_key") or "").strip().upper()
    status_up = str(muni_row.get("municipal_status") or "").strip().upper()
    has_upper_tier = area_df["municipal_status"].astype(str).str.upper().str.contains("UPPER").any()

    # 1. Separated Single-Tier cities inside counties/districts (e.g. Guelph, London, Windsor, Stratford, Barrie, Brantford, Greater Sudbury)
    if "SINGLE" in status_up and lk_up.endswith(", C"):
        return True

    # 2. Separated Single-Tier urban towns inside two-tier counties (keeps rural Pelee Tp included in Essex)
    if has_upper_tier and "SINGLE" in status_up and name_up in SEPARATED_URBAN_TOWNS:
        return True

    # 3. Major urban Lower-Tier cities inside Counties/Regions (e.g. Owen Sound, Woodstock, Sarnia, Mississauga, Kitchener)
    if name_up in MAJOR_URBAN_LOWER_TIER_CITIES:
        return True

    return False


def describe_county_scope(
    munis_df: pd.DataFrame,
    geographic_area: str,
    exclude_large_cities: bool = True,
) -> dict[str, pd.DataFrame]:
    """Split a geographic_area's municipalities into default-included vs. default-excluded cities."""
    if munis_df is None or munis_df.empty:
        return {"included_df": pd.DataFrame(), "excluded_df": pd.DataFrame()}

    if geographic_area == "ALL_ONTARIO":
        area_df = munis_df.copy()
        if not exclude_large_cities:
            return {"included_df": area_df, "excluded_df": pd.DataFrame(columns=area_df.columns)}
        excluded_ids = set()
        for _, grp in area_df.groupby("geographic_area", dropna=False):
            for _, row in grp.iterrows():
                if is_excluded_large_city(row, grp):
                    excluded_ids.add(int(row["id"]))
        inc = area_df[~area_df["id"].isin(excluded_ids)].copy()
        exc = area_df[area_df["id"].isin(excluded_ids)].copy()
        return {"included_df": inc, "excluded_df": exc}

    area_df = munis_df[munis_df["geographic_area"] == geographic_area].copy()
    if area_df.empty or not exclude_large_cities:
        return {"included_df": area_df, "excluded_df": pd.DataFrame(columns=area_df.columns)}

    exc_mask = area_df.apply(lambda r: is_excluded_large_city(r, area_df), axis=1)
    return {
        "included_df": area_df[~exc_mask].copy(),
        "excluded_df": area_df[exc_mask].copy(),
    }


def resolve_subscription_municipalities(
    munis_df: pd.DataFrame,
    subscription: dict[str, Any],
) -> pd.DataFrame:
    """Resolve the exact DataFrame of municipalities monitored for a subscription."""
    explicit_ids = [int(x) for x in (subscription.get("municipality_ids") or [])]
    if explicit_ids:
        sub_df = munis_df[munis_df["id"].isin(explicit_ids)].copy()
        if not sub_df.empty:
            return sub_df

    geo_area = str(subscription.get("geographic_area") or "").strip()
    excl = bool(subscription.get("exclude_large_cities", True))
    scope = describe_county_scope(munis_df, geo_area, exclude_large_cities=excl)
    return scope["included_df"]


def _build_muni_name_resolver(munis_df: pd.DataFrame):
    """Map cached_portal_docs municipality_name -> municipality row dict, prioritizing exact name/lookup_key."""
    exact_map: dict[str, dict[str, Any]] = {}
    canon_map: dict[str, list[dict[str, Any]]] = {}

    for _, r in munis_df.iterrows():
        rec = {
            "id": int(r["id"]),
            "name": str(r["name"]),
            "lookup_key": str(r.get("lookup_key") or ""),
            "municipal_status": str(r.get("municipal_status") or ""),
            "geographic_area": str(r.get("geographic_area") or ""),
        }
        nm_up = rec["name"].strip().upper()
        lk_up = rec["lookup_key"].strip().upper()
        if nm_up:
            exact_map[nm_up] = rec
        if lk_up:
            exact_map[lk_up] = rec
        cn = canon_name(rec["name"])
        if cn:
            canon_map.setdefault(cn, []).append(rec)

    def resolve(raw_name: str) -> dict[str, Any] | None:
        s = str(raw_name or "").strip()
        if not s:
            return None
        s_up = s.upper()
        if s_up in exact_map:
            return exact_map[s_up]
        # Disambiguate "County of X" vs "Town of X" when canon_name collides
        cn = canon_name(s)
        cands = canon_map.get(cn)
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0]
        is_county_hint = any(tok in s_up for tok in ("COUNTY", ", CO", "REGION", ", R"))
        for c in cands:
            c_is_ut = "UPPER" in c["municipal_status"].upper() or ", CO" in c["lookup_key"].upper() or ", R" in c["lookup_key"].upper()
            if is_county_hint and c_is_ut:
                return c
            if not is_county_hint and not c_is_ut:
                return c
        return cands[0]

    return resolve


def load_cached_council_docs(cache_path: str = DEFAULT_CACHE_PATH) -> pd.DataFrame:
    """Load the unified council agendas/minutes text cache."""
    if not os.path.exists(cache_path):
        return pd.DataFrame(columns=["municipality_name", "portal_type", "doc_url", "doc_text", "doc_type", "fetch_date"])
    try:
        df = pd.read_csv(cache_path)
    except Exception:
        return pd.DataFrame(columns=["municipality_name", "portal_type", "doc_url", "doc_text", "doc_type", "fetch_date"])
    for col in ("municipality_name", "portal_type", "doc_url", "doc_text", "doc_type", "fetch_date"):
        if col not in df.columns:
            df[col] = ""
    return df


def _clean_discussion_text(raw_text: str) -> str:
    """Normalize PDF/HTML whitespace while preserving natural paragraph and agenda-item line breaks."""
    if not raw_text:
        return ""
    txt = str(raw_text)
    txt = re.sub(r"<script[^>]*>.*?</script>", " ", txt, flags=re.DOTALL | re.IGNORECASE)
    txt = re.sub(r"<style[^>]*>.*?</style>", " ", txt, flags=re.DOTALL | re.IGNORECASE)
    txt = re.sub(r"<[a-zA-Z/!][^>\n]{0,300}>", " ", txt)
    txt = txt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    txt = txt.replace("&nbsp;", " ").replace("&quot;", '"')
    txt = txt.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n\n")
    # Collapse horizontal runs of spaces/tabs on each line
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in txt.split("\n")]
    txt = "\n".join(lines)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def extract_full_discussion_context(
    raw_text: str,
    matched_keywords: list[str],
    back_chars: int = 1100,
    fwd_chars: int = 2100,
    max_total_chars: int = 3800,
) -> str:
    """Extract the full surrounding agenda item, staff report, or council resolution context.

    Expands outward from keyword matches to natural section/paragraph/sentence boundaries,
    merging nearby hits in the same council item into one continuous, readable passage.
    """
    text = _clean_discussion_text(raw_text)
    if not text or not matched_keywords:
        return ""

    spans: list[tuple[int, int]] = []
    for kw in matched_keywords:
        pat = build_keyword_regex(kw)
        for m in pat.finditer(text):
            spans.append((m.start(), m.end()))
            if len(spans) >= 12:
                break

    if not spans:
        return text[:max_total_chars].strip()

    spans.sort()

    # Merge spans that belong to the same agenda item / discussion block
    clusters: list[tuple[int, int]] = []
    for s, e in spans:
        if not clusters or s - clusters[-1][1] > 1400:
            clusters.append((s, e))
        else:
            clusters[-1] = (clusters[-1][0], max(clusters[-1][1], e))

    # Focus on the primary (most keyword-dense, or first) cluster + optional second cluster if space allows
    passages: list[str] = []
    budget = max_total_chars

    agenda_heading_re = re.compile(
        r"(?:\n\s*(?:\d+(?:\.\d+){1,2}|[A-Z]\.\d+|Item\s+\d+|Report\s+(?:No\.?|#)|By-?law\s+(?:No\.?|#)|Motion\s+(?:No\.?|#)|Resolution\s+(?:No\.?|#)|MOVED\s+BY)\b|\n\n)",
        re.IGNORECASE,
    )
    resolution_end_re = re.compile(
        r"(?:\b(?:CARRIED|DEFEATED|ADOPTED|TABLED|DEFERRED)\b\.?|\n\s*(?:\d+(?:\.\d+){1,2}|[A-Z]\.\d+|Item\s+\d+)\b|\n\n)",
        re.IGNORECASE,
    )

    for c_start, c_end in clusters[:2]:
        if budget < 600:
            break
        raw_start = max(0, c_start - back_chars)
        raw_end = min(len(text), c_end + fwd_chars)

        # Snap start to a clean agenda heading or paragraph boundary before c_start
        start = raw_start
        if raw_start > 0:
            back_slice = text[raw_start:c_start]
            heading_matches = list(agenda_heading_re.finditer(back_slice))
            if heading_matches:
                # Pick the closest heading at least 120 chars before the match (or the earliest if all are close)
                chosen = None
                for hm in reversed(heading_matches):
                    if len(back_slice) - hm.start() >= 120:
                        chosen = hm
                        break
                if chosen is None:
                    chosen = heading_matches[0]
                start = raw_start + chosen.start()
            else:
                # Fall back to sentence start or whitespace boundary
                dot_idx = back_slice.find(". ")
                if dot_idx != -1 and dot_idx < 250:
                    start = raw_start + dot_idx + 2
                else:
                    sp = back_slice.find(" ")
                    if sp != -1 and sp < 40:
                        start = raw_start + sp + 1

        # Snap end to a clean CARRIED/next-heading/paragraph boundary after c_end
        end = raw_end
        if raw_end < len(text):
            fwd_slice = text[c_end:raw_end]
            end_matches = list(resolution_end_re.finditer(fwd_slice))
            chosen_end = None
            for em in end_matches:
                if em.start() >= 350:
                    # Include CARRIED/DEFEATED word itself, stop before next agenda item heading
                    matched_str = em.group(0).strip().upper()
                    if any(w in matched_str for w in ("CARRIED", "DEFEATED", "ADOPTED", "TABLED", "DEFERRED")):
                        chosen_end = c_end + em.end()
                    else:
                        chosen_end = c_end + em.start()
                    break
            if chosen_end is not None:
                end = chosen_end
            else:
                last_dot = fwd_slice.rfind(". ")
                if last_dot > 250:
                    end = c_end + last_dot + 1
                else:
                    last_sp = fwd_slice.rfind(" ")
                    if last_sp > 200:
                        end = c_end + last_sp

        excerpt = text[start:end].strip()
        if len(excerpt) > budget:
            cut = excerpt[:budget]
            last_p = cut.rfind(". ")
            if last_p > budget * 0.65:
                excerpt = cut[: last_p + 1].strip() + " ..."
            else:
                excerpt = cut.rsplit(" ", 1)[0].strip() + " ..."
        else:
            if start > 0:
                excerpt = "... " + excerpt
            if end < len(text):
                excerpt = excerpt + " ..."

        passages.append(excerpt)
        budget -= len(excerpt) + 20

    return "\n\n[...]\n\n".join(passages)


def _deterministic_summary(item: dict[str, Any]) -> dict[str, str]:
    """Fallback grounded summary when Gemini API key is unavailable or fails."""
    doc_type = str(item.get("doc_type") or "")
    kws = item.get("matched_keywords") or []
    kw_str = ", ".join(kws[:4])
    muni = item.get("municipality_name") or "Council"

    if "Upcoming Agenda" in doc_type:
        badge = "Upcoming Agenda Item"
    elif "Official Minutes" in doc_type:
        badge = "Official Council Minutes"
    elif "Agenda" in doc_type:
        badge = "Council Agenda Item"
    else:
        badge = "Council Discussion"

    ctx = str(item.get("full_context") or "").strip()
    # Pull first ~2 coherent sentences around the first matched keyword
    flat = re.sub(r"\s+", " ", ctx)
    first_kw = kws[0] if kws else ""
    lead = ""
    if first_kw:
        m = build_keyword_regex(first_kw).search(flat)
        if m:
            s = max(0, m.start() - 160)
            e = min(len(flat), m.end() + 260)
            lead = flat[s:e].strip()
            if s > 0:
                lead = "..." + lead.split(" ", 1)[-1]
            if e < len(flat):
                lead = lead.rsplit(" ", 1)[0] + "..."
    if not lead:
        lead = flat[:380] + ("..." if len(flat) > 380 else "")

    return {
        "status_badge": badge,
        "headline": f"{muni}: {kw_str} ({badge})",
        "executive_summary": (
            f"Keyword match for {kw_str} detected in {muni}'s {badge.lower()}. "
            f"Excerpt highlight: \"{lead}\""
        ),
        "key_action_or_date": f"Meeting Date: {item.get('meeting_date_display') or 'See source document'}",
        "ai_generated": False,
    }


def summarize_discussion_with_gemini(
    item: dict[str, Any],
    use_ai: bool = True,
) -> dict[str, Any]:
    """Generate a strictly grounded plain-English summary for one matched council item."""
    if not use_ai:
        return _deterministic_summary(item)

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        try:
            import streamlit as st
            api_key = str(st.secrets.get("GEMINI_API_KEY", "") or "").strip()
        except Exception:
            api_key = ""
    if not api_key:
        return _deterministic_summary(item)

    try:
        from google import genai
        from google.genai import types
    except Exception:
        return _deterministic_summary(item)

    muni = item.get("municipality_name", "Unknown Municipality")
    doc_type = item.get("doc_type", "Council Document")
    meeting_date = item.get("meeting_date_display", "Unknown")
    kws = ", ".join(item.get("matched_keywords") or [])
    excerpt = str(item.get("full_context") or "")[:4000]

    prompt = (
        "You are an agricultural policy analyst for the Ontario Federation of Agriculture (OFA), "
        "briefing a County Federation of Agriculture board on local municipal council activity.\n\n"
        "STRICT GROUNDING RULE: Base your summary EXCLUSIVELY on the verbatim council document excerpt below. "
        "Do NOT invent facts, dates, bylaw numbers, dollar amounts, or vote results that do not appear in the excerpt. "
        "If an item is only an agenda listing without full report text, state clearly that it is listed on the agenda.\n\n"
        f"Municipality: {muni}\n"
        f"Document Type: {doc_type}\n"
        f"Meeting Date: {meeting_date}\n"
        f"Matched Watchlist Keywords: {kws}\n\n"
        "VERBATIM COUNCIL EXCERPT:\n"
        f"\"\"\"\n{excerpt}\n\"\"\"\n\n"
        "Return ONLY valid JSON with these exact 4 string fields:\n"
        "{\n"
        '  "status_badge": one of ["Upcoming Agenda Item", "Public Meeting Notice", "Staff Report / Briefing", "Motion / Resolution Passed", "By-law Enacted / Amended", "Council Discussion"],\n'
        '  "headline": "Concise 6 to 12 word factual title of the municipal item",\n'
        '  "executive_summary": "2 to 4 clear, plain-English sentences explaining what Council is proposing, discussing, or deciding, including any stated recommendations, bylaw numbers, locations, or agricultural impacts mentioned in the excerpt.",\n'
        '  "key_action_or_date": "1 short line noting any upcoming public meeting date, deadline, or vote outcome stated in the excerpt (or empty string if none)"\n'
        "}"
    )

    import time
    client = genai.Client(api_key=api_key)
    for attempt_idx, model_id in enumerate(("gemini-3.5-flash-lite", "gemini-3.5-flash-lite", "gemini-3.8-flash")):
        if attempt_idx > 0:
            time.sleep(2.0)
        try:
            resp = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    response_mime_type="application/json",
                ),
            )
            raw_out = (resp.text or "").strip()
            raw_out = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_out, flags=re.DOTALL).strip()
            parsed = json.loads(raw_out)
            if isinstance(parsed, dict) and parsed.get("executive_summary"):
                return {
                    "status_badge": str(parsed.get("status_badge") or "Council Discussion").strip(),
                    "headline": str(parsed.get("headline") or f"{muni}: {kws}").strip(),
                    "executive_summary": str(parsed.get("executive_summary") or "").strip(),
                    "key_action_or_date": str(parsed.get("key_action_or_date") or "").strip(),
                    "ai_generated": True,
                }
        except Exception:
            continue

    return _deterministic_summary(item)


def compute_item_content_hash(
    municipality_id: int | None,
    doc_url: str,
    doc_type: str,
    matched_keywords: list[str],
) -> str:
    """Stable deduplication hash per (municipality, meeting/url, doc_type, matched_keywords).

    Includes doc_type so an Upcoming Agenda item WILL alert again when published as Official Minutes,
    while identical Minutes remain suppressed on subsequent Mondays.
    """
    url_norm = str(doc_url or "").strip().lower()
    # Normalize eScribe GUID while keeping doc_type distinct
    m_guid = re.search(r"id=([a-f0-9\-]+)", url_norm, re.IGNORECASE)
    doc_key = f"escribe:{m_guid.group(1)}" if m_guid else url_norm.split("?")[0]
    kw_sig = "|".join(sorted({k.strip().lower() for k in matched_keywords}))
    payload = f"{municipality_id or 0}|{doc_key}|{doc_type.strip().lower()}|{kw_sig}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def build_county_digest_payload(
    subscription: dict[str, Any],
    munis_df: pd.DataFrame,
    cached_docs_df: pd.DataFrame | None = None,
    exclude_hashes: set[str] | None = None,
    use_ai: bool = True,
    max_days: int = 180,
    cache_path: str = DEFAULT_CACHE_PATH,
    conn=None,
    upcoming_renewals: list[dict[str, Any]] | None = None,
    renewal_months: int = 12,
) -> dict[str, Any]:
    """Build the complete structured weekly digest payload for one County Federation subscription.

    Returns a dict containing metadata, coverage counts (portals checked / munis monitored),
    deduplicated matched items with full discussion context + grounded summaries, upcoming
    12-month bylaw renewals from the OFA Bylaw Database, and skipped counts.
    """
    if cached_docs_df is None:
        cached_docs_df = load_cached_council_docs(cache_path)

    scope_munis = resolve_subscription_municipalities(munis_df, subscription)
    scope_ids = set(scope_munis["id"].astype(int).tolist()) if not scope_munis.empty else set()
    resolver = _build_muni_name_resolver(munis_df)

    # Fetch upcoming bylaw renewals (next 12 months) for all monitored County + Lower/Single-Tier municipalities
    if upcoming_renewals is None and conn is not None and scope_ids:
        try:
            from db_utils import get_upcoming_bylaw_renewals
            upcoming_renewals = get_upcoming_bylaw_renewals(conn, list(scope_ids), months_ahead=renewal_months)
        except Exception:
            upcoming_renewals = []
    elif upcoming_renewals is None:
        upcoming_renewals = []

    pos_kws = [str(k).strip() for k in (subscription.get("keywords") or []) if str(k).strip()]
    neg_kws = [str(k).strip() for k in (subscription.get("negative_keywords") or []) if str(k).strip()]

    sorted_pos = sorted(pos_kws, key=len, reverse=True)
    combined_pat = build_combined_keyword_regex(sorted_pos)
    kw_patterns = [(kw, build_keyword_regex(kw)) for kw in sorted_pos]

    exclude_hashes = exclude_hashes or set()
    docs_checked = 0
    munis_with_docs_checked: set[int] = set()
    already_sent_skipped = 0

    # Collect raw matches keyed by (muni_id, meeting_key) so Minutes win over Agenda if both are cached
    by_meeting: dict[tuple[int, str], dict[str, Any]] = {}

    if not cached_docs_df.empty and scope_ids and sorted_pos:
        for _, row in cached_docs_df.iterrows():
            raw_muni = str(row.get("municipality_name") or "").strip()
            mrec = resolver(raw_muni)
            if not mrec or mrec["id"] not in scope_ids:
                continue

            doc_text = str(row.get("doc_text") or "")
            doc_url = str(row.get("doc_url") or "").strip()
            fetch_date = str(row.get("fetch_date") or "").strip()[:10]
            if len(doc_text.strip()) < 50 or not doc_url:
                continue

            # 180-day recency check + valid council meeting filter
            u_dt = extract_date_from_text(doc_url)
            if u_dt and not is_recent_date(u_dt, max_days=max_days):
                continue
            h_dt = extract_date_from_text(doc_text[:600])
            if h_dt and not is_recent_date(h_dt, max_days=max_days):
                continue
            if not is_valid_meeting_document(doc_url, doc_text):
                continue

            docs_checked += 1
            munis_with_docs_checked.add(mrec["id"])

            filtered_text = apply_negative_keywords(doc_text, neg_kws) if neg_kws else doc_text
            if not combined_pat.search(filtered_text):
                continue

            matched_kws: list[str] = []
            matched_lows: list[str] = []
            for kw, kw_re in kw_patterns:
                kl = kw.lower()
                if any(kl in prev for prev in matched_lows):
                    continue
                if kw_re.search(filtered_text):
                    matched_kws.append(kw)
                    matched_lows.append(kl)

            if not matched_kws:
                continue

            full_context = extract_full_discussion_context(filtered_text, matched_kws)
            if is_stale_context(doc_url, doc_text[:600], full_context[:800], max_days=max_days):
                continue

            doc_type = str(row.get("doc_type") or "").strip()
            if not doc_type or doc_type.lower() == "nan":
                doc_type = classify_meeting_doc(doc_url, doc_text)

            meeting_dt = u_dt or h_dt or extract_date_from_text(full_context[:600])
            meeting_date_iso = meeting_dt.isoformat() if meeting_dt else fetch_date
            meeting_date_display = (
                meeting_dt.strftime("%B %d, %Y")
                if meeting_dt
                else (f"Fetched {fetch_date}" if fetch_date else "Recent 2026 Meeting")
            )

            m_guid = re.search(r"id=([a-f0-9\-]+)", doc_url, re.IGNORECASE)
            meeting_key = m_guid.group(1).lower() if m_guid else doc_url.split("?")[0].lower()

            c_hash = compute_item_content_hash(mrec["id"], doc_url, doc_type, matched_kws)
            candidate = {
                "municipality_id": mrec["id"],
                "municipality_name": mrec["name"],
                "municipal_status": mrec["municipal_status"],
                "geographic_area": mrec["geographic_area"],
                "doc_url": doc_url,
                "doc_type": doc_type,
                "meeting_date_iso": meeting_date_iso,
                "meeting_date_display": meeting_date_display,
                "fetch_date": fetch_date,
                "matched_keywords": matched_kws,
                "full_context": full_context,
                "content_hash": c_hash,
            }

            dedup_key = (mrec["id"], meeting_key)
            if dedup_key not in by_meeting:
                by_meeting[dedup_key] = candidate
            else:
                # Upgrade Agenda -> Official Minutes if both exist for same meeting
                if "Official Minutes" in doc_type and "Official Minutes" not in by_meeting[dedup_key]["doc_type"]:
                    by_meeting[dedup_key] = candidate

    # Apply week-over-week sent deduplication + summarize surviving items
    final_items: list[dict[str, Any]] = []
    for item in by_meeting.values():
        if item["content_hash"] in exclude_hashes:
            already_sent_skipped += 1
            continue
        summary_info = summarize_discussion_with_gemini(item, use_ai=use_ai)
        item.update(summary_info)
        final_items.append(item)

    # Sort newest meeting first, with Upcoming Agendas prominently ordered at the top
    def _sort_key(it: dict[str, Any]):
        is_upcoming = 0 if "Upcoming" in str(it.get("doc_type", "")) else 1
        return (is_upcoming, -(int(re.sub(r"\D", "", it.get("meeting_date_iso") or "0") or 0)), it["municipality_name"])

    final_items.sort(key=_sort_key)

    return {
        "subscription": subscription,
        "generated_at": datetime.datetime.now().strftime("%B %d, %Y at %I:%M %p"),
        "run_date": datetime.date.today().isoformat(),
        "geographic_area": subscription.get("geographic_area", ""),
        "federation_name": subscription.get("federation_name", ""),
        "monitored_municipalities": sorted(scope_munis["name"].tolist()) if not scope_munis.empty else [],
        "monitored_count": len(scope_ids),
        "munis_with_docs_checked": len(munis_with_docs_checked),
        "docs_checked": docs_checked,
        "already_sent_skipped": already_sent_skipped,
        "keywords": pos_kws,
        "negative_keywords": neg_kws,
        "items": final_items,
        "upcoming_renewals": upcoming_renewals,
        "renewal_months": renewal_months,
    }
