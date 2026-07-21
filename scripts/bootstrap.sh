#!/usr/bin/env bash
# Bootstrap agent-azuresdk-demo for BRANCH=main|ogx|ogx-native (Linux / macOS).
# App workload is managed only by OpenShift GitOps (Argo CD) after bootstrap.
# Bootstrap may: create NS, out-of-band Secrets, Tekton, Argo RBAC + Application.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${BRANCH:-main}"

case "${BRANCH}" in
  main)
    NS="agent-azuresdk-demo-main"
    OVERLAY="${ROOT}/deploy/overlays/main"
    PIPELINE_FILE="${ROOT}/deploy/tekton/pipeline-main.yaml"
    APP_FILE="${ROOT}/deploy/gitops/application-main.yaml"
    ;;
  ogx)
    NS="agent-azuresdk-demo-ogx"
    OVERLAY="${ROOT}/deploy/overlays/ogx"
    PIPELINE_FILE="${ROOT}/deploy/tekton/pipeline-ogx.yaml"
    APP_FILE="${ROOT}/deploy/gitops/application-ogx.yaml"
    ;;
  ogx-native)
    NS="agent-azuresdk-demo-ogx-native"
    OVERLAY="${ROOT}/deploy/overlays/ogx-native"
    PIPELINE_FILE="${ROOT}/deploy/tekton/pipeline-ogx-native.yaml"
    APP_FILE="${ROOT}/deploy/gitops/application-ogx-native.yaml"
    ;;
  *)
    echo "BRANCH must be main, ogx, or ogx-native (got: ${BRANCH})" >&2
    exit 1
    ;;
esac

GIT_REPO_URL="${GIT_REPO_URL:-https://github.com/maschind/agent-azuresdk-demo.git}"
GITHUB_USER="${GITHUB_USER:-maschind}"
GITHUB_TOKEN="${GITHUB_TOKEN:-}"
SKIP_GITOPS="${SKIP_GITOPS:-false}"
# Strict GitOps: never oc apply -k the app overlay unless explicitly forced.
APPLY_DIRECT="${APPLY_DIRECT:-false}"
SKIP_LLM_SECRET="${SKIP_LLM_SECRET:-false}"
RBAC_FILE="${ROOT}/deploy/gitops/argocd-namespace-rbac.yaml"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

need oc
need git

echo "==> Checking cluster login"
oc whoami >/dev/null
oc project default >/dev/null 2>&1 || true

echo "==> Ensuring namespace ${NS}"
oc get ns "${NS}" >/dev/null 2>&1 || oc new-project "${NS}" >/dev/null
oc project "${NS}" >/dev/null

if [[ "${SKIP_LLM_SECRET}" != "true" ]]; then
  echo "==> LLM credentials (interactive — nothing committed to git)"
  BRANCH="${BRANCH}" NAMESPACE="${NS}" "${ROOT}/scripts/create-llm-secret.sh"
else
  if ! oc -n "${NS}" get secret llm-credentials >/dev/null 2>&1; then
    echo "Secret llm-credentials missing. Run: BRANCH=${BRANCH} ./scripts/create-llm-secret.sh" >&2
    exit 1
  fi
  echo "==> Reusing existing Secret llm-credentials (SKIP_LLM_SECRET=true)"
fi

if [[ -n "${GITHUB_TOKEN}" ]]; then
  echo "==> Creating/updating Secret github-basic-auth for Tekton git-clone"
  TMP="$(mktemp -d)"
  printf '%s\n' "[credential]" "	helper = store" >"${TMP}/.gitconfig"
  printf '%s\n' "https://x-access-token:${GITHUB_TOKEN}@github.com" >"${TMP}/.git-credentials"
  oc -n "${NS}" create secret generic github-basic-auth \
    --from-file=.gitconfig="${TMP}/.gitconfig" \
    --from-file=.git-credentials="${TMP}/.git-credentials" \
    --dry-run=client -o yaml | oc apply -f -
  rm -rf "${TMP}"
else
  echo "==> GITHUB_TOKEN not set (optional for public repos)"
fi

if [[ ! -f "${PIPELINE_FILE}" ]]; then
  echo "Pipeline file not found for BRANCH=${BRANCH}: ${PIPELINE_FILE}" >&2
  echo "For ogx, ensure you are on the ogx branch or the file exists." >&2
  exit 1
fi

echo "==> Applying Tekton pipeline resources (build tooling; not the app runtime)"
oc apply -f "${PIPELINE_FILE}"

# Allow pipeline SA to push images in this namespace
oc policy add-role-to-user system:image-builder -z pipeline -n "${NS}" >/dev/null 2>&1 || true
oc adm policy add-scc-to-user privileged -z pipeline -n "${NS}" >/dev/null 2>&1 || true

