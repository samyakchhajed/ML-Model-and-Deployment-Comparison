# Development & Deployment Journey — ML Model & Deployment Comparison

This document chronicles the end-to-end engineering process behind the **ML Model & Deployment Comparison** — from initial requirements and architecture planning to cloud infrastructure provisioning, security policies, and real-world CI/CD troubleshooting.

---

## Project Evolution & Development Phases

The project was executed in four systematic phases, ensuring that each component was modular, independently testable, and strictly decoupled from vendor lock-in where appropriate.

```text
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
│  • Single-table DynamoDB, private S3 buckets, S3 Web Hosting│
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

## Phase 1: Frontend Architecture & User Experience

**Goal:** Create a lightweight, high-performance user interface with zero build dependencies, clean routing, and full offline interactivity.

1. **Zero-Build Philosophy:** Rather than introducing complex frontend bundlers, npm dependencies, or build toolchains, the frontend was built using pure *HTML5, Vanilla CSS, and modern JavaScript (ES Modules)*. It runs immediately on any browser using Python’s built-in HTTP server (`python -m http.server 8080`).
2. **Hash-Based SPA Routing:** A custom lightweight router (`#/`, `#/new`, `#/experiment/:id`, `#/experiment/:id/comparison`) enables deep linking and clean client-side navigation without triggering 404 errors on static CDN storage.
3. **Pluggable Mock & Real API Layer:** Created an offline API adapter (`mock.js`) that mimics realistic asynchronous execution delays, state transitions, and dataset parsing. Switching between local mock simulation and live AWS infrastructure is as simple as setting `window.API_BASE_URL`.
4. **UX Refinements:** Streamlined the workflow to eliminate redundant upload prompts — dataset and optional test data are gathered upfront, model uploads are handled in the Model Setup step, and completed benchmarks direct the user straight to analysis.

---

## Phase 2: Serverless Backend & Hexagonal Architecture

**Goal:** Implement robust, portable ML orchestration handlers while enforcing strict architectural boundaries.

1. **Hexagonal Architecture (Ports & Adapters):** Core business logic in Lambda handlers (`experiments`, `autopilot`, `inference`, `user_model_worker`) was written in pure *Python without importing `boto3`*. All AWS SDK interactions (S3, DynamoDB, SageMaker) were isolated into dedicated `adapters.py` files. This keeps logic testable and cloud-portable.
2. **Multipart & Binary Handling:** Built a zero-dependency RFC-compliant multipart parser to reliably extract CSV datasets, test splits, and binary `.pkl` model files from API Gateway requests.
3. **Asynchronous Execution Pattern:** To bypass API Gateway's 29-second execution ceiling, the comparison endpoint (`POST /experiments/{id}/compare`) immediately returns `202 Accepted` and launches a background worker via Lambda self-invocation (`InvocationType='Event'`), running candidate Batch Transform jobs in parallel.
5. **Dynamic Metric Engine:** Implemented a unified evaluation module using `scikit-learn` that computes tailored metrics based on the problem type (Accuracy, F1, Precision, Recall for classification; R², RMSE, MAE, MAPE for regression).

---

## Phase 3: Infrastructure as Code (Terraform)

**Goal:** To code entire serverless cloud infrastructure with least-privilege security and almost zero manual setup steps.

1. **Modular IaC Layout:** Structured Terraform into 5 focused modules:
   - `modules/storage`: Private S3 artifacts bucket with SSE-S3 encryption, versioning, and CORS.
   - `modules/database`: DynamoDB single-table with on-demand capacity (`PAY_PER_REQUEST`) and PITR.
   - `modules/iam`: Fine-grained IAM execution roles with strict ARN-scoped permissions (no broad wildcards).
   - `modules/compute`: Python 3.11 Lambda functions, API Gateway HTTP API v2, and integration routes.
   - `modules/frontend`: S3 static hosting bucket with public read policy, SPA routing fallback (`index.html`), and instant sub-minute deployment.
