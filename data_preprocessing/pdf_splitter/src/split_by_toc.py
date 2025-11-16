import argparse
import os
import re
from typing import List, Set, TypedDict

import fitz  # type: ignore  # PyMuPDF (no stubs)
from pypdf import PdfReader, PdfWriter

MIN_TITLE_CHARS = 4  # minimum characters for a TOC title
MAX_CONSECUTIVE_NONMATCH = (
    6  # stop TOC scanning after this many non-matching lines in sequence
)
MAX_TOC_PAGES_DEFAULT = 1  # maximum pages to scan after finding "Contents"


class TocEntry(TypedDict):
    title: str
    page: int


class PageRange(TypedDict):
    title: str
    start: int
    end: int


def find_toc_start_pages(pdf_path: str, max_scan_pages: int = 12) -> List[int]:
    """
    Scan the PDF to find pages that likely contain the printed TOC marker
    (e.g., "Table of Contents" as the first line of a page).
    Returns a list of page indices (0-based) to treat as TOC pages.
    Stops after scanning max_scan_pages pages after the first hit.
    """
    toc_pages = []
    with fitz.open(pdf_path) as doc:
        n = len(doc)
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            # Split into lines and check if the first line or top few lines contain TOC keywords
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if not lines:
                continue

            # Only check the first few lines (top 3) for "Table of Contents" keywords
            top_lines = " ".join(lines[:3])
            if re.search(r"\b(table of contents)\b", top_lines, re.I):
                # Add this page and following pages up to max_scan_pages or until likely end
                start = i
                end = min(n, start + max_scan_pages)
                toc_pages = list(range(start, end))
                print(
                    f"[INFO] Detected 'Contents' marker on page {i+1}. Will scan pages {start+1}-{end}."
                )
                break
    if not toc_pages:
        print("[WARN] No explicit 'Contents' marker detected at top of any page.")
    return toc_pages


def extract_page_lines(pdf_path: str, page_index: int) -> List[str]:
    """Return cleaned lines of text from a page (preserve line-break segmentation)."""
    with fitz.open(pdf_path) as doc:
        text = doc[page_index].get_text("text")
    # split in lines, strip whitespace but keep internal spaces
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines


def parse_toc_from_pages(
    pdf_path: str,
    toc_page_indices: List[int],
    total_pages: int,
    max_consecutive_nonmatch: int = MAX_CONSECUTIVE_NONMATCH,
) -> List[TocEntry]:
    """
    Parse TOC entries from the provided pages.
    Returns list of {"title": str, "page": int}.
    Heuristics: a TOC line should end with a page number or a '(pages X-Y)' marker.
    """
    entries: List[TocEntry] = []

    line_page_re = re.compile(
        r"""^
            (?P<title>.+?)               # title (non-greedy)
            (?:\s*[\.\u2026\s\-–—]*\s*)? # optional dots/ellipses/dashes/space padding
            (?:                         # page / pages patterns:
               (?P<page>\d{1,4})\s*$ |                              # trailing page number
               pages?\s*(?P<range1>\d{1,4})(?:\s*[-–—]\s*(?P<range2>\d{1,4}))?\s*\)?\s*$  # pages X or pages X-Y
            )
        """,
        re.I | re.VERBOSE,
    )

    # iterate pages in order
    for p_idx in toc_page_indices:
        lines = extract_page_lines(pdf_path, p_idx)
        if not lines:
            continue

        i, j = 0, 0
        while i < len(lines):
            ln = str(lines[i + j])
            if "table" in ln.lower() or "contents" in ln.lower():
                # skip this line
                i += 1
                continue

            merged = ""
            if not re.search(r"^(?:.*\D)?(\d{1,4})$", ln):
                j += 1
                continue
            else:
                merged = " ".join(lines[i : i + j + 1])
                i += 1 + j

            m = line_page_re.search(merged)
            page_num = None
            title_raw = None

            if m:
                title_raw = m.group("title").strip()
                page_num = int(m.group("page"))
                j = 0

            # Validate extracted page number
            if page_num is None:
                continue
            if page_num < 1 or page_num > total_pages:
                print(
                    f"[DEBUG] Ignored entry with out-of-range page {page_num}: '{(title_raw or '')[:40]}...'"
                )
                continue

            # filter out lines that are clearly not bona fide entries
            if not title_raw or len(title_raw) < MIN_TITLE_CHARS:
                continue

            # Clean title: remove leading numbering and trailing punctuation/dots
            title = re.sub(r"^\s*\d+[\.)]?\s*", "", title_raw)
            title = re.sub(r"[\.\s\-–—]+$", "", title).strip()

            # Additional heuristic: skip if the title looks like a tiny uppercase label
            if len(title.split()) <= 1 and title.isupper() and len(title) < 8:
                continue

            entries.append({"title": title, "page": page_num})

    # Remove duplicates while preserving order (same start page repeated)
    seen = set()
    filtered = []
    for e in entries:
        key = (e["title"].lower(), e["page"])
        if key not in seen:
            seen.add(key)
            filtered.append(e)

    return filtered


