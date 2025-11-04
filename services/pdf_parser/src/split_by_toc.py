#!/usr/bin/env python3
"""
split_by_toc.py — Improved PDF splitter by detecting a printed TOC and splitting by ranges.

Usage:
    python split_by_toc.py input.pdf --dry-run
    python split_by_toc.py input.pdf --output-dir ./chapters --max-toc-pages 4

Requirements:
    pip install pypdf PyMuPDF
"""

import re
import os
import argparse
from typing import List, Dict, Tuple, Optional
import fitz  # PyMuPDF
from pypdf import PdfReader, PdfWriter


# ---------- Configurable heuristics ----------
MIN_TITLE_CHARS = 4            # minimum characters for a TOC title
MAX_CONSECUTIVE_NONMATCH = 6   # stop TOC scanning after this many non-matching lines in sequence
MAX_TOC_PAGES_DEFAULT = 2      # maximum pages to scan after finding "Contents"
# ---------------------------------------------


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
                print(f"[INFO] Detected 'Contents' marker on page {i+1}. Will scan pages {start+1}-{end}.")
                print(f"[INFO] First lines on page {i+1}:")
                for line in lines[:5]:
                    print(f"    {line}")
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


def parse_toc_from_pages(pdf_path: str, toc_page_indices: List[int], total_pages: int,
                         max_consecutive_nonmatch: int = MAX_CONSECUTIVE_NONMATCH) -> List[Dict]:
    """
    Parse TOC entries from the provided pages.
    Returns list of {"title": str, "page": int}.
    Heuristics: a TOC line should end with a page number or a '(pages X-Y)' marker.
    """
    entries = []
    consec_nonmatch = 0

    # regex patterns to match lines that *end* with a page number or page-range marker
    # Examples matched:
    # "1. Sets and cartesian product ........................... 5"
    # "Powers and radicals (pages 33-370)"
    # "Study of functions (pages 371-4)" -> we'll take 371
    line_page_re = re.compile(
        r"""^
            (?P<title>.+?)               # title (non-greedy)
            (?:\s*[\.\u2026\s\-–—]*\s*)? # optional dots/ellipses/dashes/space padding
            (?:                         # page / pages patterns:
               (?P<page>\d{1,4})\s*$ |                              # trailing page number
               pages?\s*(?P<range1>\d{1,4})(?:\s*[-–—]\s*(?P<range2>\d{1,4}))?\s*\)?\s*$  # pages X or pages X-Y
            )
        """,
        re.I | re.VERBOSE
    )

    # iterate pages in order
    for p_idx in toc_page_indices:
        lines = extract_page_lines(pdf_path, p_idx)
        if not lines:
            continue

        # Use an index-based loop so we can merge a title line with a following
        # line that contains only the page number (common layout), and also
        # support multi-line titles that span several lines until a delimiter
        # (dots/ellipsis/dashes) or a page-number line appears.
        i = 0
        while i < len(lines):
            ln = lines[i]

            # Skip very short lines
            if len(ln) < MIN_TITLE_CHARS:
                consec_nonmatch += 1
                if consec_nonmatch >= max_consecutive_nonmatch:
                    print(f"[INFO] Reached {consec_nonmatch} consecutive non-matching lines; stopping TOC parsing.")
                    return entries
                i += 1
                continue

            # Try to assemble a possible title block by merging subsequent lines
            # until we encounter a delimiter line (dots/ellipsis/dashes) or a
            # line that looks like a page number. We'll then try the strict
            # regex against the assembled block.
            merged = ln
            lookahead = i + 1
            # limit lookahead to avoid runaway merging
            while lookahead < len(lines) and lookahead - i <= 4:
                nxt = lines[lookahead]
                # if next line is clearly a page-number or contains 'pages X', stop merging
                if re.search(r"^\.*\s*\d{1,4}\s*$", nxt) or re.search(r"pages?\s*\d{1,4}", nxt, re.I) or re.search(r"(\.{2,}|\u2026|[-–—]{2,})", nxt):
                    break
                # otherwise append as continuation of title
                merged = merged + " " + nxt
                lookahead += 1

            # Now try strict regex on merged block
            m = line_page_re.search(merged)
            page_num = None
            title_raw = None

            if m:
                # matched title+page on the merged block
                consec_nonmatch = 0
                title_raw = m.group("title").strip()
                if m.group("page"):
                    page_num = int(m.group("page"))
                elif m.group("range1"):
                    page_num = int(m.group("range1"))
                # advance i past consumed lines
                # if we merged extra lines, move i to lookahead; otherwise i++
                if lookahead > i + 1:
                    i = lookahead
                else:
                    i += 1
            else:
                # If merged didn't match, maybe the page number is on the next line
                next_page = None
                if i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    m_next = re.search(r"(\d{1,4})\s*$", nxt)
                    if m_next:
                        next_page = int(m_next.group(1))
                if next_page:
                    consec_nonmatch = 0
                    title_raw = merged
                    page_num = next_page
                    # consume title lines up to the page-number line
                    # determine how many lines were merged (lookahead - i)
                    # and then consume the additional page-number line as well
                    consume = max(1, lookahead - i)
                    i = i + consume + 1
                else:
                    consec_nonmatch += 1
                    if consec_nonmatch >= max_consecutive_nonmatch:
                        print(f"[INFO] Reached {consec_nonmatch} consecutive non-matching lines; stopping TOC parsing.")
                        return entries
                    i += 1
                    continue

            # Validate extracted page number
            if page_num is None:
                continue
            if page_num < 1 or page_num > total_pages:
                print(f"[DEBUG] Ignored entry with out-of-range page {page_num}: '{(title_raw or '')[:40]}...'")
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
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:100]


