#!/usr/bin/env bash
# Bootstrap agent-azuresdk-demo for BRANCH=main|ogx (Linux / macOS).
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
  *)
    echo "BRANCH must be main or ogx (got: ${BRANCH})" >&2
    exit 1
    ;;
esac

GIT_REPO_URL="${GIT_REPO_URL:-https://github.com/maschind/agent-azuresdk-demo.git}"
LLM_API_KEY="${LLM_API_KEY:-}"
LLM_BASE_URL="${LLM_BASE_URL:-https://litellm-litemaas.apps.prod.rhoai.rh-aiservices-bu.com/v1}"
LLM_MODEL="${LLM_MODEL:-Qwen3.6-35B-A3B}"
SKIP_GITOPS="${SKIP_GITOPS:-false}"
APPLY_DIRECT="${APPLY_DIRECT:-true}"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

need oc
need git

if [[ -z "${LLM_API_KEY}" ]]; then
  echo "Set LLM_API_KEY to your LiteMaaS (or provider) API key before running bootstrap." >&2
  exit 1
fi

echo "==> Checking cluster login"
oc whoami >/dev/null
oc project default >/dev/null 2>&1 || true

echo "==> Ensuring namespace ${NS}"
oc get ns "${NS}" >/dev/null 2>&1 || oc new-project "${NS}" >/dev/null
oc project "${NS}" >/dev/null

echo "==> Creating/updating Secret llm-credentials"
oc -n "${NS}" create secret generic llm-credentials \
  --from-literal=LLM_API_KEY="${LLM_API_KEY}" \
  --from-literal=LLM_BASE_URL="${LLM_BASE_URL}" \
  --from-literal=LLM_MODEL="${LLM_MODEL}" \
  --dry-run=client -o yaml | oc apply -f -

if [[ ! -f "${PIPELINE_FILE}" ]]; then
  echo "Pipeline file not found for BRANCH=${BRANCH}: ${PIPELINE_FILE}" >&2
  echo "For ogx, ensure you are on the ogx branch or the file exists." >&2
  exit 1
fi

echo "==> Applying Tekton pipeline resources"
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

if [[ "${SKIP_GITOPS}" != "true" ]]; then
  install_gitops || {
    echo "GitOps install failed; continuing with direct apply" >&2
    APPLY_DIRECT=true
  }
  if [[ -f "${APP_FILE}" ]] && oc get crd applications.argoproj.io >/dev/null 2>&1; then
    echo "==> Applying Argo CD Application (${APP_FILE})"
    # Allow substituting repo URL if needed
    sed "s|https://github.com/maschind/agent-azuresdk-demo.git|${GIT_REPO_URL}|g" "${APP_FILE}" | oc apply -f -
  fi
fi

if [[ "${APPLY_DIRECT}" == "true" ]]; then
  if [[ ! -d "${OVERLAY}" ]]; then
    echo "Overlay not found: ${OVERLAY}" >&2
    exit 1
  fi
  echo "==> Applying manifests directly: ${OVERLAY}"
  oc apply -k "${OVERLAY}"
fi

echo ""
echo "Bootstrap complete for BRANCH=${BRANCH} namespace=${NS}"
echo "Next steps:"
echo "  1) Push this repo so Tekton can clone: ${GIT_REPO_URL} (revision ${BRANCH})"
echo "  2) Start a build:"
echo "       oc create -f ${ROOT}/deploy/tekton/pipelinerun-${BRANCH}.yaml -n ${NS}"
echo "  3) After build, set images.newTag in deploy/overlays/${BRANCH}/kustomization.yaml and re-apply / sync"
echo "  4) Route:"
oc -n "${NS}" get route agent -o jsonpath='{.spec.host}' 2>/dev/null && echo || echo "     (route appears after agent Deployment is available)"
echo ""
