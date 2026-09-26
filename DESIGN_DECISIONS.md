# Design Decisions — ML Model & Deployment Comparison

This document records every significant design decision made for this project, including what was chosen, what was rejected, and why. It is the authoritative reference for understanding why the system is built the way it is.

---

## Application Architecture

### Decision: No AWS-specific code in the application layer
**Chosen:** Business logic in `backend/` handlers and `frontend/` is cloud-agnostic. Each Lambda function has a thin `adapters.py` that is the only file importing `boto3` or referencing AWS resource names.
**Rejected:** Mixing AWS SDK calls directly into handler logic.
**Why:** Keeps business logic portable and integration-testable without AWS. Swapping cloud provider means rewriting only `adapters.py`, not the core logic.

### Decision: Python ZIP Packages with Pre-Built Layers for Lambda
**Chosen:** Lambda functions deployed as lightweight Python ZIP packages with a compiled Linux ML Layer (`scikit-learn`, `numpy`, `pandas`).
**Rejected:** Custom Docker container images for Lambda (Container Image Lambda).
**Why:** Lambda ZIP packaging with layers deploys significantly faster, eliminates local Docker build overhead during CI/CD, and avoids maintaining a custom ECR repository. For SageMaker serverless endpoints, the platform leverages AWS's official pre-built Scikit-Learn container (`683313688378.dkr.ecr.<region>.amazonaws.com/sagemaker-scikit-learn`) rather than building custom containers.

### Decision: No separate backend server
**Chosen:** API Gateway + Lambda functions *are* the backend. Terraform provisions them.
**Rejected:** A standalone FastAPI or Flask server running somewhere.
**Why:** There is nothing to keep running. Deploy the infrastructure, get the API. No server to maintain, scale, or pay for at idle.

---

## Infrastructure

### Decision: Terraform for all AWS resources
**Chosen:** One Terraform root config with reusable modules.
**Rejected:** Manual console setup, CDK, SAM.
**Why:** Reproducible, reviewable, version-controlled infrastructure. Destroying and recreating is one command.

### Decision: GitHub Actions — manual `workflow_dispatch` only
**Chosen:** Deploy and destroy workflows are manually triggered with an approval gate.
**Rejected:** Push-triggered CI/CD.
**Why:** Normal commits (README, screenshots, code iterations) should never touch AWS automatically. You explicitly approve every infrastructure change.

### Decision: Keyless authentication via GitHub Actions OIDC
**Chosen:** GitHub Actions OpenID Connect (OIDC) via `AWS_ROLE_ARN` with temporary STS credentials (`sts:AssumeRoleWithWebIdentity`). Default AWS region is Mumbai (`ap-south-1`).
**Rejected:** Storing static, long-lived AWS access keys (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) in GitHub Secrets.
**Why:** Modern security best practice. Eliminates secret rotation overhead, removes hardcoded static credentials, and scopes trust strictly to the GitHub repository.

### Decision: Secrets & Resource Wiring
**Chosen:** CI/CD role ARN → GitHub Secrets (`AWS_ROLE_ARN`). Sensitive runtime values → AWS Secrets Manager accessed via IAM role. Resource names (bucket, table, endpoints) → Terraform auto-wires them as Lambda environment variables from its own resource graph.
**Rejected:** Hardcoded values, manually typed Terraform variables.
**Why:** Nothing sensitive ever lives in code or is manually typed.

---

## ML / Inference

### Decision: Model format is `.pkl` only
**Chosen:** scikit-learn pickle format (`.pkl`).
**Rejected:** joblib (`.joblib`), ONNX, SageMaker-native formats.
**Why:** `.pkl` is the simplest and most common scikit-learn serialization format. Straightforward to load with a single `pickle.load()`.

### Decision: Targeted Lambda Layer for ML dependencies
**Chosen:** A single pre-configured Lambda Layer (`scikit-learn==1.4.2`, `numpy==1.26.4`, `pandas==2.2.2`) attached **strictly to the Lambdas that require ML execution or data manipulation** (`experiments`, `user_model_worker`, and `inference`). `autopilot` and `sagemaker_deployer` receive no layer.
**Rejected:** Attaching the heavy ML layer to all Lambda functions indiscriminately, or asking the user to upload dependencies.
**Why:** Keeps individual function packages lightweight and avoids unnecessary layer overhead on functions that only use Python's standard library and runtime `boto3`.

