# DealRoom — Project Brief

## What this is
A tool where an LLM reads initial deal information (term sheet / commitment letter / deal memo PDF), determines what kind of deal it is, and derives an organized, self-auditing closing data room from that. Input: a deal document. Output: a deal-type-appropriate folder structure with an expected-documents checklist, automatic filing of uploaded documents, missing-document alerts, and drafted chaser emails.

Thesis: lawyers repeat this organization work thousands of times across deal types. The LLM sets the standard from the document itself — the skeleton adapts to the deal, and the data becomes usable for clients, for drafting, and for knowing exactly who to chase.

## The core design principle
NOTHING about the deal is hardcoded. The extraction step (T0) produces `deal_profile.json` including `deal_type`, and the rules engine selects the matching taxonomy from a rules library. Adding a new deal type = adding one rules file, zero code changes.

## Deal types in the rules library (v1)
- **secured_term_loan** (real estate): per-entity KYC (formation cert, operating agreement/LPA, good standing, W-9, beneficial ownership); per-asset third-party reports (appraisal, PCA, Phase I, zoning, title commitment, survey, insurance cert); per-asset security docs (mortgage/deed of trust, UCC-1); per-deal loan docs (loan agreement, note, guaranty, assignment of leases and rents, interest rate cap agreement, closing cert, legal opinion); per-asset underwriting (rent roll, operating statement) and per-guarantor financial statements.
- **unsecured_term_loan**: NO collateral or per-asset diligence sections; per-entity KYC; per-deal loan docs (credit agreement, notes, subsidiary guaranties, closing cert, legal opinion, solvency certificate, officer's certificate, board resolutions); per-deal financial diligence (audited financials, projections, compliance certificate).
- **revolver**: same corporate/KYC base as unsecured plus borrowing base certificate, fee letters, deposit account control agreements, LC documentation; if the profile has facility_feature "asset_based", add field exam report and collateral schedules with UCC-1s.
- **sponsor_backed** (cross-cutting): when `sponsor_backed: true` in the deal profile, ANY deal type appends fund-layer docs — fund LPA, GP formation docs, sponsor guaranty, guarantor financial statements, structure/org chart.
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
- If a step is ambiguous, ask before building — do not invent scope.
