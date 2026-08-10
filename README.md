# DealRoom

AI-powered closing data room generator.

Reads a term sheet PDF, extracts the deal profile (deal type, assets, borrowers, guarantors), and builds a deal-type-appropriate folder structure with an expected-documents checklist. Drop documents into the inbox — they get classified and filed automatically. Missing documents are flagged with draft chaser emails.

## Pipeline

1. **Parse** — PDF term sheet → `deal_profile.json` (via Claude API)
2. **Rules** — deal profile + rules library → document manifest
3. **Build** — manifest → numbered folder tree + `checklist.csv`
4. **Sort** — inbox files classified and filed against the manifest
5. **Report** — missing-doc report + draft chaser emails by responsible party

## Project structure

```
intake/    — input term sheets / deal documents (PDFs)
rules/     — one JSON per deal type defining expected documents
engine/    — pipeline scripts (parse, rules, build, sort, report)
inbox/     — drop zone for incoming documents to be classified
output/    — generated data room, checklist, emails (gitignored)
```

## Usage

```bash
export ANTHROPIC_API_KEY=sk-...
python engine/parse_deal.py intake/term_sheet.pdf
python engine/rules.py
python engine/build_tree.py
python engine/sort_inbox.py
python engine/report.py
```
