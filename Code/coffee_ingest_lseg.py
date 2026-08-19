"""
Coffee Currency Index -- LSEG Data Ingest (interim migration)
================================================================
LSEG-API replacement for ICEBREAKER/Currency/Code/coffee_ingest.py
(icepython-based). Same origin-country universe, same basket weights
(carried over unchanged — verified identical to the proven RICs/weights
already running in Non Fundamental/Price Action/Currency/currency_ingest.py),
same derived Arabica_Idx/Robusta_Idx/Spread_Ara_Rob formulas. Output column
is named RC_Price (not LRC_Price) specifically to match what the ICE
Dashboard/app.py (copied verbatim into this project) expects.

Usage:
    python coffee_ingest_lseg.py            # incremental update
    python coffee_ingest_lseg.py --full     # full pull from 2014-01-01

Saves to: ../Database/currency_data.parquet
"""

import argparse
import datetime
import logging
import sys
import time
from pathlib import Path

import pandas as pd
pd.set_option("future.no_silent_downcasting", True)  # silences a harmless lseg.data internal FutureWarning
import lseg.data as ld

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

DB_DIR     = Path(__file__).resolve().parent.parent / "Database"
OUT_FILE   = DB_DIR / "currency_data.parquet"
FULL_START = "2014-01-01"

FX_RICS      = ["BRL=", "COP=", "HNL=", "PEN=", "ETB=", "VND=", "IDR=", "UGX=", "INR="]
FUTURES_RICS = ["KCc2", "LRCc1"]

ARABICA_WEIGHTS = {
    "BRL=": 0.54047,
    "COP=": 0.207225,
    "HNL=": 0.074291,
    "ETB=": 0.119151,
    "PEN=": 0.058863,
}

ROBUSTA_WEIGHTS = {
    "VND=": 0.47,
    "BRL=": 0.11,
    "IDR=": 0.17,
    "UGX=": 0.16,
    "INR=": 0.09,
}

COLUMN_NAMES = {
    "BRL=": "Brazil",
    "COP=": "Colombia",
    "HNL=": "Honduras",
    "PEN=": "Peru",
    "ETB=": "Ethiopia",
    "VND=": "Vietnam",
    "IDR=": "Indonesia",
    "UGX=": "Uganda",
    "INR=": "India",
    "KCc2":  "KC_Price",
    "LRCc1": "RC_Price",  # matches the ICE Dashboard's expected column name
}


def fetch_fx(start: str, end: str, retries: int = 3, delay: int = 30) -> pd.DataFrame:
    log.info("Fetching FX rates (%d RICs) from %s", len(FX_RICS), start)
    for attempt in range(1, retries + 1):
        try:
            df = ld.get_history(
                universe=FX_RICS, fields=["MID_PRICE"],
                start=start, end=end, interval="daily",
            )
            df.index = pd.to_datetime(df.index)
            df.index.name = "Date"
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [ric for ric, _ in df.columns]
            else:
                df.columns = FX_RICS[: len(df.columns)]
            return df
        except Exception as e:
            if attempt < retries:
                log.warning("fetch_fx attempt %d/%d failed: %s — retrying in %ds", attempt, retries, e, delay)
                time.sleep(delay)
            else:
                log.error("fetch_fx failed after %d attempts: %s", retries, e)
                raise


def fetch_futures(start: str, end: str) -> pd.DataFrame:
    log.info("Fetching Coffee futures settlement prices from %s", start)
    try:
        df = ld.get_history(universe=FUTURES_RICS, fields=["TR.SETTLEMENTPRICE"],
                             start=start, end=end, interval="daily")
    except Exception as e:
        log.warning("TR.SETTLEMENTPRICE failed, falling back to default history: %s", e)
        df = ld.get_history(universe=FUTURES_RICS, start=start, end=end, interval="daily")

    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"

    if isinstance(df.columns, pd.MultiIndex):
        cols = list(df.columns)
        picked = {}
        pref_order = ["TR.SETTLEMENTPRICE", "SETTLEMENTPRICE", "TR.CLOSEPRICE",
                      "CLOSE", "VALUE", "TRDPRC_1", "OFF_CLOSE", "OFFCLPRC"]
        for ric in FUTURES_RICS:
            ric_cols = [c for c in cols if c[0] == ric]
            if not ric_cols:
                continue
            chosen = None
            for f in pref_order:
                for c in ric_cols:
                    if str(c[1]).upper() == f.upper():
                        chosen = c
                        break
                if chosen is not None:
                    break
            if chosen is None:
                chosen = ric_cols[0]
            picked[ric] = df[chosen]
        out = pd.DataFrame(picked, index=df.index)
    else:
        out = df.copy()
        if len(out.columns) >= len(FUTURES_RICS):
            out = out.iloc[:, :len(FUTURES_RICS)]
            out.columns = FUTURES_RICS[: len(out.columns)]

    return out


