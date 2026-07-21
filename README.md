# agent-azuresdk-demo (`ogx` / v2)

OpenShift AI Llama Stack variant. Azure SDK talks to configured endpoints (LiteMaaS, in-cluster vLLM, or Llama Stack `/v1`).

| Version | Branch | Namespace |
|---------|--------|-----------|
| v1 | `main` | `agent-azuresdk-demo-main` |
| v2 | `ogx` (this branch) | `agent-azuresdk-demo-ogx` |

See [docs/SPEC.md](docs/SPEC.md) and [docs/DEMO.md](docs/DEMO.md).

## GitOps rules (source of truth = git)

- **Runtime manifests** live under `deploy/overlays/<branch>` and are applied **only** by the Argo CD Application in `deploy/gitops/`.
- **App release:** change only `images[].newTag` in `deploy/overlays/<branch>/kustomization.yaml`, commit, push. Use `scripts/gitops-release.sh`.
- **Do not** `oc apply -k`, `oc set image`, or `oc set env` on the agent for routine changes (breaks sync). Break-glass: `APPLY_DIRECT=true` on bootstrap only.
- **Secrets** `llm-credentials` / `llama-stack-inference` are created out of band (`scripts/create-llm-secret.sh`); never committed.
- **Tekton** builds images; it does not deploy the app.

## Quick start (v2 / ogx)

```bash
oc login ...
git checkout ogx
export BRANCH=ogx
./scripts/bootstrap.sh
# Prompts for LLM URL/model/key; installs Argo RBAC + Application.

oc create -f deploy/tekton/pipelinerun-ogx.yaml -n agent-azuresdk-demo-ogx
BRANCH=ogx ./scripts/gitops-release.sh v0.1.0   # if tag already matches, skip
# commit + push kustomization if newTag changed
oc -n openshift-gitops get application agent-azuresdk-demo-ogx
oc -n agent-azuresdk-demo-ogx get route agent
```

In the UI, switch **LLM endpoint** between `litemaas`, `vllm`, and `llamastack`.
