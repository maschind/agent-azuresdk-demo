# Demo runbook (`ogx` / v2)

## Bootstrap v2

```bash
git checkout ogx
export BRANCH=ogx
export GIT_REPO_URL=https://github.com/maschind/agent-azuresdk-demo.git
export LLM_API_KEY='sk-...'
export LLM_BASE_URL='https://litellm-litemaas.apps.prod.rhoai.rh-aiservices-bu.com/v1'
export LLM_MODEL='Qwen3.6-35B-A3B'
./scripts/bootstrap.sh
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

For v1 demos, checkout `main` and use namespace `agent-azuresdk-demo-main` (see that branch’s DEMO.md).
