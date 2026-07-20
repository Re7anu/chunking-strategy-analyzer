import os
import re
import io
import pdfplumber


def list_to_markdown_table(table: list[list[str | None]]) -> str:
    """
    Converts a list-of-lists table extracted from a PDF into a clean Markdown table.
    """
    if not table or not any(table):
        return ""

    # Filter out completely empty rows/columns
    cleaned_rows = []
    for row in table:
        if not row:
            continue
        cleaned_row = [str(cell or "").strip().replace("\n", " ").replace("|", "\\|") for cell in row]
        # Skip rows that are entirely empty
        if any(cleaned_row):
            cleaned_rows.append(cleaned_row)

    if not cleaned_rows:
        return ""

    headers = cleaned_rows[0]
    rows = cleaned_rows[1:]

    # Markdown table syntax requires header, separator, and body rows
    separator = ["---"] * len(headers)

    md_lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(separator) + " |"
    ]
    for row in rows:
        # Pad row elements if shorter than header
        if len(row) < len(headers):
            row += [""] * (len(headers) - len(row))
        elif len(row) > len(headers):
            row = row[:len(headers)]
        md_lines.append("| " + " | ".join(row) + " |")

    return "\n\n" + "\n".join(md_lines) + "\n\n"


def detect_financial_metadata(filename: str, text_sample: str) -> tuple[int | None, str | None]:
    """
    Detects fiscal year (int) and quarter (str) from filename or text sample.
    """
    fiscal_year = None
    quarter = None

    # 1. Inspect filename first (common convention, e.g. "GOOG_2025_Q3.pdf", "TSLA-Q2-24.pdf")
    fn_lower = filename.lower()
    
    # Try finding 4-digit years in filename
    year_match = re.search(r"\b(20[23][0-9])\b", fn_lower)
    if year_match:
        fiscal_year = int(year_match.group(1))
    else:
        # Try finding 2-digit years after Q or FY (e.g. Q3_24, Q2-25, FY25_Annual)
        year_match_2 = re.search(r"(?:q[1-4]|fy|fiscal)\s*[-_]?\s*([23][0-9])(?!\d)", fn_lower)
        if year_match_2:
            fiscal_year = 2000 + int(year_match_2.group(1))

    # Try finding quarter in filename
    quarter_match = re.search(r"\b(q[1-4])\b", fn_lower)
    if quarter_match:
        quarter = quarter_match.group(1).upper()
    elif "10-k" in fn_lower or "fy" in fn_lower or "annual" in fn_lower:
        quarter = "FY"
    elif "10-q" in fn_lower:
        # Default quarterly placeholder if it is Form 10-Q but exact quarter isn't in name
        quarter = "Q"

    # 2. If metadata not fully found, scan the text sample (first 1-2 pages of report)
    text_sample_clean = text_sample.replace("\n", " ").lower()

    if not fiscal_year:
        # Look for ended dates like "ended December 31, 2025", "ended June 30, 2024"
        ended_match = re.search(r"ended\s+[a-zA-Z]+\s+\d{1,2},\s*(20[23][0-9])", text_sample_clean)
        if ended_match:
            fiscal_year = int(ended_match.group(1))
        else:
            # Fallback to any 4-digit year starting with 202 or 203
            year_match_text = re.search(r"\b(20[23][0-9])\b", text_sample_clean)
            if year_match_text:
                fiscal_year = int(year_match_text.group(1))

    if not quarter or quarter == "Q":
        # Check Form types
        if "form 10-k" in text_sample_clean or "annual report" in text_sample_clean:
            quarter = "FY"
        elif "form 10-q" in text_sample_clean:
            # Try to identify quarter from ended month:
            # Q1: March, Q2: June, Q3: September
            if "march" in text_sample_clean:
                quarter = "Q1"
            elif "june" in text_sample_clean:
                quarter = "Q2"
            elif "september" in text_sample_clean:
                quarter = "Q3"
            else:
                quarter = "Q"  # Fallback quarterly

    return fiscal_year, quarter


def parse_financial_pdf(file_bytes: bytes, filename: str) -> tuple[list[dict], int | None, str | None]:
    """
    Parses a PDF file from bytes using pdfplumber.
    Extracts text page-by-page, extracts tables and formats them inline as Markdown,
    and returns page contents along with auto-detected metadata.
    """
    pages = []
    metadata_text_accumulator = ""
    
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for idx, page in enumerate(pdf.pages):
            page_num = idx + 1
            
            # Extract plain text
            text = page.extract_text() or ""
            
            # Extract tables
            tables = page.extract_tables()
            md_tables = []
            for t in tables:
                md_table = list_to_markdown_table(t)
                if md_table:
                    md_tables.append(md_table)
            
            # Combine page text and markdown tables
            combined_text = text
            if md_tables:
                combined_text += "\n" + "\n".join(md_tables)
                
            pages.append({
                "number": page_num,
                "text": combined_text
            })
            
            # Accumulate text from first 2 pages for metadata detection
            if page_num <= 2:
                metadata_text_accumulator += " " + text

    # Run auto-detection
    fiscal_year, quarter = detect_financial_metadata(filename, metadata_text_accumulator)
    
    return pages, fiscal_year, quarter
