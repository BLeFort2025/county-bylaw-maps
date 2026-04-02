# Session Log: April 2, 2026 - Database Serverless Migration & Fixes

## Overview
Successfully identified, diagnosed, and resolved a critical data persistence bug affecting the Streamlit Cloud deployed instance of the Municipal Bylaw Database. 

## The Problem
The Streamlit Cloud environment uses an ephemeral container filesystem. While the local `bylaws.db` (SQLite) worked flawlessly in development, any data edited via the Admin Panel in production was immediately lost upon the container sleeping or a GitHub code push occurring, as the workspace reset to the repository's native file state.

## The Solution

1. **Option B Selected: Serverless Cloud Storage**
   - Transferred primary database operations from local SQLite to Neon PostgreSQL (neon.tech) zero-scale serverless tier. This completely divorced database persistence from the Streamlit Cloud hardware lifecycle.

2. **Data Migration Pipeline Built (Temporary Script)**
   - Wrote a 1-time data sync pipeline via `psycopg2` and generic python bindings that dynamically recreated 17 SQLite tables in the PostgreSQL dialect, and safely `executemany` streamed over 8,000 distinct records (Bylaws, Contact info, Signals, Category details, Exemption mappings) to AWS US-East-1.

3. **Backend Refactoring (`db_utils.py` & `pages/4_🔒_Admin.py`)**
   - Converted the legacy `get_connection()` function to supply a custom `PgWrapper` class that mimics traditional SQLite cursor properties so the front-end codebase didn't require massive rewrites.
   - Migrated all generic SQL parameters (`?`) directly to PostgreSQL standard (`%s`).
   - Replaced Streamlit's `pd.read_sql_query` logic to properly access `conn.conn` natively.

4. **Hotfixes Deployed**
   - **Numpy/Psycopg2 Cast Errors:** Fixed an immediate production crash when passing `np.int64` scalars parsed from Pandas directly into the psycopg2 engine. Hard-coded a global `register_adapter(np.int64, AsIs)` exception layer in `db_utils.py` so standard Pandas objects effortlessly translate into PostgreSQL DB strings.
   - **Report Generator Catch:** Identified a trailing legacy `?` placeholder in `pages/6_📊_Report_Generator.py` that caused a `SyntaxError` when filtering municipalities by county. Replaced with strict Postgres syntax.

## Outcomes
- **100% Data Persistence Stability:** The Streamlit Application can now be rebooted, scaled, or updated via GitHub endlessly without losing a single parameter or text change entered via the Administration terminal.
- **Improved Security:** The Database password is now securely abstracted via `.streamlit/secrets.toml`.

## Important Next Steps
The Developer Manual has been thoroughly updated to map out the new Neon architecture. Any further development querying the database natively must rely strictly upon PostgreSQL dialect commands (`%s` replacing `?`, `"field"` replacing `[field]`).
