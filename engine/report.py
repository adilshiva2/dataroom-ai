#!/usr/bin/env python3
"""T6 — Missing-document report + draft chaser emails.

Reads checklist.csv and deal_profile.json, produces:
  1. A printed missing-documents report grouped by responsible party.
  2. One draft chaser email per party written to output/emails/.

Routing rules (who gets chased for what):
  - Borrower's counsel: Organizational & KYC Documents,
    Sponsor & Fund Documents, Guarantor Financials (Due Diligence 5.3),
    Rent Rolls and Financial Statements (Due Diligence 5.1, 5.2)
  - Third-party / broker: Third-Party Reports
  - Internal (not chased): Principal Loan Documents (executed),
    Security & Collateral Documents (Mortgages, UCC-1s) — these are
    drafting items prepared by lender's counsel

No LLM calls — plain templating from checklist data.
"""

import csv
import json
import os
import sys
from collections import OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT, "output")
DATAROOM = os.path.join(OUTPUT_DIR, "dataroom")
CHECKLIST_PATH = os.path.join(DATAROOM, "checklist.csv")
DEAL_PROFILE_PATH = os.path.join(OUTPUT_DIR, "deal_profile.json")
EMAILS_DIR = os.path.join(OUTPUT_DIR, "emails")


# ── Responsible-party routing ────────────────────────────────────────

BORROWER_COUNSEL = "Borrower's Counsel"
THIRD_PARTY = "Third-Party / Broker"
INTERNAL = "Internal (Drafting)"


def route_party(row):
    """Determine the responsible party for a missing doc."""
    cat = row["category"]

    if cat == "Organizational & KYC Documents":
        return BORROWER_COUNSEL
    if cat == "Sponsor & Fund Documents":
        return BORROWER_COUNSEL
    if cat == "Due Diligence":
        return BORROWER_COUNSEL
    if cat == "Third-Party Reports":
        return THIRD_PARTY
    if cat == "Security & Collateral Documents":
        return INTERNAL
    if cat == "Principal Loan Documents":
        return INTERNAL
    return THIRD_PARTY


# ── Helpers ──────────────────────────────────────────────────────────

def load_checklist():
    rows = []
    with open(CHECKLIST_PATH, newline="") as f:
        for row in csv.DictReader(f):
            if row["doc_name"] != "--- SUBFOLDER TOTAL ---":
                rows.append(row)
    return rows


def load_deal_profile():
    with open(DEAL_PROFILE_PATH) as f:
        return json.load(f)


def format_amount(n):
    return f"${n:,.0f}"


def group_missing_items(missing_rows):
    """Group missing docs by (doc_name) and collect owners."""
    grouped = OrderedDict()
    for row in missing_rows:
        doc = row["doc_name"]
        owner = row["owner"]
        grouped.setdefault(doc, []).append(owner)
    return grouped


def describe_owners(owners, profile):
    """Turn a list of owners into a readable description."""
    asset_names = {a["name"] for a in profile.get("assets", [])}
    entity_names = {profile["borrower"]["name"]}
    for g in profile.get("guarantors", []):
        entity_names.add(g["name"])

    if len(owners) == 1 and owners[0] == "deal":
        return None  # per-deal doc, no owner qualifier needed
    if set(owners) == asset_names:
        return f"all {len(owners)} Properties"
    if set(owners) <= asset_names:
        return ", ".join(owners)
    if set(owners) <= entity_names:
        return ", ".join(owners)
    if owners == ["deal"]:
        return None
    return ", ".join(owners)


# ── Report printing ─────────────────────────────────────────────────

def print_report(parties, profile):
    deal_desc = (f"{profile['borrower']['name']} — "
                 f"{format_amount(profile['loan_amount'])} "
                 f"{profile.get('deal_type', '').replace('_', ' ').title()}")
    print(f"\n{'=' * 80}")
    print(f"MISSING DOCUMENTS REPORT")
    print(f"{deal_desc}")
    print(f"{'=' * 80}")

    for party, missing_rows in parties.items():
        grouped = group_missing_items(missing_rows)
        total = len(missing_rows)
        print(f"\n{'─' * 80}")
        print(f"  {party}  ({total} item{'s' if total != 1 else ''})")
        print(f"{'─' * 80}")

        # Sub-group by category for readability
        cat_groups = OrderedDict()
        for row in missing_rows:
            cat_groups.setdefault(row["category"], []).append(row)

        for cat, rows in cat_groups.items():
            print(f"\n  {cat}:")
            items = group_missing_items(rows)
            for doc_name, owners in items.items():
                desc = describe_owners(owners, profile)
                if desc:
                    print(f"    - {doc_name} — {desc}")
                else:
                    print(f"    - {doc_name}")

    print(f"\n{'=' * 80}\n")