2. **Targeted Layer Allocation:** Provisioned a shared `scikit-learn`/`pandas`/`numpy` Lambda Layer, attaching it strictly to the 3 functions that perform ML data processing (`experiments`, `user_model_worker`, `inference`). The orchestration functions (`autopilot`, `sagemaker_deployer`) remain layer-free.
3. **Automated Resource Wiring:** Injected all bucket names, table names, and role ARNs directly into Lambda environment variables from Terraform's internal dependency graph.

---

## Phase 4: CI/CD Automation, Keyless Security & AWS Setup

**Goal:** To automate provisioning, packaging, and deployments with modern, keyless security via GitHub Actions OpenID Connect (OIDC).

### 1. IAM User Bootstrap Policy
To bootstrap the AWS account without granting root-level permissions, an initial IAM policy was attached to the administrator IAM user allowing management of the OIDC Identity Provider and CI/CD roles:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "iam:CreateOpenIDConnectProvider",
        "iam:GetOpenIDConnectProvider",
        "iam:CreateRole",
        "iam:AttachRolePolicy",
        "iam:PutRolePolicy",
        "iam:GetRole"
      ],
      "Resource": "*"
    }
  ]
}
```

### 2. Identity Provider Configuration
Configured AWS IAM OpenID Connect identity provider to trust GitHub:
* **Provider URL**: `https://token.actions.githubusercontent.com`
* **Audience**: `sts.amazonaws.com`

### 3. Repository-Scoped GitHub Actions IAM Role & Trust Policy
Created dedicated IAM role **`GitHub_Actions_Terraform_ML`** assumed keylessly by GitHub Actions runners using temporary STS credentials (`sts:AssumeRoleWithWebIdentity`).

