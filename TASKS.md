# TASKS

Work strictly top to bottom. One task per prompt. Commit after each ✅.

- [ ] **T0a — Scaffold.** Repo structure (`intake/`, `rules/`, `engine/`, `inbox/`, `output/`), .gitignore (secrets, tokens, output/), README stub. Done when: tree matches CLAUDE.md, first commit pushed.
- [ ] **T0b — Fake term sheet.** Generate 1 realistic fake term sheet PDF into `intake/`: $42M secured RE term loan, fund borrower (DE LLC), 2 guarantors, 4 TX multifamily assets, named lender, covenants section. Done when: it reads like a real bank term sheet.
- [ ] **T0c — Extractor.** `engine/parse_deal.py`: PDF → `output/deal_profile.json` matching the schema in CLAUDE.md, via Claude API, strict JSON only. This is the categorization step: secured vs unsecured, term/revolver/add-on, # assets, # borrowers + guarantors. Done when: the term sheet extracts correctly (deal_type=secured_term_loan, 4 assets, 1 borrower, 2 guarantors).
- [ ] **T1 — Rules library.** `rules/secured_term_loan.json`, `rules/unsecured_term_loan.json`, `rules/revolver.json` defining expected docs by scope. Done when: files validate and cover the doc lists in CLAUDE.md.
- [ ] **T2 — Rules engine.** `engine/rules.py`: profile + matching rules file → `output/manifest.json` (every expected doc: name, category, scope, owner, status "missing"). Unknown deal_type → best-guess skeleton + UNKNOWN_DEAL_TYPE flag. Done when: counts match hand-checked totals computed from the profile (e.g., 3 entities × 5 KYC = 15; 4 assets × 6 reports = 24).
- [ ] **T3 — Folder tree + checklist.** `engine/build_tree.py`: manifest → numbered tree under `output/dataroom/` + `checklist.csv` with per-folder expected/received/missing counts. Done when: the tree and CSV match the manifest exactly.
- [ ] **T4 — Fake documents.** ~20 stub files into `inbox/` for the secured deal, covering most (not all) expected docs, some with messy names ("scan_0042.pdf" with the real title inside). Done when: inbox looks like a real messy client upload.
- [ ] **T5 — Inbox sorter.** `engine/sort_inbox.py`: classify each file (filename + first-page text via Claude API) against the manifest, move into place, update checklist, unknowns → NEEDS_REVIEW. Done when: ≥90% filed correctly on T4 files.
- [ ] **T6 — Missing report + chaser emails.** `engine/report.py`: missing docs grouped by responsible party + one draft email each to `output/emails/`. Done when: emails read like an associate wrote them.
- [ ] **T7 — Zip path.** A .zip dropped in inbox → unzip → sort → updated checklist, one command. Done when: zip-to-sorted-room runs clean.
- [ ] **T8 — Google Drive delivery.** `--dest` flag on `build_tree.py` and `sort_inbox.py` (and `report.py`) so the data room can be built and sorted at any path — including a Google Drive for Desktop synced folder. No OAuth, no Drive API. Done when: data room browsable in Berkeley Drive via `--dest` to the synced folder.
- [ ] **T9 — Package.** README (problem/thesis, screenshots: term sheet → JSON profile → data room + checklist, NEEDS_REVIEW shot), 2-min Loom, repo public. Optional flex if time: a second term sheet (unsecured) to show the room reshapes itself. Done when: a stranger gets it in 90 seconds.

## Roadmap (README only — do not build)
- Draft loan agreement from precedent + extracted change list
- VDR export package (numbered zip + index sheet for Intralinks/Datasite upload)
- Email intake: docs arriving by email filed automatically
- More deal types (REIT credit facilities, construction loans, subscription lines)
