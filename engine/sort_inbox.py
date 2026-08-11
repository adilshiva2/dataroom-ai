#!/usr/bin/env python3
"""T5 — Inbox sorter.

Classifies files in inbox/ against the manifest via a single claude -p
call, moves each to the correct data room folder with a standardized
name, and updates checklist.csv.

Usage:
    python engine/sort_inbox.py [inbox_path_or_zip]

Accepts a directory path OR a .zip file.  When given a .zip, the archive
is extracted to a temporary directory, sorted normally, and the temp dir
is cleaned up afterward.

Classification outcomes:
  MATCH        → move to the matching subfolder, mark checklist "received"
  DRAFT        → move to 4.1 Drafts/<doc type>/, do NOT tick checklist
  NEEDS_REVIEW → move to NEEDS_REVIEW/

NO direct Anthropic API calls — uses claude -p per project policy.
"""

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from pypdf import PdfReader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT, "output")
DATAROOM = os.path.join(OUTPUT_DIR, "dataroom")
MANIFEST_PATH = os.path.join(OUTPUT_DIR, "manifest.json")
CHECKLIST_PATH = os.path.join(DATAROOM, "checklist.csv")


# ── Text extraction ─────────────────────────────────────────────────

def extract_pdf_text(path, max_pages=2):
    try:
        reader = PdfReader(path)
        parts = []
        for page in reader.pages[:max_pages]:
            t = page.extract_text()
            if t:
                parts.append(t)
        return "\n".join(parts)
    except Exception:
        return ""


def extract_docx_text(path):
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    try:
        with zipfile.ZipFile(path) as z:
            with z.open("word/document.xml") as f:
                tree = ET.parse(f)
        return " ".join(
            el.text for el in tree.iter(f"{{{ns}}}t") if el.text
        )
    except Exception:
        return ""


def extract_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return extract_pdf_text(path)
    if ext == ".docx":
        return extract_docx_text(path)
    try:
        with open(path) as f:
            return f.read(4000)
    except Exception:
        return ""


# ── Checklist I/O ───────────────────────────────────────────────────

FIELDS = ["folder", "doc_name", "owner", "category", "scope",
          "status", "expected", "received", "missing"]


def load_checklist():
    rows = []
    with open(CHECKLIST_PATH, newline="") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def write_checklist(rows):
    with open(CHECKLIST_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def recompute_totals(rows):
    """Recalculate every SUBFOLDER TOTAL row from the doc rows above it."""
    out = []
    batch = []
    for row in rows:
        if row["doc_name"] == "--- SUBFOLDER TOTAL ---":
            expected = len(batch)
            received = sum(1 for r in batch if r["status"] == "received")
            row["expected"] = str(expected)
            row["received"] = str(received)
            row["missing"] = str(expected - received)
            out.append(row)
            batch = []
        else:
            batch.append(row)
            out.append(row)
    return out


# ── Classification via claude -p ────────────────────────────────────

def build_prompt(files_info, manifest_docs):
    # Compact manifest: one line per expected doc
    manifest_lines = []
    for d in manifest_docs:
        manifest_lines.append(
            f"  {d['doc_name']}  |  owner: {d['owner']}  |  "
            f"category: {d['category']}"
        )

    file_blocks = []
    for i, (name, text) in enumerate(files_info, 1):
        snippet = text[:1500] if text else "(no text extracted)"
        file_blocks.append(f"FILE {i}: {name}\nTEXT:\n{snippet}\n---")

    return f"""\
You are a document classifier for a legal closing data room.
Classify each file below against the manifest of expected documents.

EXPECTED DOCUMENTS (doc_name | owner | category):
{chr(10).join(manifest_lines)}

FILES TO CLASSIFY:
{chr(10).join(file_blocks)}

Return a JSON array with one object per file.  Fields:
  "filename"       – the original filename exactly as shown above
  "classification" – "MATCH" | "DRAFT" | "NEEDS_REVIEW"
  "doc_name"       – exact doc_name from the manifest (MATCH), or the
                     loan-doc type it is a draft of (DRAFT), or null
  "owner"          – exact owner string from the manifest (MATCH only),
                     or null

Rules:
• MATCH  – content clearly matches one manifest entry.  doc_name and
  owner must be copied character-for-character from the manifest.
• DRAFT  – file is a draft / redline / markup of a loan document.
  Set doc_name to the loan-doc type (e.g. "Loan Agreement"). owner = null.
• NEEDS_REVIEW – file does not match any expected document or is
  irrelevant.  doc_name = null, owner = null.

Return ONLY the JSON array.  No markdown fences, no explanation."""


def call_claude(prompt):
    r = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True, text=True, timeout=180,
    )
    if r.returncode != 0:
        print(f"claude -p failed (exit {r.returncode}):", file=sys.stderr)
        print(r.stderr, file=sys.stderr)
        sys.exit(1)
    return r.stdout.strip()


