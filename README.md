# agent-azuresdk-demo (`ogx` / v2)

Bridge demo: same Azure SDK agent as v1, **default chat via Llama Stack**, RAG still app-pgvector. Full platform path is **v3** on branch [`ogx-native`](https://github.com/maschind/agent-azuresdk-demo/tree/ogx-native) ([docs/SPEC-v3.md](docs/SPEC-v3.md)).

| Version | Branch | Namespace |
|---------|--------|-----------|
| v1 | `main` | `agent-azuresdk-demo-main` |
| v2 | `ogx` (this branch) | `agent-azuresdk-demo-ogx` |
| v3 | `ogx-native` (spec) | `agent-azuresdk-demo-ogx-native` |

See [docs/SPEC.md](docs/SPEC.md), [docs/SPEC-v3.md](docs/SPEC-v3.md), and [docs/DEMO.md](docs/DEMO.md).

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

UI defaults to **`llamastack`**. Optional bypass: `litemaas` / `vllm`.
