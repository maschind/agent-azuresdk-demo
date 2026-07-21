# agent-azuresdk-demo (`ogx-native` / v3)

**Full OpenShift AI** variant (spec → implementation). Same Azure SDK agent as v1/v2; inference + embeddings + RAG via Llama Stack / KServe.

| Version | Branch | Namespace |
|---------|--------|-----------|
| v1 | `main` | `agent-azuresdk-demo-main` |
| v2 | `ogx` | `agent-azuresdk-demo-ogx` |
| v3 | `ogx-native` (this branch) | `agent-azuresdk-demo-ogx-native` |

See [docs/SPEC-v3.md](docs/SPEC-v3.md) (authoritative for this branch) and [docs/SPEC.md](docs/SPEC.md).

## Status

Specification only. Deployables (`deploy/overlays/ogx-native`, Tekton, Argo Application) to be added here — not on `ogx`.

## GitOps rules

Same as v2: Argo CD is the only applicator of overlays; release via `images.newTag` + git push. Secrets out of band via `scripts/create-llm-secret.sh`.
