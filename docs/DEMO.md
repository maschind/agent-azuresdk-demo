# Demo runbook (`ogx` / v2)

## Bootstrap v2

```bash
git checkout ogx
export BRANCH=ogx
./scripts/bootstrap.sh
# CLI prompts for LLM base URL, model, API key → Secret llm-credentials
# (and optional llama-stack-inference)
```

Or secrets only:

```bash
BRANCH=ogx ./scripts/create-llm-secret.sh
```

Namespace: `agent-azuresdk-demo-ogx`

## Build and tag

```bash
oc create -f deploy/tekton/pipelinerun-ogx.yaml -n agent-azuresdk-demo-ogx
# Set images.newTag in deploy/overlays/ogx/kustomization.yaml
oc apply -k deploy/overlays/ogx
```

## Click path

1. Open `oc get route agent -n agent-azuresdk-demo-ogx`
2. Use sidebar **LLM endpoint**: `litemaas` | `vllm` | `llamastack`
3. Upload a document → ask a grounded question → confirm tool call → delete

For v1 demos, checkout `main` and use namespace `agent-azuresdk-demo-main`.
