# ML Model & Deployment Comparison

A serverless, cloud-native benchmarking platform on AWS that lets you evaluate custom machine learning models against automated *Amazon SageMaker Autopilot* candidates across multiple deployment paradigms.

---

## Overview

When building machine learning solutions for tabular datasets, data teams constantly face two critical questions:
1. **Model Quality:** How does my hand-tuned model compare against automated SageMaker AutoML models on identical held-out test data?
2. **Serving & Deployment Trade-offs:** Should the model be served via lightweight, serverless compute (*AWS Lambda*) or a dedicated managed inference service (*Amazon SageMaker Serverless Inference*)?

This tool lets you explore both questions in one place. You bring a tabular dataset and optionally your pre-trained scikit-learn model (`.pkl`), and the platform handles the execution: training AutoML candidate models, preparing inference endpoints, running concurrent batch evaluations, and calculating comparison metrics.

---

## How It Works

```
                        Tabular Dataset (.csv) + Optional Model (.pkl)
                                              │
                    ┌─────────────────────────┴─────────────────────────┐
                    ▼                                                   ▼
         User Model Deployment Paths                          SageMaker Autopilot
      ┌───────────────────────────────┐                  ┌───────────────────────────────┐
      │  Path 1: AWS Lambda           │                  │  AutoML Training Pipeline     │
      │  (Serverless Python runtime)  │                  │  (Max 5 candidate models)     │
      ├───────────────────────────────┤                  └──────────────┬────────────────┘
      │  Path 2: SageMaker Serverless │                                 │
      │  (Dedicated ML endpoint)      │                                 ▼
      └──────────────┬────────────────┘                  ┌───────────────────────────────┐
                     │                                   │  Path 3: SageMaker Batch      │
                     │                                   │  Transform (Concurrent jobs)  │
                     │                                   └──────────────┬────────────────┘
                     └────────────────────────┬─────────────────────────┘
                                              ▼
                             Unified Multi-Path Evaluation
                     (Classification & Regression Metric Engine)
                                              ▼
                             Side-by-Side Comparison Matrix
                        + Direct Model Artifact Downloads (.tar.gz / .pkl)
```

The platform evaluates predictions across *three distinct execution paths* using identical test data:

1. **AWS Lambda Execution:** Direct inference in a serverless Python execution environment equipped with an attached scikit-learn/pandas ML Layer.
2. **Amazon SageMaker Serverless Inference:** Dedicated endpoint packaging the user model with containerized inference logic, providing autoscaling serverless inference.
3. **Amazon SageMaker Autopilot via Batch Transform:** Fully automated candidate generation (e.g., XGBoost, LightGBM, CatBoost, Multi-Layer Perceptrons) evaluated concurrently using SageMaker Batch Transform jobs.

---

## Key Features

### 1. Dual Experimentation Modes
- **Full Comparison Mode:** Evaluates your custom model alongside SageMaker Autopilot candidates across all three serving paths.
- **Autopilot-Only Mode:** If you do not have a trained model yet, upload only your dataset and let Autopilot discover and benchmark the top 5 model architectures automatically.

### 2. Flexible Test Data Strategy
- **User-Supplied Test Set:** Upload a dedicated labeled test CSV during experiment creation for strict benchmark consistency.
- **Automatic 80/20 Holdout:** If no test CSV is provided, the platform automatically performs an 80/20 train/test holdout split server-side, routing 80% to Autopilot for training and preserving 20% for pure unbiased evaluation.

### 3. Problem-Specific Evaluation Metrics
Metrics adapt dynamically to the task type:
- **Classification:** Accuracy, Weighted F1 Score, Weighted Precision, Weighted Recall.
- **Regression:** R² Score, Root Mean Squared Error (RMSE), Mean Absolute Error (MAE), Mean Absolute Percentage Error (MAPE).

### 4. Portable Model Artifact Downloads
Winning isn't just about viewing scores. Every Autopilot candidate model artifact (`model.tar.gz`) and uploaded user model (`.pkl`) includes direct, secure download links, allowing data scientists to immediately export the best performing pipeline for further local evaluation or deployment.

### 5. Asynchronous, Non-Blocking Execution
Long-running workloads (AutoML training and concurrent Batch Transform evaluations) run asynchronously with immediate `202 Accepted` acknowledgments and polling states, preventing API timeouts and keeping the interface responsive.

---

## Architecture Summary

The platform is built on a *serverless, pay-per-use* architecture deployed in the Mumbai (`ap-south-1`) region (compute scales to zero when inactive, with minimal baseline storage and database cost):

- **Frontend:** Zero-build single-page application (vanilla HTML5, modern CSS, ES Modules) hosted directly via *Amazon S3 Static Website Hosting* with instant sub-minute deployments and client-side SPA routing fallback.
- **API Surface:** *Amazon API Gateway HTTP API (v2)* with built-in CORS and payload format 2.0 proxy integrations.
- **Compute Layer:** *AWS Lambda (Python 3.11)* built with a hexagonal architecture isolating pure business logic handlers from cloud adapters.
- **Data & Artifacts:** *Amazon DynamoDB* (single-table design with on-demand capacity) for metadata and benchmark results; *Amazon S3* (private SSE-S3 encrypted) for datasets and model binaries.
- **ML Workloads:** *Amazon SageMaker* (AutoML, Serverless Endpoints, and Batch Transform).
- **Security:** Keyless authentication via *GitHub Actions OpenID Connect (OIDC)* and strict least-privilege IAM policies.

---

## Screenshots

Visual walkthroughs and interface screenshots illustrating the experiments dashboard, dataset configuration, model deployment tracking, and side-by-side comparison results are organized in the `screenshots/` directory.
