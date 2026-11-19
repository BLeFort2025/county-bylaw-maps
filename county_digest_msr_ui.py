"""
county_digest_msr_ui.py — Self-Serve MSR & County Federation Keyword Sandbox,
Live OFA-Branded Digest Preview, Sample Email (OFA staff only), and Enrollment Request UI.

Embedded as a tab inside pages/5_🔎_Intelligence_Scanner.py so MSRs can freely experiment
with keywords for their counties without needing Admin database-editing access.
Submitted enrollment requests are saved as Pending (active=0) in Neon PostgreSQL and
email ben.lefort@ofa.on.ca for 1-click activation in Admin.
"""

from __future__ import annotations

import datetime
import html
import streamlit as st
import streamlit.components.v1 as components

from county_digest_engine import (
    DEFAULT_CACHE_PATH,
    build_county_digest_payload,
    describe_county_scope,
    format_areas_human,
    format_geographic_areas,
    load_cached_council_docs,
)
from county_digest_mailer import (
    OFA_BLUEWOOD,
    OFA_VALENCIA,
    load_smtp_settings,
    render_county_digest_html,
    send_branded_email,
)
from db_utils import (
    DEFAULT_BCC_EMAIL,
    ensure_digest_tables,
    get_connection,
    get_geographic_areas,
    get_municipalities,
    upsert_county_subscription,
)
from shared_config import CUSTOM_KEYWORD_PACKS, OFA_BYLAW_CATEGORY_PACKS


