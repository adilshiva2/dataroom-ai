#!/usr/bin/env bash
# demo.sh — Reset and rerun the full DataRoom AI pipeline end to end.
#
# Rebuilds the data room at output/dataroom/, regenerates test docs,
# zips them, sorts the zip, and prints the missing-document report.
#
# Prerequisites: Python 3.9+, pypdf (pip install pypdf), Claude Code (claude -p)

set -euo pipefail
cd "$(dirname "$0")"

# Check prerequisites
if ! command -v claude &> /dev/null; then
    echo "Error: 'claude' is not installed or not on PATH."
    echo ""
    echo "This demo requires Claude Code (https://docs.anthropic.com/en/docs/claude-code)."
    echo "The pipeline uses 'claude -p' for document extraction and classification."
    echo ""
    echo "Install it, log in with your Claude subscription, then rerun ./demo.sh."
    exit 1
fi

echo "=== DataRoom AI Demo ==="
echo ""

# 1. Parse deal (uses existing term sheet + deal profile)
echo "--- Step 1: Deal profile ---"
if [ ! -f output/deal_profile.json ]; then
    echo "Running extractor on term sheet..."
    python3 engine/parse_deal.py intake/term_sheet_meridian.pdf
else
    echo "Using existing output/deal_profile.json"
fi
echo ""

# 2. Build manifest from rules
echo "--- Step 2: Rules engine ---"
python3 engine/rules.py
echo ""

# 3. Build folder tree (resets data room to empty)
echo "--- Step 3: Build folder tree ---"
python3 engine/build_tree.py
echo ""

# 4. Generate test documents
echo "--- Step 4: Generate test documents ---"
python3 engine/generate_test_docs.py
echo ""

# 5. Zip and sort
echo "--- Step 5: Zip and sort ---"
(cd inbox && zip -q -r ../output/test_inbox.zip . -x '.*')
echo "Created output/test_inbox.zip with $(unzip -l output/test_inbox.zip | tail -1 | awk '{print $2}') files"
python3 engine/sort_inbox.py output/test_inbox.zip
rm output/test_inbox.zip
echo ""

# 6. Missing-document report
echo "--- Step 6: Missing-document report ---"
python3 engine/report.py
echo ""

echo "=== Demo complete ==="
echo "Data room:  output/dataroom/"
echo "Checklist:  output/dataroom/checklist.csv"
echo "Emails:     output/emails/"
