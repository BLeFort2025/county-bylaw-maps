"""
county_digest_admin_ui.py — Streamlit Admin UI module for managing OFA County Federation
Weekly Municipal Council Digest subscriptions, live OFA-branded previews, on-demand test sends,
and delivery audit logs.

Imported by pages/4_🔒_Admin.py under the "📬 County Federation Digests" mode.
"""

from __future__ import annotations

import datetime
import streamlit as st
import streamlit.components.v1 as components

from county_digest_engine import (
    DEFAULT_CACHE_PATH,
    build_county_digest_payload,
    describe_county_scope,
    format_areas_human,
    format_geographic_areas,
    load_cached_council_docs,
    parse_geographic_areas,
)
from county_digest_mailer import (
    load_smtp_settings,
    process_subscription,
    render_county_digest_html,
)
from db_utils import (
    DEFAULT_BCC_EMAIL,
    delete_county_subscription,
    ensure_digest_tables,
    get_digest_sent_history,
    get_geographic_areas,
    get_municipalities,
    get_sent_content_hashes,
    list_county_subscriptions,
    upsert_county_subscription,
)
from shared_config import CUSTOM_KEYWORD_PACKS, OFA_BYLAW_CATEGORY_PACKS


def render_county_digest_admin(conn) -> None:
    """Render the full County Federation Digests management tab inside Admin."""
    ensure_digest_tables(conn)

    st.title("📬 County Federation Weekly Digests")
    st.markdown(
        "Manage automated **Monday 9:00 AM** OFA-branded email digests for County Federations "
        "(and custom test watchlists to your own inbox). Active subscriptions send directly to "
        f"signed-up recipients and **always blind-copy `{DEFAULT_BCC_EMAIL}`**."
    )

    munis_df = get_municipalities(conn)
    cached_docs_df = load_cached_council_docs(DEFAULT_CACHE_PATH)
    subs = list_county_subscriptions(conn, active_only=False)
    smtp_cfg = load_smtp_settings()

    # Top status banner
    m1, m2, m3, m4 = st.columns(4)
    active_count = sum(1 for s in subs if s["active"] and not s["is_test_profile"])
    test_count = sum(1 for s in subs if s["is_test_profile"])
    cached_muni_cnt = int(cached_docs_df["municipality_name"].nunique()) if not cached_docs_df.empty else 0
    m1.metric("Active County Federations", active_count)
    m2.metric("Custom / Test Profiles", test_count)
    m3.metric("Cached Council Docs", f"{len(cached_docs_df)} ({cached_muni_cnt} munis)")
    m4.metric("SMTP Email Status", "✅ Ready" if smtp_cfg["configured"] else "⚠️ Not Configured")

    tab_manage, tab_preview, tab_history = st.tabs([
        "📋 Subscriptions & Watchlists",
        "👁️ Live Preview & Test Send",
        "📜 Delivery History",
    ])

    # ═══════════════════════════════════════════════════════════════
    # TAB 1: Create / Edit Subscriptions & Watchlists
    # ═══════════════════════════════════════════════════════════════
    with tab_manage:
        if subs:
            summary_rows = []
            for s in subs:
                is_pending_msr = (not s["active"]) and ("[MSR SELF-SERVE REQUEST" in (s.get("notes") or ""))
                status_badge = "✅ Active" if s["active"] else ("🟡 Pending MSR Request" if is_pending_msr else "⏸️ Paused")
                summary_rows.append({
                    "ID": s["id"],
                    "Federation / Profile": ("🧪 " if s["is_test_profile"] else "🌾 ") + s["federation_name"],
                    "County / Area": format_areas_human(s["geographic_area"]),
                    "Munis": len(s["municipality_ids"]) if s["municipality_ids"] else "Auto",
                    "Keywords": len(s["keywords"]),
                    "Recipients (To)": s["recipient_emails"],
                    "Quiet Week": "All-Clear Email" if s["send_empty_digest"] else "Skip",
                    "Status": status_badge,
                })
            st.dataframe(summary_rows, use_container_width=True, hide_index=True)
        else:
            st.info("No County Federation digest subscriptions configured yet. Create your first subscription or personal test run below.")

        st.markdown("---")
        choice_labels = ["➕ Create New County Federation / Custom Test Profile"] + [
            f"[{s['id']}] {'🧪 ' if s['is_test_profile'] else ''}{s['federation_name']} ({s['geographic_area']})"
            for s in subs
        ]
        selected_choice = st.selectbox("Select Subscription to Edit or Create", choice_labels, key="digest_sub_selector")

        editing_sub = None
        if selected_choice != choice_labels[0]:
            sel_id = int(selected_choice.split("]", 1)[0].lstrip("["))
            for s in subs:
                if s["id"] == sel_id:
                    editing_sub = s
                    break

        is_new = editing_sub is None
        sub_key = f"sub_{editing_sub['id']}" if editing_sub else "sub_new"

        st.subheader("➕ New Subscription" if is_new else f"✏️ Edit: {editing_sub['federation_name']}")

        # Preset Keyword Pack helper (outside form so clicking adds cleanly)
        all_packs = {**OFA_BYLAW_CATEGORY_PACKS, **CUSTOM_KEYWORD_PACKS}
        pcol1, pcol2 = st.columns([3, 1])
        with pcol1:
            pack_to_add = st.selectbox(
                "Quick-Add Preset Keyword Pack (optional)",
                ["— Choose a preset pack to add —"] + list(all_packs.keys()),
                key=f"pack_sel_{sub_key}",
            )
        with pcol2:
            st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
            if st.button("➕ Add Keywords", key=f"btn_append_pack_{sub_key}", use_container_width=True):
                if pack_to_add in all_packs:
                    kw_state_key = f"kw_text_{sub_key}"
                    existing_txt = st.session_state.get(
                        kw_state_key,
                        "\n".join(editing_sub["keywords"]) if editing_sub else "",
                    )
                    existing_lines = [ln.strip() for ln in existing_txt.splitlines() if ln.strip()]
                    existing_low = {ln.lower() for ln in existing_lines}
                    for kw in all_packs[pack_to_add]:
                        if kw.lower() not in existing_low:
                            existing_lines.append(kw)
                            existing_low.add(kw.lower())
                    st.session_state[kw_state_key] = "\n".join(existing_lines)
                    st.rerun()

        # Reactive area(s) + exclude_large_cities controls (outside form so municipality list updates immediately)
        geo_areas = get_geographic_areas(conn)
        existing_parsed_areas = parse_geographic_areas(editing_sub["geographic_area"]) if editing_sub else []
        existing_is_all = existing_parsed_areas == ["ALL_ONTARIO"]

        c_top1, c_top2, c_top3 = st.columns([2.2, 1.4, 1.4])
        with c_top1:
            province_wide_mode = st.checkbox(
                "🌐 Province-Wide (All Ontario)",
                value=existing_is_all,
                key=f"pw_mode_{sub_key}",
                help="Check for a province-wide custom run; uncheck to select one or more specific counties below.",
            )
        with c_top2:
            exclude_cities = st.checkbox(
                "Exclude large / separated cities by default",
                value=editing_sub["exclude_large_cities"] if editing_sub else True,
                key=f"excl_cities_{sub_key}",
                help="Excludes separated cities (e.g. Guelph, London, Stratford, Windsor, Barrie) and major urban cities by default. You can still toggle any municipality below.",
            )
        with c_top3:
            is_test_profile = st.checkbox(
                "🧪 Custom Test Profile (Ben's Test Run)",
                value=editing_sub["is_test_profile"] if editing_sub else False,
                key=f"is_test_{sub_key}",
                help="Marks this profile as a personal/test run (defaults To email to ben.lefort@ofa.on.ca).",
            )

        if province_wide_mode:
            selected_areas = ["ALL_ONTARIO"]
        else:
            default_multi = [a for a in existing_parsed_areas if a in geo_areas]
            if not default_multi and geo_areas:
                default_multi = [geo_areas[0]]
            selected_areas = st.multiselect(
                "County / Geographic Area(s) — select one or more",
                options=geo_areas,
                default=default_multi,
                key=f"area_ms_{sub_key}",
                help="Select a single county or multiple counties. Multi-county digests automatically divide results by county.",
            )

        selected_area = format_geographic_areas(selected_areas)
        area_human_lbl = format_areas_human(selected_areas)
        is_multi_area = len(selected_areas) > 1 and not province_wide_mode

        # Compute available municipalities & defaults for selected_areas
        scope = describe_county_scope(munis_df, selected_areas, exclude_large_cities=exclude_cities)
        inc_df = scope["included_df"]
        exc_df = scope["excluded_df"]

        if province_wide_mode:
            all_area_df = munis_df.copy()
        elif selected_areas:
            all_area_df = munis_df[munis_df["geographic_area"].isin(selected_areas)].copy()
        else:
            all_area_df = munis_df.iloc[0:0].copy()

        muni_label_to_id = {}
        muni_id_to_label = {}
        for _, mr in all_area_df.sort_values(["geographic_area", "name"]).iterrows():
            lbl = f"{mr['name']} [{mr['geographic_area']} — {mr['municipal_status']}]" if is_multi_area else f"{mr['name']} ({mr['municipal_status']})"
            mid = int(mr["id"])
            muni_label_to_id[lbl] = mid
            muni_id_to_label[mid] = lbl

        # Determine pre-selected municipalities
        if editing_sub and editing_sub["geographic_area"] == selected_area and editing_sub["municipality_ids"]:
            default_selected_labels = [
                muni_id_to_label[mid] for mid in editing_sub["municipality_ids"] if mid in muni_id_to_label
            ]
        else:
            default_selected_labels = [
                muni_id_to_label[int(mid)] for mid in inc_df["id"].tolist() if int(mid) in muni_id_to_label
            ]

        if not province_wide_mode:
            if selected_areas:
                area_sig = "_".join(sorted(selected_areas))[:80]
                selected_muni_labels = st.multiselect(
                    f"Municipalities Monitored across {area_human_lbl} ({len(default_selected_labels)} default)",
                    options=list(muni_label_to_id.keys()),
                    default=default_selected_labels,
                    key=f"munis_ms_{sub_key}_{area_sig}_{exclude_cities}",
                )
                chosen_muni_ids = [muni_label_to_id[lbl] for lbl in selected_muni_labels]
                if not exc_df.empty:
                    exc_names = ", ".join(sorted(exc_df["name"].tolist()))
                    st.caption(f"🏙️ Excluded by default (large/separated cities): **{exc_names}** — add any of them above if requested by the County Federation.")
            else:
                st.warning("Please select at least one County / Geographic Area above.")
                chosen_muni_ids = []
        else:
            st.info(
                f"🌐 **Province-Wide Scope:** Monitors **{len(inc_df)}** municipalities "
                + (f"(excluding {len(exc_df)} large/separated cities)." if exclude_cities else "(all 444 Ontario municipalities).")
            )
            chosen_muni_ids = []  # Dynamic province-wide resolution

        # Main Save Form
        with st.form(f"digest_form_{sub_key}"):
            if editing_sub:
                default_fed_name = editing_sub["federation_name"]
            elif is_test_profile:
                default_fed_name = f"Ben Test — {'Province-Wide' if province_wide_mode else area_human_lbl}"
            elif province_wide_mode:
                default_fed_name = "OFA Province-Wide Watch"
            elif len(selected_areas) == 1:
                default_fed_name = f"{selected_areas[0]} Federation of Agriculture"
            else:
                default_fed_name = f"{area_human_lbl} Municipal Council Watch"
            default_to = (
                editing_sub["recipient_emails"]
                if editing_sub
                else (DEFAULT_BCC_EMAIL if is_test_profile else "")
            )
            default_cc = editing_sub["cc_emails"] if editing_sub else ""
            default_bcc = editing_sub["bcc_emails"] if editing_sub else DEFAULT_BCC_EMAIL
            default_kw_str = st.session_state.get(
                f"kw_text_{sub_key}",
                "\n".join(editing_sub["keywords"]) if editing_sub else "",
            )
            default_neg_str = "\n".join(editing_sub["negative_keywords"]) if editing_sub else ""

            f1, f2 = st.columns(2)
            with f1:
                fed_name = st.text_input("County Federation / Profile Name *", value=default_fed_name)
                recip_emails = st.text_input(
                    "Recipient Emails (To) — comma-separated *",
                    value=default_to,
                    placeholder="president@countyfa.ca, admin@countyfa.ca",
                )
                cc_emails = st.text_input(
                    "CC Emails (optional — e.g. local MSR)",
                    value=default_cc,
                    placeholder="msr@ofa.on.ca",
                )
                bcc_emails = st.text_input(
                    "BCC Emails (Ben is always blind-copied automatically on Monday runs)",
                    value=default_bcc or DEFAULT_BCC_EMAIL,
                )

            with f2:
                send_empty = st.checkbox(
                    "Send 'All Clear (0 matches)' email on quiet weeks",
                    value=editing_sub["send_empty_digest"] if editing_sub else True,
                )
                is_active = st.checkbox(
                    "Active — include in automated Monday 9:00 AM email run",
                    value=editing_sub["active"] if editing_sub else True,
                )
                notes = st.text_input(
                    "Internal Notes (optional)",
                    value=editing_sub["notes"] if editing_sub else "",
                    placeholder="e.g. Requested by County Board Nov 2026",
                )

            kcol1, kcol2 = st.columns(2)
            with kcol1:
                kw_text = st.text_area(
                    "Watchlist Keywords (one phrase per line) *",
                    value=default_kw_str,
                    height=180,
                    placeholder="Tree Cutting By-law\nSite Alteration\nBattery Energy Storage\nBESS\nSolar Farm\nDrainage\nDevelopment Charges",
                    help="Matches Bylaw / By-law and case variations automatically.",
                )
            with kcol2:
                neg_text = st.text_area(
                    "Exclude Words / Negative Keywords (optional, one per line)",
                    value=default_neg_str,
                    height=180,
                    placeholder="greenhouse gas\nNon-Development Charge",
                    help="Any mention matching these exclusion phrases is ignored.",
                )

            submitted = st.form_submit_button("💾 Save County Digest Subscription", type="primary", use_container_width=True)
            if submitted:
                pos_list = [ln.strip() for ln in kw_text.splitlines() if ln.strip()]
                neg_list = [ln.strip() for ln in neg_text.splitlines() if ln.strip()]
                if not fed_name.strip():
                    st.error("Please enter a Federation or Profile Name.")
                elif not selected_area:
                    st.error("Please select at least one County / Geographic Area above.")
                elif not recip_emails.strip() or "@" not in recip_emails:
                    st.error("Please enter at least one valid Recipient Email address.")
                elif not pos_list:
                    st.error("Please enter at least one Watchlist Keyword.")
                else:
                    sub_payload = {
                        "id": editing_sub["id"] if editing_sub else None,
                        "federation_name": fed_name.strip(),
                        "geographic_area": selected_area,
                        "municipality_ids": chosen_muni_ids,
                        "exclude_large_cities": exclude_cities,
                        "recipient_emails": recip_emails.strip(),
                        "cc_emails": cc_emails.strip(),
                        "bcc_emails": bcc_emails.strip() or DEFAULT_BCC_EMAIL,
                        "send_empty_digest": send_empty,
                        "is_test_profile": is_test_profile,
                        "active": is_active,
                        "notes": notes.strip(),
                    }
                    saved_id = upsert_county_subscription(conn, sub_payload, pos_list, neg_list)
                    st.session_state.pop(f"kw_text_{sub_key}", None)
                    st.success(f"✅ Saved subscription **#{saved_id} — {fed_name.strip()}** ({len(pos_list)} keywords) to live database!")
                    st.rerun()

        if editing_sub:
            with st.expander("🗑️ Delete This Subscription"):
                st.warning(f"This permanently removes **{editing_sub['federation_name']}**, its watchlist, and its sent history.")
                if st.button("Confirm Permanent Delete", key=f"del_sub_{editing_sub['id']}"):
                    delete_county_subscription(conn, editing_sub["id"])
                    st.success("Subscription deleted.")
                    st.rerun()

    # ═══════════════════════════════════════════════════════════════
    # TAB 2: Live Preview & On-Demand Test / Custom Send
    # ═══════════════════════════════════════════════════════════════
    with tab_preview:
        if not subs:
            st.info("Create at least one subscription in the **Subscriptions & Watchlists** tab to preview and test emails.")
        else:
            prev_choices = {
                f"[{s['id']}] {'🧪 ' if s['is_test_profile'] else '🌾 '}{s['federation_name']} ({s['geographic_area']})": s
                for s in subs
            }
            chosen_prev_lbl = st.selectbox("Select Subscription to Preview or Send", list(prev_choices.keys()), key="prev_sub_sel")
            chosen_sub = prev_choices[chosen_prev_lbl]

            opt1, opt2 = st.columns(2)
            with opt1:
                use_ai_prev = st.checkbox("Use Gemini AI Plain-English Summaries", value=True, key="prev_use_ai")
            with opt2:
                ignore_dedup_prev = st.checkbox(
                    "Include previously sent items (recommended for previews/testing)",
                    value=True,
                    key="prev_ignore_dedup",
                )

            b1, b2, b3 = st.columns(3)
            with b1:
                run_preview_btn = st.button("🔍 Generate Live Preview", type="primary", use_container_width=True)
            with b2:
                send_test_btn = st.button(f"📧 Send Test Email to {DEFAULT_BCC_EMAIL}", use_container_width=True)
            with b3:
                confirm_live = st.checkbox("Confirm live send to county recipients", value=False, key="confirm_live_send")
                send_live_btn = st.button(
                    "🚀 Send Live Email Now",
                    disabled=not confirm_live,
                    use_container_width=True,
                )

            if run_preview_btn:
                with st.spinner("Scanning cached council documents and generating OFA-branded digest..."):
                    sent_hashes = set() if ignore_dedup_prev else get_sent_content_hashes(conn, chosen_sub["id"])
                    payload = build_county_digest_payload(
                        subscription=chosen_sub,
                        munis_df=munis_df,
                        cached_docs_df=cached_docs_df,
                        exclude_hashes=sent_hashes,
                        use_ai=use_ai_prev,
                        conn=conn,
                    )
                    subj, html_inline = render_county_digest_html(payload, logo_mode="inline", is_test_banner=False)
                    st.session_state["_digest_preview_payload"] = payload
                    st.session_state["_digest_preview_subject"] = subj
                    st.session_state["_digest_preview_html"] = html_inline

            if send_test_btn:
                with st.spinner(f"Building and sending test email to {DEFAULT_BCC_EMAIL}..."):
                    res = process_subscription(
                        conn=conn,
                        subscription=chosen_sub,
                        munis_df=munis_df,
                        cached_docs_df=cached_docs_df,
                        dry_run=False,
                        test_to=DEFAULT_BCC_EMAIL,
                        ignore_dedup=ignore_dedup_prev,
                        use_ai=use_ai_prev,
                    )
                    if res["status"] == "sent":
                        st.success(f"✅ Test email sent to **{DEFAULT_BCC_EMAIL}** ({res['hits']} matches) — Subject: *{res.get('subject')}*")
                    else:
                        st.error(f"❌ Test send failed: {res.get('message')}")

            if send_live_btn and confirm_live:
                with st.spinner("Sending live digest email to recipients + BCC Ben..."):
                    res = process_subscription(
                        conn=conn,
                        subscription=chosen_sub,
                        munis_df=munis_df,
                        cached_docs_df=cached_docs_df,
                        dry_run=False,
                        test_to=None,
                        ignore_dedup=False,
                        use_ai=use_ai_prev,
                    )
                    if res["status"] == "sent":
                        st.success(f"✅ Live digest sent! {res['message']} ({res['hits']} matches)")
                    elif res["status"] == "skipped_empty":
                        st.info("0 new matches and quiet-week email is disabled for this subscription.")
                    else:
                        st.error(f"❌ Send failed: {res.get('message')}")

            if st.session_state.get("_digest_preview_html"):
                pl = st.session_state["_digest_preview_payload"]
                st.markdown("---")
                pm1, pm2, pm3, pm4, pm5 = st.columns(5)
                pm1.metric("Matches Found", len(pl["items"]))
                pm2.metric("Municipalities Watched", pl["monitored_count"])
                pm3.metric("Munis with Cached Docs", pl["munis_with_docs_checked"])
                pm4.metric("Council Docs Checked", pl["docs_checked"])
                pm5.metric("Upcoming Renewals (12 Mo)", len(pl.get("upcoming_renewals") or []))
                st.caption(f"**Email Subject:** `{st.session_state['_digest_preview_subject']}`")
                components.html(st.session_state["_digest_preview_html"], height=920, scrolling=True)
                st.download_button(
                    "📥 Download Preview HTML",
                    data=st.session_state["_digest_preview_html"].encode("utf-8"),
                    file_name=f"county_digest_preview_{datetime.date.today().isoformat()}.html",
                    mime="text/html",
                )

    # ═══════════════════════════════════════════════════════════════
    # TAB 3: Sent History & Deduplication Log
    # ═══════════════════════════════════════════════════════════════
    with tab_history:
        st.subheader("📜 Weekly Digest Delivery & Deduplication Log")
        filter_opts = ["All Subscriptions"] + [f"[{s['id']}] {s['federation_name']}" for s in subs]
        hist_filter = st.selectbox("Filter by Subscription", filter_opts, key="hist_sub_filter")
        hist_sub_id = None
        if hist_filter != "All Subscriptions":
            hist_sub_id = int(hist_filter.split("]", 1)[0].lstrip("["))

        hist_df = get_digest_sent_history(conn, subscription_id=hist_sub_id, limit=200)
        if hist_df.empty:
            st.info("No County Federation digest emails have been sent yet.")
        else:
            st.dataframe(hist_df, use_container_width=True, hide_index=True)
            st.download_button(
                "📥 Download Delivery History CSV",
                data=hist_df.to_csv(index=False).encode("utf-8"),
                file_name=f"county_digest_history_{datetime.date.today().isoformat()}.csv",
                mime="text/csv",
            )

        if hist_sub_id is not None:
            with st.expander("🔄 Reset Deduplication History for Selected Subscription"):
                st.caption("Clearing the sent log allows previously delivered agenda/minutes items to be included again on the next run.")
                if st.button("Clear Sent Log for This Subscription", key=f"clear_log_{hist_sub_id}"):
                    conn.execute("DELETE FROM county_digest_sent_log WHERE subscription_id = %s", (hist_sub_id,))
                    conn.commit()
                    st.success("Deduplication log cleared for this subscription.")
                    st.rerun()