install_gitops() {
  if oc get ns openshift-gitops >/dev/null 2>&1 && oc get deploy openshift-gitops-server -n openshift-gitops >/dev/null 2>&1; then
    echo "==> OpenShift GitOps already present"
    return 0
  fi
  echo "==> Installing OpenShift GitOps operator"
  oc apply -f - <<'EOF'
apiVersion: v1
kind: Namespace
metadata:
  name: openshift-gitops-operator
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: openshift-gitops-operator
  namespace: openshift-gitops-operator
spec:
  upgradeStrategy: Default
---
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: openshift-gitops-operator
  namespace: openshift-gitops-operator
spec:
  channel: latest
  name: openshift-gitops-operator
  source: redhat-operators
  sourceNamespace: openshift-marketplace
  installPlanApproval: Automatic
EOF
  echo "==> Waiting for openshift-gitops namespace / Argo CD server"
  for _ in $(seq 1 60); do
    if oc get deploy openshift-gitops-server -n openshift-gitops >/dev/null 2>&1; then
      oc -n openshift-gitops rollout status deploy/openshift-gitops-server --timeout=120s || true
      return 0
    fi
    sleep 10
  done
  echo "Timed out waiting for OpenShift GitOps" >&2
  return 1
}

grant_argocd_rbac() {
  echo "==> Granting OpenShift GitOps admin on demo namespaces"
  if [[ -f "${RBAC_FILE}" ]]; then
    # Other-branch NS may be missing — apply per binding as needed.
    oc apply -f "${RBAC_FILE}" 2>/dev/null || true
  fi
  oc policy add-role-to-user admin \
    system:serviceaccount:openshift-gitops:openshift-gitops-argocd-application-controller \
    -n "${NS}"
}

if [[ "${SKIP_GITOPS}" != "true" ]]; then
  install_gitops || {
    echo "GitOps install failed." >&2
    if [[ "${APPLY_DIRECT}" != "true" ]]; then
      echo "Set APPLY_DIRECT=true only for break-glass; otherwise fix GitOps and re-run." >&2
      exit 1
    fi
  }
  grant_argocd_rbac
  if [[ -f "${APP_FILE}" ]] && oc get crd applications.argoproj.io >/dev/null 2>&1; then
    echo "==> Applying Argo CD Application (${APP_FILE})"
    sed "s|https://github.com/maschind/agent-azuresdk-demo.git|${GIT_REPO_URL}|g" "${APP_FILE}" | oc apply -f -
    echo "==> Requesting Argo CD sync"
    oc -n openshift-gitops patch application "agent-azuresdk-demo-${BRANCH}" --type merge \
      -p '{"operation":{"initiatedBy":{"username":"bootstrap"},"sync":{"prune":true}}}' 2>/dev/null || true
  else
    echo "Argo Application file missing or CRD not ready: ${APP_FILE}" >&2
    exit 1
  fi
fi

if [[ "${APPLY_DIRECT}" == "true" ]]; then
  if [[ ! -d "${OVERLAY}" ]]; then
    echo "Overlay not found: ${OVERLAY}" >&2
    exit 1
  fi
  echo "==> BREAK-GLASS: APPLY_DIRECT=true — oc apply -k ${OVERLAY}"
  echo "    Prefer GitOps. Revert local drift with: oc -n openshift-gitops patch application agent-azuresdk-demo-${BRANCH} ..."
  oc apply -k "${OVERLAY}"
else
  echo "==> Skipping direct overlay apply (GitOps is source of truth)"
fi

echo ""
echo "Bootstrap complete for BRANCH=${BRANCH} namespace=${NS}"
echo "Strict GitOps next steps:"
echo "  1) Ensure this branch is pushed: ${GIT_REPO_URL} @ ${BRANCH}"
echo "  2) Build image (Tekton):"
echo "       oc create -f ${ROOT}/deploy/tekton/pipelinerun-${BRANCH}.yaml -n ${NS}"
echo "  3) Release ONLY via images.newTag + git push (never oc set image / oc apply -k):"
echo "       BRANCH=${BRANCH} ${ROOT}/scripts/gitops-release.sh <new-tag>"
echo "       git add deploy/overlays/${BRANCH}/kustomization.yaml && git commit && git push"
echo "  4) Watch sync:"
echo "       oc -n openshift-gitops get application agent-azuresdk-demo-${BRANCH} -w"
echo "  5) Route (after Synced):"
oc -n "${NS}" get route agent -o jsonpath='{.spec.host}' 2>/dev/null && echo || echo "     (appears after Argo syncs the overlay)"
echo ""