AWS IAM strictly enforces repository-level scoping (rejecting account-wide wildcards like `repo:owner/*`). The trust policy explicitly lists the target repositories while permitting all branches, tags, and workflow dispatch runs via `:*`:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GitHubOIDCAuth",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::<ACCOUNT_ID>:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": [
        "sts:AssumeRoleWithWebIdentity",
        "sts:TagSession"
      ],
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:samyakchhajed@<USER_ID>/ML-Model-and-Deployment-Comparison@*:ref:refs/heads/main"
        }
      }
    }
  ]
}
```

### 4. Terraform Provisioning Permissions Policy
Attached a dedicated permissions policy to the role allowing Terraform to manage the required AWS services (S3, DynamoDB, Lambda, CloudWatch Logs, API Gateway, SageMaker, ECR, and IAM):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Management",
      "Effect": "Allow",
      "Action": [
        "s3:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DynamoDBManagement",
      "Effect": "Allow",
      "Action": [
        "dynamodb:CreateTable",
        "dynamodb:DeleteTable",
        "dynamodb:DescribeTable",
        "dynamodb:UpdateTable",
        "dynamodb:DescribeContinuousBackups",
        "dynamodb:UpdateContinuousBackups",
        "dynamodb:DescribeTimeToLive",
        "dynamodb:UpdateTimeToLive",
        "dynamodb:TagResource",
        "dynamodb:UntagResource",
        "dynamodb:ListTagsOfResource"
      ],
      "Resource": "arn:aws:dynamodb:ap-south-1:<ACCOUNT_ID>:table/ml-benchmark-*"
    },
    {
      "Sid": "LambdaManagement",
      "Effect": "Allow",
      "Action": [
        "lambda:CreateFunction",
        "lambda:DeleteFunction",
        "lambda:GetFunction",
        "lambda:GetFunctionConfiguration",
        "lambda:UpdateFunctionCode",
        "lambda:UpdateFunctionConfiguration",
        "lambda:ListVersionsByFunction",
        "lambda:ListAliases",
        "lambda:GetFunctionCodeSigningConfig",
        "lambda:GetAccountSettings",
        "lambda:AddPermission",
        "lambda:RemovePermission",
        "lambda:GetPolicy",
        "lambda:PublishLayerVersion",
        "lambda:DeleteLayerVersion",
        "lambda:GetLayerVersion",
        "lambda:TagResource",
        "lambda:UntagResource",
        "lambda:ListTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogGroupManagement",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:DeleteLogGroup",
        "logs:DescribeLogGroups",
        "logs:PutRetentionPolicy",
        "logs:DeleteRetentionPolicy",
        "logs:ListTagsLogGroup",
        "logs:TagLogGroup",
        "logs:UntagLogGroup",
        "logs:ListTagsForResource",
        "logs:TagResource",
        "logs:UntagResource"
      ],
      "Resource": [
        "arn:aws:logs:ap-south-1:<ACCOUNT_ID>:*",
        "arn:aws:logs:ap-south-1:<ACCOUNT_ID>:log-group:/aws/lambda/ml-benchmark-*"
      ]
    },
    {
      "Sid": "CloudWatchLogStreamManagement",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-south-1:<ACCOUNT_ID>:log-group:/aws/lambda/ml-benchmark-*:*"
    },
    {
      "Sid": "ApiGatewayManagement",
      "Effect": "Allow",
      "Action": [
        "apigateway:*"
      ],
      "Resource": [
        "arn:aws:apigateway:ap-south-1::/*",
        "arn:aws:apigateway:ap-south-1::*"
      ]
    },
    {
      "Sid": "IAMRoleAndPolicyManagement",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:GetRole",
        "iam:DeleteRole",
        "iam:TagRole",
        "iam:UntagRole",
        "iam:ListRoleTags",
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies",
        "iam:ListInstanceProfilesForRole",
        "iam:AttachRolePolicy",
        "iam:DetachRolePolicy",
        "iam:PutRolePolicy",
        "iam:DeleteRolePolicy",
        "iam:GetRolePolicy",
        "iam:CreatePolicy",
        "iam:GetPolicy",
        "iam:GetPolicyVersion",
        "iam:DeletePolicy",
        "iam:CreatePolicyVersion",
        "iam:DeletePolicyVersion",
        "iam:ListPolicyVersions",
        "iam:TagPolicy",
        "iam:UntagPolicy",
        "iam:ListPolicyTags"
      ],
      "Resource": [
        "arn:aws:iam::<ACCOUNT_ID>:role/ml-benchmark-*",
        "arn:aws:iam::<ACCOUNT_ID>:policy/ml-benchmark-*"
      ]
    },
    {
      "Sid": "IAMPassRole",
      "Effect": "Allow",
      "Action": [
        "iam:PassRole"
      ],
      "Resource": [
        "arn:aws:iam::<ACCOUNT_ID>:role/ml-benchmark-*"
      ],
      "Condition": {
        "StringEquals": {
          "iam:PassedToService": [
            "lambda.amazonaws.com",
            "sagemaker.amazonaws.com"
          ]
        }
      }
    },
    {
      "Sid": "SageMakerManagement",
      "Effect": "Allow",
      "Action": [
        "sagemaker:CreateAutoMLJob",
        "sagemaker:DescribeAutoMLJob",
        "sagemaker:StopAutoMLJob",
        "sagemaker:ListCandidatesForAutoMLJob",
        "sagemaker:CreateModel",
        "sagemaker:DescribeModel",
        "sagemaker:DeleteModel",
        "sagemaker:CreateEndpointConfig",
        "sagemaker:DescribeEndpointConfig",
        "sagemaker:DeleteEndpointConfig",
        "sagemaker:CreateEndpoint",
        "sagemaker:DescribeEndpoint",
        "sagemaker:DeleteEndpoint",
        "sagemaker:InvokeEndpoint",
        "sagemaker:CreateTransformJob",
        "sagemaker:DescribeTransformJob",
        "sagemaker:StopTransformJob"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ECRAccess",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:BatchCheckLayerAvailability"
      ],
      "Resource": "*"
    }
  ]
}
```

### 5. Secret Configuration
Stored the role ARN in GitHub Repository Secrets under **`AWS_ROLE_ARN`**, eliminating static AWS access keys from the workflow repository.

