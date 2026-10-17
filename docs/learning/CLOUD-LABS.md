# Cloud labs: AWS, Azure, GCP

Each stack runs the assistant image (with its baked index) on the cloud's cheapest managed container service, stores `MISTRAL_API_KEY` in the cloud's secret store, and creates a budget alert.

- [AWS: ECS Fargate](../../terraform/aws/README.md)
- [Azure: Container Apps](../../terraform/azure/README.md)
- [GCP: Cloud Run](../../terraform/gcp/README.md)

## Rules

1. **Sandbox only.** Use a dedicated sandbox account, subscription or project.
2. **Budget:** USD 50 per month per cloud for infrastructure; LLM tokens are billed by Mistral separately (set a spend limit in the Mistral console).
3. **Plan first**, then apply, then **destroy** at the end of every lab.
4. **Never commit** state files, plans or `.tfvars` (the key goes in as a variable or straight into the secret store).

## Typical lab flow (about 45 minutes)

```bash
docker build -t fde-02-llm-applications:local .        # add --platform linux/amd64 on Apple silicon
make tf-<cloud>-init
# apply 1: registry, secret store (with the key), identity, budget  ·  push  ·  apply 2: the service
python scripts/smoke_test.py --base-url <url printed by terraform output>
# ask three questions in the UI; note latency (and cold start on scale-to-zero)
make tf-<cloud>-destroy
```

## Evidence for your portfolio

Plan summary, smoke-test output, a UI screenshot with a cited answer and a refusal from the cloud URL, cold-start and warm latency, and the destroy output.
