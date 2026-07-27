"""
cleaner.py
----------
Deterministic data-cleaning layer. This is pure Python/pandas — NO LLM calls here.
Rationale (see Decision Log): LLMs are unreliable at arithmetic and exact parsing
over many rows. All parsing/normalization happens here so the analytics layer
works on trustworthy, typed data, and the LLM only ever reasons over already-
computed, already-correct numbers.

Handles the specific messiness observed in the real Skylark datasets:
- Numbers with unit suffixes: "5360 HA", "40MW", "2 location", "1,310.850"
- Spreadsheet error values: "#VALUE!"
- Inconsistent/missing dates
- Free-text sector/status fields with casing or spacing variants
- Missing values across almost every column
"""

import re
import pandas as pd
from datetime import datetime

# ---------- Data quality tracking ----------
# Every cleaning function appends here so the agent can tell the user
# what was ambiguous or missing, instead of silently guessing.
DATA_QUALITY_NOTES: list[str] = []


def reset_quality_notes():
    DATA_QUALITY_NOTES.clear()


def note(msg: str):
    if msg not in DATA_QUALITY_NOTES:
        DATA_QUALITY_NOTES.append(msg)


# ---------- Primitive parsers ----------

def parse_numeric(value) -> float | None:
    """
    Extract a numeric value from messy strings like:
    '5360 HA', '40MW', '1,310.850', '#VALUE!', '', None, '2 location'
    Returns None if nothing numeric could be extracted.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if s == "" or s.upper() in {"NA", "N/A", "#VALUE!", "NONE"}:
        return None
    s = s.replace(",", "")
    match = re.search(r"-?\d+(\.\d+)?", s)
    if not match:
        note(f"Could not parse numeric value from: '{value}'")
        return None
    return float(match.group())


def parse_date(value) -> pd.Timestamp | None:
    """Parse dates across the several formats seen in the data (ISO is dominant, but be defensive)."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return pd.to_datetime(value, errors="raise", dayfirst=False)
    except Exception:
        try:
            return pd.to_datetime(value, errors="raise", dayfirst=True)
        except Exception:
            note(f"Could not parse date value: '{value}'")
            return None


def normalize_text(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if s == "":
        return None
    return re.sub(r"\s+", " ", s)


# Known sector spelling/casing variants -> canonical name.
# Extend this as new variants surface in the full dataset.
SECTOR_CANONICAL = {
    "energy": "Energy",
    "oil & gas": "Oil & Gas",
    "oil and gas": "Oil & Gas",
    "mining": "Mining",
    "powerline": "Powerline",
    "power line": "Powerline",
    "renewables": "Renewables",
    "renewable": "Renewables",
    "railways": "Railways",
    "railway": "Railways",
    "dsp": "DSP",
    "tender": "Tender",
    "construction": "Construction",
    "security and surveillance": "Security & Surveillance",
    "others": "Others",
    "other": "Others",
}


def normalize_sector(value) -> str | None:
    s = normalize_text(value)
    if s is None:
        return None
    key = s.lower()
    if key in SECTOR_CANONICAL:
        return SECTOR_CANONICAL[key]
    note(f"Unrecognized sector value kept as-is: '{s}' (add to SECTOR_CANONICAL if it's a known variant)")
    return s  # keep original rather than silently dropping the row


# ---------- Board-level cleaners ----------

def clean_deals(raw_items: list[dict]) -> pd.DataFrame:
    """
    Expected monday.com columns (Deals board):
    Deal Name, Owner code, Client Code, Deal Status, Close Date (A),
    Closure Probability, Masked Deal value, Tentative Close Date,
    Deal Stage, Product deal, Sector/service, Created Date
    """
    rows = []
    for item in raw_items:
        rows.append({
            "deal_name": normalize_text(item.get("Deal Name") or item.get("name")),
            "owner_code": normalize_text(item.get("Owner code")),
            "client_code": normalize_text(item.get("Client Code")),
            "deal_status": normalize_text(item.get("Deal Status")),
            "closure_probability": normalize_text(item.get("Closure Probability")),
            "deal_value": parse_numeric(item.get("Masked Deal value")),
            "tentative_close_date": parse_date(item.get("Tentative Close Date")),
            "deal_stage": normalize_text(item.get("Deal Stage")),
            "product": normalize_text(item.get("Product deal")),
            "sector": normalize_sector(item.get("Sector/service")),
            "created_date": parse_date(item.get("Created Date")),
        })
    df = pd.DataFrame(rows)

    missing_value_count = df["deal_value"].isna().sum()
    if missing_value_count > 0:
        note(f"{missing_value_count} deals have missing/unparseable deal value — excluded from revenue sums, "
             f"but still counted for pipeline stage/status breakdowns.")

    missing_sector = df["sector"].isna().sum()
    if missing_sector > 0:
        note(f"{missing_sector} deals have no sector recorded — excluded from sector-level breakdowns.")

    return df


def clean_work_orders(raw_items: list[dict]) -> pd.DataFrame:
    """
    Expected monday.com columns (Work Orders board) — see README for full list.
    Only the fields needed for BI metrics are extracted here; extend as needed.
    """
    rows = []
    for item in raw_items:
        rows.append({
            "deal_name_masked": normalize_text(item.get("Deal name masked") or item.get("name")),
            "customer_code": normalize_text(item.get("Customer Name Code")),
            "serial": normalize_text(item.get("Serial #")),
            "nature_of_work": normalize_text(item.get("Nature of Work")),
            "execution_status": normalize_text(item.get("Execution Status")),
            "po_date": parse_date(item.get("Date of PO/LOI")),
            "probable_start": parse_date(item.get("Probable Start Date")),
            "probable_end": parse_date(item.get("Probable End Date")),
            "owner_code": normalize_text(item.get("BD/KAM Personnel code")),
            "sector": normalize_sector(item.get("Sector")),
            "type_of_work": normalize_text(item.get("Type of Work")),
            "amount_excl_gst": parse_numeric(item.get("Amount in Rupees (Excl of GST) (Masked)")),
            "billed_excl_gst": parse_numeric(item.get("Billed Value in Rupees (Excl of GST.) (Masked)")),
            "collected_incl_gst": parse_numeric(item.get("Collected Amount in Rupees (Incl of GST.) (Masked)")),
            "amount_receivable": parse_numeric(item.get("Amount Receivable (Masked)")),
            "invoice_status": normalize_text(item.get("Invoice Status")),
            "wo_status": normalize_text(item.get("WO Status (billed)")),
            "billing_status": normalize_text(item.get("Billing Status")),
        })
    df = pd.DataFrame(rows)

    missing_amount = df["amount_excl_gst"].isna().sum()
    if missing_amount > 0:
        note(f"{missing_amount} work orders have missing/unparseable amount values.")

    today = pd.Timestamp(datetime.now().date())
    delayed_mask = (
        df["probable_end"].notna()
        & (df["probable_end"] < today)
        & (~df["execution_status"].fillna("").str.lower().isin(["completed", "closed"]))
    )
    df["is_delayed"] = delayed_mask

    return df


def get_quality_notes() -> list[str]:
    return list(DATA_QUALITY_NOTES)
