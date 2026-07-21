# agent-azuresdk-demo (`ogx` / v2)

OpenShift AI Llama Stack variant. Azure SDK talks to configured endpoints (LiteMaaS, in-cluster vLLM, or Llama Stack `/v1`).

| Version | Branch | Namespace |
|---------|--------|-----------|
| v1 | `main` | `agent-azuresdk-demo-main` |
| v2 | `ogx` (this branch) | `agent-azuresdk-demo-ogx` |

See [docs/SPEC.md](docs/SPEC.md) and [docs/DEMO.md](docs/DEMO.md).

## Quick start (v2 / ogx)

```bash
oc login ...
git checkout ogx
export BRANCH=ogx
./scripts/bootstrap.sh
# Prompts for LLM URL, model, and API key; creates Secrets (not stored in git).
# Standalone: BRANCH=ogx ./scripts/create-llm-secret.sh
```

```bash
oc create -f deploy/tekton/pipelinerun-ogx.yaml -n agent-azuresdk-demo-ogx
# Align newTag in deploy/overlays/ogx/kustomization.yaml, then:
oc apply -k deploy/overlays/ogx
oc -n agent-azuresdk-demo-ogx get route agent
```

**App release:** change only `images[].newTag` in `deploy/overlays/ogx/kustomization.yaml`.

In the UI, switch **LLM endpoint** between `litemaas`, `vllm`, and `llamastack`.
