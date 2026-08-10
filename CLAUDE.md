# DealRoom — Project Brief

## What this is
A tool where an LLM reads initial deal information (term sheet / commitment letter / deal memo PDF), determines what kind of deal it is, and derives an organized, self-auditing closing data room from that. Input: a deal document. Output: a deal-type-appropriate folder structure with an expected-documents checklist, automatic filing of uploaded documents, missing-document alerts, and drafted chaser emails.

Thesis: lawyers repeat this organization work thousands of times across deal types. The LLM sets the standard from the document itself — the skeleton adapts to the deal, and the data becomes usable for clients, for drafting, and for knowing exactly who to chase.

## The core design principle
NOTHING about the deal is hardcoded. The extraction step (T0) produces `deal_profile.json` including `deal_type`, and the rules engine selects the matching taxonomy from a rules library. Adding a new deal type = adding one rules file, zero code changes.

## Deal types in the rules library (v1)
- **secured_term_loan** (real estate): per-entity KYC; per-asset third-party reports (appraisal, PCA, Phase I, zoning/PZR, title commitment, survey); per-deal loan docs (loan agreement, note, guaranty, assignment of leases and rents, closing cert) plus per-asset mortgage/deed of trust and UCC-1; underwriting (per-asset rent roll + operating statement, per-guarantor financials)
- **unsecured_term_loan**: per-entity KYC; NO collateral/asset sections; loan docs (loan agreement, note, guaranty, closing cert); heavier financial diligence (borrower financial statements, compliance certificates, projections)
- **revolver**: as unsecured plus borrowing base certificate, and if asset-based: field exam report, collateral schedules, UCC-1s
Deal types outside the library → build a best-guess skeleton and flag UNKNOWN_DEAL_TYPE for review; never fail silently.

## Deal profile schema (what T0 must extract)
{deal_type, loan_amount, borrower {name, entity_type, jurisdiction}, guarantors [], assets [{name, type, location}] (may be empty), lender, governing_law, facility_features [] (e.g. revolver, term, LC sublimit)}

## Pipeline (build in this order)
0. `parse_deal.py` — PDF → deal_profile.json via Claude API (strict JSON out, no prose)
1. `rules/` library — one JSON/YAML per deal type defining expected docs by scope (per-entity / per-asset / per-deal)
2. `rules.py` — profile + rules library → manifest of every expected document, counts COMPUTED from the profile
3. `build_tree.py` — manifest → numbered local folder tree + checklist.csv (expected/received/missing)
4. `sort_inbox.py` — files or zip dropped in `inbox/` get classified (filename + first-page text via Claude API) against the manifest, moved into place, checklist updated; unclassifiable → NEEDS_REVIEW, never guess silently
5. `report.py` — missing-doc report grouped by responsible party + one draft chaser email per party
6. Google Drive mirror (Drive API) — only after local works end to end

## Working rules
- One task at a time from TASKS.md, each with a done-condition. Verify, then commit before the next.
- Small plain Python scripts, standard library where possible. No frameworks, no database, no web server.
- Test inputs are FAKE term sheets and stub documents generated for this project. Never real deal documents.
- `credentials.json`, `token.json`, `secrets/` are gitignored. API key from env var `ANTHROPIC_API_KEY`.
- If a step is ambiguous, ask before building — do not invent scope.
