# agent-azuresdk-demo

POC: Azure AI Inference SDK agents on OpenShift → OpenShift AI (Llama Stack / KServe).

| Version | Branch | Namespace | Role |
|---------|--------|-----------|------|
| v1 | `main` | `agent-azuresdk-demo-main` | Plain OpenShift (no OpenShift AI) |
| v2 | `ogx` | `agent-azuresdk-demo-ogx` | Bridge: Stack chat, app-pgvector RAG |
| v3 | `ogx-native` | `agent-azuresdk-demo-ogx-native` | Full OpenShift AI (Stack RAG + KServe) |

**Docs (identical on all three branches):** [docs/SPEC.md](docs/SPEC.md) · [docs/DEMO.md](docs/DEMO.md)

This checkout is branch **`main`** (v1).

## GitOps rules

- Runtime manifests under `deploy/overlays/<branch>` applied **only** by Argo CD.
- Release: `images.newTag` + git push (`scripts/gitops-release.sh`). No routine `oc apply -k` / `oc set image` / `oc set env`.
- Secrets out of band: `scripts/create-llm-secret.sh`.

## Quick start

Follow [docs/DEMO.md](docs/DEMO.md) for the version you are demoing (`BRANCH=main|ogx|ogx-native`).
