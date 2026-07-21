# Demo runbook

Single source of truth for **v1**, **v2**, and **v3**. Keep this file identical on branches `main`, `ogx`, and `ogx-native`.

See [SPEC.md](SPEC.md) for architecture and decisions.

## Story beats

1. **v1** (`main`): Azure SDK on plain OpenShift — chat → LiteMaaS, RAG → app pgvector. **No OpenShift AI.**
2. **v2** (`ogx`): Same agent + same RAG; **default chat → Llama Stack**. Optional bypass `litemaas` / `vllm`.
3. **v3** (`ogx-native`): Full OpenShift AI — chat + ingest + retrieve via Stack / KServe (implement on `ogx-native`; see SPEC § Version 3).

Success line: *We did not rewrite the agent — we moved AI dependencies onto OpenShift AI.*

---

## Version matrix

| | v1 | v2 | v3 |
|--|----|----|----|
| Branch | `main` | `ogx` | `ogx-native` |
| Namespace | `agent-azuresdk-demo-main` | `agent-azuresdk-demo-ogx` | `agent-azuresdk-demo-ogx-native` |
| Chat | LiteMaaS (direct) | Stack (default) | Stack only |
| RAG | App pgvector | App pgvector | Stack vector IO |
| Status | Implemented | Implemented | Spec |

---

## Bootstrap (once per version)

```bash
# v1
git checkout main && export BRANCH=main && ./scripts/bootstrap.sh

# v2
git checkout ogx && export BRANCH=ogx && ./scripts/bootstrap.sh

# v3 (when deployables exist)
git checkout ogx-native && export BRANCH=ogx-native && ./scripts/bootstrap.sh
```

Secrets only (out of band — never commit keys):

```bash
BRANCH=<main|ogx|ogx-native> ./scripts/create-llm-secret.sh
# After rotating secrets: oc -n <namespace> rollout restart deploy/agent
```

Bootstrap creates NS, out-of-band Secrets, Tekton, Argo RBAC + Application. It does **not** `oc apply -k` the app overlay (strict GitOps).

---

## Build and release (strict GitOps)

Same pattern for every branch (`BRANCH` / overlay name match):

```bash
export BRANCH=<main|ogx|ogx-native>   # and checkout that branch
NS=agent-azuresdk-demo-${BRANCH}

# 1) Build + push image (Tekton → internal registry)
oc create -f deploy/tekton/pipelinerun-${BRANCH}.yaml -n "${NS}"

# 2) Bump ONLY images.newTag in git
BRANCH=${BRANCH} ./scripts/gitops-release.sh v0.1.1
git add deploy/overlays/${BRANCH}/kustomization.yaml
git commit -m "Release agent v0.1.1 (${BRANCH})"
git push origin "${BRANCH}"

# 3) Argo CD auto-syncs. Do not: oc apply -k, oc set image, oc set env
oc -n openshift-gitops get application "agent-azuresdk-demo-${BRANCH}"
```

---

## Click paths

### v1 — plain OpenShift

1. `oc get route agent -n agent-azuresdk-demo-main`
2. Upload a document → ask a grounded question → confirm tool call → delete
3. Note: no Llama Stack; chat goes to LiteMaaS

### v2 — bridge (OpenShift AI for chat)

1. `oc get route agent -n agent-azuresdk-demo-ogx`
2. Confirm sidebar **LLM endpoint** defaults to **`llamastack`**
3. Upload → grounded question → tool call (RAG still **app-pgvector**) → delete
4. Optionally switch to `litemaas` or `vllm` to show bypass vs Stack

### v3 — full OpenShift AI (when implemented)

1. `oc get route agent -n agent-azuresdk-demo-ogx-native`
2. Chat only via Stack; no LiteMaaS/vLLM agent bypass
3. Upload / list / delete via Stack; grounded answers from Stack vector IO
4. In OpenShift AI console: show LSD Ready + InferenceService; optionally stop Stack/ISVC to prove platform dependency
