# One entry point for every path: local Python, three desktops, local Kubernetes,
# OpenShift, Helm and three clouds. Run `make help` for the list.
#
# Desktops:  Docker Desktop (docker), Podman Desktop (podman), Rancher Desktop
#            (dockerd/moby engine via the rancher-desktop docker context, or nerdctl).
# Run only ONE desktop engine at a time to avoid port and socket clashes.

SHELL      := /bin/bash
APP        ?= fde-02-llm-applications
LOADENV    := set -a; [ -f .env ] && . ./.env; set +a;
IMAGE      ?= $(APP):local
HOST_PORT  ?= 8000
BASE_URL   ?= http://127.0.0.1:$(HOST_PORT)
PY         ?= python
COMPOSE    := deploy/compose/compose.yaml
NAMESPACE  ?= fde
RANCHER    ?= docker --context rancher-desktop   # or: nerdctl --namespace k8s.io
KIND_NAME  ?= fde

.DEFAULT_GOAL := help

## ---- Local Python -------------------------------------------------------
install: ## Create the dev environment (also needs the tesseract binary for OCR)
	$(PY) -m pip install -e ".[dev]"

lint: ## Ruff lint (starter repos ignore unused-import noise from TODO stubs)
	@if [ -f .starter ]; then ruff check . --extend-ignore F401,F841,ARG001; else ruff check .; fi

fmt: ## Auto-format and fix imports
	ruff check . --fix && ruff format .

test: ## Unit and API tests (reference: with coverage gate; starter: skips exercises)
	@if [ -f .starter ]; then pytest -m "not exercise"; else pytest --cov --cov-report=term-missing; fi

exercises: ## Run the learner exercise tests (they fail until the TODOs are done)
	pytest -m exercise

structure: ## Check the required repo structure is present
	$(PY) scripts/check_structure.py

run: ## Run the API locally with reload
	uvicorn app.main:app --reload --port $(HOST_PORT)

E2E_DIR ?= /tmp/$(APP)-e2e
e2e: ## Index the offline demo filings into a temp dir, start the API, smoke test, stop it
	@rm -rf $(E2E_DIR); mkdir -p $(E2E_DIR); \
	 if [ ! -f .starter ]; then filing-assistant --data-dir $(E2E_DIR)/data \
	   --index-dir $(E2E_DIR)/index ingest --demo --embed lsa >/dev/null; fi; \
	 DATA_DIR=$(E2E_DIR)/data INDEX_DIR=$(E2E_DIR)/index MISTRAL_API_KEY= \
	   uvicorn app.main:app --port $(HOST_PORT) > /tmp/$(APP)-e2e.log 2>&1 & echo $$! > /tmp/$(APP)-e2e.pid; \
	 $(PY) scripts/smoke_test.py --base-url $(BASE_URL); rc=$$?; \
	 kill $$(cat /tmp/$(APP)-e2e.pid) 2>/dev/null; exit $$rc

smoke: ## Run the smoke checks against BASE_URL (any running deployment)
	$(PY) scripts/smoke_test.py --base-url $(BASE_URL)

## ---- Corpus, index and evaluation --------------------------------------
download: ## Download FinanceBench questions and all 84 PDFs (pinned commit, ~160 MB)
	filing-assistant download

ingest: ## Build index/ from FinanceBench PDFs + the demo filings, with offline LSA vectors
	filing-assistant ingest --financebench --demo --embed lsa

ingest-demo: ## Build index/ from the fictional demo filings only (offline, seconds)
	filing-assistant ingest --demo --embed lsa

embed-mistral: ## Add mistral-embed vectors to index/ (needs MISTRAL_API_KEY; costs money)
	filing-assistant embed mistral

ask: ## Ask a question: make ask Q="What was 3M's capex in FY2018?"
	filing-assistant ask "$(Q)"

eval: ## Retrieval, refusal (dev and test halves) and extractive answer evaluation
	filing-assistant eval-retrieval
	filing-assistant eval-refusal --split dev
	filing-assistant eval-refusal --split test
	filing-assistant eval-answers --answer-mode extractive

eval-llm: ## Answer accuracy with Mistral and an LLM judge on the test half (needs a key)
	filing-assistant eval-answers --answer-mode llm --judge --split test

mcp: ## Run the MCP tool server on stdio (for Claude Desktop, Claude Code, other MCP clients)
	filing-assistant mcp

starter: ## Generate the learner starter repo into ../<repo>-starter
	$(PY) scripts/make_starter.py --out ../$(notdir $(CURDIR))-starter --force

## ---- Docker Desktop ------------------------------------------------------
up-docker: ## Docker Desktop: build and start with Compose, then smoke test
	@$(LOADENV) docker compose -f $(COMPOSE) up -d --build
	$(MAKE) smoke

down-docker: ## Docker Desktop: stop and remove the Compose stack
	docker compose -f $(COMPOSE) down -v

## ---- Podman Desktop ------------------------------------------------------
up-podman: ## Podman Desktop: build the image and run the pod with `podman kube play`
	podman build -t localhost/$(IMAGE) .
	podman kube play --replace deploy/podman/pod.yaml
	$(MAKE) smoke