def parse_response(raw):
    text = raw.strip()
    # Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    start, end = text.find("["), text.rfind("]") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    return json.loads(text)


# ── File routing helpers ────────────────────────────────────────────

def find_folder(checklist, doc_name, owner):
    """Return the checklist folder path for a matched doc."""
    for row in checklist:
        if (row["doc_name"] == doc_name and row["owner"] == owner
                and row["doc_name"] != "--- SUBFOLDER TOTAL ---"):
            return row["folder"]
    return None


def find_drafts_folder(checklist, doc_name):
    """Derive the Drafts path from the Executed path for the same doc.

    Checklist paths use "N.2 Executed"; the matching Drafts folder is
    "N.1 Drafts".  A simple .replace("Executed","Drafts") would produce
    "N.2 Drafts" which is wrong.
    """
    for row in checklist:
        if (row["doc_name"] == doc_name
                and "Executed" in row.get("folder", "")
                and row["doc_name"] != "--- SUBFOLDER TOTAL ---"):
            return re.sub(r'(\d+)\.2 Executed', r'\1.1 Drafts',
                          row["folder"])
    return None


def std_filename(doc_name, owner, ext):
    name = doc_name if owner == "deal" else f"{doc_name} - {owner}"
    # Filesystem-safe
    return name.replace("/", "-").replace("\\", "-").replace(":", "-") + ext


# ── Main ────────────────────────────────────────────────────────────

def unzip_to_temp(zip_path):
    """Extract a .zip to a temp directory, returning the path.

    Nested directories inside the zip are flattened — only the leaf
    files are kept (with their basenames) so the sorter sees a flat
    list identical to a normal inbox folder.  Dotfiles and __MACOSX
    artifacts are skipped.
    """
    tmp = tempfile.mkdtemp(prefix="dataroom_inbox_")
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            basename = os.path.basename(member.filename)
            if not basename or basename.startswith("."):
                continue
            # Skip macOS resource forks
            if "__MACOSX" in member.filename:
                continue
            target = os.path.join(tmp, basename)
            # Handle duplicate basenames by appending a suffix
            if os.path.exists(target):
                name, ext = os.path.splitext(basename)
                i = 2
                while os.path.exists(target):
                    target = os.path.join(tmp, f"{name}_{i}{ext}")
                    i += 1
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    return tmp


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "inbox")
    tmp_dir = None

    # Handle .zip input
    if os.path.isfile(arg) and arg.lower().endswith(".zip"):
        print(f"Extracting {arg}...")
        tmp_dir = unzip_to_temp(arg)
        inbox = tmp_dir
        print(f"Extracted to temporary directory: {tmp_dir}")
    elif os.path.isdir(arg):
        inbox = arg
    else:
        print(f"Inbox not found: {arg}", file=sys.stderr)
        sys.exit(1)

    try:
        _sort_inbox(inbox)
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            print(f"\nCleaned up temp directory.")


