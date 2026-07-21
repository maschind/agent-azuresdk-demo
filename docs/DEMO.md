# Demo runbook

## Prerequisites

- `oc login` as a user who can create projects and install operators (cluster-admin for GitOps bootstrap)
- Repo cloned; network access to LiteMaaS from the cluster

## Bootstrap v1 (`main`)

```bash
export BRANCH=main
export GIT_REPO_URL=https://github.com/maschind/agent-azuresdk-demo.git
export LLM_API_KEY='sk-...'          # LiteMaaS key
export LLM_BASE_URL='https://litellm-litemaas.apps.prod.rhoai.rh-aiservices-bu.com/v1'
export LLM_MODEL='Qwen3.6-35B-A3B'
# Required for private GitHub repos (fine-grained PAT: Contents Read on this repo)
export GITHUB_TOKEN='github_pat_...'
export GITHUB_USER=maschind
./scripts/bootstrap.sh
```

Namespace: `agent-azuresdk-demo-main`

## Build and tag

```bash
# Run Tekton pipeline (see scripts or oc create -f)
# Then manually set the image tag in deploy/overlays/main/kustomization.yaml:
#   newTag: v0.1.0
# Commit, push; Argo syncs (or oc apply -k deploy/overlays/main)
```

## Click path

1. Open the Route URL printed by bootstrap / `oc get route -n agent-azuresdk-demo-main`
2. **Upload** a `.txt` / `.md` / `.pdf` (≤ 5 MB) with a distinctive fact (e.g. “Project Codename is BlueHeron”)
3. Ask: *What is the project codename in the knowledge base?*
4. Confirm the UI shows a `search_knowledge_base` tool call and a grounded answer
5. **Delete** the document and ask again — answer should no longer cite that fact

## Sample prompts

- “Summarize the uploaded documents.”
- “What facts did you find about &lt;topic in your file&gt;?”
- “Search the knowledge base for deployment steps.”

## Bootstrap v2 (`ogx`)

Checkout `ogx`, set `BRANCH=ogx`, run `./scripts/bootstrap.sh`.  
Namespace: `agent-azuresdk-demo-ogx`. Use the UI/env model switch for LiteMaaS vs in-cluster vLLM.
