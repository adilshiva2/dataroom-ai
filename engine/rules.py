#!/usr/bin/env python3
"""T2 — Rules engine.

Reads output/deal_profile.json and the matching rules file from rules/,
expands scoped document lists into a flat manifest of every expected
document, applies the sponsor_backed overlay if applicable, dedupes
by (doc_name, owner), and writes output/manifest.json.

Unknown deal types get a minimal best-guess skeleton with an
UNKNOWN_DEAL_TYPE flag.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(ROOT, "rules")
OUTPUT_DIR = os.path.join(ROOT, "output")

FALLBACK_CATEGORIES = [
    {
        "name": "General Documents",
        "scope": "per_deal",
        "docs": [
            {"name": "Loan Agreement", "subfolder": "Loan Agreement"},
            {"name": "Closing Certificate", "subfolder": "Closing Certificate"},
            {"name": "Legal Opinion", "subfolder": "Legal Opinion"},
        ],
    },
    {
        "name": "Organizational & KYC Documents",
        "scope": "per_entity",
        "docs": [
            {"name": "Formation Certificate", "subfolder": "Formation Certificates"},
            {"name": "Good Standing Certificate", "subfolder": "Good Standing Certificates"},
            {"name": "W-9", "subfolder": "W-9s"},
        ],
    },
]


def load_json(path):
    with open(path) as f:
        return json.load(f)


def load_profile():
    return load_json(os.path.join(OUTPUT_DIR, "deal_profile.json"))


def load_rules(deal_type):
    path = os.path.join(RULES_DIR, f"{deal_type}.json")
    if os.path.exists(path):
        return load_json(path), False
    return {"deal_type": deal_type, "categories": FALLBACK_CATEGORIES}, True


def load_overlay(name):
    path = os.path.join(RULES_DIR, f"{name}.json")
    if os.path.exists(path):
        return load_json(path)
    return None


def entities_from_profile(profile):
    """Return list of all entities (borrower + guarantors)."""
    entities = [profile["borrower"]]
    entities.extend(profile.get("guarantors", []))
    return entities


def parse_doc(doc_entry):
    """Handle both string and object doc formats."""
    if isinstance(doc_entry, str):
        return doc_entry, doc_entry
    return doc_entry["name"], doc_entry["subfolder"]


def expand_categories(categories, profile):
    """Expand scoped categories into flat doc entries."""
    entries = []
    entities = entities_from_profile(profile)
    guarantors = profile.get("guarantors", [])
    assets = profile.get("assets", [])

    for cat in categories:
        scope = cat["scope"]
        drafts_and_executed = cat.get("drafts_and_executed", False)

        for doc_entry in cat["docs"]:
            doc_name, subfolder = parse_doc(doc_entry)

            def make_entry(owner):
                entry = {
                    "doc_name": doc_name,
                    "category": cat["name"],
                    "subfolder": subfolder,
                    "scope": scope,
                    "owner": owner,
                    "status": "missing",
                }
                if drafts_and_executed:
                    entry["drafts_and_executed"] = True
                return entry

            if scope == "per_entity":
                for entity in entities:
                    entries.append(make_entry(entity["name"]))
            elif scope == "per_asset":
                for asset in assets:
                    entries.append(make_entry(asset["name"]))
            elif scope == "per_guarantor":
                for g in guarantors:
                    entries.append(make_entry(g["name"]))
            elif scope == "per_deal":
                entries.append(make_entry("deal"))

    return entries


def evaluate_conditionals(rules, profile):
    """Return extra categories from conditional blocks whose conditions match."""
    extra = []
    for cond_block in rules.get("conditional", []):
        condition = cond_block["condition"]
        if "facility_feature" in condition:
            required = condition["facility_feature"]
            if required in profile.get("facility_features", []):
                extra.extend(cond_block["categories"])
    return extra


def dedupe(entries):
    """Remove duplicates by (doc_name, owner)."""
    seen = set()
    result = []
    for entry in entries:
        key = (entry["doc_name"], entry["owner"])
        if key not in seen:
            seen.add(key)
            result.append(entry)
    return result


def build_manifest(profile):
    deal_type = profile["deal_type"]
    rules, unknown = load_rules(deal_type)

    categories = list(rules["categories"])
    categories.extend(evaluate_conditionals(rules, profile))

    entries = expand_categories(categories, profile)

    # Apply sponsor_backed overlay
    if profile.get("sponsor_backed"):
        overlay = load_overlay("sponsor_backed")
        if overlay:
            entries.extend(expand_categories(overlay["categories"], profile))

    entries = dedupe(entries)

    manifest = {
        "deal_type": deal_type,
        "total_expected": len(entries),
        "docs": entries,
    }
    if unknown:
        manifest["flags"] = ["UNKNOWN_DEAL_TYPE"]

    return manifest


def summarize(manifest):
    """Print per-category counts."""
    counts = {}
    for doc in manifest["docs"]:
        cat = doc["category"]
        counts[cat] = counts.get(cat, 0) + 1

    print(f"\nDeal type: {manifest['deal_type']}")
    if "flags" in manifest:
        print(f"Flags: {manifest['flags']}")
    print(f"{'Category':<35} Count")
    print("-" * 45)
    for cat, count in counts.items():
        print(f"{cat:<35} {count}")
    print("-" * 45)
    print(f"{'TOTAL':<35} {manifest['total_expected']}")


def main():
    profile = load_profile()
    manifest = build_manifest(profile)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "manifest.json")
    with open(out_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"Wrote {out_path}")

    summarize(manifest)


if __name__ == "__main__":
    main()
