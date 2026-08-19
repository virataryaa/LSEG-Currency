# Currency — Interim Migration (LSEG)

Interim replacement for `ICEBREAKER/Currency`, rebuilt against the **LSEG
Data API** (`lseg.data`) instead of ICE Connect (`icepython`), for the period
while ICE API access is unavailable. Two origin-country FX baskets —
Coffee (Arabica + Robusta) and Cocoa — each rebased to a weighted index vs.
USD, plus the underlying futures prices they're compared against.

**Motivating context, not just a scheduled migration:** the ICE-side pipeline
has been silently failing since 2026-07-29 — every symbol has returned "no
data" on every daily run for three weeks, despite the automation reporting
`[OK]` the whole time (the ingest scripts treat zero rows fetched as
success). The ICE database is stale at 2026-07-28 as a result.

## Where the RICs came from

Unlike the other four migrations in this series, this one didn't need fresh
RIC discovery — a separate, already-working LSEG-based project
(`Non Fundamental/Price Action/Currency`) has been running the *same* basket
methodology against LSEG for years, with identical weights to the ICE
source. Its ingest scripts were ported here essentially unchanged, and its
current parquet data (already current through yesterday) was used directly
to seed this project's database — no historical backfill from scratch was
needed.

**One schema fix on the way in:** the ICE Dashboard (copied verbatim from
`ICEBREAKER/Currency/Dashboard/app.py`, zero API dependency) expects a
`RC_Price` column for the Robusta futures price. The source LSEG project
named it `LRC_Price`. Renamed on ingest — see `COLUMN_NAMES` in
`coffee_ingest_lseg.py`.

## What's here

- **`Code/coffee_ingest_lseg.py`**, **`Code/cocoa_ingest_lseg.py`** — one
  script per commodity, each handling both full backfill (`--full`) and
  incremental update (default), matching the ICE source's structure exactly.
  FX via `MID_PRICE`, futures via `TR.SETTLEMENTPRICE` (with a fallback
  field chain if that's unavailable for a given RIC).
- **`Database/currency_data.parquet`** (Coffee), **`cocoa_currency_data.parquet`**
  (Cocoa) — full history from 2014, current through today.
- **`Dashboard/app.py`** — copied verbatim from the ICE source.
- **`Automator/`** — `run.bat` (daily ingest + git push + email), `notify.py`.

## RICs and weights (unchanged from the proven LSEG source)

**Coffee** — FX: `BRL=`, `COP=`, `HNL=`, `PEN=`, `ETB=`, `VND=`, `IDR=`,
`UGX=`, `INR=`. Futures: `KCc2` (Arabica), `LRCc1` (Robusta). Arabica basket
weights: Brazil 54.0%, Colombia 20.7%, Honduras 7.4%, Ethiopia 11.9%, Peru
5.9%. Robusta basket weights: Vietnam 47%, Brazil 11%, Indonesia 17%, Uganda
16%, India 9%.

**Cocoa** — FX: `XOF=`, `GHS=`, `NGN=`, `IDR=`, `BRL=`, `PEN=`. Futures:
`CCc2` (NY), `LCCc2` (London). Basket weights: Ivory Coast + Cameroon
(combined, both settle in XOF) 53.3%, Ghana 15.7%, USD (numeraire, no fetch
needed) 11.6%, Nigeria 7.2%, Indonesia 4.0%, Brazil 4.7%, Peru 3.5%.

Each basket index is rebased to 100 at the first available historical value
per currency, weight-averaged, and — on every incremental run — recomputed
from the full combined timeline (not just the incremental window) so the
base year never drifts.

## Validation

Checked against the ICE archive for the entire overlapping period
(2014-01-01 → 2026-07-28, ~3,280 days) — this is the cleanest validation of
any migration in this series, since FX and settlement data don't have the
gap-density issues found in continuation/thin-contract series elsewhere:

| Series | Correlation | Median diff |
|---|---|---|
| KC_Price, RC_Price, CC_Price, LCC_Price | 1.00000 | 0.00% |
| Brazil (FX) | 0.99999 | 0.03% |
| Arabica_Idx | 0.99969 | 0.67% |
| Robusta_Idx | 0.99987 | 0.31% |
| Cocoa_Idx | 0.99952 | 0.37% |

The small FX-level differences (well under 1%) are normal cross-vendor
mid-price quote-basis noise, not a data-quality gap.

## Running it

```bash
python Code/coffee_ingest_lseg.py           # incremental
python Code/coffee_ingest_lseg.py --full    # full rebuild from 2014-01-01
python Code/cocoa_ingest_lseg.py
streamlit run Dashboard/app.py
```

Requires an authenticated LSEG Workspace/Eikon session on the host running
the ingest scripts.
