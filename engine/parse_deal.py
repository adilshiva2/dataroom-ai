#!/usr/bin/env python3
"""T0c — Deal profile extractor.

Reads a PDF term sheet, extracts its text, and shells out to Claude Code
headless mode (claude -p) to produce a deal_profile.json matching the
schema in CLAUDE.md.

Usage:
    python engine/parse_deal.py intake/term_sheet_meridian.pdf

Output:
    output/deal_profile.json

NO direct Anthropic API calls — uses claude -p per project policy.
"""

import json
import os
import subprocess
import sys

from pypdf import PdfReader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(ROOT, "output")

PROMPT_TEMPLATE = """\
You are a deal document parser. Read the term sheet text below and extract a JSON object matching this exact schema. Return ONLY valid JSON, no markdown fences, no prose, no explanation.

Schema:
{{
  "deal_type": "secured_term_loan" | "unsecured_term_loan" | "revolver" | "<other>",
  "loan_amount": <number>,
  "borrower": {{
    "name": "<legal name>",
    "entity_type": "LLC" | "LP" | "Corp" | "<other>",
    "jurisdiction": "<two-letter state code>"
  }},
  "guarantors": [
    {{
      "name": "<legal name>",
      "entity_type": "LLC" | "LP" | "Corp" | "<other>",
      "jurisdiction": "<two-letter state code>"
    }}
  ],
  "assets": [
    {{
      "name": "<property name>",
      "type": "multifamily" | "office" | "retail" | "industrial" | "<other>",
      "location": "<City, ST>"
    }}
  ],
  "lender": "<legal name>",
  "governing_law": "<state name>",
  "facility_features": ["term" | "revolver" | "LC sublimit" | "asset_based" | ...],
  "sponsor_backed": true | false
}}

Classification rules:
- deal_type: "secured_term_loan" if there is real estate collateral / mortgages / deeds of trust and the facility is a term loan. "unsecured_term_loan" if term loan with no collateral. "revolver" if revolving credit facility.
- sponsor_backed: true if the borrower is a subsidiary of a fund, or if a fund/GP entity appears as guarantor or parent, indicating a sponsor/fund structure.
- facility_features: include "term" for term loans, "revolver" for revolving, "LC sublimit" if letter of credit sublimit exists, "asset_based" if asset-based lending.
- For guarantors, infer jurisdiction from context (e.g., "Delaware limited partnership" → "DE").
- assets may be empty for unsecured deals.

Term sheet text:
---
{text}
---

Return ONLY the JSON object."""


def extract_text(pdf_path):
    """Extract all text from a PDF."""
    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def call_claude(prompt):
    """Shell out to claude -p headless mode."""
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        print(f"claude -p failed (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def clean_json(raw):
    """Strip markdown fences or surrounding text if present."""
    text = raw.strip()
    # Remove markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first line (```json) and last line (```)
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    # Find the JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    return text


def main():
    if len(sys.argv) < 2:
        print("Usage: python engine/parse_deal.py <pdf_path>", file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting text from {pdf_path}...")
    text = extract_text(pdf_path)
    if not text.strip():
        print("No text extracted from PDF.", file=sys.stderr)
        sys.exit(1)
    print(f"Extracted {len(text)} chars from {len(PdfReader(pdf_path).pages)} pages.")

    prompt = PROMPT_TEMPLATE.format(text=text)
    print("Calling claude -p for extraction...")
    raw = call_claude(prompt)

    cleaned = clean_json(raw)
    # Validate JSON
    try:
        profile = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON from claude output: {e}", file=sys.stderr)
        print("Raw output:", file=sys.stderr)
        print(raw, file=sys.stderr)
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "deal_profile.json")
    with open(out_path, "w") as f:
        json.dump(profile, f, indent=2)
        f.write("\n")
    print(f"Wrote {out_path}")

    # Print summary
    print(f"\n  deal_type:       {profile.get('deal_type')}")
    print(f"  loan_amount:     ${profile.get('loan_amount', 0):,.0f}")
    print(f"  borrower:        {profile.get('borrower', {}).get('name')}")
    print(f"  guarantors:      {len(profile.get('guarantors', []))}")
    print(f"  assets:          {len(profile.get('assets', []))}")
    print(f"  lender:          {profile.get('lender')}")
    print(f"  sponsor_backed:  {profile.get('sponsor_backed')}")


if __name__ == "__main__":
    main()
