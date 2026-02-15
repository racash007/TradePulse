"""
Data Download UI component - Download/update stock data into SQLite database.
"""
import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional

import pandas as pd
import streamlit as st

# ── Database path (relative to working directory, i.e. app/) ──────────────
DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "resource", "stock_data.db",
)


# ── Token map (reuse from download_stocks) ────────────────────────────────
def _get_stock_tokens() -> Dict[str, str]:
    """Import and return the stock_tokens dict from download_stocks module."""
    try:
        from utility.download_stocks import stock_tokens
        return stock_tokens
    except ImportError:
        return {}


def _get_db_summary(db_path: str) -> pd.DataFrame:
    """Return per-symbol record count + date range from the database."""
    if not os.path.exists(db_path):
        return pd.DataFrame(columns=["symbol", "records", "earliest", "latest"])
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(
            """
            SELECT symbol,
                   COUNT(*)       AS records,
                   MIN(datetime)  AS earliest,
                   MAX(datetime)  AS latest
            FROM stock_data
            GROUP BY symbol
            ORDER BY symbol
            """,
            conn,
        )
        conn.close()
        return df
    except Exception:
        return pd.DataFrame(columns=["symbol", "records", "earliest", "latest"])


def _get_last_date_for_symbol(db_path: str, symbol: str) -> Optional[str]:
    """Return the latest datetime string stored for *symbol*, or None."""
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "SELECT MAX(datetime) FROM stock_data WHERE symbol = ?", (symbol,)
        )
        row = cur.fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────
#  Main render function
# ──────────────────────────────────────────────────────────────────────────
def render_data_download():
    """Render the stock-data download / update UI."""
    st.header("📥 Stock Data Download")

    stock_tokens = _get_stock_tokens()
    if not stock_tokens:
        st.error("Could not load stock token map. Check utility/download_stocks.py.")
        return

    all_symbols = sorted(stock_tokens.keys())

    # ── Database status ───────────────────────────────────────────────────
    st.subheader("Database Status")
    db_summary = _get_db_summary(DB_PATH)
    if db_summary.empty:
        st.info("No data in database yet. Download stocks below to get started.")
    else:
        col1, col2, col3 = st.columns(3)
        col1.metric("Stocks in DB", len(db_summary))
        col2.metric("Total Records", f"{db_summary['records'].sum():,}")
        latest_overall = db_summary["latest"].max() if not db_summary.empty else "—"
        col3.metric("Latest Date", str(latest_overall)[:10] if latest_overall else "—")

        with st.expander("View per-stock details", expanded=False):
            st.dataframe(db_summary, use_container_width=True, hide_index=True)

    st.divider()

    # ── Download controls ─────────────────────────────────────────────────
    st.subheader("Download / Update Data")

    mode = st.radio(
        "Mode",
        ["Update existing stocks to today", "Download selected stocks"],
        horizontal=True,
        help="'Update' fetches only missing data since the last stored date. "
             "'Download selected' lets you pick specific stocks and a date range.",
    )

    if mode == "Download selected stocks":
        selected = st.multiselect(
            "Select stocks to download",
            options=all_symbols,
            default=[],
            help="Pick one or more symbols from the token list.",
        )
        col_from, col_to = st.columns(2)
        with col_from:
            from_date = st.date_input(
                "From date",
                value=datetime.now() - timedelta(days=365 * 5),
                max_value=datetime.now(),
            )
        with col_to:
            to_date = st.date_input(
                "To date",
                value=datetime.now(),
                max_value=datetime.now(),
            )
    else:
        # Update mode – use all symbols already in DB (or all if DB empty)
        existing_symbols = db_summary["symbol"].tolist() if not db_summary.empty else []
        if existing_symbols:
            selected = existing_symbols
            st.info(f"Will update **{len(selected)}** stocks currently in the database to today's date.")
        else:
            selected = all_symbols
            st.info(f"Database is empty — will download all **{len(selected)}** available stocks (5-year history).")
        from_date = None  # determined per-symbol
        to_date = datetime.now().date()

    save_csv = st.checkbox("Also save to CSV files (resource/data/)", value=False)

    delay = st.slider(
        "Delay between API requests (seconds)",
        min_value=0.5, max_value=5.0, value=1.5, step=0.5,
        help="Increase if you hit rate-limit errors.",
    )

    # ── Trigger download ──────────────────────────────────────────────────
    if st.button("🚀 Start Download", type="primary", use_container_width=True):
        if not selected:
            st.warning("No stocks selected.")
            return

        _run_download(
            symbols=selected,
            stock_tokens=stock_tokens,
            db_path=DB_PATH,
            from_date=from_date,
            to_date=to_date,
            save_csv=save_csv,
            delay=delay,
            update_mode=(mode == "Update existing stocks to today"),
        )


