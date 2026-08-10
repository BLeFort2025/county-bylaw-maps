---
name: data_updates
description: Mandatory rules and procedures for updating municipal bylaw data, databases, and the Streamlit UI.
---

# Data Update Standard Operating Procedure (SOP)

When asked to update data, modify the database, or push changes to the live Streamlit app in this repository, you **MUST** follow these rules to avoid data corruption and deployment failures.

## 1. The Source of Truth (SQLite vs. PostgreSQL)
- **Local `bylaws.db` (SQLite)** is the canonical source of truth for all manual data updates.
- **Neon PostgreSQL** is the live production database used by the web app, but its internal primary keys (`id`) **DO NOT MATCH** the SQLite `id`s. 
- **Rule:** Do NOT write custom SQL scripts to update Postgres directly using hardcoded IDs. If you must update Postgres via a python script, you MUST perform a `JOIN` on the `municipalities` table by `name` to dynamically fetch the correct `bylaw_id`.
- **Best Practice:** Update the local `bylaws.db` file, then run `python sync_to_cloud.py --push` to safely truncate and insert the fresh data into the Postgres cloud database.

## 2. The Map Builder (Parquet Files)
- The Streamlit map pages (`1_Lower_Tier_Map.py`, `2_Upper_Tier_Map.py`) do NOT query the Postgres database on the fly. They rely entirely on pre-compiled `.parquet` files in the root directory.
- **Rule:** After making ANY database changes (either to SQLite or Postgres), you MUST run `python build_maps_v2_rollup_metadata.py` locally to bake the fresh data into `lower_single_map_beta.parquet` and `upper_single_map_beta.parquet`.

## 3. The Target Git Branch
- The live Streamlit Community Cloud app is currently linked to the **`staging-expiry-signals`** branch.
- **Rule:** All commits (including the updated `.parquet` files and any python modifications) MUST be pushed to the `staging-expiry-signals` branch. Pushing to `main` will result in the live app silently ignoring your updates.

## 4. Streamlit Caching and Rebooting
- Streamlit Community Cloud aggressively caches `.parquet` files and occasionally fails to auto-deploy new commits seamlessly.
- **Rule:** If you push to `staging-expiry-signals` but the live UI doesn't update within a few minutes, instruct the user to manually reboot the server. (Click the black **"Manage app"** button in the bottom right corner of the live app -> Click the three dots menu -> Select **"Reboot app"**).

## 5. UI Modifications and Testing
- The Streamlit application renders linearly. If you introduce a Python syntax error or exception in a component (like `Data_Browser.py`), the app will crash and immediately stop rendering the rest of the page.
- **Rule:** Before committing UI changes, double-check that your pandas logic (e.g. `.sum()`, `.apply()`) gracefully handles empty DataFrames, missing columns, or `None` values to prevent catastrophic live crashes.