down-podman: ## Podman Desktop: stop and remove the pod
	podman kube down deploy/podman/pod.yaml

up-podman-compose: ## Podman Desktop alternative: run the same Compose file with podman compose
	@$(LOADENV) podman compose -f $(COMPOSE) up -d --build
	$(MAKE) smoke

## ---- Rancher Desktop -----------------------------------------------------
up-rancher: ## Rancher Desktop (dockerd/moby engine): build and start with Compose
	@$(LOADENV) $(RANCHER) compose -f $(COMPOSE) up -d --build
	$(MAKE) smoke

down-rancher: ## Rancher Desktop: stop the Compose stack
	$(RANCHER) compose -f $(COMPOSE) down -v

## ---- Local Kubernetes ----------------------------------------------------
k8s-docker: ## Docker Desktop Kubernetes: build, deploy overlay, port-forward, smoke
	docker build -t $(IMAGE) .
	kubectl --context docker-desktop apply -k deploy/kubernetes/overlays/docker-desktop
	kubectl --context docker-desktop -n $(NAMESPACE) rollout status deploy/$(APP) --timeout=120s
	$(MAKE) _portforward CONTEXT=docker-desktop

k8s-rancher: ## Rancher Desktop k3s (moby engine shares the image store): deploy and smoke
	$(RANCHER) build -t $(IMAGE) .
	kubectl --context rancher-desktop apply -k deploy/kubernetes/overlays/rancher-desktop
	kubectl --context rancher-desktop -n $(NAMESPACE) rollout status deploy/$(APP) --timeout=120s
	$(MAKE) _portforward CONTEXT=rancher-desktop

k8s-kind: ## kind (works with Podman Desktop: KIND_EXPERIMENTAL_PROVIDER=podman)
	kind get clusters | grep -qx $(KIND_NAME) || kind create cluster --name $(KIND_NAME)
	podman build -t localhost/$(IMAGE) . 2>/dev/null || docker build -t localhost/$(IMAGE) .
	(podman save localhost/$(IMAGE) 2>/dev/null || docker save localhost/$(IMAGE)) > /tmp/$(APP).tar
	kind load image-archive /tmp/$(APP).tar --name $(KIND_NAME)
	kubectl --context kind-$(KIND_NAME) apply -k deploy/kubernetes/overlays/kind
	kubectl --context kind-$(KIND_NAME) -n $(NAMESPACE) rollout status deploy/$(APP) --timeout=180s
	$(MAKE) _portforward CONTEXT=kind-$(KIND_NAME)

k8s-delete: ## Delete the app from the current kube context
	kubectl delete namespace $(NAMESPACE) --ignore-not-found

_portforward:
	@kubectl --context $(CONTEXT) -n $(NAMESPACE) port-forward svc/$(APP) $(HOST_PORT):80 > /tmp/$(APP)-pf.log 2>&1 & echo $$! > /tmp/$(APP)-pf.pid; \
	 sleep 3; $(MAKE) smoke; rc=$$?; kill $$(cat /tmp/$(APP)-pf.pid) 2>/dev/null; exit $$rc

## ---- OpenShift and Helm --------------------------------------------------
k8s-openshift: ## Render the OpenShift overlay (apply with `oc apply -k deploy/openshift` when logged in)
	kubectl kustomize deploy/openshift

helm-lint: ## Lint and render the Helm chart
	helm lint deploy/helm/$(APP)
	helm template $(APP) deploy/helm/$(APP) > /dev/null

## ---- Clouds (Terraform/OpenTofu) -----------------------------------------
TF ?= terraform
tf-%-init: ## Init a cloud stack: make tf-aws-init | tf-azure-init | tf-gcp-init
	$(TF) -chdir=terraform/$* init

tf-%-plan: ## Plan a cloud stack (safe; no changes): make tf-aws-plan
	$(TF) -chdir=terraform/$* plan -out=tfplan

tf-%-apply: ## Apply a planned stack (costs money; stay inside the lab budget)
	$(TF) -chdir=terraform/$* apply tfplan

tf-%-destroy: ## Destroy a cloud stack at the end of every lab
	$(TF) -chdir=terraform/$* destroy

tf-validate: ## Format-check and validate all three clouds without credentials
	@for c in aws azure gcp; do $(TF) -chdir=terraform/$$c init -backend=false -input=false >/dev/null && \
	  $(TF) -chdir=terraform/$$c validate || exit 1; done; $(TF) fmt -check -recursive terraform

## ---- Docs ----------------------------------------------------------------
diagrams: ## Render Mermaid sources to SVG (needs Node.js)
	@mkdir -p diagrams/rendered
	@for f in diagrams/source/*.mmd; do npx -y @mermaid-js/mermaid-cli -i $$f -o diagrams/rendered/$$(basename $${f%.mmd}).svg; done

clean: ## Remove caches and local artefacts
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov dist build **/__pycache__

help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_%-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n",$$1,$$2}'

.PHONY: install lint fmt test exercises structure run e2e smoke starter up-docker down-docker \
        up-podman down-podman up-podman-compose up-rancher down-rancher k8s-docker k8s-rancher \
        k8s-kind k8s-delete _portforward k8s-openshift helm-lint tf-validate diagrams clean help