def _sort_inbox(inbox):
    files = sorted(
        f for f in os.listdir(inbox)
        if os.path.isfile(os.path.join(inbox, f)) and not f.startswith(".")
    )
    if not files:
        print("No files in inbox.")
        return

    print(f"Found {len(files)} files in {inbox}/")

    # Extract text
    files_info = []
    for f in files:
        text = extract_text(os.path.join(inbox, f))
        files_info.append((f, text))
        print(f"  {f}  ({len(text)} chars)")

    manifest = json.load(open(MANIFEST_PATH))
    checklist = load_checklist()

    # Single classification call
    prompt = build_prompt(files_info, manifest["docs"])
    print(f"\nClassifying {len(files)} files in one claude -p call...")
    raw = call_claude(prompt)

    try:
        classifications = parse_response(raw)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        print(raw[:3000], file=sys.stderr)
        sys.exit(1)

    class_map = {c["filename"]: c for c in classifications}

    # Process each file
    needs_review_dir = os.path.join(DATAROOM, "NEEDS_REVIEW")
    summary = []

    for filename in files:
        src = os.path.join(inbox, filename)
        ext = os.path.splitext(filename)[1]
        c = class_map.get(filename, {})
        kind = c.get("classification", "NEEDS_REVIEW")
        doc_name = c.get("doc_name")
        owner = c.get("owner")

        if kind == "MATCH" and doc_name and owner:
            folder = find_folder(checklist, doc_name, owner)
            if folder:
                dest_dir = os.path.join(DATAROOM, folder)
                dest = os.path.join(dest_dir, std_filename(doc_name, owner, ext))
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(src, dest)
                # Tick checklist
                for row in checklist:
                    if (row["doc_name"] == doc_name and row["owner"] == owner
                            and row["doc_name"] != "--- SUBFOLDER TOTAL ---"):
                        row["status"] = "received"
                        break
                summary.append((filename, f"{doc_name} — {owner}", folder))
            else:
                os.makedirs(needs_review_dir, exist_ok=True)
                shutil.move(src, os.path.join(needs_review_dir, filename))
                summary.append((filename, f"NO FOLDER: {doc_name} / {owner}", "NEEDS_REVIEW/"))

        elif kind == "DRAFT" and doc_name:
            folder = find_drafts_folder(checklist, doc_name)
            if folder:
                dest_dir = os.path.join(DATAROOM, folder)
                dest = os.path.join(dest_dir, std_filename(doc_name, "DRAFT", ext))
                os.makedirs(dest_dir, exist_ok=True)
                shutil.move(src, dest)
                summary.append((filename, f"DRAFT: {doc_name}", folder))
            else:
                os.makedirs(needs_review_dir, exist_ok=True)
                shutil.move(src, os.path.join(needs_review_dir, filename))
                summary.append((filename, f"DRAFT NO FOLDER: {doc_name}", "NEEDS_REVIEW/"))

        else:  # NEEDS_REVIEW
            os.makedirs(needs_review_dir, exist_ok=True)
            shutil.move(src, os.path.join(needs_review_dir, filename))
            summary.append((filename, "NEEDS_REVIEW", "NEEDS_REVIEW/"))

    # Recompute totals and write checklist
    checklist = recompute_totals(checklist)
    write_checklist(checklist)

    # Print summary table
    matched = sum(1 for _, _, d in summary if "NEEDS_REVIEW" not in d and "Drafts" not in d)
    drafts = sum(1 for _, _, d in summary if "Drafts" in d)
    review = sum(1 for _, _, d in summary if "NEEDS_REVIEW" in d)

    print(f"\n{'#':<4} {'Original Filename':<50} {'Identified As':<60} Destination")
    print("=" * 170)
    for i, (orig, identity, dest) in enumerate(summary, 1):
        print(f"{i:<4} {orig:<50} {identity:<60} {dest}")
    print("=" * 170)
    print(f"Filed: {matched}  |  Drafts: {drafts}  |  Needs Review: {review}  |  Total: {len(summary)}")


if __name__ == "__main__":
    main()
