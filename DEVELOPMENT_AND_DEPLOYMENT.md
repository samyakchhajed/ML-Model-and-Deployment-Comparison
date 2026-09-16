# Development & Deployment Journey

This document chronicles the end-to-end engineering process behind the **ML Model & Deployment Comparison** — from initial requirements and architecture planning to cloud infrastructure provisioning and CI/CD automation.

---

## Project Evolution & Development Phases

The project was executed in four systematic phases, ensuring that each component was modular, independently testable, and strictly decoupled from vendor lock-in where appropriate.

```
┌─────────────────────────────────────────────────────────────┐
│  Phase 1: Zero-Build Frontend & Mock Architecture           │
│  • Vanilla HTML5, CSS custom properties, ES Module router   │
│  • Local development runtime with built-in mock simulation  │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│  Phase 2: Serverless Backend & Hexagonal Design             │
│  • Pure Python business logic isolated from AWS SDK (boto3) │
│  • Asynchronous 202 comparison pipeline + worker pattern    │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│  Phase 3: Infrastructure as Code with Terraform             │
│  • Single-table DynamoDB, private S3 buckets, CloudFront OAC│
│  • Targeted Lambda Layer allocation & least-privilege IAM   │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│  Phase 4: Keyless CI/CD & Automated Cloud Deployment        │
│  • GitHub Actions OIDC integration (AWS STS WebIdentity)    │
│  • Automated ML layer compilation & one-click deployment    │
└─────────────────────────────────────────────────────────────┘
```

---

### Phase 1: Frontend Architecture & User Experience

**Goal:** Create a lightweight, high-performance user interface with zero build dependencies, clean routing, and full offline interactivity.

1. **Zero-Build Philosophy:** Rather than introducing complex frontend bundlers, npm dependencies, or build toolchains, the frontend was built using pure *HTML5, Vanilla CSS, and modern JavaScript (ES Modules)*. It runs immediately on any browser using Python’s built-in HTTP server (`python -m http.server 8080`).
2. **Hash-Based SPA Routing:** A custom lightweight router (`#/`, `#/new`, `#/experiment/:id`, `#/experiment/:id/comparison`) enables deep linking and clean client-side navigation without triggering 404 errors on static CDN storage.
3. **Pluggable Mock & Real API Layer:** Created an offline API adapter (`mock.js`) that mimics realistic asynchronous execution delays, state transitions, and dataset parsing. Switching between local mock simulation and live AWS infrastructure is as simple as setting `window.API_BASE_URL`.
4. **UX Refinements:** Streamlined the workflow to eliminate redundant upload prompts — dataset and optional test data are gathered upfront, model uploads are handled in the Model Setup step, and completed benchmarks direct the user straight to analysis.

---

### Phase 2: Serverless Backend & Hexagonal Architecture

**Goal:** Implement robust, portable ML orchestration handlers while enforcing strict architectural boundaries.

1. **Hexagonal Architecture (Ports & Adapters):** Core business logic in Lambda handlers (`experiments`, `autopilot`, `inference`, `user_model_worker`) was written in pure *Python without importing `boto3`*. All AWS SDK interactions (S3, DynamoDB, SageMaker) were isolated into dedicated `adapters.py` files. This keeps logic testable and cloud-portable.
2. **Multipart & Binary Handling:** Built a zero-dependency RFC-compliant multipart parser to reliably extract CSV datasets, test splits, and binary `.pkl` model files from API Gateway requests.
3. **Asynchronous Execution Pattern:** To bypass API Gateway's 29-second execution ceiling, the comparison endpoint (`POST /experiments/{id}/compare`) immediately returns `202 Accepted` and launches a background worker via Lambda self-invocation (`InvocationType='Event'`), running candidate Batch Transform jobs in parallel.
4. **Dynamic Metric Engine:** Implemented a unified evaluation module using `scikit-learn` that computes tailored metrics based on the problem type (Accuracy, F1, Precision, Recall for classification; R², RMSE, MAE, MAPE for regression).

---

### Phase 3: Infrastructure as Code (Terraform)

**Goal:** To code entire serverless cloud infrastructure with least-privilege security and almost zero manual setup steps.

1. **Modular IaC Layout:** Structured Terraform into 5 focused modules:
   - `modules/storage`: Private S3 artifacts bucket with SSE-S3 encryption, versioning, and CORS.
   - `modules/database`: DynamoDB single-table with on-demand capacity (`PAY_PER_REQUEST`) and PITR.
   - `modules/iam`: Fine-grained IAM execution roles with strict ARN-scoped permissions (no broad wildcards).
   - `modules/compute`: Python 3.11 Lambda functions, API Gateway HTTP API v2, and integration routes.
   - `modules/frontend`: S3 static hosting bucket, CloudFront Origin Access Control (OAC), and CDN distribution.
2. **Targeted Layer Allocation:** Provisioned a shared `scikit-learn`/`pandas`/`numpy` Lambda Layer, attaching it strictly to the 3 functions that perform ML data processing (`experiments`, `user_model_worker`, `inference`). The orchestration functions (`autopilot`, `sagemaker_deployer`) remain layer-free.
3. **Automated Resource Wiring:** Injected all bucket names, table names, and role ARNs directly into Lambda environment variables from Terraform's internal dependency graph.

---

### Phase 4: CI/CD Automation & Keyless Cloud Deployment

**Goal:** To automate provisioning, packaging, and deployments with modern, keyless security.

1. **Keyless Authentication via GitHub OIDC:** Configured GitHub Actions to authenticate to AWS using *OpenID Connect (OIDC)* and AWS Security Token Service (`sts:AssumeRoleWithWebIdentity`). This eliminates long-lived static AWS access keys from repository secrets.
2. **Automated Build & Deployment Pipeline (`deploy.yaml`):**
   - Packages Linux `manylinux2014_x86_64` Python 3.11 wheels for the Lambda Layer.
   - Runs `terraform init`, `terraform validate`, and `terraform apply` targeting *Mumbai (`ap-south-1`)*.
   - Dynamically extracts the deployed API Gateway URL and injects it into `frontend/config.js`.
   - Syncs static assets to S3 and triggers a CloudFront CDN cache invalidation.
3. **Safe Teardown Pipeline (`destroy.yaml`):** Implemented a one-click teardown workflow with an explicit `"destroy"` string confirmation gate, ensuring cloud resources can be torn down immediately to avoid unnecessary costs.

---

## Role of AI in This Project

In the spirit of complete transparency, AI was used as an *accelerator and developer assistant* during the building of this project — similar to an advanced pair-programming tool.

- **Human-Led Architecture & Engineering:** All core system designs, trade-off decisions, UX workflows, API contracts, and security boundaries were conceived, directed, and decided by me.

- **AI as a Productivity Tool:** AI assistance was used for generating repetitive boilerplate, exploring better solutions for this project, exploring syntax variations across Terraform and AWS SDK APIs, and speeding up routine drafting tasks. Every code, configuration, and documentation was reviewed, tested, and shaped to meet the project's strict architectural standards.
