#!/usr/bin/env python3
"""
AIB Bank Statement Parser

Supports:
  1. Single‐PDF mode   → parse one PDF, produce one CSV
  2. Combined‐dir mode → parse all PDFs in a directory, produce one combined CSV
  3. Separate‐dir mode → parse all PDFs in a directory, produce one CSV per PDF

In debug mode, the CSV will also include x_coord and y_coord for each transaction.
"""

import argparse
import csv
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf  # PyMuPDF

# --- Constants & Config ----------------------------------------------------

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

AMOUNT_RE = re.compile(r"^\d+\.\d{2}$")
DATE_RE = re.compile(
    r"(?P<day>\d{1,2})\s+"
    r"(?P<month>" + "|".join(MONTHS) + r")\s+"
    r"(?P<year>\d{4})"
)

COLUMN_BOUNDS = {
    "DEBIT": (250, 324),
    "CREDIT": (325, 350),
    "BALANCE": (395, float("inf")),
}

PAGE_HEIGHT = 842
TABLE_BBOX = (
    25,
    PAGE_HEIGHT - 535,
    561,
    PAGE_HEIGHT - 87,
)

WordTuple = Tuple[float, float, float, float, str, int, int, int]


# --- Utility Functions -----------------------------------------------------

def extract_date_from_raw_text(text: str) -> Optional[str]:
    match = DATE_RE.search(text + " BALANCE FORWARD")
    if match:
        return f"{match.group('day')} {match.group('month')} {match.group('year')}"
    return None


def find_amount_coordinates(
    words: List[WordTuple],
    amount: float
) -> Optional[Dict[str, Any]]:
    target = f"{amount:.2f}"
    for x0, y0, x1, y1, txt, *rest in words:
        if txt.replace(",", "") == target:
            for col, (xmin, xmax) in COLUMN_BOUNDS.items():
                if xmin <= x0 <= xmax:
                    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "column": col}
            return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "column": "UNKNOWN"}
    return None


def parse_amount_field(amount_str: str, is_balance: bool = False) -> float:
    if not amount_str or not amount_str.strip():
        return 0.0

    s = amount_str.strip().lower().replace("€", "").replace("£", "").replace(",", "")
    overdrawn = False

    if "dr" in s:
        if is_balance:
            overdrawn = True
            s = s.replace("dr", "").strip()
        else:
            return 0.0

    negative = s.startswith("-")
    if negative:
        s = s[1:]

    try:
        val = float(s)
        if is_balance and overdrawn:
            val = -val
        elif negative:
            val = -val
        return val
    except ValueError:
        return 0.0


def extract_initial_date(table: List[List[str]]) -> str:
    limit = min(len(table), 12)
    for i in range(limit):
        row_text = " ".join(table[i]).upper()
        if any(k in row_text for k in ("BALANCE FORWARD", "LENDING @")):
            for j in range(i, min(i + 4, limit)):
                cells = table[j]
                if len(cells) >= 3:
                    d, m, y = cells[0].strip(), cells[1].strip(), cells[2].strip()
                    if d.isdigit() and m in MONTHS and y.isdigit():
                        return f"{d} {m} {y}"
    return ""


def find_transaction_start_index(table: List[List[str]]) -> int:
    for i, row in enumerate(table[:12]):
        text = " ".join(cell.strip() for cell in row).upper()
        if any(k in text for k in ("BALANCE FORWARD", "LENDING @")):
            idx = i + 3
            while idx < len(table) and not any(table[idx]):
                idx += 1
            return idx
    return 0


# --- Core Parsing ----------------------------------------------------------

def parse_transaction_row(
    row: List[str],
    idx: int,
    words: List[WordTuple],
    inherited_date: str
) -> Optional[Dict[str, Any]]:
    debit = credit = balance = 0.0
    coords: Optional[Dict[str, Any]] = None

    for cell in row:
        if AMOUNT_RE.match(cell):
            amt = float(cell)
            coords = find_amount_coordinates(words, amt)
            col = coords["column"] if coords else "DEBIT"
            if col == "DEBIT":
                debit = amt
            elif col == "CREDIT":
                credit = amt
            elif col == "BALANCE":
                balance = amt
            break

    date = ""
    details = ""
    for i in range(len(row) - 2):
        d, m, y = row[i].strip(), row[i + 1].strip(), row[i + 2].strip()
        if d.isdigit() and m in MONTHS and y.isdigit():
            date = f"{d} {m} {y}"
            details = " ".join(
                c for c in row[i + 3:] if not AMOUNT_RE.match(c)
            ).strip()
            break

    if not date:
        date = inherited_date
        details = " ".join(c for c in row if not AMOUNT_RE.match(c)).strip()

    if not any((date, details, debit, credit, balance)):
        return None

    return {
        "row": idx,
        "date": date,
        "details": details,
        "debit": debit,
        "credit": credit,
        "balance": balance,
        "x_coord": coords["x0"] if coords else "",
        "y_coord": coords["y0"] if coords else "",
    }


