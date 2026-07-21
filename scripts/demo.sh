#!/usr/bin/env bash
set -euo pipefail

BRANCH="${BRANCH:-main}"
NS="agent-azuresdk-demo-${BRANCH}"

echo "Namespace: ${NS}"
oc -n "${NS}" get route agent -o wide 2>/dev/null || echo "No agent route yet"
echo ""
echo "Demo path:"
echo "  1. Open the Route URL"
echo "  2. Upload a .txt/.md/.pdf with a distinctive fact"
echo "  3. Ask a question that requires search_knowledge_base"
echo "  4. Delete the document and confirm the fact is gone"
echo ""
echo "See docs/DEMO.md for details."