# ──────────────────────────────────────────────────────────────────────────
#  Download runner (uses download_stocks functions)
# ──────────────────────────────────────────────────────────────────────────
def _run_download(
    symbols: List[str],
    stock_tokens: Dict[str, str],
    db_path: str,
    from_date,
    to_date,
    save_csv: bool,
    delay: float,
    update_mode: bool,
):
    """Execute the download inside Streamlit, showing live progress."""
    from utility.download_stocks import (
        login,
        historical_data,
        create_database,
        save_to_database,
        log_download,
        granularity_map,
    )

    # Ensure DB exists
    create_database(db_path)

    # Login
    status_area = st.empty()
    status_area.info("🔑 Logging in to Angel One API …")

    if not login():
        status_area.error(
            "❌ Login failed. Please verify your Angel One credentials in the .env file "
            "(ANGEL_API_KEY, ANGEL_CLIENT_ID, ANGEL_PASSWORD, ANGEL_TOTP_SECRET)."
        )
        return

    status_area.success("✅ Logged in successfully.")

    # Prepare CSV dir
    csv_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "resource", "data")
    if save_csv:
        os.makedirs(csv_dir, exist_ok=True)

    interval = "ONE_DAY"
    progress_bar = st.progress(0.0)
    log_container = st.container()
    success_count = 0
    fail_count = 0
    skip_count = 0
    total = len(symbols)

    results_log: List[Dict] = []

    for idx, symbol in enumerate(symbols):
        token = stock_tokens.get(symbol)
        if not token:
            results_log.append({"symbol": symbol, "status": "⚠️ skipped", "detail": "Token not found"})
            skip_count += 1
            progress_bar.progress((idx + 1) / total)
            continue

        # Determine from_date for this symbol
        if update_mode or from_date is None:
            last = _get_last_date_for_symbol(db_path, symbol)
            if last:
                sym_from = pd.to_datetime(last) + timedelta(days=1)
                sym_from = sym_from.to_pydatetime()
            else:
                sym_from = datetime.now() - timedelta(days=365 * 5)
        else:
            sym_from = datetime.combine(from_date, datetime.min.time())

        sym_to = datetime.combine(to_date, datetime.min.time()).replace(hour=15, minute=30)
        sym_from = sym_from.replace(hour=9, minute=15, second=0, microsecond=0)

        # Skip if already up to date
        if sym_from.date() >= sym_to.date():
            results_log.append({"symbol": symbol, "status": "✅ up-to-date", "detail": f"Last date: {sym_from.date() - timedelta(days=1)}"})
            skip_count += 1
            progress_bar.progress((idx + 1) / total)
            continue

        from_str = sym_from.strftime("%Y-%m-%d %H:%M")
        to_str = sym_to.strftime("%Y-%m-%d %H:%M")

        status_area.info(f"⬇️ [{idx+1}/{total}] Downloading **{symbol}** ({from_str[:10]} → {to_str[:10]}) …")

        try:
            df, error = historical_data("NSE", token, from_str, to_str, interval)

            if df is not None and not df.empty:
                save_to_database(df, symbol, db_path)
                log_download(symbol, token, "success", len(df), None, db_path)
                if save_csv:
                    csv_path = os.path.join(csv_dir, f"{symbol}_1_day_5_years.csv")
                    df.to_csv(csv_path, index=False)
                results_log.append({"symbol": symbol, "status": "✅ success", "detail": f"{len(df)} records"})
                success_count += 1
            else:
                err = error or "No data"
                log_download(symbol, token, "failed", 0, err, db_path)
                results_log.append({"symbol": symbol, "status": "❌ failed", "detail": err})
                fail_count += 1
        except Exception as exc:
            log_download(symbol, token, "failed", 0, str(exc), db_path)
            results_log.append({"symbol": symbol, "status": "❌ error", "detail": str(exc)})
            fail_count += 1

        progress_bar.progress((idx + 1) / total)

        if idx < total - 1:
            time.sleep(delay)

    # ── Summary ───────────────────────────────────────────────────────────
    progress_bar.progress(1.0)
    status_area.empty()

    st.success(f"Download complete — ✅ {success_count} succeeded, ❌ {fail_count} failed, ⏭️ {skip_count} skipped.")

    if results_log:
        with st.expander("Download details", expanded=True):
            st.dataframe(
                pd.DataFrame(results_log),
                use_container_width=True,
                hide_index=True,
            )

    # Refresh DB summary
    st.subheader("Updated Database Status")
    refreshed = _get_db_summary(db_path)
    if not refreshed.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Stocks in DB", len(refreshed))
        col2.metric("Total Records", f"{refreshed['records'].sum():,}")
        col3.metric("Latest Date", str(refreshed["latest"].max())[:10])
        with st.expander("Per-stock details"):
            st.dataframe(refreshed, use_container_width=True, hide_index=True)