def clean_page_transactions(
    table: List[List[str]],
    page_num: int,
    page: pymupdf.Page,
    words: List[WordTuple]
) -> List[Dict[str, Any]]:
    logging.info("Page %d: raw rows: %d", page_num, len(table))

    initial_date = extract_initial_date(table)
    if not initial_date:
        raw_text = page.get_text()
        initial_date = extract_date_from_raw_text(raw_text) or ""
        logging.warning("Used fallback raw-text date: %r", initial_date)

    start_idx = find_transaction_start_index(table)
    logging.info("Page %d: transactions start at row %d", page_num, start_idx)

    txs: List[Dict[str, Any]] = []
    current_date = initial_date

    for idx, raw_row in enumerate(table[start_idx:], start_idx):
        if not any(cell.strip() for cell in raw_row):
            continue
        row = [cell.strip() for cell in raw_row]
        tx = parse_transaction_row(row, idx, words, current_date)
        if not tx:
            continue
        if tx["date"] and tx["date"] != current_date:
            current_date = tx["date"]
        else:
            tx["date"] = current_date
        txs.append(tx)
        logging.debug("Parsed txn: %r", tx)

    return txs


# --- I/O & Orchestration --------------------------------------------------

def read_pdf_and_extract(pdf_path: Path) -> List[Dict[str, Any]]:
    doc = pymupdf.open(str(pdf_path))
    all_txs: List[Dict[str, Any]] = []
    logging.info("Opened %r with %d pages", pdf_path, doc.page_count)

    for p in range(doc.page_count):
        page = doc[p]
        words = page.get_text("words", sort=True)

        tables = page.find_tables(
            strategy="text",
            clip=TABLE_BBOX,
            min_words_vertical=2,
            min_words_horizontal=1,
            text_tolerance=5,
            snap_tolerance=3,
            intersection_tolerance=10
        ).tables

        if not tables:
            logging.debug("Page %d: no table found", p + 1)
            continue

        raw_table = tables[0].extract()
        txs = clean_page_transactions(raw_table, p + 1, page, words)
        all_txs.extend(txs)

    doc.close()
    return all_txs


def export_to_csv(
    transactions: List[Dict[str, Any]],
    csv_path: Path,
    debug: bool = False
) -> None:
    if not transactions:
        logging.warning("No transactions to export for %r", csv_path)
        return

    # Base columns
    fieldnames = ["date", "details", "debit", "credit", "balance"]
    # Add coords in debug mode
    if debug:
        fieldnames += ["x_coord", "y_coord"]

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for tx in transactions:
            row = {
                "date":    tx["date"],
                "details": tx["details"],
                "debit":   tx["debit"] or "",
                "credit":  tx["credit"] or "",
                "balance": tx["balance"] or "",
            }
            if debug:
                row["x_coord"] = tx["x_coord"]
                row["y_coord"] = tx["y_coord"]
            writer.writerow(row)

    logging.info("Wrote %d txns to %r", len(transactions), csv_path)


def process(
    input_path: Path,
    combined: bool,
    separate: bool,
    debug: bool
) -> None:
    if input_path.is_file():
        pdfs = [input_path]
    elif input_path.is_dir():
        pdfs = sorted(input_path.glob("*.pdf"))
    else:
        logging.error("Input path is neither file nor directory: %r", input_path)
        return

    if input_path.is_dir() and not (combined or separate):
        combined = True

    all_transactions: List[Dict[str, Any]] = []

    for pdf in pdfs:
        logging.info("Processing %r", pdf)
        txs = read_pdf_and_extract(pdf)

        if separate:
            out_csv = pdf.with_suffix(".csv")
            export_to_csv(txs, out_csv, debug=debug)

        all_transactions.extend(txs)

    if combined:
        if input_path.is_dir():
            out_name = input_path.name + "_combined.csv"
            combined_csv = input_path / out_name
        else:
            combined_csv = input_path.with_suffix(".csv")
        export_to_csv(all_transactions, combined_csv, debug=debug)


# --- Entrypoint ------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Parse AIB bank PDFs into CSV"
    )
    parser.add_argument(
        "input_path",
        type=Path,
        help="PDF file or directory of PDFs to parse"
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--combined",
        action="store_true",
        help="For directory input: produce one combined CSV"
    )
    group.add_argument(
        "--separate",
        action="store_true",
        help="For directory input: produce one CSV per PDF"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging and include x_coord/y_coord in CSV"
    )

    args = parser.parse_args()

    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")

    process(
        input_path=args.input_path,
        combined=args.combined,
        separate=args.separate,
        debug=args.debug
    )


if __name__ == "__main__":
    main()