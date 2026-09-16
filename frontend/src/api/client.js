import { mock } from './mock.js'

// Set this to your API Gateway URL to switch from mock to real AWS backend.
// Leave as empty string or configure window.API_BASE_URL for deployed environments.
const API_BASE_URL = window.API_BASE_URL || ''

const USE_MOCK = !API_BASE_URL

function matchMock(method, path) {
  for (const key of Object.keys(mock)) {
    const [kMethod, kPattern] = key.split(' ')
    if (kMethod !== method) continue
    const regex = new RegExp('^' + kPattern.replace(/:([^/]+)/g, '(?<$1>[^/]+)') + '$')
    const m = path.match(regex)
    if (m) return { handler: mock[key], params: m.groups || {} }
  }
  return null
}

async function request(method, path, body, file, formData) {
  if (USE_MOCK) {
    const match = matchMock(method, path)
    if (!match) throw new Error(`No mock for ${method} ${path}`)
    return match.handler(body, match.params)
  }
  const url = `${API_BASE_URL}${path}`
  const opts = { method, headers: {} }
  if (formData) {
    // Pre-built FormData (multi-file uploads e.g. dataset + test CSV + model)
    opts.body = formData
  } else if (file) {
    const fd = new FormData()
    fd.append('file', file)
    if (body) Object.entries(body).forEach(([k, v]) => fd.append(k, v))
    opts.body = fd
  } else if (body) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const res = await fetch(url, opts)
  // 202 Accepted = async job started, not an error
  if (!res.ok && res.status !== 202) { const e = await res.json().catch(() => ({})); throw new Error(e.message || `HTTP ${res.status}`) }
  return res.json()
}

export const api = {
  experiments: {
    list:   ()                          => request('GET',  '/experiments'),
    get:    (id)                        => request('GET',  `/experiments/${id}`),
    // datasetFile required; testCsvFile + modelFile optional
    create: (body, datasetFile, testCsvFile, modelFile) => {
      if (USE_MOCK) return request('POST', '/experiments', { ...body, has_model: !!modelFile, has_test_data: !!testCsvFile }, datasetFile)
      const fd = new FormData()
      fd.append('file', datasetFile)
      if (testCsvFile) fd.append('test_csv', testCsvFile)
      if (modelFile)   fd.append('model',    modelFile)
      Object.entries({ ...body, has_model: !!modelFile, has_test_data: !!testCsvFile }).forEach(([k, v]) => fd.append(k, v))
      return request('POST', '/experiments', null, null, fd)
    },
  },
  model:    { upload:    (id, file) => request('POST', `/experiments/${id}/model`, {}, file) },
  deploy:   {
    lambda:    (id) => request('POST', `/experiments/${id}/deploy/lambda`),
    sagemaker: (id) => request('POST', `/experiments/${id}/deploy/sagemaker`),
  },
  autopilot: {
    start:  (id) => request('POST', `/experiments/${id}/autopilot/start`),
    status: (id) => request('GET',  `/experiments/${id}/autopilot/status`),
  },
  compare: {
    run:     (id) => request('POST', `/experiments/${id}/compare`),   // may return 202
    results: (id) => request('GET',  `/experiments/${id}/results`),
  },
}