### Decision: SageMaker Serverless Inference for the user's model (path 2)
**Chosen:** SageMaker Serverless Inference endpoint.
**Rejected:** Persistent SageMaker real-time endpoint.
**Why:** Serverless scales to zero between calls. No persistent endpoint cost. This is a personal experimentation tool, not a production traffic handler.

### Decision: SageMaker Autopilot capped at 5 candidates
**Chosen:** `MaxCandidates = 5`, training job runs ~10–15 minutes.
**Rejected:** Uncapped Autopilot (can run for hours and train dozens of candidates).
**Why:** Keeps the experiment fast and cost-controlled. Five candidates gives enough variety for a meaningful comparison without excessive cost or waiting.

### Decision: Batch Transform for Autopilot candidate inference
**Chosen:** Run SageMaker Batch Transform jobs concurrently across the candidates (managed via a thread pool inside the asynchronous worker), pointing directly at each candidate's S3 model artifact.
**Rejected:** Deploying a temporary live SageMaker endpoint per candidate, inferring, then deleting (repeated 5×).
**Why:**
- Temporary real-time endpoints require explicit deletion calls — creating a significant cost risk if a deletion API call fails or the worker crashes.
- The test dataset is a one-off batch evaluation CSV, not a continuous stream of real-time traffic. A persistent real-time endpoint introduces unnecessary operational overhead.
- Batch Transform provisions compute on demand for the exact duration of the evaluation and terminates automatically upon completion, preventing orphaned resources or unexpected charges.
- Fits the asynchronous execution and polling pattern cleanly.

### Decision: Asynchronous inference execution (202 Accepted + background worker)
**Chosen:** `POST /experiments/{id}/compare` triggers an asynchronous Lambda self-invocation (via `InvocationType='Event'`) and returns HTTP `202 Accepted` immediately. The background worker runs parallel Batch Transform jobs across all candidates, calls the user model worker, and saves results to DynamoDB. The frontend polls `GET /experiments/{id}` until status is `completed`.
**Rejected:** Synchronous HTTP request waiting for all Batch Transform jobs to finish.
**Why:** API Gateway has a strict 29-second timeout. Running Batch Transform for multiple candidates takes several minutes and would inevitably time out a synchronous HTTP request.

### Decision: Two problem types only (classification / regression)
**Chosen:** Classification and Regression.
**Rejected:** Adding more types.
**Why:** SageMaker Autopilot for tabular data supports exactly these two types. There is no third option to offer that Autopilot would accept.

### Decision: Test data — optional user test CSV with automatic 80/20 split fallback
**Chosen:**
- **User-supplied test CSV (Optional):** Users can upload a dedicated labeled test CSV during experiment creation or on the optional Test Data configuration page.
- **Automatic 80/20 Holdout Split (Default Fallback):** If no test CSV is provided, the backend automatically runs `train_test_split(data, test_size=0.2, random_state=42)` on the training CSV.
**Rejected:** Synthetic test data generation (statistically weaker than real held-out data).
**Why:** Maximizes simplicity and scientific rigor. Real held-out data guarantees authentic ground-truth labels and real distributions without synthetic artifacts.

### Decision: Evaluation metrics per problem type (no ROC-AUC)
**Chosen:**
- **Classification:** Accuracy, F1 Score (weighted), Precision (weighted), Recall (weighted).
- **Regression:** R² Score, RMSE, MAE, MAPE.

**Rejected:** ROC-AUC.
**Why:** ROC-AUC requires probability scores (not just hard class predictions) from every inference path — Lambda, SageMaker Serverless, and all 5 Autopilot Batch Transform candidates. Probability output is not guaranteed to be available or in a consistent format across all paths. Dropping it keeps metric computation robust and uniform.

---

## Frontend