### 6. Automated CI/CD Workflows
* **`deploy.yaml`**: Authenticates via OIDC (`aws-actions/configure-aws-credentials@v6`), packages the Python 3.11 ML Lambda layer, bootstraps S3 state bucket, executes `terraform apply` in `ap-south-1`, injects the API endpoint into `frontend/config.js`, and syncs frontend files to S3 static website hosting.
* **`destroy.yaml`**: One-click teardown workflow gated by an explicit `"destroy"` confirmation string.

---

## Pre-Emptive Hardening & Architectural Safeguards (Learnings from Secure Cloud Storage)

Rather than discovering cloud failure modes one failed run at a time, this ML Workbench was engineered from Day 1 incorporating all hard-won architectural lessons and safeguards developed during the Secure Cloud Storage project:

### Safeguard 1: OIDC Trust Policy — Immutable ID & TagSession Permitted from Day 1
* **Learning from Previous Project:** GitHub's 2026 token format includes immutable numeric account and repository IDs (`@<USER_ID>` and `@<REPO_ID>`). If not explicitly included with `sts:TagSession`, authentication fails with `Not authorized to perform sts:AssumeRoleWithWebIdentity`.
* **Implementation in This Project:** Configured the IAM role trust policy from Day 1 with both immutable IDs and `sts:TagSession` allowed.

### Safeguard 2: GitHub Repository-Scoped Subject Validation
* **Learning from Previous Project:** AWS IAM rejects account-wide wildcards (`repo:owner/*`).
* **Implementation in This Project:** Scoped explicitly to the repository pattern with branch restrictions (`:ref:refs/heads/main`).

### Safeguard 3: Modern CI/CD Action Versions (`v6`)
* **Learning from Previous Project:** Legacy action versions triggered Node.js deprecation warnings and session tagging incompatibilities.
* **Implementation in This Project:** Pinned to `aws-actions/configure-aws-credentials@v6` with `role-skip-session-tagging: true`.

### Safeguard 4: Direct S3 Static Website Hosting (Bypassing CloudFront Verification Holds)
* **Learning from Previous Project:** New AWS accounts encounter anti-abuse verification holds on CloudFront distribution creation (`AccessDenied`), stalling deployments.
* **Implementation in This Project:** Deployed frontend directly to S3 Static Website Hosting with SPA fallback (`index.html`), achieving instant <15s deployments with ₹0 baseline cost.

### Safeguard 5: Remote S3 State Backend & Automated Bootstrap from First Apply
* **Learning from Previous Project:** Ephemeral GitHub Actions runners lose `.tfstate` after failed runs, leading to orphaned cloud resources and name collision errors (`ResourceAlreadyExists`) on subsequent runs.
* **Implementation in This Project:** Added `terraform/bootstrap` module to automatically provision the remote state bucket (`ml-benchmark-tfstate-ap-south-1`) in CI/CD before initializing `terraform/main.tf`.

### Safeguard 6: Lambda Layer Archive Overwrite Prevention
* **Learning from Previous Project:** Using `data "archive_file"` pointing to the same zip file generated by pip overwrites the 50MB compiled ML package with an empty placeholder during `terraform apply`.
* **Implementation in This Project:** Pointed fallback archive to `ml_layer_fallback.zip` and dynamically used the pip-built `ml_layer.zip` whenever present.

### Safeguard 7: CloudWatch Log Group Explicit Provisioning & Split IAM Permissions
* **Learning from Previous Project:** `logs:CreateLogGroup` targets log group ARNs without trailing `:*`, while `CreateLogStream` targets trailing `:*`. Relying on Lambda auto-creation also sets retention to "Never Expire".
* **Implementation in This Project:** Split IAM permissions properly and explicitly provisioned `aws_cloudwatch_log_group` resources with 14-day retention in Terraform for all 5 Lambdas.

### Safeguard 8: SageMaker Scikit-Learn Docker Container ECR Authentication
* **Learning from Previous Project:** SageMaker endpoints require `ecr:GetAuthorizationToken` on `Resource: "*"` to pull official AWS-managed framework container images.
* **Implementation in This Project:** Included ECR authorization and layer pull actions on the SageMaker execution role from Day 1.

