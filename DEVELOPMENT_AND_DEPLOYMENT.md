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
Created dedicated IAM role **`GitHubActions-Terraform-Pipeline`** assumed keylessly by GitHub Actions runners using temporary STS credentials (`sts:AssumeRoleWithWebIdentity`).

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
        "s3:CreateBucket",
        "s3:DeleteBucket",
        "s3:ListBucket",
        "s3:GetBucketLocation",
        "s3:GetBucketPolicy",
        "s3:PutBucketPolicy",
        "s3:DeleteBucketPolicy",
        "s3:GetBucketWebsite",
        "s3:PutBucketWebsite",
        "s3:DeleteBucketWebsite",
        "s3:GetBucketPublicAccessBlock",
        "s3:PutBucketPublicAccessBlock",
        "s3:GetBucketVersioning",
        "s3:PutBucketVersioning",
        "s3:GetEncryptionConfiguration",
        "s3:PutEncryptionConfiguration",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
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
        "apigateway:GET",
        "apigateway:POST",
        "apigateway:PUT",
        "apigateway:PATCH",
        "apigateway:DELETE"
      ],
      "Resource": "arn:aws:apigateway:ap-south-1::/*"
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
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies",
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
        "iam:ListPolicyVersions"
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

## Role of AI in This Project

In the spirit of complete transparency, AI was used as an *accelerator and developer assistant* during the building of this project — similar to an advanced pair-programming tool.

- **Human-Led Architecture & Engineering:** All core system designs, trade-off decisions, UX workflows, API contracts, and security boundaries were conceived, directed, and decided by me.
- **AI as a Productivity Tool:** AI assistance was used for generating repetitive boilerplate, exploring better solutions for this project, exploring syntax variations across Terraform and AWS SDK APIs, and speeding up routine drafting tasks. Every code, configuration, and documentation was reviewed, tested, and shaped to meet the project's strict architectural standards.
