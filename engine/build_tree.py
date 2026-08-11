#!/usr/bin/env python3
"""T3 — Folder tree + checklist.

Reads output/manifest.json, creates a numbered folder tree under
output/dataroom/, and writes output/dataroom/checklist.csv with every
expected document and per-folder expected/received/missing counts.

Per-entity, per-asset, and per-guarantor categories get numbered
subfolders per owner (e.g. "2.1 Oakline Commons").  Per-deal categories
are flat.
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
    """Return an ordered list of folder entries from the manifest docs.

    Each entry: {
        "category": str,
        "cat_num": int,          # 1-based
        "cat_folder": str,       # e.g. "1 Entity - KYC"
        "owner": str or None,    # None for per_deal
        "owner_num": str or None,# e.g. "1.2"
        "owner_folder": str or None,
        "folder_path": str,      # relative path under dataroom/
        "docs": [doc_entries],
    }
    """
    # Discover categories in manifest order, preserving first-seen ordering
    cat_order = []
    cat_seen = set()
    for doc in docs:
        cat = doc["category"]
        if cat not in cat_seen:
            cat_seen.add(cat)
            cat_order.append(cat)

    # Group docs by (category, owner)
    groups = {}
    for doc in docs:
        key = (doc["category"], doc["owner"])
        groups.setdefault(key, []).append(doc)

    # For each category, discover unique owners in manifest order
    cat_owners = {}
    for doc in docs:
        cat = doc["category"]
        owner = doc["owner"]
        cat_owners.setdefault(cat, [])
        if owner not in cat_owners[cat]:
            cat_owners[cat].append(owner)

    folders = []
    for cat_idx, cat in enumerate(cat_order, 1):
        cat_folder_name = sanitize(f"{cat_idx} {cat}")
        owners = cat_owners[cat]
        scoped = len(owners) > 1 or (len(owners) == 1 and owners[0] != "deal")

        if scoped:
            for owner_idx, owner in enumerate(owners, 1):
                owner_folder_name = sanitize(f"{cat_idx}.{owner_idx} {owner}")
                folder_path = os.path.join(cat_folder_name, owner_folder_name)
                folders.append({
                    "category": cat,
                    "cat_folder": cat_folder_name,
                    "owner": owner,
                    "folder_path": folder_path,
                    "docs": groups[(cat, owner)],
                })
        else:
            folder_path = cat_folder_name
            folders.append({
                "category": cat,
                "cat_folder": cat_folder_name,
                "owner": "deal",
                "folder_path": folder_path,
                "docs": groups[(cat, owners[0])],
            })

    return folders


def create_tree(folders):
    """Create the folder tree on disk."""
    if os.path.exists(DATAROOM):
        shutil.rmtree(DATAROOM)
    os.makedirs(DATAROOM)

    for folder in folders:
        os.makedirs(os.path.join(DATAROOM, folder["folder_path"]), exist_ok=True)


def write_checklist(folders):
    """Write checklist.csv with doc rows and per-folder summary rows."""
    csv_path = os.path.join(DATAROOM, "checklist.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "folder", "doc_name", "owner", "category", "scope",
            "status", "expected", "received", "missing",
        ])

        for folder in folders:
            docs = folder["docs"]
            expected = len(docs)
            received = sum(1 for d in docs if d["status"] == "received")
            missing = expected - received

            for doc in docs:
                writer.writerow([
                    folder["folder_path"],
                    doc["doc_name"],
                    doc["owner"],
                    doc["category"],
                    doc["scope"],
                    doc["status"],
                    "", "", "",
                ])

            # Summary row for this folder
            writer.writerow([
                folder["folder_path"],
                "--- FOLDER TOTAL ---",
                "", "", "", "",
                expected, received, missing,
            ])

    return csv_path


def print_tree(folders):
    """Print the folder tree."""
    print("\noutput/dataroom/")
    prev_cat = None
    for folder in folders:
        cat_folder = folder["cat_folder"]
        if cat_folder != prev_cat:
            print(f"├── {cat_folder}/")
            prev_cat = cat_folder

        if folder["owner"] != "deal" or cat_folder != folder["folder_path"]:
            parts = folder["folder_path"].split(os.sep)
            if len(parts) > 1:
                is_last_in_cat = (
                    folder == folders[-1]
                    or folders[folders.index(folder) + 1]["cat_folder"] != cat_folder
                )
                connector = "└" if is_last_in_cat else "├"
                print(f"│   {connector}── {parts[1]}/")


def main():
    manifest = load_manifest()
    folders = build_folder_plan(manifest["docs"])
    create_tree(folders)
    csv_path = write_checklist(folders)

    print(f"Created {len(folders)} folders under output/dataroom/")
    print(f"Wrote {csv_path}")
    print_tree(folders)

    # Print total counts
    total_docs = sum(len(f["docs"]) for f in folders)
    print(f"\nChecklist: {total_docs} expected docs, all missing")


if __name__ == "__main__":
    main()