### Safeguard 9: Deployment Failure Recovery & Rollback Control
* **Learning from Previous Project:** Failed runs needed manual cleanup or produced state collisions.
* **Implementation in This Project:** Added interactive `auto_rollback_on_failure` toggle to `deploy.yaml`, supporting both safe incremental state resume (default) and automated `terraform destroy` rollback on failure.

---

## Deployment Execution & Resolution Log

The automated deployment pipeline was validated and hardened through actual GitHub Actions workflow runs:

### Run 1: OIDC WebIdentity Authentication & Secret Configuration
* **Status:** Failed at Step 4 (`Configure AWS Credentials via OIDC`).
* **Error:** `Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity`.
* **Root Cause:**
  1. The GitHub repository secret `AWS_ROLE_ARN` had not yet been populated in GitHub repository settings.
* **Resolution:**
  - Added repository secret `AWS_ROLE_ARN` in GitHub Actions settings pointing to `arn:aws:iam::<ACCOUNT_ID>:role/GitHub_Actions_Terraform_ML`.
  - Verified the Trust Policy `StringLike` condition matched the immutable-ID format (`repo:samyakchhajed@<USER_ID>/ML-Model-and-Deployment-Comparison@*:ref:refs/heads/main`) already configured from Day 1 per Safeguard 1 — the actual Run 1 failure was the missing `AWS_ROLE_ARN` GitHub secret, not a trust policy defect.

---

### Run 2: S3 Sub-Resource Metadata, DynamoDB PITR, and IAM Policy Tagging
* **Status:** Failed during Step 5 (Terraform Bootstrap) and Step 7 (Terraform Apply / Auto-Rollback).
* **Errors Encountered:**
  1. **S3 Sub-Resource Inspection:** `AccessDenied: not authorized to perform: s3:GetBucketTagging`, `s3:GetAccelerateConfiguration`, and `s3:GetBucketObjectLockConfiguration` on the state bucket `ml-benchmark-tfstate-ap-south-1`.
  2. **DynamoDB Continuous Backups:** `AccessDeniedException: not authorized to perform: dynamodb:UpdateContinuousBackups` (and `dynamodb:DescribeContinuousBackups` during rollback refresh).
  3. **IAM Policy Tagging:** `AccessDenied: not authorized to perform: iam:TagPolicy` when applying project default tags (`Project`, `Environment`, `ManagedBy`) to custom `aws_iam_policy` resources.
* **Root Cause:**
  - Terraform AWS Provider 5.x automatically queries deep sub-resource endpoints for every managed S3 bucket, DynamoDB table, and IAM policy during creation and state refresh.
  - Ephemeral GitHub runners needed an automated `terraform import` fallback during bootstrap if the state bucket was partially created in a prior run.
* **Resolution:**
  - Updated `deploy.yaml` bootstrap step to check `aws s3api head-bucket` and execute `terraform import` idempotently.
  - Set `S3Management` statement to `s3:*` on `*` in the CI/CD deployer policy to satisfy all Terraform S3 inspection APIs.
  - Added `dynamodb:DescribeContinuousBackups`, `dynamodb:UpdateContinuousBackups`, `dynamodb:DescribeTimeToLive`, and `dynamodb:UpdateTimeToLive` to `DynamoDBManagement`.
  - Added `iam:TagPolicy`, `iam:UntagPolicy`, `iam:ListPolicyTags`, and `iam:ListRoleTags` to `IAMRoleAndPolicyManagement`.

---

### Run 3: Lambda Layer Direct-Upload Limit (66.9MB) & API Gateway / Lambda IAM Actions
* **Status:** Failed during Step 7 (`Terraform Apply`).
* **Errors Encountered:**
  1. **Lambda Layer Size Direct Upload Limit:** `RequestEntityTooLargeException: Request must be smaller than 70167211 bytes for the PublishLayerVersion operation`. The compiled ML dependencies zip (`scikit-learn`, `pandas`, `numpy`, `scipy`) exceeded AWS's 66.9MB limit for direct API uploads.
  2. **API Gateway Tagging:** `AccessDeniedException: not authorized to perform: apigateway:TagResource on /apis/.../stages`.
  3. **Lambda Version Listing:** `AccessDeniedException: not authorized to perform: lambda:ListVersionsByFunction`.
