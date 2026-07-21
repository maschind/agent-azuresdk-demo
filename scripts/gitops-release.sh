#!/usr/bin/env bash
# Bump deploy/overlays/<branch>/kustomization.yaml images.newTag and print GitOps next steps.
# Does NOT apply to the cluster — commit + push; Argo CD self-heals.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${BRANCH:-$(git -C "${ROOT}" rev-parse --abbrev-ref HEAD)}"
TAG="${1:-}"

case "${BRANCH}" in
  main|ogx) ;;
  *)
    echo "BRANCH must be main or ogx (got: ${BRANCH})" >&2
    exit 1
    ;;
esac

KUST="${ROOT}/deploy/overlays/${BRANCH}/kustomization.yaml"
if [[ ! -f "${KUST}" ]]; then
  echo "Missing ${KUST}" >&2
  exit 1
fi

if [[ -z "${TAG}" ]]; then
  echo "Usage: BRANCH=${BRANCH} $0 <image-tag>" >&2
  echo "Example: BRANCH=ogx $0 v0.1.1" >&2
  exit 1
fi

# Portable in-place newTag update (GNU/BSD sed)
if sed --version >/dev/null 2>&1; then
  sed -i -E "s/^([[:space:]]*newTag:).*/\\1 ${TAG}/" "${KUST}"
else
  sed -i '' -E "s/^([[:space:]]*newTag:).*/\\1 ${TAG}/" "${KUST}"
fi

echo "==> Set images.newTag=${TAG} in ${KUST}"
echo ""
echo "GitOps release (do not oc apply / oc set image):"
echo "  git add ${KUST}"
echo "  git commit -m \"Release agent ${TAG} (${BRANCH})\""
echo "  git push origin ${BRANCH}"
echo "  # Argo CD Application agent-azuresdk-demo-${BRANCH} auto-syncs"
echo "  oc -n openshift-gitops get application agent-azuresdk-demo-${BRANCH}"