# ── Email generation ────────────────────────────────────────────────

def generate_email(party, missing_rows, profile):
    """Generate a professional chaser email for a responsible party."""
    deal_desc = (f"{profile['borrower']['name']} "
                 f"{format_amount(profile['loan_amount'])} "
                 f"Senior Secured Term Loan Facility")
    lender = profile.get("lender", "Lender")

    # Group by category, then by doc
    cat_groups = OrderedDict()
    for row in missing_rows:
        cat_groups.setdefault(row["category"], []).append(row)

    lines = []

    if party == INTERNAL:
        lines.append(f"Subject: Outstanding Drafting Items — {deal_desc}")
        lines.append("")
        lines.append("Team,")
        lines.append("")
        lines.append(
            f"Below is the current list of outstanding loan documents and "
            f"security instruments for the {deal_desc}. Please coordinate "
            f"with outside counsel to finalize and circulate execution "
            f"copies."
        )
    elif party == BORROWER_COUNSEL:
        lines.append(
            f"Subject: Outstanding Closing Checklist Items — {deal_desc}"
        )
        lines.append("")
        lines.append("Counsel,")
        lines.append("")
        lines.append(
            f"We are writing in connection with the {deal_desc} (the "
            f"\"Facility\"). As we continue to work toward closing, the "
            f"following items remain outstanding on our closing checklist. "
            f"We would appreciate your assistance in coordinating delivery "
            f"of these documents at your earliest convenience."
        )
    else:  # THIRD_PARTY
        lines.append(
            f"Subject: Outstanding Due Diligence Items — {deal_desc}"
        )
        lines.append("")
        lines.append("Dear Sir or Madam,")
        lines.append("")
        lines.append(
            f"In connection with the {deal_desc} (the \"Facility\"), "
            f"the following third-party reports remain outstanding. "
            f"We would be grateful if you could arrange for delivery of "
            f"these items at your earliest convenience."
        )

    lines.append("")
    lines.append("Outstanding Items:")
    lines.append("")

    for cat, rows in cat_groups.items():
        lines.append(f"  {cat}:")
        items = group_missing_items(rows)
        for doc_name, owners in items.items():
            desc = describe_owners(owners, profile)
            if desc:
                lines.append(f"    - {doc_name} — {desc}")
            else:
                lines.append(f"    - {doc_name}")
        lines.append("")

    if party == INTERNAL:
        lines.append(
            "Please update the data room as execution copies become available."
        )
    else:
        lines.append(
            "Please do not hesitate to reach out if you have any questions "
            "or if any of the above items require further clarification."
        )

    lines.append("")
    lines.append("Best regards,")
    lines.append(f"Closing Team — {lender}")
    lines.append("")

    return "\n".join(lines)


def safe_filename(party):
    return (party.lower()
            .replace("'", "")
            .replace("/", "_")
            .replace(" ", "_")
            .replace("(", "").replace(")", ""))


# ── Main ─────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(CHECKLIST_PATH):
        print(f"Checklist not found: {CHECKLIST_PATH}", file=sys.stderr)
        sys.exit(1)

    checklist = load_checklist()
    profile = load_deal_profile()

    missing = [r for r in checklist if r["status"] == "missing"]
    received = [r for r in checklist if r["status"] == "received"]

    if not missing:
        print("All documents received. Nothing to report.")
        return

    # Route missing docs to parties
    parties = OrderedDict()
    for row in missing:
        party = route_party(row)
        parties.setdefault(party, []).append(row)

    # Print report
    print_report(parties, profile)

    # Summary counts
    print(f"Summary: {len(received)} received, {len(missing)} missing "
          f"out of {len(checklist)} expected")
    print(f"Responsible parties: {len(parties)}")
    for party, rows in parties.items():
        print(f"  {party}: {len(rows)} items")

    # Generate emails
    os.makedirs(EMAILS_DIR, exist_ok=True)
    for party, rows in parties.items():
        email = generate_email(party, rows, profile)
        fname = f"chaser_{safe_filename(party)}.txt"
        path = os.path.join(EMAILS_DIR, fname)
        with open(path, "w") as f:
            f.write(email)
        print(f"\nWrote {path}")

    # Print one full email as sample
    first_party = next(iter(parties))
    first_path = os.path.join(
        EMAILS_DIR, f"chaser_{safe_filename(first_party)}.txt"
    )
    print(f"\n{'─' * 80}")
    print(f"SAMPLE EMAIL: {first_party}")
    print(f"{'─' * 80}")
    with open(first_path) as f:
        print(f.read())


if __name__ == "__main__":
    main()