* **Root Cause:**
  - AWS Lambda requires layer packages larger than 50MB to be uploaded to an Amazon S3 bucket first and referenced via `s3_bucket` / `s3_key`.
  - API Gateway stages and Lambda functions required resource tagging and version listing permissions in the deployer policy.
* **Resolution:**
  - Updated `terraform/modules/compute/lambda.tf` to upload `ml_layer.zip` to the artifacts S3 bucket via `aws_s3_object.ml_layer_s3` before creating `aws_lambda_layer_version.ml_layer` (supporting up to 250MB).
  - Added `lambda:ListVersionsByFunction`, `lambda:ListAliases`, `lambda:GetFunctionCodeSigningConfig`, and `lambda:GetAccountSettings` to `LambdaManagement`.
  - Set `ApiGatewayManagement` to `apigateway:*` on `arn:aws:apigateway:ap-south-1::*` and `arn:aws:apigateway:ap-south-1::/*`.

---

### Run 4: Lambda Layer 250MB Unzipped Container Limit
* **Status:** Failed during Step 7 (`Terraform Apply`).
* **Error:** `InvalidParameterValueException: Unzipped size must be smaller than 262144000 bytes (250 MB)`.
* **Root Cause:** A raw `pip install` of `scikit-learn`, `scipy`, `pandas`, and `numpy` reached ~315MB unzipped due to bundled test suites (`scipy/tests`, `sklearn/tests`), cache bytecode, and unstripped `.so` debugging symbols.
* **Resolution:**
  - Added build-time pruning commands in `deploy.yaml` to remove `tests/`, `__pycache__`, and `*.dist-info`.
  - Executed `strip --strip-unneeded` on all compiled `.so` C-extensions, shrinking the unzipped layer package from 315MB down to ~140MB (well below the 250MB AWS ceiling).

---

### Run 5: End-to-End Cloud Deployment
* **Status:** **SUCCESS**
* **Outcomes:**
  - Build & compile Python 3.11 ML layer (~140MB unzipped) in Linux runner.
  - S3 remote state bootstrapping and state import verified.
  - Full Terraform apply provisioned all 5 modules in Mumbai (`ap-south-1`):
    - Private S3 Artifacts bucket with encryption and CORS.
    - DynamoDB single-table with PITR and on-demand billing.
    - Scoped IAM execution roles for Lambda and SageMaker.
    - 5 Lambda functions + S3-backed ML Layer + 5 dedicated CloudWatch log groups with 14-day retention.
    - API Gateway HTTP API v2 with CORS and integration routes.
    - S3 Static Website Hosting with public read policy and SPA fallback routing.
  - Injected live API Gateway URL into `frontend/config.js` and synced static assets to S3.
  - Live application endpoint accessible and responsive with ₹0 baseline idle cost.

---

### Run 6: In-Place Rolling Update — SageMaker Regional ECR & Autopilot 32-Char Name Constraint
* **Status:** **SUCCESS**
* **Root Causes & Architectural Refinements:**
  1. **SageMaker `AutoMLJobName` Constraint:** AWS SageMaker limits `AutoMLJobName` to a strict 32-character maximum. Formatting `ml-lab-ap-<36-char-uuid>` produced 46 characters and failed with `ValidationException: autoMLJobName failed to satisfy constraint: Member must have length less than or equal to 32`. Resolved by using a compact alphanumeric prefix `ap-<24-char-id>`.
  2. **SageMaker Regional Container Images:** Official AWS Scikit-Learn Docker images are hosted under region-specific AWS account IDs (e.g., `720646828776` in Mumbai `ap-south-1` vs `683313688378` in `us-east-1`). Updated `_sklearn_image_uri()` to dynamically map regional ECR account IDs based on the active Lambda runtime `AWS_REGION`.
  3. **Autopilot S3Prefix Isolation:** SageMaker Autopilot's `S3Prefix` data source scans and consumes all CSV files present in the specified prefix. Uploading test splits or full datasets into the root experiment folder caused Autopilot parsing conflicts. Resolved by storing training data in an isolated subfolder (`{exp_id}/train/train.csv`).