def sanitize_filename(name: str) -> str:
    """Sanitize filenames by removing illegal characters and trimming length."""
    # Remove control characters (0x00-0x1F and 0x7F-0x9F)
    name = re.sub(r'[\x00-\x1F\x7F-\x9F]', "", name)
    # Remove illegal Windows filename characters
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    # Replace whitespace sequences with single underscore
    name = re.sub(r"\s+", "_", name.strip())
    return name[:100]


def split_pdf_by_toc(
    pdf_path: str, toc_entries: List[TocEntry], output_dir: str, dry_run: bool = False
):
    """Split the PDF using computed TOC entries (expects entries sorted by page ascending)."""
    if not toc_entries:
        print("[ERROR] No TOC entries provided to split.")
        return

    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    os.makedirs(output_dir, exist_ok=True)

    # Sort entries by page (safety)
    toc_entries_sorted = sorted(toc_entries, key=lambda x: x["page"])

    for i, entry in enumerate(toc_entries_sorted):
        start: int = entry["page"]
        end: int = (
            (toc_entries_sorted[i + 1]["page"] - 1)
            if i + 1 < len(toc_entries_sorted)
            else total_pages
        )
        start_idx = max(0, start - 1)
        end_idx = min(total_pages, end)  # end is inclusive in our convention

        fname = f"{sanitize_filename(entry['title'])}.pdf"
        out_path = os.path.join(output_dir, fname)
        print(f"→ {entry['title']} (pages {start}-{end}) -> {out_path}")

        if not dry_run:
            writer = PdfWriter()
            for p in range(start_idx, end_idx):
                writer.add_page(reader.pages[p])
            writer.write(out_path)

    if dry_run:
        print("\n[DRY-RUN] Simulation complete. No files were created.")
    else:
        print("\n✅ Split complete.")


def split_selected_ranges(
    pdf_path: str, ranges: List[PageRange], output_dir: str, dry_run: bool = False
):
    """Split PDF using explicit start/end page ranges.

    ranges: list of {'title': str, 'start': int, 'end': int}
    """
    if not ranges:
        print("[ERROR] No ranges provided to split.")
        return

    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    os.makedirs(output_dir, exist_ok=True)

    for r in ranges:
        title = r["title"]
        start = r["start"]
        end = r["end"]
        # clamp
        start_idx = max(0, start - 1)
        end_idx = min(total_pages, end)

        fname = f"{sanitize_filename(title)}.pdf"
        out_path = os.path.join(output_dir, fname)
        print(f"→ {title} (pages {start}-{end}) -> {out_path}")

        if not dry_run:
            writer = PdfWriter()
            for p in range(start_idx, end_idx):
                writer.add_page(reader.pages[p])
            writer.write(out_path)

    if dry_run:
        print("\n[DRY-RUN] Simulation complete. No files were created.")
    else:
        print("\n✅ Split complete.")


