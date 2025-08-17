# AIB Bank Statement PDF Parser

This script parses AIB bank statement PDFs and converts them into CSV files for easier analysis. It supports parsing a single PDF, all PDFs in a directory (combined or separate CSVs), and includes a debug mode for advanced inspection.

## Features

- **Single-PDF mode:** Parse one PDF and produce one CSV.
- **Combined-dir mode:** Parse all PDFs in a directory and produce one combined CSV.
- **Separate-dir mode:** Parse all PDFs in a directory and produce one CSV per PDF.
- **Debug mode:** CSV includes x/y coordinates for each transaction.

## Requirements

- Python 3.7+
- [PyMuPDF](https://pymupdf.readthedocs.io/) (`pip install pymupdf`)

## Usage

```sh
python golden_parser_aib.py <input_path> [--combined | --separate] [--debug]
```

- `<input_path>`: Path to a PDF file or a directory containing PDF files.
- `--combined`: (Directory only) Output a single combined CSV for all PDFs.
- `--separate`: (Directory only) Output one CSV per PDF.
- `--debug`: Enable debug logging and include x/y coordinates in the CSV.

### Examples

**Parse a single PDF:**
```sh
python golden_parser_aib.py bank_statements/29th\ August\ 2024.pdf
```

**Parse all PDFs in a directory into one combined CSV:**
```sh
python golden_parser_aib.py bank_statements/ --combined
```

**Parse all PDFs in a directory into separate CSVs:**
```sh
python golden_parser_aib.py bank_statements/ --separate
```

**Enable debug mode:**
```sh
python golden_parser_aib.py bank_statements/ --combined --debug
```

## Output

- CSV files will be created in the same directory as the input PDFs.
- In combined mode, the CSV will be named `<directory>_combined.csv`.
- In separate mode, each CSV will have the same name as the PDF but with a `.csv` extension.

## How it Works

1. **PDF Parsing:** Uses PyMuPDF to extract tables and words from each PDF page.
2. **Transaction Extraction:** Identifies transaction rows, parses dates, details, debit/credit/balance amounts, and (optionally) their coordinates.
3. **CSV Export:** Writes the parsed transactions to CSV, with optional debug columns.

## Notes

- The script is tailored for AIB statement layouts and may not work with other banks.
- Sensitive financial data should be handled securely; the `bank_statements/` directory is `.gitignore`d by default.

## License