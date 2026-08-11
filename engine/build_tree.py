#!/usr/bin/env python3
"""T3 — Folder tree + checklist.

Reads output/manifest.json, creates a numbered folder tree under
output/dataroom/, and writes output/dataroom/checklist.csv with every
expected document and per-subfolder expected/received/missing counts.

Subfolders are by DOCUMENT TYPE (not by owner).  Files inside are
named "{Doc Name} - {Owner}.pdf" for scoped docs, or "{Doc Name}.pdf"
for per-deal docs.

Principal Loan Documents get a special "Drafts / Executed" split:
  N.1 Drafts/   — untracked working folder (no checklist entries)
  N.2 Executed/  — tracked; checklist entries point here
Both contain identical doc-type subfolders.
"""

import csv
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT, "output")
DATAROOM = os.path.join(OUTPUT_DIR, "dataroom")


def load_manifest():
    with open(os.path.join(OUTPUT_DIR, "manifest.json")) as f:
        return json.load(f)


def sanitize(name):
    """Make a name filesystem-safe."""
    return name.replace("/", "-").replace("\\", "-").replace(":", "-")


def build_folder_plan(docs):
    """Build the folder structure from manifest docs.

    Returns (folders, checklist_rows) where:
      folders   = set of directory paths to create (relative to dataroom/)
      checklist_rows = list of dicts with folder, doc_name, owner, etc.
    """
    # Discover categories in manifest order
    cat_order = []
    cat_seen = set()
    for doc in docs:
        cat = doc["category"]
        if cat not in cat_seen:
            cat_seen.add(cat)
            cat_order.append(cat)

    # For each category, discover unique subfolders in manifest order
    cat_subfolders = {}
    for doc in docs:
        cat = doc["category"]
        sf = doc["subfolder"]
        cat_subfolders.setdefault(cat, [])
        if sf not in cat_subfolders[cat]:
            cat_subfolders[cat].append(sf)

    # Check which categories use drafts_and_executed
    cat_drafts = {}
    for doc in docs:
        if doc.get("drafts_and_executed"):
            cat_drafts[doc["category"]] = True

    dirs_to_create = set()
    checklist_rows = []

    for cat_idx, cat in enumerate(cat_order, 1):
        cat_folder = sanitize(f"{cat_idx} {cat}")
        dirs_to_create.add(cat_folder)
        subfolders = cat_subfolders[cat]
        is_drafts = cat_drafts.get(cat, False)

        if is_drafts:
            # Special: Drafts + Executed split
            drafts_folder = os.path.join(cat_folder, f"{cat_idx}.1 Drafts")
            executed_folder = os.path.join(cat_folder, f"{cat_idx}.2 Executed")
            dirs_to_create.add(drafts_folder)
            dirs_to_create.add(executed_folder)

            for sf in subfolders:
                sf_safe = sanitize(sf)
                dirs_to_create.add(os.path.join(drafts_folder, sf_safe))
                dirs_to_create.add(os.path.join(executed_folder, sf_safe))

            # Checklist entries point to Executed only
            for doc in docs:
                if doc["category"] != cat:
                    continue
                sf_safe = sanitize(doc["subfolder"])
                folder_path = os.path.join(executed_folder, sf_safe)
                checklist_rows.append({
                    "folder": folder_path,
                    "doc_name": doc["doc_name"],
                    "owner": doc["owner"],
                    "category": doc["category"],
                    "subfolder": doc["subfolder"],
                    "scope": doc["scope"],
                    "status": doc["status"],
                })
        else:
            # Standard: numbered doc-type subfolders
            for sf_idx, sf in enumerate(subfolders, 1):
                sf_safe = sanitize(f"{cat_idx}.{sf_idx} {sf}")
                sf_path = os.path.join(cat_folder, sf_safe)
                dirs_to_create.add(sf_path)

                for doc in docs:
                    if doc["category"] != cat or doc["subfolder"] != sf:
                        continue
                    checklist_rows.append({
                        "folder": sf_path,
                        "doc_name": doc["doc_name"],
                        "owner": doc["owner"],
                        "category": doc["category"],
                        "subfolder": doc["subfolder"],
                        "scope": doc["scope"],
                        "status": doc["status"],
                    })

    return dirs_to_create, checklist_rows


def create_tree(dirs_to_create):
    """Create the folder tree on disk."""
    if os.path.exists(DATAROOM):
        shutil.rmtree(DATAROOM)
    os.makedirs(DATAROOM)

    for d in sorted(dirs_to_create):
        os.makedirs(os.path.join(DATAROOM, d), exist_ok=True)


def write_checklist(checklist_rows):
    """Write checklist.csv with doc rows and per-subfolder summary rows."""
    csv_path = os.path.join(DATAROOM, "checklist.csv")

    # Group rows by folder for summary totals
    folder_groups = []
    current_folder = None
    current_batch = []
    for row in checklist_rows:
        if row["folder"] != current_folder:
            if current_batch:
                folder_groups.append((current_folder, current_batch))
            current_folder = row["folder"]
            current_batch = [row]
        else:
            current_batch.append(row)
    if current_batch:
        folder_groups.append((current_folder, current_batch))

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "folder", "doc_name", "owner", "category", "scope",
            "status", "expected", "received", "missing",
        ])

        for folder, rows in folder_groups:
            expected = len(rows)
            received = sum(1 for r in rows if r["status"] == "received")
            missing = expected - received

            for row in rows:
                writer.writerow([
                    row["folder"], row["doc_name"], row["owner"],
                    row["category"], row["scope"], row["status"],
                    "", "", "",
                ])

            writer.writerow([
                folder, "--- SUBFOLDER TOTAL ---",
                "", "", "", "",
                expected, received, missing,
            ])

    return csv_path


def print_tree():
    """Print the tree from the filesystem."""
    print("\noutput/dataroom/")
    all_dirs = []
    for dirpath, dirnames, _ in os.walk(DATAROOM):
        dirnames.sort()
        rel = os.path.relpath(dirpath, DATAROOM)
        if rel == ".":
            continue
        all_dirs.append(rel)

    for i, d in enumerate(sorted(all_dirs)):
        depth = d.count(os.sep)
        name = os.path.basename(d)
        indent = "│   " * depth
        is_last = (
            i == len(all_dirs) - 1
            or not sorted(all_dirs)[i + 1].startswith(d.rsplit(os.sep, 1)[0] + os.sep)
            if depth > 0 and i < len(all_dirs) - 1
            else i == len(all_dirs) - 1
        )
        connector = "└── " if is_last else "├── "
        print(f"{indent}{connector}{name}/")


def main():
    manifest = load_manifest()
    dirs_to_create, checklist_rows = build_folder_plan(manifest["docs"])
    create_tree(dirs_to_create)
    csv_path = write_checklist(checklist_rows)

    dir_count = len(dirs_to_create)
    doc_count = len(checklist_rows)
    print(f"Created {dir_count} directories under output/dataroom/")
    print(f"Wrote {csv_path}")
    print(f"Checklist: {doc_count} expected docs, all missing")
    print_tree()


if __name__ == "__main__":
    main()
