#!/usr/bin/env bash
# Interactively create OpenShift Secret(s) for LLM / LiteMaaS (Linux / macOS).
# Does not print the API key. Nothing secret is stored in git.
set -euo pipefail

BRANCH="${BRANCH:-main}"
case "${BRANCH}" in
  main) DEFAULT_NS="agent-azuresdk-demo-main" ;;
  ogx) DEFAULT_NS="agent-azuresdk-demo-ogx" ;;
  *) DEFAULT_NS="agent-azuresdk-demo-main" ;;
esac

NAMESPACE="${NAMESPACE:-${DEFAULT_NS}}"
SECRET_NAME="${SECRET_NAME:-llm-credentials}"

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

prompt() {
  # prompt "Label" "default" -> sets REPLY
  local label="$1"
  local default="${2:-}"
  if [[ -n "${default}" ]]; then
    read -r -p "${label} [${default}]: " REPLY || true
    REPLY="${REPLY:-${default}}"
  else
    read -r -p "${label}: " REPLY || true
  fi
}

prompt_secret() {
  local label="$1"
  # -s hides input (bash on Linux/macOS)
  read -r -s -p "${label}: " REPLY || true
  echo ""
}

need oc

echo "==> OpenShift LLM secret helper"
echo "    Namespace default: ${NAMESPACE}"
echo ""

oc whoami >/dev/null

prompt "OpenShift namespace" "${NAMESPACE}"
NAMESPACE="${REPLY}"

prompt "LLM base URL (OpenAI-compatible, e.g. LiteMaaS .../v1)" ""
LLM_BASE_URL="${REPLY}"
if [[ -z "${LLM_BASE_URL}" ]]; then
  echo "LLM base URL is required." >&2
  exit 1
fi

prompt "LLM model name" ""
LLM_MODEL="${REPLY}"
if [[ -z "${LLM_MODEL}" ]]; then
  echo "LLM model name is required." >&2
  exit 1
fi

prompt_secret "LLM API key (input hidden)"
LLM_API_KEY="${REPLY}"
if [[ -z "${LLM_API_KEY}" ]]; then
  echo "LLM API key is required." >&2
  exit 1
fi

oc get ns "${NAMESPACE}" >/dev/null 2>&1 || oc new-project "${NAMESPACE}" >/dev/null
oc project "${NAMESPACE}" >/dev/null

echo "==> Creating/updating Secret ${SECRET_NAME} in ${NAMESPACE}"
oc -n "${NAMESPACE}" create secret generic "${SECRET_NAME}" \
  --from-literal=LLM_API_KEY="${LLM_API_KEY}" \
  --from-literal=LLM_BASE_URL="${LLM_BASE_URL}" \
  --from-literal=LLM_MODEL="${LLM_MODEL}" \
  --dry-run=client -o yaml | oc apply -f -

# Optional: Llama Stack inference secret on ogx
if [[ "${NAMESPACE}" == *"-ogx" ]] || [[ "${BRANCH}" == "ogx" ]]; then
  echo ""
  read -r -p "Also create llama-stack-inference Secret? [Y/n]: " CREATE_LSD || true
  CREATE_LSD="${CREATE_LSD:-Y}"
  if [[ "${CREATE_LSD}" =~ ^[Yy]$ ]]; then
    prompt "Inference model for Llama Stack" "${LLM_MODEL}"
    INFERENCE_MODEL="${REPLY}"
    prompt "Inference provider URL (VLLM_URL / OpenAI-compat)" "${LLM_BASE_URL}"
    VLLM_URL="${REPLY}"
    prompt_secret "Inference API token (input hidden; same as LLM key is OK)"
    VLLM_API_TOKEN="${REPLY:-${LLM_API_KEY}}"
    oc -n "${NAMESPACE}" create secret generic llama-stack-inference \
      --from-literal=INFERENCE_MODEL="${INFERENCE_MODEL}" \
      --from-literal=VLLM_URL="${VLLM_URL}" \
      --from-literal=VLLM_TLS_VERIFY=false \
      --from-literal=VLLM_API_TOKEN="FAKESECRET_i4j5k6l7m8n9o0p1q2r3" \
      --from-literal=VLLM_MAX_TOKENS=4096 \
      --dry-run=client -o yaml | oc apply -f -
    echo "==> Secret llama-stack-inference applied"
  fi
fi

# Clear sensitive vars
unset LLM_API_KEY VLLM_API_TOKEN REPLY

echo ""
echo "Done. Secrets applied in namespace ${NAMESPACE}."
echo "Restart the agent if it was already running:"
echo "  oc -n ${NAMESPACE} rollout restart deploy/agent"
