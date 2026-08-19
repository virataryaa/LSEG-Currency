"""
notify.py — Currency (LSEG interim migration) Automator email summary
Called by run.bat after ingest + git push.
Usage: python notify.py <status> <git_status>
  status     : ok | error
  git_status : pushed | skipped | failed
"""

import sys
import datetime
import pandas as pd
from pathlib import Path

TO_EMAIL    = "virat.arya@etgworld.com"
DB_DIR      = Path(r"C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\Interim_Migration\Currency\Database")
COFFEE_FILE = DB_DIR / "currency_data.parquet"
COCOA_FILE  = DB_DIR / "cocoa_currency_data.parquet"

status     = sys.argv[1] if len(sys.argv) > 1 else "ok"
git_status = sys.argv[2] if len(sys.argv) > 2 else "unknown"
run_dt     = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
today      = datetime.date.today().strftime("%Y-%m-%d")

COFFEE_COLS = ["Brazil", "Colombia", "Honduras", "Ethiopia", "Peru",
               "Vietnam", "Indonesia", "Uganda", "India"]
COCOA_COLS  = ["IvoryCoast_Cameroon", "Ghana", "Nigeria", "Indonesia", "Brazil", "Peru"]


def parquet_summary(path: Path, label: str, fx_cols: list, idx_cols: list) -> str:
    if not path.exists():
        return f"  {label}: FILE NOT FOUND\n"
    df = pd.read_parquet(path)
    df["Date"] = pd.to_datetime(df["Date"])
    lines = [
        f"  {label}:",
        f"    Rows      : {len(df)}",
        f"    Range     : {df['Date'].min().date()} -> {df['Date'].max().date()}",
        f"    Latest FX :",
    ]
    for c in fx_cols:
        if c in df.columns:
            val = pd.to_numeric(df[c], errors="coerce").dropna()
            if not val.empty:
                lines.append(f"      {c:<25} {val.iloc[-1]:.4f}")
    for col in idx_cols:
        if col in df.columns:
            val = pd.to_numeric(df[col], errors="coerce").dropna()
            if not val.empty:
                lines.append(f"    {col:<27} {val.iloc[-1]:.2f}")
    return "\n".join(lines) + "\n"


def send_outlook_email(subject: str, body: str):
    try:
        import win32com.client
        outlook      = win32com.client.Dispatch("Outlook.Application")
        mail         = outlook.CreateItem(0)
        mail.To      = TO_EMAIL
        mail.Subject = subject
        mail.Body    = body
        mail.Send()
        print(f"  Email sent -> {TO_EMAIL}")
    except Exception as e:
        print(f"  Email failed: {e}")


ok  = status == "ok"
tag = "[OK]" if ok else "[ERROR]"
subject = f"{tag} Interim_Migration-Currency (LSEG) — {today}"

git_line = {
    "pushed":  "GitHub  : Pushed successfully",
    "skipped": "GitHub  : No changes — push skipped",
    "failed":  "GitHub  : PUSH FAILED",
}.get(git_status, f"GitHub  : {git_status}")

body = f"""Interim_Migration Currency (LSEG) — Daily Update
Run time : {run_dt}
Status   : {"OK" if ok else "ERROR — ingest failed, check run_log.txt"}
{git_line}

{"=" * 45}
DATABASE SUMMARY
{"=" * 45}
{parquet_summary(COFFEE_FILE, "Coffee FX", COFFEE_COLS, ["Arabica_Idx", "Robusta_Idx"])}
{parquet_summary(COCOA_FILE,  "Cocoa FX",  COCOA_COLS,  ["Cocoa_Idx"])}
{"=" * 45}
Log: C:\\Users\\virat.arya\\ETG\\SoftsDatabase - Documents\\Database\\Hardmine\\Interim_Migration\\Currency\\Automator\\run_log.txt
"""

print(body)
send_outlook_email(subject, body)
