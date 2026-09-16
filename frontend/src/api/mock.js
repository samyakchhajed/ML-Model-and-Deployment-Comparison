// Local mock API — in-memory stateful store for offline development

const delay = (ms = 400) => new Promise(r => setTimeout(r, ms))

let experiments = []
let nextId = 1

const AUTOPILOT_ALGORITHMS = [
  'XGBoost',
  'LightGBM',
  'CatBoost',
  'RandomForest',
  'LinearLearner',
  'MLP',
  'AutoGluon',
]

const CLF_ALGORITHMS = AUTOPILOT_ALGORITHMS
const REG_ALGORITHMS = AUTOPILOT_ALGORITHMS

function shuffle(arr) {
  return [...arr].sort(() => Math.random() - 0.5)
}

function randRange(min, max, decimals = 3) {
  const val = Math.random() * (max - min) + min
  return Number(val.toFixed(decimals))
}

export const mock = {
  'GET /experiments': async () => {
    await delay(200)
    return { experiments }
  },

  'POST /experiments': async (body) => {
    await delay(500)
    const id = `exp-${String(nextId++).padStart(3, '0')}`
    const exp = {
      id,
      name: body.name || 'Untitled Experiment',
      target_col: body.target_col || 'target',
      problem_type: body.problem_type || 'classification',
      created_at: new Date().toISOString(),
      status: 'created',
      split: {
        train_s3_uri: `s3://ml-lab-artifacts/${id}/train.csv`,
        test_features_s3_uri: `s3://ml-lab-artifacts/${id}/test_features.csv`,
        test_labels_s3_uri: `s3://ml-lab-artifacts/${id}/test_labels.csv`,
        test_source: body.has_test_data ? 'user_supplied' : 'auto_split',
      },
      model: null,
      autopilot: { job_name: null, status: null, candidates: [] },
      results: null,
    }
    experiments.unshift(exp)
    return exp
  },

  'GET /experiments/:id': async (_, { id }) => {
    await delay(150)
    const exp = experiments.find(e => e.id === id)
    if (!exp) throw new Error('Experiment not found')
    return exp
  },

  'POST /experiments/:id/model': async (_, { id }) => {
    await delay(600)
    const exp = experiments.find(e => e.id === id)
    if (!exp) throw new Error('Experiment not found')
    exp.model = {
      model_s3_uri: `s3://ml-lab-artifacts/${id}/model.pkl`,
      lambda_fn_name: null,
      sagemaker_serverless_endpoint: null,
    }
    exp.status = 'model_uploaded'
    return exp
  },

  'POST /experiments/:id/deploy/lambda': async (_, { id }) => {
    await delay(1000)
    const exp = experiments.find(e => e.id === id)
    if (!exp) throw new Error('Experiment not found')
    if (!exp.model) exp.model = { model_s3_uri: `s3://ml-lab-artifacts/${id}/model.pkl` }
    exp.model.lambda_fn_name = `ml-lab-${id}-lambda-fn`
    exp.status = 'lambda_deployed'
    return exp
  },

  'POST /experiments/:id/deploy/sagemaker': async (_, { id }) => {
    await delay(1200)
    const exp = experiments.find(e => e.id === id)
    if (!exp) throw new Error('Experiment not found')
    if (!exp.model) exp.model = { model_s3_uri: `s3://ml-lab-artifacts/${id}/model.pkl` }
    exp.model.sagemaker_serverless_endpoint = `ml-lab-${id}-serverless-endpoint`
    exp.status = 'sagemaker_deployed'
    return exp
  },

  'POST /experiments/:id/autopilot/start': async (_, { id }) => {
    await delay(600)
    const exp = experiments.find(e => e.id === id)
    if (!exp) throw new Error('Experiment not found')

    const isReg = exp.problem_type === 'regression'
    const algPool = isReg ? REG_ALGORITHMS : CLF_ALGORITHMS
    const chosenAlgs = shuffle(algPool).slice(0, 5)

    exp.autopilot = {
      job_name: `autopilot-${id}-${Date.now().toString().slice(-4)}`,
      status: 'InProgress',
      candidates: [],
    }
    exp.status = 'autopilot_running'

    // Simulate async job completion
    setTimeout(() => {
      exp.autopilot.status = 'Completed'
      exp.autopilot.candidates = chosenAlgs.map((alg, i) => ({
        name: `Candidate-${i + 1}`,
        algorithm: alg,
        model_s3_uri: `s3://ml-lab-artifacts/${id}/autopilot/candidate-${i + 1}/model.tar.gz`,
      }))
    }, 4500)

    return exp
  },

  'GET /experiments/:id/autopilot/status': async (_, { id }) => {
    await delay(200)
    const exp = experiments.find(e => e.id === id)
    if (!exp) throw new Error('Experiment not found')
    return { status: exp.autopilot.status, candidates: exp.autopilot.candidates }
  },

  'POST /experiments/:id/compare': async (_, { id }) => {
    await delay(1800)
    const exp = experiments.find(e => e.id === id)
    if (!exp) throw new Error('Experiment not found')

    const hasModel = !!exp.model?.model_s3_uri
    const isReg = exp.problem_type === 'regression'
    const candidates = exp.autopilot?.candidates?.length
      ? exp.autopilot.candidates
      : (isReg ? REG_ALGORITHMS : CLF_ALGORITHMS).slice(0, 5).map((alg, i) => ({
          name: `Candidate-${i + 1}`,
          algorithm: alg,
          model_s3_uri: `s3://ml-lab-artifacts/${id}/autopilot/candidate-${i + 1}/model.tar.gz`,
        }))

    if (isReg) {
      const candidateResults = candidates.map((c, i) => {
        const baseR2 = randRange(0.81, 0.93, 3)
        const baseRMSE = randRange(12.0, 35.0, 2)
        const baseMAE = Number((baseRMSE * 0.75).toFixed(2))
        const baseMAPE = randRange(5.0, 11.0, 1)
        const preds = Array.from({ length: 8 }, () => randRange(15.0, 95.0, 1))
        return {
          name: c.name || `Candidate-${i + 1}`,
          algorithm: c.algorithm,
          predictions: preds,
          r2: baseR2,
          rmse: baseRMSE,
          mae: baseMAE,
          mape: baseMAPE,
          model_s3_uri: c.model_s3_uri || `s3://ml-lab-artifacts/${id}/autopilot/candidate-${i + 1}/model.tar.gz`,
        }
      })

      // Sort to identify best model
      const sorted = [...candidateResults].sort((a, b) => b.r2 - a.r2)
      const best = sorted[0]

      const lambdaR2 = hasModel ? randRange(0.82, 0.90, 3) : null
      const lambdaRMSE = hasModel ? randRange(15.0, 30.0, 2) : null
      const lambdaMAE = hasModel ? Number((lambdaRMSE * 0.75).toFixed(2)) : null
      const lambdaMAPE = hasModel ? randRange(6.0, 10.0, 1) : null
      const userPreds = hasModel ? Array.from({ length: 8 }, () => randRange(15.0, 95.0, 1)) : []

      exp.results = {
        ...(hasModel ? {
          lambda_predictions: userPreds,
          lambda_r2: lambdaR2,
          lambda_rmse: lambdaRMSE,
          lambda_mae: lambdaMAE,
          lambda_mape: lambdaMAPE,
          sagemaker_predictions: userPreds,
          sagemaker_r2: lambdaR2,
          sagemaker_rmse: lambdaRMSE,
          sagemaker_mae: lambdaMAE,
          sagemaker_mape: lambdaMAPE,
        } : {}),
        candidate_results: candidateResults,
        best_model: (hasModel && lambdaR2 > best.r2) ? 'Your Model (Lambda / SageMaker)' : `${best.name} (${best.algorithm})`,
        best_metric_name: 'R²',
        best_metric_value: (hasModel && lambdaR2 > best.r2) ? lambdaR2 : best.r2,
      }
    } else {
      // Classification
      const candidateResults = candidates.map((c, i) => {
        const acc = randRange(0.81, 0.94, 3)
        const f1 = Number((acc - randRange(0.005, 0.02, 3)).toFixed(3))
        const prec = Number((acc + randRange(0.005, 0.02, 3)).toFixed(3))
        const rec = Number((acc - randRange(0.005, 0.015, 3)).toFixed(3))
        const preds = Array.from({ length: 8 }, () => Math.round(Math.random()))
        return {
          name: c.name || `Candidate-${i + 1}`,
          algorithm: c.algorithm,
          predictions: preds,
          accuracy: acc,
          f1,
          precision: prec,
          recall: rec,
          model_s3_uri: c.model_s3_uri || `s3://ml-lab-artifacts/${id}/autopilot/candidate-${i + 1}/model.tar.gz`,
        }
      })

      const sorted = [...candidateResults].sort((a, b) => b.accuracy - a.accuracy)
      const best = sorted[0]

      const lambdaAcc = hasModel ? randRange(0.82, 0.91, 3) : null
      const lambdaF1 = hasModel ? Number((lambdaAcc - 0.01).toFixed(3)) : null
      const lambdaPrec = hasModel ? Number((lambdaAcc + 0.01).toFixed(3)) : null
      const lambdaRec = hasModel ? Number((lambdaAcc - 0.005).toFixed(3)) : null
      const userPreds = hasModel ? Array.from({ length: 8 }, () => Math.round(Math.random())) : []

      exp.results = {
        ...(hasModel ? {
          lambda_predictions: userPreds,
          lambda_accuracy: lambdaAcc,
          lambda_f1: lambdaF1,
          lambda_precision: lambdaPrec,
          lambda_recall: lambdaRec,
          sagemaker_predictions: userPreds,
          sagemaker_accuracy: lambdaAcc,
          sagemaker_f1: lambdaF1,
          sagemaker_precision: lambdaPrec,
          sagemaker_recall: lambdaRec,
        } : {}),
        candidate_results: candidateResults,
        best_model: (hasModel && lambdaAcc > best.accuracy) ? 'Your Model (Lambda / SageMaker)' : `${best.name} (${best.algorithm})`,
        best_metric_name: 'Accuracy',
        best_metric_value: (hasModel && lambdaAcc > best.accuracy) ? lambdaAcc : best.accuracy,
      }
    }

    exp.status = 'completed'
    return exp
  },
}