def split_pdf_by_toc(pdf_path: str, toc_entries: List[Dict], output_dir: str, dry_run: bool = False):
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
        start = entry["page"]
        end = (toc_entries_sorted[i + 1]["page"] - 1) if i + 1 < len(toc_entries_sorted) else total_pages
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


def split_selected_ranges(pdf_path: str, ranges: List[Dict], output_dir: str, dry_run: bool = False):
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
        title = r.get('title')
        start = r.get('start')
        end = r.get('end')
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

    ap = argparse.ArgumentParser(description="Split PDF by printed TOC (improved parsing heuristics).")
    ap.add_argument("pdf", help="Input PDF path.")
    ap.add_argument("--output-dir", default="splits", help="Output directory.")
    ap.add_argument("--dry-run", action="store_true", help="Simulate the split; don't create files.")
    ap.add_argument("--max-toc-pages", type=int, default=MAX_TOC_PAGES_DEFAULT,
                    help="Maximum number of pages to scan after the detected 'Contents' page.")
    ap.add_argument("--min-title-chars", type=int, default=MIN_TITLE_CHARS, help="Minimum title length to accept.")
    ap.add_argument("--all", action="store_true", help="Select all parsed chapters (non-interactive).")
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
        print("[ERROR] No valid TOC entries found. Try OCRing the PDF (ocrmypdf) or increase heuristics limits.")
        return

    # If user asked for all chapters via CLI flag, split everything non-interactively
    if args.all:
        split_pdf_by_toc(args.pdf, toc_entries, args.output_dir, args.dry_run)
        return

    # Interactive selection: list chapters and allow the user to pick indices/ranges
    print('\nParsed chapters:')
    for idx, e in enumerate(toc_entries, start=1):
        print(f" {idx:3d}. {e['title']} (p{e['page']})")

    def prompt_selection(max_idx: int) -> List[int]:
        """Prompt user until a valid selection is entered. Returns list of 1-based indices."""
        while True:
            sel = input("\nEnter chapters to extract (e.g. 1,3-5), 'all' to select all, or 'q' to quit: ").strip()
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
            indices = set()
            try:
                for part in parts:
                    if '-' in part:
                        s_s, e_s = part.split('-', 1)
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
                print("Invalid selection. Use numbers, comma-separated and ranges (e.g. 1,3-5). Try again.")
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
        start = toc_entries[i0]['page']
        end = (toc_entries[i0 + 1]['page'] - 1) if i0 + 1 < len(toc_entries) else total_pages
        ranges.append({'title': toc_entries[i0]['title'], 'start': start, 'end': end})

    split_selected_ranges(args.pdf, ranges, args.output_dir, args.dry_run)


if __name__ == "__main__":
    main()