def main():
    # Declare we will override the module-level constant so any use below refers to the global
    global MIN_TITLE_CHARS

    ap = argparse.ArgumentParser(
        description="Split PDF by printed TOC (improved parsing heuristics)."
    )
    ap.add_argument("pdf", help="Input PDF path.")
    ap.add_argument("--output-dir", default="splits", help="Output directory.")
    ap.add_argument(
        "--dry-run", action="store_true", help="Simulate the split; don't create files."
    )
    ap.add_argument(
        "--max-toc-pages",
        type=int,
        default=MAX_TOC_PAGES_DEFAULT,
        help="Maximum number of pages to scan after the detected 'Contents' page.",
    )
    ap.add_argument(
        "--min-title-chars",
        type=int,
        default=MIN_TITLE_CHARS,
        help="Minimum title length to accept.",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Select all parsed chapters (non-interactive).",
    )
    args = ap.parse_args()

    # allow heuristic constant overrides from CLI
    MIN_TITLE_CHARS = args.min_title_chars

    reader = PdfReader(args.pdf)
    total_pages = len(reader.pages)

    toc_page_indices = find_toc_start_pages(args.pdf, max_scan_pages=args.max_toc_pages)
    if not toc_page_indices:
        # Fallback: attempt to scan the first N pages for top-of-document TOC area
        print("[INFO] Falling back to scanning first few pages for TOC-like lines.")
        toc_page_indices = list(range(0, min(total_pages, args.max_toc_pages)))

    toc_entries = parse_toc_from_pages(args.pdf, toc_page_indices, total_pages)
    print(f"[INFO] Extracted {len(toc_entries)} TOC entries after heuristics.")

    # small sanity: ensure entries sorted and unique pages
    toc_entries = sorted(toc_entries, key=lambda e: e["page"])

    if not toc_entries:
        print(
            "[ERROR] No valid TOC entries found. Try OCRing the PDF (ocrmypdf) or increase heuristics limits."
        )
        return

    # If user asked for all chapters via CLI flag, split everything non-interactively
    if args.all:
        split_pdf_by_toc(args.pdf, toc_entries, args.output_dir, args.dry_run)
        return

    # Interactive selection: list chapters and allow the user to pick indices/ranges
    print("\nParsed chapters:")
    for idx, e in enumerate(toc_entries, start=1):
        print(f" {idx:3d}. {e['title']} (p{e['page']})")

    def prompt_selection(max_idx: int) -> List[int]:
        """Prompt user until a valid selection is entered. Returns list of 1-based indices."""
        while True:
            sel = input(
                "\nEnter chapters to extract (e.g. 1,3-5), 'all' to select all, or 'q' to quit: "
            ).strip()
            if not sel:
                print("No selection provided. Aborting.")
                return []
            low = sel.lower()
            if low in ("all", "a"):
                return list(range(1, max_idx + 1))
            if low in ("q", "quit", "exit"):
                print("Aborted by user.")
                return []

            parts = [p.strip() for p in sel.split(",") if p.strip()]
            indices: Set[int] = set()
            try:
                for part in parts:
                    if "-" in part:
                        s_s, e_s = part.split("-", 1)
                        s = int(s_s)
                        e = int(e_s)
                        if s < 1 or e > max_idx or s > e:
                            raise ValueError()
                        indices.update(range(s, e + 1))
                    else:
                        n = int(part)
                        if n < 1 or n > max_idx:
                            raise ValueError()
                        indices.add(n)
            except ValueError:
                print(
                    "Invalid selection. Use numbers, comma-separated and ranges (e.g. 1,3-5). Try again."
                )
                continue

            if not indices:
                print("No valid indices parsed. Try again.")
                continue
            return sorted(indices)

    selected = prompt_selection(len(toc_entries))
    if not selected:
        return

    # Build explicit ranges from selected indices
    ranges = []
    for idx in selected:
        i0 = idx - 1
        start = toc_entries[i0]["page"]
        end = (
            (toc_entries[i0 + 1]["page"] - 1)
            if i0 + 1 < len(toc_entries)
            else total_pages
        )
        ranges.append({"title": toc_entries[i0]["title"], "start": start, "end": end})

    split_selected_ranges(args.pdf, ranges, args.output_dir, args.dry_run)


if __name__ == "__main__":
    main()