def render_msr_digest_sandbox() -> None:
    """Render the self-serve MSR County Digest Keyword Sandbox & Sign-Up tab."""
    st.header("📬 County Weekly Council Digest — Preview & Sign-Up")
    st.markdown(
        "Test custom keywords for your county and preview the exact **OFA-branded Monday morning email** "
        "(including plain-English summaries, full council discussion context, and upcoming 12-month bylaw renewals). "
        "When you're happy with your keyword list, submit it at the bottom to enroll your County Federation."
    )

    try:
        conn = get_connection()
        ensure_digest_tables(conn)
        munis_df = get_municipalities(conn)
        geo_areas = get_geographic_areas(conn)
    except Exception as exc:
        st.error(f"Unable to connect to the Municipal Bylaw Database: {exc}")
        return

    cached_docs_df = load_cached_council_docs(DEFAULT_CACHE_PATH)
    smtp_cfg = load_smtp_settings()

    # ── Step 1: Select One or More Counties & Municipalities ──
    st.subheader("1️⃣ Choose Your County / Region(s)")
    c1, c2 = st.columns([2.2, 1.3])
    with c1:
        default_areas = ["Bruce"] if "Bruce" in geo_areas else ([geo_areas[0]] if geo_areas else [])
        selected_areas = st.multiselect(
            "County / Geographic Area(s) — select one or more",
            options=geo_areas,
            default=default_areas,
            key="msr_digest_areas",
            help="Select one county, or multiple counties (e.g., all counties in your MSR territory). Results in the email are clearly divided by county.",
        )
    with c2:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        exclude_cities = st.checkbox(
            "Exclude large / separated cities (default)",
            value=True,
            key="msr_digest_excl_cities",
            help="Large/separated cities (e.g., Guelph, London, Stratford, Windsor, Barrie) are excluded by default. You can add any municipality back below.",
        )

    selected_areas_str = format_geographic_areas(selected_areas)
    area_human_label = format_areas_human(selected_areas)
    is_multi = len(selected_areas) > 1

    scope = describe_county_scope(munis_df, selected_areas, exclude_large_cities=exclude_cities)
    inc_df = scope["included_df"]
    exc_df = scope["excluded_df"]
    all_area_df = munis_df[munis_df["geographic_area"].isin(selected_areas)].copy() if selected_areas else munis_df.iloc[0:0].copy()

    muni_label_to_id = {}
    muni_id_to_label = {}
    for _, mr in all_area_df.sort_values(["geographic_area", "name"]).iterrows():
        lbl = f"{mr['name']} [{mr['geographic_area']} — {mr['municipal_status']}]" if is_multi else f"{mr['name']} ({mr['municipal_status']})"
        mid = int(mr["id"])
        muni_label_to_id[lbl] = mid
        muni_id_to_label[mid] = lbl

    default_labels = [
        muni_id_to_label[int(mid)] for mid in inc_df["id"].tolist() if int(mid) in muni_id_to_label
    ]
    if selected_areas:
        area_key_sig = "_".join(sorted(selected_areas))[:80]
        selected_muni_labels = st.multiselect(
            f"Municipalities Included across {area_human_label} ({len(default_labels)} selected by default)",
            options=list(muni_label_to_id.keys()),
            default=default_labels,
            key=f"msr_munis_{area_key_sig}_{exclude_cities}",
        )
        chosen_muni_ids = [muni_label_to_id[lbl] for lbl in selected_muni_labels]
    else:
        st.warning("Please select at least one County / Region above.")
        chosen_muni_ids = []

    if not exc_df.empty:
        exc_names = ", ".join(sorted(exc_df["name"].tolist()))
        st.caption(
            f"🏙️ Excluded by default (large/separated cities): **{exc_names}** — "
            "you can add any of them above if your County Federation wants them monitored."
        )

    # ── Step 2: Experiment With Keywords ──
    st.subheader("2️⃣ Experiment With Keywords")
    all_packs = {**OFA_BYLAW_CATEGORY_PACKS, **CUSTOM_KEYWORD_PACKS}
    pcol1, pcol2, pcol3 = st.columns([2.5, 1, 1])
    with pcol1:
        pack_choice = st.selectbox(
            "Quick-Add OFA Preset Keyword Pack",
            ["— Choose a preset pack to add —"] + list(all_packs.keys()),
            key="msr_pack_choice",
        )
    with pcol2:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        if st.button("➕ Add Keywords", key="msr_append_pack_btn", use_container_width=True):
            if pack_choice in all_packs:
                cur_txt = st.session_state.get("msr_kw_text", "")
                lines = [ln.strip() for ln in cur_txt.splitlines() if ln.strip()]
                low_set = {ln.lower() for ln in lines}
                for kw in all_packs[pack_choice]:
                    if kw.lower() not in low_set:
                        lines.append(kw)
                        low_set.add(kw.lower())
                st.session_state["msr_kw_text"] = "\n".join(lines)
                st.rerun()
    with pcol3:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        if st.button("🧹 Clear Keywords", key="msr_clear_kw_btn", use_container_width=True):
            st.session_state["msr_kw_text"] = ""
            st.session_state["msr_neg_text"] = ""
            st.session_state.pop("_msr_preview_html", None)
            st.session_state.pop("_msr_preview_payload", None)
            st.rerun()

    if "msr_kw_text" not in st.session_state:
        st.session_state["msr_kw_text"] = "Development Charges\nTree Cutting By-law\nSite Alteration By-law\nDrainage\nBackyard Chickens"
    if "msr_neg_text" not in st.session_state:
        st.session_state["msr_neg_text"] = "Non-Development Charge\ngreenhouse gas"

    k1, k2 = st.columns(2)
    with k1:
        kw_text = st.text_area(
            "Watchlist Keywords (one phrase per line)",
            height=165,
            key="msr_kw_text",
            help="Automatically matches 'Bylaw' and 'By-law' variations, case-insensitively.",
        )
    with k2:
        neg_text = st.text_area(
            "Exclude Words / Negative Keywords (optional, one per line)",
            height=165,
            key="msr_neg_text",
            help="Filters out false positives (for example, 'greenhouse gas' when watching 'greenhouse').",
        )

    pos_kws = [ln.strip() for ln in kw_text.splitlines() if ln.strip()]
    neg_kws = [ln.strip() for ln in neg_text.splitlines() if ln.strip()]

    default_profile_title = (
        f"{selected_areas[0]} Federation of Agriculture"
        if len(selected_areas) == 1
        else (f"{area_human_label} Municipal Council Watch" if selected_areas else "OFA County Municipal Council Watch")
    )

    # ── Step 3: Live Email Preview ──
    st.subheader("3️⃣ Preview Your Weekly Email")
    use_ai = st.checkbox(
        "Include Gemini AI Plain-English Summaries in Preview",
        value=True,
        key="msr_use_ai",
    )

    if st.button("🔍 Generate Live Digest Preview", type="primary", use_container_width=True, key="msr_gen_preview_btn"):
        if not selected_areas or not chosen_muni_ids:
            st.warning("Please select at least one county and municipality above.")
        elif not pos_kws:
            st.warning("Please enter at least one keyword above.")
        else:
            with st.spinner(f"Scanning cached council agendas & minutes for {area_human_label} and checking 12-month bylaw renewals..."):
                temp_sub = {
                    "id": 0,
                    "federation_name": default_profile_title,
                    "geographic_area": selected_areas_str,
                    "municipality_ids": chosen_muni_ids,
                    "exclude_large_cities": exclude_cities,
                    "recipient_emails": "",
                    "send_empty_digest": True,
                    "keywords": pos_kws,
                    "negative_keywords": neg_kws,
                }
                payload = build_county_digest_payload(
                    subscription=temp_sub,
                    munis_df=munis_df,
                    cached_docs_df=cached_docs_df,
                    exclude_hashes=set(),
                    use_ai=use_ai,
                    conn=conn,
                )
                subj, html_inline = render_county_digest_html(payload, logo_mode="inline", is_test_banner=True)
                _, html_cid = render_county_digest_html(payload, logo_mode="cid", is_test_banner=True)
                st.session_state["_msr_preview_payload"] = payload
                st.session_state["_msr_preview_subject"] = subj
                st.session_state["_msr_preview_html"] = html_inline
                st.session_state["_msr_preview_html_cid"] = html_cid

    if st.session_state.get("_msr_preview_html"):
        pl = st.session_state["_msr_preview_payload"]
        st.markdown("---")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Matches Found", len(pl["items"]))
        m2.metric("Munis Watched", pl["monitored_count"])
        m3.metric("Munis with Cached Docs", pl["munis_with_docs_checked"])
        m4.metric("Council Docs Checked", pl["docs_checked"])
        m5.metric("12-Mo Bylaw Renewals", len(pl.get("upcoming_renewals") or []))

        st.caption(f"**Preview Subject Line:** `{st.session_state['_msr_preview_subject']}`")
        components.html(st.session_state["_msr_preview_html"], height=920, scrolling=True)

        dl_c1, dl_c2 = st.columns([1, 2])
        with dl_c1:
            dl_slug = "_".join(a.lower().replace(" ", "_") for a in (selected_areas[:2] or ["county"]))
            st.download_button(
                "📥 Download Preview HTML",
                data=st.session_state["_msr_preview_html"].encode("utf-8"),
                file_name=f"{dl_slug}_digest_preview_{datetime.date.today().isoformat()}.html",
                mime="text/html",
                use_container_width=True,
            )
        with dl_c2:
            if smtp_cfg["configured"]:
                with st.expander("📧 Send This Sample Preview to Your @ofa.on.ca Inbox"):
                    st.caption("Restricted to `@ofa.on.ca` staff addresses so you can see how it renders in Outlook.")
                    s_col1, s_col2 = st.columns([2, 1])
                    with s_col1:
                        ofa_sample_email = st.text_input(
                            "Your OFA Email",
                            placeholder="firstname.lastname@ofa.on.ca",
                            key="msr_sample_ofa_email",
                            label_visibility="collapsed",
                        )
                    with s_col2:
                        if st.button("Send Sample", key="msr_send_sample_btn", use_container_width=True):
                            addr = ofa_sample_email.strip().lower()
                            if not addr.endswith("@ofa.on.ca") or "@" not in addr:
                                st.error("Please enter a valid `@ofa.on.ca` email address.")
                            else:
                                ok, msg = send_branded_email(
                                    subject=st.session_state["_msr_preview_subject"],
                                    html_body=st.session_state["_msr_preview_html_cid"],
                                    to_emails=[addr],
                                    bcc_emails=[DEFAULT_BCC_EMAIL],
                                    smtp_settings=smtp_cfg,
                                )
                                if ok:
                                    st.success(f"✅ Sample email sent to **{addr}**! Check Outlook.")
                                else:
                                    st.error(f"❌ Could not send sample: {msg}")

    # ── Step 4: Submit County Federation Enrollment Request ──
    st.markdown("---")
    st.subheader("4️⃣ Ready to Enroll This County Federation for Weekly Monday Emails?")
    st.caption(
        "Submitting this form saves your tested keyword watchlist and recipient list as **Pending Review** "
        "and notifies Ben (`ben.lefort@ofa.on.ca`) so he can activate automated Monday 9:00 AM delivery with one click."
    )

    with st.form("msr_enroll_form"):
        ef1, ef2 = st.columns(2)
        with ef1:
            msr_name = st.text_input("Your Name (MSR / OFA Staff) *", placeholder="e.g., Karen Smith")
            msr_email = st.text_input("Your Email *", placeholder="firstname.lastname@ofa.on.ca")
            fed_name = st.text_input(
                "County Federation / Digest Title *",
                value=default_profile_title,
            )
        with ef2:
            recip_emails = st.text_input(
                "Monday Digest Recipient Email(s) (To) *",
                placeholder="president@countyfa.ca, admin@countyfa.ca",
                help="Comma-separated list of who should receive the weekly Monday email.",
            )
            cc_emails = st.text_input(
                "CC Email(s) (optional — e.g., yourself as MSR)",
                placeholder="msr@ofa.on.ca",
            )
            send_empty = st.checkbox(
                "Send 'All Clear (0 matches)' email on quiet weeks",
                value=True,
            )

        req_notes = st.text_input(
            "Notes for Ben (optional)",
            placeholder="e.g., County Board approved pilot — please start next Monday",
        )

        submit_req = st.form_submit_button("📩 Submit Enrollment Request for Activation", type="primary", use_container_width=True)
        if submit_req:
            if not msr_name.strip() or not msr_email.strip() or "@" not in msr_email:
                st.error("Please enter your name and a valid email address.")
            elif not fed_name.strip() or not recip_emails.strip() or "@" not in recip_emails:
                st.error("Please enter a County Federation name and at least one recipient email.")
            elif not pos_kws:
                st.error("Please add at least one keyword in Step 2 above before submitting.")
            elif not chosen_muni_ids:
                st.error("Please select at least one municipality in Step 1 above before submitting.")
            else:
                note_tag = f"[MSR SELF-SERVE REQUEST from {msr_name.strip()} <{msr_email.strip()}>]"
                full_notes = f"{note_tag} {req_notes.strip()}".strip()
                sub_payload = {
                    "id": None,
                    "federation_name": fed_name.strip(),
                    "geographic_area": selected_areas_str,
                    "municipality_ids": chosen_muni_ids,
                    "exclude_large_cities": exclude_cities,
                    "recipient_emails": recip_emails.strip(),
                    "cc_emails": cc_emails.strip(),
                    "bcc_emails": DEFAULT_BCC_EMAIL,
                    "send_empty_digest": send_empty,
                    "is_test_profile": False,
                    "active": False,  # Pending Ben's 1-click activation in Admin
                    "notes": full_notes,
                }
                new_id = upsert_county_subscription(conn, sub_payload, pos_kws, neg_kws)

                # Notify Ben via email if SMTP is configured
                if smtp_cfg["configured"]:
                    notify_html = f"""
                    <html><body style="font-family:Arial,Helvetica,sans-serif; color:#222222;">
                      <h2 style="color:{OFA_VALENCIA}; margin-bottom:6px;">New County Weekly Digest Enrollment Request (#{new_id})</h2>
                      <p><strong>Submitted by:</strong> {html.escape(msr_name.strip())} ({html.escape(msr_email.strip())})</p>
                      <p><strong>Federation / Watchlist:</strong> {html.escape(fed_name.strip())} ({html.escape(area_human_label)} — {len(chosen_muni_ids)} municipalities)</p>
                      <p><strong>Recipients (To):</strong> {html.escape(recip_emails.strip())}</p>
                      <p><strong>CC:</strong> {html.escape(cc_emails.strip() or 'None')}</p>
                      <p><strong>Watchlist Keywords ({len(pos_kws)}):</strong> {html.escape(', '.join(pos_kws))}</p>
                      <p><strong>Excluded Terms:</strong> {html.escape(', '.join(neg_kws) or 'None')}</p>
                      <p><strong>Notes:</strong> {html.escape(req_notes.strip() or 'None')}</p>
                      <hr style="border:none; border-top:1px solid #DDD;" />
                      <p style="font-size:13px; color:{OFA_BLUEWOOD};">
                        This profile has been saved as <strong>Pending Review (Paused)</strong> in
                        <strong>Admin &rarr; County Federation Digests</strong>. Open Admin to review and check
                        <strong>Active</strong> to begin Monday 9:00 AM automated emails.
                      </p>
                    </body></html>
                    """
                    send_branded_email(
                        subject=f"[OFA Action] New County Digest Request: {fed_name.strip()} (from {msr_name.strip()})",
                        html_body=notify_html,
                        to_emails=[DEFAULT_BCC_EMAIL],
                        smtp_settings=smtp_cfg,
                    )

                st.success(
                    f"✅ Request **#{new_id}** submitted for **{fed_name.strip()}** ({len(pos_kws)} keywords, {len(chosen_muni_ids)} municipalities)! "
                    f"Ben (`{DEFAULT_BCC_EMAIL}`) has been notified and will review and activate it for Monday morning delivery."
                )

    conn.close()