### Decision: Vanilla HTML + JavaScript + CSS (no framework, no build step)
**Chosen:** Single `index.html` + ES module JS files + vanilla CSS. Runs locally with `python -m http.server 8080`.
**Rejected:** React + Vite (originally chosen, then dropped).
**Why:** Node.js / npm had execution policy issues on the development machine. More importantly, a plain HTML/JS app has zero build dependencies, works immediately with Python's built-in server, and deploys to S3 as-is.

### Decision: Hash-based client-side routing (`#/`)
**Chosen:** `window.location.hash` for routing (`#/`, `#/new`, `#/experiment/id`, etc.).
**Rejected:** History API (`pushState`) routing.
**Why:** Hash routing works correctly when serving static files from Python's http.server or S3 without any server-side routing configuration. No 404 issues on refresh.

### Decision: Local mock API for development
**Chosen:** A `mock.js` module that intercepts all API calls and returns realistic fake data with simulated delays. Switched to real API by setting `API_BASE_URL` in `client.js`.
**Rejected:** Running AWS locally (LocalStack), or requiring a deployed backend before any frontend work.
**Why:** The frontend is fully demonstrable and interactive without any AWS account, credentials, or deployed infrastructure.

### Decision: Direct S3 Static Website Hosting (Option B)
**Chosen:** Direct S3 Static Website Hosting with SPA fallback (`index.html` error document).
**Rejected:** CloudFront Distribution (OAC) and running a dedicated Node/Python server on EC2/Lambda.
**Why:** The frontend consists of lightweight static assets (~50 KB). Direct S3 Static Website Hosting deploys instantly in <15 seconds, incurs ₹0 baseline cost at portfolio scale, completely bypasses new account CloudFront anti-abuse verification holds, and provides built-in client-side SPA routing via error document redirection.

### Decision: Light color theme
**Chosen:** White/light-gray backgrounds, indigo accents, dark text.
**Rejected:** Dark/glassmorphism theme (originally built, then replaced).
**Why:** My preference.

### Decision: Model upload is optional — two experiment modes
**Chosen:** The `.pkl` model upload is optional at experiment creation.
- **Full comparison mode** (model provided): all three inference paths run — Lambda, SageMaker Serverless, and all 5 Autopilot candidates.
- **Autopilot-only mode** (no model): only the 5 Autopilot candidates run. Lambda and SageMaker paths are silently skipped — no errors, no broken UI.

**Why:** A user may want to explore what Autopilot produces before committing to training their own model, or may simply not have a `.pkl` ready yet. Forcing a model upload as a prerequisite would block a meaningful use case. The app degrades gracefully rather than crashing.

**Implementation:** The `has_model` flag is passed in the creation request body. The comparison page's `buildRows()` function checks `exp.model?.model_s3_uri` and conditionally includes or excludes the Lambda and SageMaker rows. Mock and real API both respect this.

### Decision: Model upload is isolated to the Model Setup page
**Chosen:** The New Experiment form handles only experiment metadata (Name, Target Column, Problem Type) and CSV uploads (Training Dataset + optional Separate Test CSV). Model upload (`.pkl`) is located exclusively on the Model Setup page (`#/experiment/:id`).
**Rejected:** Asking for model upload twice (once at creation and again on setup).
**Why:** Eliminates duplicate prompts and confusing re-requests. If the user doesn't have a model, they can immediately run Autopilot from the setup page.

### Decision: Autopilot step is always visible on the Model Setup page
**Chosen:** The Autopilot card is shown regardless of whether a model was uploaded. It is labelled "Step 2" in Autopilot-only mode and "Step 3" in full mode.
**Rejected:** Hiding Autopilot entirely until a model is uploaded.
**Why:** Autopilot is the core of the comparison — it should never be gated behind the optional model upload.

### Decision: Test Data page removed from the user workflow
**Chosen:** No separate "Test Data" page or step. Test data is handled once upfront at experiment creation: user-supplied Test CSV (primary) or automatic 80/20 train/test split (fallback).
**Rejected:** A mandatory or separate Test Data page after model training.
**Why:** Eliminates duplicate test data prompts and avoids synthetic row generation.

