# Desktop labs: Docker Desktop, Podman Desktop, Rancher Desktop

Every FDE repo runs on all three desktops, first as containers, then on local Kubernetes. Do the lab on the desktop you have; doing it on a second one is the best way to understand what is engine-specific and what is not.

> Run only **one** desktop engine at a time. Two engines fight over port 8000, the Docker socket and kubectl contexts.

## Sizing

| Profile | CPU | RAM | Free disk |
| --- | --- | --- | --- |
| Assistant, `sample` index (6 filings + demo) | 1 vCPU | 1.5 GiB | 6 GiB |
| Assistant, `full` index (84 filings) | 2 vCPU | 3 GiB | 8 GiB |
| + Prometheus + Grafana | +1 vCPU | +1 GiB | +2 GiB |
| Desktop engine VM (Windows/macOS) | 2-4 CPUs | 4 GiB minimum, 6-8 GiB comfortable | 20 GiB |
| Local Kubernetes on top | +1 CPU | +2 GiB | +5 GiB |

These are starting estimates (not measured). The first `docker build` downloads six FinanceBench PDFs from GitHub, OCRs scanned pages and builds the index inside the build (a few minutes). Offline? `docker build --build-arg CORPUS=demo`. No GPU is needed: answers come from the Mistral API, or from the offline extractive mode without a key.

## 0. Prepare (all desktops)

```bash
git clone https://github.com/<you>/<repo>.git && cd <repo>
python3.12 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\Activate.ps1
make install && make test && make e2e                       # proves the code before containers
cp .env.example .env                                        # add MISTRAL_API_KEY for LLM answers (optional)
```

Windows users: run the labs from WSL2 (Ubuntu) for `make` and the shell syntax used here.

## 1A. Docker Desktop

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/), start it, and in **Settings → Resources** give it at least 2 CPUs, 4 GiB RAM and 20 GiB disk.
2. Containers:

   ```bash
   make up-docker            # docker compose build + up, then the smoke test
   docker compose -f deploy/compose/compose.yaml ps
   docker compose -f deploy/compose/compose.yaml logs --tail=50 api
   make down-docker
   ```

3. Kubernetes: **Settings → Kubernetes → Enable Kubernetes**, wait for the green light, then:

   ```bash
   make k8s-docker           # builds, applies the docker-desktop overlay, port-forwards, smoke test
   kubectl --context docker-desktop -n fde get pods,svc,hpa,pdb
   make k8s-delete
   ```

## 1B. Podman Desktop

1. Install [Podman Desktop](https://podman-desktop.io/). On Windows and macOS, create and start a Podman machine (2+ CPUs, 4+ GiB):

   ```bash
   podman machine init --cpus 2 --memory 4096 --disk-size 30
   podman machine start
   podman info | head
   ```

2. Pod (the Kubernetes-style path):

   ```bash
   make up-podman            # podman build + podman kube play deploy/podman/pod.yaml + smoke test
   podman pod ps && podman logs fde-02-llm-applications-api
   make down-podman
   ```

   Mistral key (optional): `kubectl create secret generic fde-02-llm-applications-mistral --from-literal=MISTRAL_API_KEY="$MISTRAL_API_KEY" --dry-run=client -o yaml | podman kube play -`, then `make up-podman` again. Without it the pod answers in extractive mode.

3. Compose alternative: `make up-podman-compose` (needs `podman compose`, which uses docker-compose or podman-compose).
4. Kubernetes with kind: install [kind](https://kind.sigs.k8s.io/), or install it through Podman Desktop's Kind integration, then:

   ```bash
   export KIND_EXPERIMENTAL_PROVIDER=podman
   make k8s-kind             # creates cluster 'fde', loads the image, applies the kind overlay, smoke test
   kind delete cluster --name fde
   ```

Notes: Podman is rootless by default, which matches the non-root image. On SELinux hosts (Fedora, RHEL) add `:Z` to bind mounts you create yourself.

## 1C. Rancher Desktop

1. Install [Rancher Desktop](https://rancherdesktop.io/). In **Preferences → Container Engine** choose **dockerd (moby)**; in **Preferences → Kubernetes** enable Kubernetes. Give the VM 2+ CPUs and 4+ GiB.
2. Rancher Desktop sets a `rancher-desktop` Docker context. Containers:

   ```bash
   docker context ls
   make up-rancher           # docker --context rancher-desktop compose up, then the smoke test
   make down-rancher
   ```

3. Kubernetes (k3s). With the moby engine, k3s sees images you build, so no registry is needed:

   ```bash
   make k8s-rancher          # build, apply the rancher-desktop overlay, port-forward, smoke test
   kubectl --context rancher-desktop -n fde get pods
   make k8s-delete
   ```

   Using the **containerd** engine instead? Build with `nerdctl --namespace k8s.io build -t fde-02-llm-applications:local .` and run `make k8s-rancher RANCHER="nerdctl --namespace k8s.io"`.

## 2. Observability (any desktop)

```bash
docker compose -f deploy/compose/compose.yaml --profile observability up -d --build
# Prometheus http://127.0.0.1:9090 · Grafana http://127.0.0.1:3000 → "FDE service overview"
```

## 3. Evidence for your portfolio

Capture: the smoke-test output, `kubectl get pods` showing Ready, a Grafana screenshot, and the commit SHA. Note which desktop and versions you used.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `port is already allocated` | Another engine or old stack on 8000 | Stop the other desktop; `make down-*`; or `HOST_PORT=8080 make up-docker` |
| Pod `ImagePullBackOff` on desktop Kubernetes | Cluster cannot see the local image | Docker/Rancher: build with the same engine as the cluster. kind: re-run `make k8s-kind` (it loads the image) |
| `CreateContainerConfigError` | Missing Secret referenced as required | The base marks the Secret optional; check you did not change that |
| Answers say "extractive (no model)" | `MISTRAL_API_KEY` not set in the container | Set it in `.env` (Compose), the Podman secret, or the Kubernetes Secret; check `/health/ready` → `answer_mode` |
| `ask` returns 503 "no index loaded" | Image built from the starter before the ingestion exercises were done | Finish weeks 12–13 and rebuild |
| Build fails downloading PDFs | No internet during the build | `--build-arg CORPUS=demo` |
| Container OOMKilled | `CORPUS=full` with a 1.5 GiB limit | Raise the memory limit to 3 GiB |
| Podman `kube play` port not reachable | Podman machine not running | `podman machine start` |
| Rancher `docker: context not found` | Engine set to containerd | Switch to dockerd (moby) or use `nerdctl` as above |
| Smoke test times out | Container crashed on start | `docker compose ... logs api`, `podman logs`, or `kubectl logs` |