def compute_indices(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().apply(pd.to_numeric, errors="coerce")

    all_rics = list(set(list(ARABICA_WEIGHTS.keys()) + list(ROBUSTA_WEIGHTS.keys())))
    base = {}
    for ric in all_rics:
        if ric in out.columns:
            s = out[ric].dropna()
            base[ric] = s.iloc[0] if not s.empty else 1.0

    ara = sum(
        (out[ric] / base[ric]) * w
        for ric, w in ARABICA_WEIGHTS.items() if ric in out.columns and ric in base
    ) * 100

    rob = sum(
        (out[ric] / base[ric]) * w
        for ric, w in ROBUSTA_WEIGHTS.items() if ric in out.columns and ric in base
    ) * 100

    out["Arabica_Idx"] = ara
    out["Robusta_Idx"] = rob
    out["Spread_Ara_Rob"] = ara - rob

    out = out.rename(columns=COLUMN_NAMES)

    all_cols = list(COLUMN_NAMES.values()) + ["Arabica_Idx", "Robusta_Idx", "Spread_Ara_Rob"]
    existing = [c for c in all_cols if c in out.columns]
    out[existing] = out[existing].ffill()

    return out.reset_index()


def recompute_indices_on_full(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute Arabica/Robusta indices using the full combined dataset so
    the base is always the first historical row, not the incremental window."""
    out = df.copy()
    ric_to_col = COLUMN_NAMES

    ara_parts = []
    for ric, w in ARABICA_WEIGHTS.items():
        col = ric_to_col.get(ric)
        if col and col in out.columns:
            s = pd.to_numeric(out[col], errors="coerce")
            base = s.dropna().iloc[0] if not s.dropna().empty else 1.0
            ara_parts.append((s / base) * w)

    rob_parts = []
    for ric, w in ROBUSTA_WEIGHTS.items():
        col = ric_to_col.get(ric)
        if col and col in out.columns:
            s = pd.to_numeric(out[col], errors="coerce")
            base = s.dropna().iloc[0] if not s.dropna().empty else 1.0
            rob_parts.append((s / base) * w)

    if ara_parts:
        out["Arabica_Idx"] = sum(ara_parts) * 100
    if rob_parts:
        out["Robusta_Idx"] = sum(rob_parts) * 100
    if ara_parts and rob_parts:
        out["Spread_Ara_Rob"] = out["Arabica_Idx"] - out["Robusta_Idx"]

    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Full pull from 2014-01-01")
    args = parser.parse_args()

    log.info("=" * 60)
    log.info("Coffee Currency Ingest (LSEG) | %s", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))

    DB_DIR.mkdir(parents=True, exist_ok=True)

    if args.full or not OUT_FILE.exists():
        start = FULL_START
        log.info("Mode: FULL from %s", start)
    else:
        existing = pd.read_parquet(OUT_FILE, columns=["Date"])
        latest = pd.to_datetime(existing["Date"]).max()
        start = (latest - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
        log.info("Mode: INCREMENTAL from %s", start)

    end = datetime.date.today().isoformat()

    ld.open_session()
    try:
        fx_df = fetch_fx(start, end)
        futures_df = fetch_futures(start, end)

        raw = fx_df.join(futures_df, how="outer").sort_index().ffill()
        log.info("Rows fetched: %d", len(raw))

        new_df = compute_indices(raw)

        if OUT_FILE.exists() and not args.full:
            old_df = pd.read_parquet(OUT_FILE)
            old_df["Date"] = pd.to_datetime(old_df["Date"])
            new_df["Date"] = pd.to_datetime(new_df["Date"])
            combined = (
                pd.concat([old_df, new_df])
                .drop_duplicates(subset=["Date"], keep="last")
                .sort_values("Date")
                .reset_index(drop=True)
            )
            combined = recompute_indices_on_full(combined)
        else:
            combined = new_df.sort_values("Date").reset_index(drop=True)

        today = pd.Timestamp.today().normalize()
        combined["Date"] = pd.to_datetime(combined["Date"])
        combined = combined[combined["Date"] < today].reset_index(drop=True)

        combined.to_parquet(OUT_FILE, engine="pyarrow", index=False)
        log.info("Saved: %s  (%d rows)", OUT_FILE.name, len(combined))
        log.info("=" * 60)
    finally:
        ld.close_session()


if __name__ == "__main__":
    main()