### Decision: Dynamic metrics tailored to problem type (classification vs regression)
**Chosen:** Comparison dashboard renders metrics specific to the experiment's `problem_type`:
- **Classification:** Accuracy, F1 Score (weighted), Precision, Recall. Primary ranking metric is Accuracy.
- **Regression:** R² Score, RMSE, MAE, MAPE. Primary ranking metric is R².

**Rejected:** Showing fixed classification metrics for all experiments, or including ROC-AUC.
**Why:** Regression models do not produce discrete classes and have no "Accuracy" or "F1". ROC-AUC requires probability scores not reliably available across all paths.

### Decision: Direct model artifact download links
**Chosen:** Each candidate model (and the user's uploaded `.pkl` model) has a direct download button (`.tar.gz` for Autopilot candidate artifacts, `.pkl` for user models). In real AWS mode, pre-signed S3 download URLs are provided; in mock mode, a downloadable mock model file is generated on demand.
**Why:** After comparing candidates and identifying the best model, the user should be able to immediately download it for local use or deployment outside the workbench.

### Decision: Completed experiments focus on results without prompting re-runs
**Chosen:**
- On the Experiments list, clicking a completed experiment card navigates directly to its comparison results with a "View Results →" action.
- On the Comparison dashboard, the primary call to action after execution is "← Back to Experiments", with "↺ Re-run Comparison" available as a secondary utility.
- On the Model Setup page, a banner informs the user that results are ready and links directly to comparison.

**Rejected:** Prompting or forcing users to re-run the experiment after completion.
**Why:** Once an experiment completes, the user wants to analyze metrics, inspect predictions, and download models — not be prompted to run the same inference workload again.

---

## What Was Explicitly Rejected

| Idea | Reason rejected |
|---|---|
| Docker / containers | Not needed; adds complexity and cost |
| Persistent SageMaker endpoints for user model | Serverless is cheaper for sporadic use |
| Temporary SageMaker endpoints for Autopilot candidates | Cost risk, wrong tool for one-shot inference |
| Uncapped Autopilot | Too slow and expensive for an experiment tool |
| FastAPI / Flask backend server | Lambda + API Gateway is the backend |
| React + Vite | npm execution issues; vanilla JS is simpler and zero-dependency |
| AWS Cognito auth | Over-engineered for a personal project |
| Hardcoded AWS credentials | All secrets via GitHub Secrets or AWS Secrets Manager |
| Static long-lived AWS keys in CI/CD | Replaced with keyless GitHub Actions OIDC role assumption via `AWS_ROLE_ARN` |
| AWS Docs / Console links in sidebar | Not relevant to the user workflow |
| AWS Console redirect links in Results table | Adds clutter and irrelevant external navigation; results table focuses purely on model metrics and artifact downloads |
| "Max Autopilot Candidates" stat card | It's an internal constant, not a live metric |
| Pre-seeded fake experiments | Clutters the workspace; user wants a clean state with 0 experiments until created |
| Developer-facing notes in the UI | Belongs only in developer documentation / code comments |
| Prompting for model upload twice | Handled once on Model Setup page |
| Prompting for test data twice | Handled once on New Experiment form |
| Forcing model upload before Autopilot can start | Autopilot only needs the CSV; model is optional |
| Hiding Autopilot until model is uploaded | Autopilot is the core feature — should never be gated |
| Crashing / erroring when no model is present | App degrades gracefully into Autopilot-only mode |
| Fixed accuracy metric for regression tasks | Regression requires R², RMSE, MAE, MAPE |
| ROC-AUC metric | Requires probability scores not reliably available across all inference paths |
| Synthetic test data generation | Real data (user-supplied or auto-split) is always superior |
| Mandatory "Upload Test Data" step | Optional test CSV + 80/20 fallback covers all cases without blocking the user |
| Presenting test data override on Comparison page | The choice belongs on the New Experiment form, not buried after the workflow |
| Trapping trained Autopilot models in the cloud without export | User needs download links for candidate model artifacts |

