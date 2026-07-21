# Demo runbook (`ogx` / v2)

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

## Click path

1. Open `oc get route agent -n agent-azuresdk-demo-ogx`
2. Use sidebar **LLM endpoint**: `litemaas` | `vllm` | `llamastack`
3. Upload a document → ask a grounded question → confirm tool call → delete

For v1 demos, checkout `main` and use namespace `agent-azuresdk-demo-main`.
