# agent-azuresdk-demo

POC: Azure AI Python client + Streamlit agent on OpenShift, with pgvector RAG (upload/delete in UI), Tekton builds, and OpenShift GitOps.

| Version | Branch | Namespace |
|---------|--------|-----------|
| v1 | `main` | `agent-azuresdk-demo-main` |
| v2 | `ogx` | `agent-azuresdk-demo-ogx` |

See [docs/SPEC.md](docs/SPEC.md) and [docs/DEMO.md](docs/DEMO.md).

## Quick start (v1)

```bash
oc login ...
export BRANCH=main
./scripts/bootstrap.sh
# Bootstrap prompts for LiteMaaS/LLM URL, model, and API key and creates Secret llm-credentials.
# Standalone: ./scripts/create-llm-secret.sh
```

Push this repository to GitHub, then:

```bash
oc create -f deploy/tekton/pipelinerun-main.yaml -n agent-azuresdk-demo-main
# After Succeeded, ensure deploy/overlays/main/kustomization.yaml newTag matches
oc apply -k deploy/overlays/main
oc -n agent-azuresdk-demo-main get route agent
```

**App release:** change only `images[].newTag` in `deploy/overlays/main/kustomization.yaml`.

## Local run (optional)

```bash
# Postgres with pgvector on localhost:5432, then:
cd app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export LLM_API_KEY=... LLM_BASE_URL=... LLM_MODEL=...
export DATABASE_URL=postgresql://rag:rag@localhost:5432/rag
streamlit run main.py
```

LLM credentials are never committed. Use `./scripts/create-llm-secret.sh` on the cluster.
