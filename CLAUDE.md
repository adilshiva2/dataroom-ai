# DealRoom — Project Brief

## What this is
A tool where an LLM reads initial deal information (term sheet / commitment letter / deal memo PDF), determines what kind of deal it is, and derives an organized, self-auditing closing data room from that. Input: a deal document. Output: a deal-type-appropriate folder structure with an expected-documents checklist, automatic filing of uploaded documents, missing-document alerts, and drafted chaser emails.

Thesis: lawyers repeat this organization work thousands of times across deal types. The LLM sets the standard from the document itself — the skeleton adapts to the deal, and the data becomes usable for clients, for drafting, and for knowing exactly who to chase.

## The core design principle
NOTHING about the deal is hardcoded. The extraction step (T0) produces `deal_profile.json` including `deal_type`, and the rules engine selects the matching taxonomy from a rules library. Adding a new deal type = adding one rules file, zero code changes.

## Data room taxonomy
Subfolders are by DOCUMENT TYPE, not by owner. Every doc type in each category gets a numbered subfolder; files inside are named by owner (e.g. `Formation Certificate - Meridian Multifamily Holdings LLC.pdf`).

### Category structure (closing-checklist language)
1. **Organizational & KYC Documents** — per-entity: 1.1 Formation Certificates, 1.2 Operating Agreements / LPAs, 1.3 Good Standing Certificates, 1.4 W-9s, 1.5 Beneficial Ownership Certifications
2. **Third-Party Reports** — per-asset: 2.1 Appraisals, 2.2 Property Condition Assessments, 2.3 Phase I Environmental, 2.4 Zoning Reports, 2.5 Title Commitments, 2.6 Surveys, 2.7 Insurance Certificates
3. **Security & Collateral Documents** — per-asset: 3.1 Mortgages / Deeds of Trust, 3.2 UCC-1 Financing Statements
4. **Principal Loan Documents** — per-deal, with a Drafts/Executed split: 4.1 Drafts and 4.2 Executed each contain the same doc-type folders (Loan Agreement, Promissory Note, Guaranty, Assignment of Leases and Rents, Interest Rate Cap Agreement, Closing Certificate, Legal Opinion). The checklist tracks ONLY the Executed set — Drafts is an untracked working folder. The T5 sorter must route docs titled as drafts/redlines to Drafts and file them WITHOUT ticking the checklist.
5. **Due Diligence** — 5.1 Rent Rolls (per-asset), 5.2 Financial Statements / property operating statements (per-asset), 5.3 Guarantor Financials (per-guarantor)
6. **Sponsor & Fund Documents** — per-deal (overlay when `sponsor_backed: true`): Fund LPA, GP Formation Documents, Sponsor Guaranty, Structure / Org Chart

### Deal types in the rules library (v1)
- **secured_term_loan** (real estate): all 6 categories above.
- **unsecured_term_loan**: NO collateral or per-asset sections (categories 2, 3 omitted); Organizational & KYC; Principal Loan Documents (credit agreement, notes, subsidiary guaranties, closing cert, legal opinion, solvency certificate, officer's certificate, board resolutions); Due Diligence (audited financials, projections, compliance certificate).
- **revolver**: same base as unsecured plus borrowing base certificate, fee letters, deposit account control agreements, LC documentation; if the profile has facility_feature "asset_based", add Security & Collateral (field exam report, collateral schedules, UCC-1s).
- **sponsor_backed** (cross-cutting overlay): when `sponsor_backed: true` in the deal profile, ANY deal type appends category 6 (Sponsor & Fund Documents).
Deal types outside the library → build a best-guess skeleton and flag UNKNOWN_DEAL_TYPE for review; never fail silently.

## Deal profile schema (what T0 must extract)
{deal_type, loan_amount, borrower {name, entity_type, jurisdiction}, guarantors [], assets [{name, type, location}] (may be empty), lender, governing_law, facility_features [] (e.g. revolver, term, LC sublimit, asset_based), sponsor_backed (boolean)}

## Pipeline (build in this order)
0. `parse_deal.py` — PDF → deal_profile.json via `claude -p` headless mode (strict JSON out, no prose; NO direct Anthropic API calls)
1. `rules/` library — one JSON/YAML per deal type defining expected docs by scope (per-entity / per-asset / per-deal)
2. `rules.py` — profile + rules library → manifest of every expected document, counts COMPUTED from the profile
3. `build_tree.py` — manifest → numbered local folder tree + checklist.csv (expected/received/missing)
4. `sort_inbox.py` — files or zip dropped in `inbox/` get classified (filename + first-page text via `claude -p` headless mode; NO direct Anthropic API calls) against the manifest, moved into place, checklist updated; unclassifiable → NEEDS_REVIEW, never guess silently
5. `report.py` — missing-doc report grouped by responsible party + one draft chaser email per party
6. Google Drive mirror (Drive API) — only after local works end to end

## Working rules
- One task at a time from TASKS.md, each with a done-condition. Verify, then commit before the next.
- Small plain Python scripts, standard library where possible. No frameworks, no database, no web server.
- Test inputs are FAKE term sheets and stub documents generated for this project. Never real deal documents.
- `credentials.json`, `token.json`, `secrets/` are gitignored.
- Scripts that need LLM classification (T0c extractor, T5 sorter) must NOT call the Anthropic API with an API key — instead they shell out to Claude Code headless mode (`claude -p`) so it runs on the user's subscription.
- The T2 rules engine must dedupe expected docs by (doc name + owner) so overlay items never double-count docs already required for the same entity.
- If a step is ambiguous, ask before building — do not invent scope.