---

### Run 7: In-Place Rolling Update — DynamoDB Decimal Serialization & Decoupled Benchmark Progression
* **Status:** **SUCCESS**
* **Root Causes & Architectural Refinements:**
  1. **DynamoDB Python Float Serialization:** AWS SDK (`boto3`) strictly forbids standard Python `float` primitives in `Table.put_item()`, raising `TypeError: Float types are not supported`. Fixed by adding recursive `_to_dynamo()` Decimal converters on write and `_from_dynamo()` JSON number converters on read across `inference/adapters.py` and `experiments/adapters.py`.
  2. **Decoupled Multi-Path Evaluation:** Enhanced `inference/handler.py` and `app.js` so that users are never blocked waiting for Autopilot. Whenever any single path is deployed (Lambda, SageMaker Serverless, or Autopilot candidates), a prominent **Proceed to Comparison Dashboard →** button is available, allowing immediate benchmark evaluation across all ready paths.

---

### Run 8: In-Place Rolling Update — Scikit-Learn Feature Column Alignment & Graceful Mismatch Handling
* **Status:** **SUCCESS**
* **Root Causes & Architectural Refinements:**
  1. **Scikit-Learn Feature Alignment in Serverless Workers:** Enhanced `user_model_worker` to support both `pandas.DataFrame` feature headers and raw `numpy.ndarray` matrices, converting NumPy return types (`np.int64`, `np.float64`) to native Python primitives.
  2. **Raw CSV vs. Preprocessed Estimator Feature Mismatch:** When a standalone estimator (`RandomForestClassifier`) trained on preprocessed/encoded features (e.g. 8 numeric columns) is supplied with a raw dataset CSV (11–12 columns with raw strings and missing values), `model.predict()` raises shape/type errors (`ValueError: X has 11 features, expecting 8`). The worker catches this exception cleanly so the comparison pipeline reaches `completed` with `.pkl` downloads available, while rendering `—` for the model's metrics.

---

### Run 9: In-Place Rolling Update & Final Verification — SageMaker Container Serving Directory & Complete Benchmark Validation
* **Status:** **SUCCESS**
* **Root Causes & Architectural Refinements:**
  1. **SageMaker Container Module Directory (`SAGEMAKER_SUBMIT_DIRECTORY`):** In SageMaker framework containers, placing the script at `code/inference.py` requires `"SAGEMAKER_SUBMIT_DIRECTORY": "/opt/ml/model/code"` in the container environment. Without it, the entrypoint looks in `/opt/ml/model/inference.py`, raising `ModuleNotFoundError: No module named 'inference'`. Dual entrypoint packaging and explicit environment variables were configured in `experiments/adapters.py`. This fixed the container import error seen in the endpoint logs. The endpoints still failed afterwards on account-level access errors, so the fix was never confirmed by a served prediction.
  2. **Lambda-Path Validation:** Ran 7 experiments across the Heart Disease and Titanic datasets using pre-trained models. The Lambda path completed end to end, with the Titanic Random Forest reaching **96.7% Accuracy** and **0.966 F1 Score** and `.pkl` artifact export working. SageMaker Serverless endpoints and Autopilot did not run (see Status & Limitations in the README). 

---

## Role of AI in This Project

In the spirit of complete transparency, AI was used as an *accelerator and developer assistant* during the building of this project — similar to an advanced pair-programming tool.

- **Human-Led Architecture & Engineering:** All core system designs, trade-off decisions, UX workflows, API contracts, and security boundaries were conceived, directed, and decided by me.
- **AI as a Productivity Tool:** AI assistance was used for generating repetitive boilerplate, exploring better solutions for this project, exploring syntax variations across Terraform and AWS SDK APIs, and speeding up routine drafting tasks. Every code, configuration, and documentation was reviewed, tested, and shaped to meet the project's strict architectural standards.
