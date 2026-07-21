# Demo runbook (`ogx` / v2)

## Story beats

1. **v1** (`main`): Azure SDK on plain OpenShift — chat → LiteMaaS, RAG → app pgvector. No OpenShift AI.
2. **v2** (`ogx`): Same agent + same RAG; **default chat → Llama Stack**. Optional bypass `litemaas` / `vllm`.
3. **v3** (spec): Full OpenShift AI — see [SPEC-v3.md](SPEC-v3.md) (not deployed yet).

## Bootstrap v2 (once)

```bash
git checkout ogx
export BRANCH=ogx
./scripts/bootstrap.sh
# CLI prompts for LLM base URL, model, API key → Secret llm-credentials
# (and optional llama-stack-inference)
# Grants Argo CD RBAC, applies Application; does NOT oc apply -k the app overlay.
```

Or secrets only (out of band — never commit keys):

```bash
BRANCH=ogx ./scripts/create-llm-secret.sh
# After rotating secrets: oc -n agent-azuresdk-demo-ogx rollout restart deploy/agent
```

Namespace: `agent-azuresdk-demo-ogx`

## Build and release (strict GitOps)

```bash
# 1) Build + push image (Tekton → internal registry)
oc create -f deploy/tekton/pipelinerun-ogx.yaml -n agent-azuresdk-demo-ogx

# 2) Bump ONLY images.newTag in git (script edits the file)
BRANCH=ogx ./scripts/gitops-release.sh v0.1.1
git add deploy/overlays/ogx/kustomization.yaml
git commit -m "Release agent v0.1.1 (ogx)"
git push origin ogx

# 3) Argo CD auto-syncs (selfHeal). Do not: oc apply -k, oc set image, oc set env
oc -n openshift-gitops get application agent-azuresdk-demo-ogx
```

## Click path (v2)

1. Open `oc get route agent -n agent-azuresdk-demo-ogx`
2. Confirm sidebar **LLM endpoint** defaults to **`llamastack`** (caption shows Stack URL / model id)
3. Upload a document → ask a grounded question → confirm tool call (RAG still app-pgvector) → delete
4. Optionally switch to `litemaas` or `vllm` to show bypass vs Stack

For v1 demos, checkout `main` and use namespace `agent-azuresdk-demo-main`.
