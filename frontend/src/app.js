import { api } from './api/client.js'

// ─── Utilities ────────────────────────────────────────────────────────────────

const root = () => document.getElementById('app-root')
const html = (strings, ...vals) => strings.reduce((a, s, i) => a + s + (vals[i] ?? ''), '')
const esc = v => String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
const fmt = iso => new Date(iso).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' })

function statusBadge(status) {
  const map = {
    created:            ['badge-neutral',  'Created'],
    model_uploaded:     ['badge-info',     'Model Ready'],
    lambda_deployed:    ['badge-info',     'Lambda Deployed'],
    sagemaker_deployed: ['badge-info',     'SageMaker Ready'],
    autopilot_running:  ['badge-warning',  'Autopilot Running'],
    running:            ['badge-warning',  'Running'],
    completed:          ['badge-success',  'Completed'],
    failed:             ['badge-danger',   'Failed'],
    InProgress:         ['badge-warning',  'In Progress'],
    Completed:          ['badge-success',  'Completed'],
    Failed:             ['badge-danger',   'Failed'],
  }
  const [cls, label] = map[status] || ['badge-neutral', status || 'Unknown']
  return `<span class="badge ${cls}"><span class="badge-dot"></span>${label}</span>`
}

function problemChip(type) {
  const isClass = type === 'classification'
  const style = isClass
    ? 'background:rgba(99,102,241,0.12);color:var(--accent-bright);border:1px solid rgba(99,102,241,0.25)'
    : 'background:rgba(20,184,166,0.12);color:var(--teal);border:1px solid rgba(20,184,166,0.25)'
  return `<span style="${style};padding:2px 10px;border-radius:100px;font-size:11px;font-weight:600">
    ${isClass ? '🏷 Classification' : '📈 Regression'}
  </span>`
}

function testSourceBadge(source) {
  const isUser = source === 'user_supplied'
  const label = isUser ? '📂 User Test CSV' : '✂️ Auto 80/20 Split'
  const color = isUser ? 'var(--accent-bright)' : 'var(--success)'
  const bg = isUser ? 'rgba(99,102,241,0.12)' : 'rgba(16,185,129,0.12)'
  const border = isUser ? 'rgba(99,102,241,0.25)' : 'rgba(16,185,129,0.25)'

  return `<span style="padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600;background:${bg};color:${color};border:1px solid ${border}">
    ${label}
  </span>`
}

function predChips(preds = []) {
  const shown = preds.slice(0, 6)
  const extra = preds.length > 6 ? `<span class="pred-chip" style="opacity:.5">+${preds.length-6}</span>` : ''
  return `<div style="display:flex;flex-wrap:wrap;gap:4px">${shown.map(p => `<span class="pred-chip">${esc(p)}</span>`).join('')}${extra}</div>`
}

function spinner(size = 16) {
  return `<span class="spinner" style="width:${size}px;height:${size}px"></span>`
}

function alert(type, icon, content) {
  return `<div class="alert alert-${type}"><span class="alert-icon">${icon}</span><div>${content}</div></div>`
}

// ─── Router ───────────────────────────────────────────────────────────────────

function getRoute() {
  const hash = location.hash.replace(/^#\/?/, '') || ''
  if (!hash) return { page: 'experiments', params: {} }
  if (hash === 'new') return { page: 'new', params: {} }
  const expModel = hash.match(/^experiment\/([^/]+)$/)
  if (expModel) return { page: 'model-setup', params: { id: expModel[1] } }
  const expComp = hash.match(/^experiment\/([^/]+)\/comparison$/)
  if (expComp) return { page: 'comparison', params: { id: expComp[1] } }
  return { page: 'experiments', params: {} }
}

function updateActiveNav() {
  const hash = location.hash.replace(/^#\/?/, '') || ''
  document.querySelectorAll('.nav-link[data-route]').forEach(el => {
    el.classList.toggle('active', el.dataset.route === hash || (hash === '' && el.dataset.route === ''))
  })
}

async function navigate(path) {
  location.hash = path ? `#/${path}` : '#/'
}

window.addEventListener('hashchange', () => { updateActiveNav(); render() })
window.addEventListener('DOMContentLoaded', () => { updateActiveNav(); render() })

async function render() {
  const { page, params } = getRoute()
  const pageFn = { experiments, 'new': newExperiment, 'model-setup': modelSetup, comparison }[page]
  if (pageFn) await pageFn(params)
}

// ─── Page: Experiments ────────────────────────────────────────────────────────

async function experiments() {
  root().innerHTML = `<div class="empty-state">${spinner(32)}</div>`
  try {
    const { experiments: exps } = await api.experiments.list()
    const completed = exps.filter(e => e.status === 'completed').length
    const running   = exps.filter(e => ['running','autopilot_running'].includes(e.status)).length

    root().innerHTML = html`
      <div>
        <div class="page-header" style="display:flex;align-items:flex-start;justify-content:space-between">
          <div>
            <h1>Experiments</h1>
            <p>Upload your dataset and compare your model against SageMaker Autopilot</p>
          </div>
          <a href="#/new" class="btn btn-primary btn-lg" id="new-experiment-btn">➕ New Experiment</a>
        </div>

        <div class="stats-row">
          <div class="stat-card"><div class="stat-value">${exps.length}</div><div class="stat-label">Total Experiments</div></div>
          <div class="stat-card">
            <div class="stat-value" style="background:linear-gradient(135deg,#10b981,#14b8a6);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">${completed}</div>
            <div class="stat-label">Completed</div>
          </div>
          <div class="stat-card">
            <div class="stat-value" style="background:linear-gradient(135deg,#f59e0b,#ef4444);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text">${running}</div>
            <div class="stat-label">Running</div>
          </div>
        </div>

        ${exps.length === 0 ? `
          <div class="empty-state">
            <div class="empty-state-icon">⚗️</div>
            <h3>No experiments yet</h3>
            <p>Create your first experiment to get started</p>
            <a href="#/new" class="btn btn-primary" id="first-experiment-btn">Start your first experiment</a>
          </div>
        ` : `
          <div class="experiment-grid">
            ${exps.map(exp => {
              const isDone = exp.status === 'completed' || !!exp.results
              const link = isDone ? `#/experiment/${exp.id}/comparison` : `#/experiment/${exp.id}`
              const actionText = isDone ? 'View Results →' : 'Continue Setup →'
              const testSource = exp.split?.test_source || exp.test_source
              return `
                <a href="${link}" class="experiment-card" id="experiment-card-${exp.id}">
                  <div class="experiment-card-header">
                    <div>
                      <div class="experiment-card-name">${esc(exp.name)}</div>
                      <div style="margin-top:6px">${problemChip(exp.problem_type)}</div>
                    </div>
                    ${statusBadge(exp.status)}
                  </div>
                  <div class="experiment-card-meta">
                    <div class="experiment-meta-item">
                      <div class="experiment-meta-label">Target</div>
                      <div class="experiment-meta-value" style="font-family:monospace">${esc(exp.target_col)}</div>
                    </div>
                    <div class="experiment-meta-item">
                      <div class="experiment-meta-label">Test Source</div>
                      <div class="experiment-meta-value">${testSourceBadge(testSource)}</div>
                    </div>
                    ${exp.results ? `
                      <div class="experiment-meta-item">
                        <div class="experiment-meta-label">Best Model</div>
                        <div class="experiment-meta-value" style="color:var(--accent-bright);font-size:12px">${esc(exp.results.best_model)}</div>
                      </div>
                    ` : ''}
                  </div>
                  <div class="experiment-card-footer">
                    <span class="experiment-card-date">📅 ${fmt(exp.created_at)}</span>
                    <span style="font-size:12px;color:var(--accent-bright)">${actionText}</span>
                  </div>
                </a>
              `
            }).join('')}
          </div>
        `}
      </div>
    `
  } catch (e) {
    root().innerHTML = `<div class="empty-state"><h3>Failed to load</h3><p>${esc(e.message)}</p></div>`
  }
}

// ─── Page: New Experiment ─────────────────────────────────────────────────────

function newExperiment() {
  root().innerHTML = html`
    <div style="max-width:640px">
      <div class="page-header">
        <h1>New Experiment</h1>
        <p>Set up your experiment metadata and upload your training dataset.</p>
      </div>

      ${alert('info', '💡', 'Your dataset is required for training. Supplying a separate test CSV is optional — if omitted, 20% of your training dataset will be automatically held out as test data.')}

      <div class="card">
        <div class="form-group">
          <label class="form-label" for="exp-name">Experiment Name <span>*</span></label>
          <input id="exp-name" class="form-input" placeholder="Experiment Name" />
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
          <div class="form-group">
            <label class="form-label" for="target-col">Target Column <span>*</span></label>
            <input id="target-col" class="form-input" placeholder="Target Column Name" />
            <div class="form-hint">Exact column name in your CSV</div>
          </div>
          <div class="form-group">
            <label class="form-label" for="problem-type">Problem Type <span>*</span></label>
            <select id="problem-type" class="form-select">
              <option value="classification">Classification</option>
              <option value="regression">Regression</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Training Dataset CSV <span>*</span></label>
          <div id="dataset-upload" class="file-upload" tabindex="0">
            <input type="file" id="dataset-file-input" accept=".csv" />
            <div class="file-upload-icon">📂</div>
            <div class="file-upload-text"><strong>Click to browse</strong> or drag &amp; drop</div>
            <div class="file-upload-sub">CSV file — uploaded to S3 and used for training</div>
          </div>
          <div id="file-name-display"></div>
        </div>

        <div class="form-group">
          <label class="form-label">
            Separate Test CSV
            <span style="color:var(--text-muted);font-weight:400;font-size:12px;margin-left:4px">(optional)</span>
          </label>
          <div id="test-upload" class="file-upload" tabindex="0">
            <input type="file" id="test-file-input" accept=".csv" />
            <div class="file-upload-icon">📋</div>
            <div class="file-upload-text"><strong>Click to browse</strong> or drag &amp; drop</div>
            <div class="file-upload-sub">Labeled CSV with target column</div>
          </div>
          <div id="test-name-display"></div>
          <div class="form-hint" style="margin-top:6px">Leave blank to automatically hold out a 20% slice as test data.</div>
        </div>

        <div id="form-error"></div>
        <div style="display:flex;gap:12px;justify-content:flex-end;margin-top:8px">
          <a href="#/" class="btn btn-ghost">Cancel</a>
          <button id="create-experiment-btn" class="btn btn-primary" disabled>Create Experiment →</button>
        </div>
      </div>
    </div>
  `

  let selectedFile = null
  let selectedTestFile = null

  const nameInput    = document.getElementById('exp-name')
  const targetInput  = document.getElementById('target-col')
  const fileInput    = document.getElementById('dataset-file-input')
  const testInput    = document.getElementById('test-file-input')
  const submitBtn    = document.getElementById('create-experiment-btn')
  const errorDiv     = document.getElementById('form-error')
  const fileDisplay  = document.getElementById('file-name-display')
  const testDisplay  = document.getElementById('test-name-display')
  const uploadZone   = document.getElementById('dataset-upload')
  const testZone     = document.getElementById('test-upload')

  const checkValid = () => {
    submitBtn.disabled = !(nameInput.value.trim() && targetInput.value.trim() && selectedFile)
  }

  const setFile = (f) => {
    selectedFile = f
    if (f) {
      fileDisplay.innerHTML = `<div class="file-name">📎 ${esc(f.name)} <span id="clear-file" style="cursor:pointer;opacity:.7;margin-left:4px">✕</span></div>`
      uploadZone.classList.add('has-file')
      document.getElementById('clear-file').onclick = (e) => { e.stopPropagation(); setFile(null); fileInput.value = '' }
    } else {
      fileDisplay.innerHTML = ''
      uploadZone.classList.remove('has-file')
    }
    checkValid()
  }

  const setTestFile = (f) => {
    selectedTestFile = f
    if (f) {
      testDisplay.innerHTML = `<div class="file-name">📋 ${esc(f.name)} <span id="clear-test" style="cursor:pointer;opacity:.7;margin-left:4px">✕</span></div>`
      testZone.classList.add('has-file')
      document.getElementById('clear-test').onclick = (e) => { e.stopPropagation(); setTestFile(null); testInput.value = '' }
    } else {
      testDisplay.innerHTML = ''
      testZone.classList.remove('has-file')
    }
  }

  fileInput.addEventListener('change', e => setFile(e.target.files[0]))
  uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('drag-over') })
  uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'))
  uploadZone.addEventListener('drop', e => { e.preventDefault(); uploadZone.classList.remove('drag-over'); setFile(e.dataTransfer.files[0]) })

  testInput.addEventListener('change', e => setTestFile(e.target.files[0]))
  testZone.addEventListener('dragover', e => { e.preventDefault(); testZone.classList.add('drag-over') })
  testZone.addEventListener('dragleave', () => testZone.classList.remove('drag-over'))
  testZone.addEventListener('drop', e => { e.preventDefault(); testZone.classList.remove('drag-over'); setTestFile(e.dataTransfer.files[0]) })

  nameInput.addEventListener('input', checkValid)
  targetInput.addEventListener('input', checkValid)

  submitBtn.addEventListener('click', async () => {
    errorDiv.innerHTML = ''
    submitBtn.disabled = true
    submitBtn.innerHTML = `${spinner()} Uploading & Splitting…`
    try {
      const exp = await api.experiments.create(
        { name: nameInput.value.trim(), target_col: targetInput.value.trim(), problem_type: document.getElementById('problem-type').value },
        selectedFile,
        selectedTestFile
      )
      navigate(`experiment/${exp.id}`)
    } catch (e) {
      errorDiv.innerHTML = alert('warning', '⚠️', esc(e.message))
      submitBtn.innerHTML = 'Create Experiment →'
      submitBtn.disabled = false
    }
  })
}

// ─── Page: Model Setup ────────────────────────────────────────────────────────

async function modelSetup({ id }) {
  root().innerHTML = `<div class="empty-state">${spinner(32)}</div>`
  let exp
  try { exp = await api.experiments.get(id) }
  catch { root().innerHTML = `<div class="empty-state"><h3>Experiment not found</h3></div>`; return }

  function renderPage() {
    const hasModel       = !!exp.model?.model_s3_uri
    const modelUploaded  = hasModel
    const lambdaDeployed = !!exp.model?.lambda_fn_name
    const smDeployed     = !!exp.model?.sagemaker_serverless_endpoint
    const apRunning      = exp.autopilot?.status === 'InProgress'
    const apDone         = exp.autopilot?.status === 'Completed'
    const hasAnyReady    = lambdaDeployed || smDeployed || apDone || (exp.autopilot?.candidates?.length > 0)

    root().innerHTML = html`
      <div style="max-width:780px">
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:flex-start">
          <div>
            <div style="font-size:13px;color:var(--text-muted);margin-bottom:6px">
              <a href="#/" style="color:var(--text-muted);text-decoration:none">Experiments</a> → ${esc(exp.name)}
            </div>
            <h1>Model &amp; Job Setup</h1>
            <p>Upload your <code style="background:rgba(99,102,241,.1);padding:1px 6px;border-radius:4px;font-size:13px">.pkl</code> model or launch SageMaker Autopilot</p>
          </div>
          ${statusBadge(exp.status)}
        </div>

        <div id="page-error"></div>

        ${(exp.status === 'completed' || !!exp.results) ? alert('info', '🏆', `
          <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px">
            <div><strong>Experiment Completed</strong> — Results are ready for review.</div>
            <a href="#/experiment/${id}/comparison" class="btn btn-primary btn-sm">View Comparison Results →</a>
          </div>
        `) : ''}

        ${modelUploaded ? html`
          <div class="card" style="margin-bottom:20px">
            <div class="card-title">Step 1 — Your trained model</div>
            ${alert('success', '✅', `Model uploaded to S3<div style="font-family:monospace;font-size:12px;margin-top:4px;opacity:.8">${esc(exp.model.model_s3_uri)}</div>`)}
          </div>
        ` : html`
          <div class="card" style="margin-bottom:20px">
            <div class="card-title">Step 1 — Upload your trained model (optional)</div>
            <div id="model-upload-zone" class="file-upload" tabindex="0">
              <input type="file" id="model-file-input" accept=".pkl" />
              <div class="file-upload-icon">🤖</div>
              <div class="file-upload-text"><strong>Click to browse</strong> or drag &amp; drop</div>
              <div class="file-upload-sub">.pkl file — scikit-learn compatible model</div>
            </div>
            <div id="model-file-display"></div>
            <div class="form-hint" style="margin-top:10px">No model? Skip this step — you can benchmark Autopilot candidates alone.</div>
            <div style="margin-top:16px;display:flex;justify-content:flex-end">
              <button id="upload-model-btn" class="btn btn-primary" disabled>⬆ Upload to S3</button>
            </div>
          </div>
        `}

        <!-- Step 2: deploy (only shown if model uploaded) -->
        ${modelUploaded ? html`
          <div class="card" style="margin-bottom:20px">
            <div class="card-title">Step 2 — Deploy your model to inference paths</div>
            <div class="deploy-grid">
              <div class="deploy-card ${lambdaDeployed ? 'deployed' : ''}">
                <div class="deploy-card-title">${lambdaDeployed ? '✅' : '⬜'} AWS Lambda</div>
                <div class="deploy-card-desc">Serverless inference. Loads your .pkl from S3 using the pre-provisioned scikit-learn Layer.</div>
                ${lambdaDeployed
                  ? `<div style="font-size:12px;color:var(--success);font-family:monospace">${esc(exp.model.lambda_fn_name)}</div>`
                  : `<button id="deploy-lambda-btn" class="btn btn-secondary btn-sm">Deploy</button>`}
              </div>
              <div class="deploy-card ${smDeployed ? 'deployed' : ''}">
                <div class="deploy-card-title">${smDeployed ? '✅' : '⬜'} SageMaker Serverless</div>
                <div class="deploy-card-desc">Managed inference. Scales to zero between calls — no persistent cost.</div>
                ${smDeployed
                  ? `<div style="font-size:12px;color:var(--success);font-family:monospace">${esc(exp.model.sagemaker_serverless_endpoint)}</div>`
                  : `<button id="deploy-sagemaker-btn" class="btn btn-secondary btn-sm">Deploy</button>`}
              </div>
            </div>
          </div>
        ` : ''}

        <!-- Step 3: Autopilot (always shown) -->
        <div class="card" style="margin-bottom:20px">
          <div class="card-title">${modelUploaded ? 'Step 3' : 'Step 2'} — SageMaker Autopilot</div>
          ${!modelUploaded ? alert('info', 'ℹ️', 'No model uploaded — this experiment will run in <strong>Autopilot-only mode</strong>. Only the 5 Autopilot candidates will appear in the comparison.') : ''}
          <p style="font-size:14px;color:var(--text-secondary);margin-bottom:16px">
            Autopilot trains up to 5 candidate models on your training dataset automatically.
          </p>
          ${!apRunning && !apDone ? `<button id="start-autopilot-btn" class="btn btn-secondary">🤖 Start Autopilot</button>` : ''}
          ${apRunning ? alert('warning', spinner(), `<div style="font-weight:600">Autopilot is training candidate models…</div><div style="font-size:12px;margin-top:4px;color:var(--text-secondary)">This may take a few moments. Results will update automatically.</div>`) : ''}
          ${apDone ? html`
            ${alert('success', '🎉', `<div style="font-weight:600">Autopilot complete — ${exp.autopilot.candidates?.length} candidates ready</div>`)}
            <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px">
              ${exp.autopilot.candidates?.map((c, i) => `<span class="badge badge-info">#${i+1} ${esc(c.algorithm)}</span>`).join('')}
            </div>
          ` : ''}
        </div>

        <div class="card" style="margin-top:24px;border-color:rgba(99,102,241,.25);background:linear-gradient(135deg,rgba(99,102,241,.06),rgba(20,184,166,.04));padding:20px 24px">
          <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px">
            <div>
              <div style="font-weight:700;font-size:15px;color:var(--text-primary)">
                ${hasAnyReady ? 'Ready for Benchmark Evaluation' : 'Skip Ahead to Dashboard'}
              </div>
              <div style="font-size:13px;color:var(--text-secondary);margin-top:2px">
                ${lambdaDeployed ? '⚡ Lambda Deployed  ' : ''}
                ${smDeployed ? '🤖 SageMaker Endpoint Ready  ' : ''}
                ${apDone ? '🧠 Autopilot Ready' : ''}
                ${!hasAnyReady ? 'Proceed to view comparison dashboard at any time.' : ''}
              </div>
            </div>
            <a href="#/experiment/${id}/comparison" class="btn btn-primary btn-lg" id="go-to-comparison-btn">
              Proceed to Comparison Dashboard →
            </a>
          </div>
        </div>
      </div>
    `

    // Wire up buttons
    const errDiv = document.getElementById('page-error')
    const setErr = msg => { errDiv.innerHTML = msg ? alert('warning', '⚠️', esc(msg)) : '' }

    if (!modelUploaded) {
      let selectedModel = null
      const modelInput   = document.getElementById('model-file-input')
      const modelDisplay = document.getElementById('model-file-display')
      const uploadBtn    = document.getElementById('upload-model-btn')
      const zone         = document.getElementById('model-upload-zone')

      const setFile = (f) => {
        selectedModel = f
        uploadBtn.disabled = !f
        if (f) {
          modelDisplay.innerHTML = `<div class="file-name" style="margin-top:12px">📎 ${esc(f.name)}</div>`
          zone.classList.add('has-file')
        } else {
          modelDisplay.innerHTML = ''
          zone.classList.remove('has-file')
        }
      }

      modelInput.addEventListener('change', e => setFile(e.target.files[0]))
      zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over') })
      zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'))
      zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('drag-over'); setFile(e.dataTransfer.files[0]) })

      uploadBtn.addEventListener('click', async () => {
        setErr(null); uploadBtn.disabled = true; uploadBtn.innerHTML = `${spinner()} Uploading…`
        try { exp = await api.model.upload(id, selectedModel); renderPage() }
        catch (e) { setErr(e.message); uploadBtn.innerHTML = '⬆ Upload to S3'; uploadBtn.disabled = false }
      })
    }

    document.getElementById('deploy-lambda-btn')?.addEventListener('click', async function() {
      setErr(null); this.disabled = true; this.innerHTML = `${spinner()} Deploying…`
      try { exp = await api.deploy.lambda(id); renderPage() }
      catch (e) { setErr(e.message); this.innerHTML = 'Deploy'; this.disabled = false }
    })

    document.getElementById('deploy-sagemaker-btn')?.addEventListener('click', async function() {
      setErr(null); this.disabled = true; this.innerHTML = `${spinner()} Deploying…`
      try { exp = await api.deploy.sagemaker(id); renderPage() }
      catch (e) { setErr(e.message); this.innerHTML = 'Deploy'; this.disabled = false }
    })

    document.getElementById('start-autopilot-btn')?.addEventListener('click', async function() {
      setErr(null); this.disabled = true; this.innerHTML = `${spinner()} Starting…`
      try {
        exp = await api.autopilot.start(id)
        renderPage()
        // Start polling
        const poll = setInterval(async () => {
          try {
            const s = await api.autopilot.status(id)
            exp.autopilot = { ...exp.autopilot, ...s }
            if (s.status !== 'InProgress') { clearInterval(poll); renderPage() }
            else {
              renderPage()
            }
          } catch { clearInterval(poll) }
        }, 4000)
      } catch (e) { setErr(e.message); this.innerHTML = '🤖 Start Autopilot'; this.disabled = false }
    })
  }

  renderPage()
}

// ─── Page: Comparison ─────────────────────────────────────────────────────────

function triggerModelDownload(filename, s3Uri) {
  if (s3Uri && (s3Uri.startsWith('http://') || s3Uri.startsWith('https://'))) {
    window.open(s3Uri, '_blank')
    return
  }
  const dummyContent = `Model Artifact: ${filename}\nS3 Location: ${s3Uri || 's3://ml-lab-artifacts/model'}\nGenerated for ML Model & Deployment Comparison workbench.`
  const blob = new Blob([dummyContent], { type: 'application/octet-stream' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

async function comparison({ id }) {
  root().innerHTML = `<div class="empty-state">${spinner(32)}</div>`
  let exp
  try { exp = await api.experiments.get(id) }
  catch { root().innerHTML = `<div class="empty-state"><h3>Experiment not found</h3></div>`; return }

  function buildRows(results) {
    if (!results) return []
    const hasModel = !!exp.model?.model_s3_uri
    const lambdaRes = results.lambda_result
    const smRes     = results.sagemaker_result
    const lambdaM   = lambdaRes?.metrics || {}
    const smM       = smRes?.metrics || {}

    const rows = []
    if (hasModel) {
      if (lambdaRes || exp.model?.lambda_fn_name) {
        rows.push({
          name: 'Your Model', path: 'Lambda', icon: '⚡', algorithm: 'Your .pkl',
          predictions: lambdaRes?.predictions || results.lambda_predictions,
          accuracy: lambdaM.accuracy ?? results.lambda_accuracy,
          f1: lambdaM.f1 ?? results.lambda_f1,
          precision: lambdaM.precision ?? results.lambda_precision,
          recall: lambdaM.recall ?? results.lambda_recall,
          r2: lambdaM.r2 ?? results.lambda_r2,
          rmse: lambdaM.rmse ?? results.lambda_rmse,
          mae: lambdaM.mae ?? results.lambda_mae,
          mape: lambdaM.mape ?? results.lambda_mape,
          download_filename: `${exp.name.toLowerCase().replace(/[^a-z0-9]/g, '-')}-model.pkl`,
          download_label: '.pkl',
          download_uri: lambdaRes?.download_url || exp.model?.model_s3_uri,
          isYours: true,
          error: lambdaRes?.error,
        })
      }
      if (smRes || exp.model?.sagemaker_serverless_endpoint) {
        rows.push({
          name: 'Your Model', path: 'SageMaker', icon: '🤖', algorithm: 'Your .pkl',
          predictions: smRes?.predictions || results.sagemaker_predictions,
          accuracy: smM.accuracy ?? results.sagemaker_accuracy,
          f1: smM.f1 ?? results.sagemaker_f1,
          precision: smM.precision ?? results.sagemaker_precision,
          recall: smM.recall ?? results.sagemaker_recall,
          r2: smM.r2 ?? results.sagemaker_r2,
          rmse: smM.rmse ?? results.sagemaker_rmse,
          mae: smM.mae ?? results.sagemaker_mae,
          mape: smM.mape ?? results.sagemaker_mape,
          download_filename: `${exp.name.toLowerCase().replace(/[^a-z0-9]/g, '-')}-model.pkl`,
          download_label: '.pkl',
          download_uri: smRes?.download_url || exp.model?.model_s3_uri,
          isYours: true,
          error: smRes?.error,
        })
      }
    }

    (results.candidate_results || []).forEach((c, i) => {
      const cm = c.metrics || {}
      rows.push({
        name: `Autopilot #${i + 1}`, path: c.algorithm, icon: '🧠', algorithm: c.algorithm,
        predictions: c.predictions,
        accuracy: cm.accuracy ?? c.accuracy,
        f1: cm.f1 ?? c.f1,
        precision: cm.precision ?? c.precision,
        recall: cm.recall ?? c.recall,
        r2: cm.r2 ?? c.r2,
        rmse: cm.rmse ?? c.rmse,
        mae: cm.mae ?? c.mae,
        mape: cm.mape ?? c.mape,
        download_filename: `${exp.name.toLowerCase().replace(/[^a-z0-9]/g, '-')}-candidate-${i + 1}-${c.algorithm.toLowerCase().replace(/[^a-z0-9]/g, '-')}.tar.gz`,
        download_label: '.tar.gz',
        download_uri: c.download_url || c.model_s3_uri,
        isYours: false,
        error: c.error,
      })
    })

    return rows
  }

  function renderPage() {
    const results = exp.results
    const pt = exp.problem_type
    const isReg = pt === 'regression'
    const rows = buildRows(results)
    const testSource = exp.split?.test_source || exp.test_source || 'auto_split'

    const validScores = rows
      .map(r => isReg ? r.r2 : r.accuracy)
      .filter(s => s != null && !isNaN(s))
    const bestScore = validScores.length ? Math.max(...validScores) : null
    const isBest = r => isReg
      ? (r.r2 != null && r.r2 === bestScore)
      : (r.accuracy != null && r.accuracy === bestScore)

    const bestModelName = typeof results?.best_model === 'object' && results?.best_model !== null
      ? (results.best_model.label || results.best_model.name)
      : (results?.best_model || (rows[0]?.name ? `${rows[0].name} (${rows[0].path})` : 'Model Evaluation'))

    root().innerHTML = html`
      <div>
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:flex-start">
          <div>
            <div style="font-size:13px;color:var(--text-muted);margin-bottom:6px">
              <a href="#/" style="color:var(--text-muted);text-decoration:none">Experiments</a> → ${esc(exp.name)}
            </div>
            <div style="display:flex;align-items:center;gap:10px">
              <h1 style="margin:0">Comparison Dashboard</h1>
              ${testSourceBadge(testSource)}
            </div>
            <p style="margin-top:6px">Same test data — all inference paths — side by side</p>
          </div>
          ${statusBadge(exp.status)}
        </div>

        <div id="page-error"></div>
        ${results?.error ? alert('danger', '⚠️', `<strong>Evaluation notice:</strong> ${esc(results.error)}`) : ''}

        ${!results ? html`
          <div class="card" style="text-align:center;padding:48px">
            <div style="font-size:40px;margin-bottom:16px">🚀</div>
            <h3 style="font-size:18px;font-weight:700;margin-bottom:8px">Ready to compare</h3>
            <p style="color:var(--text-secondary);margin-bottom:8px;font-size:14px">
              ${exp.model?.model_s3_uri
                ? 'Sends test data to Lambda, SageMaker, and all 5 Autopilot candidates via Batch Transform.'
                : 'No model uploaded — only Autopilot candidates will be compared (Lambda and SageMaker paths skipped).'}
            </p>
            <div style="margin-bottom:16px">${testSourceBadge(testSource)}</div>
            ${!exp.model?.model_s3_uri ? alert('info', 'ℹ️', 'Running in <strong>Autopilot-only mode</strong>. Upload a model on the setup page to enable Lambda and SageMaker inference paths.') : ''}
            <button id="run-comparison-btn" class="btn btn-primary btn-lg">⚡ Run Comparison</button>
          </div>
        ` : html`
          <!-- Best model banner -->
          ${bestScore != null ? html`
            <div class="card" style="margin-bottom:24px;background:linear-gradient(135deg,rgba(99,102,241,.12),rgba(139,92,246,.08));border-color:rgba(99,102,241,.3)">
              <div style="display:flex;align-items:center;gap:16px">
                <div style="font-size:40px">🏆</div>
                <div>
                  <div style="font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;color:var(--text-muted);margin-bottom:4px">Best Performing Model</div>
                  <div style="font-size:22px;font-weight:800;color:var(--accent-bright)">${esc(bestModelName)}</div>
                  <div style="font-size:13px;color:var(--text-secondary);margin-top:4px">
                    ${isReg
                      ? `Highest R² Score: ${(bestScore ?? 0).toFixed(3)} on the test dataset`
                      : `Highest Accuracy: ${(bestScore ?? 0).toFixed(3)} on the test dataset`}
                  </div>
                </div>
              </div>
            </div>
          ` : ''}

          <!-- Table -->
          <div class="card" style="padding:0;overflow:hidden">
            <div style="padding:20px 24px 0;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
              <div class="card-title" style="margin-bottom:16px">Results — All Inference Paths (${problemChip(pt)})</div>
              <div style="margin-bottom:16px">${testSourceBadge(testSource)}</div>
            </div>
            <div class="comparison-table-wrap" style="border-radius:0;border:none">
              <table class="comparison-table">
                <thead>
                  <tr>
                    <th>Model</th>
                    <th>Inference Path</th>
                    ${isReg ? html`
                      <th>R² Score</th>
                      <th>RMSE</th>
                      <th>MAE</th>
                      <th>MAPE</th>
                    ` : html`
                      <th>Accuracy</th>
                      <th>F1 Score</th>
                      <th>Precision</th>
                      <th>Recall</th>
                    `}
                    <th>Sample Predictions</th>
                    <th>Download Model</th>
                  </tr>
                </thead>
                <tbody>
                  ${rows.map(row => html`
                    <tr style="${isBest(row) ? 'background:rgba(99,102,241,.05)' : ''}">
                      <td>
                        <div class="model-name">
                          <span>${row.icon}</span>
                          <div>
                            <div>${esc(row.name)}</div>
                            <div style="font-size:11px;color:var(--text-muted);font-weight:400">${esc(row.algorithm)}</div>
                          </div>
                          ${isBest(row) ? '<span class="badge badge-best">Best</span>' : ''}
                        </div>
                      </td>
                      <td>
                        <span style="padding:2px 8px;border-radius:4px;font-size:12px;font-weight:600;
                          background:${row.isYours ? 'rgba(99,102,241,.1)' : 'rgba(20,184,166,.1)'};
                          color:${row.isYours ? 'var(--accent-bright)' : 'var(--teal)'}">
                          ${esc(row.path)}
                        </span>
                      </td>

                      ${isReg ? html`
                        <td>
                          <span class="metric-value ${isBest(row) ? 'metric-best' : 'metric-good'}">
                            ${row.r2?.toFixed(3) ?? '—'}
                            ${isBest(row) ? '<span style="margin-left:4px;font-size:11px">🏆</span>' : ''}
                          </span>
                        </td>
                        <td><span class="metric-value">${row.rmse?.toFixed(2) ?? '—'}</span></td>
                        <td><span class="metric-value">${row.mae?.toFixed(2) ?? '—'}</span></td>
                        <td><span class="metric-value">${row.mape != null ? `${row.mape.toFixed(1)}%` : '—'}</span></td>
                      ` : html`
                        <td>
                          <span class="metric-value ${isBest(row) ? 'metric-best' : 'metric-good'}">
                            ${row.accuracy?.toFixed(3) ?? '—'}
                            ${isBest(row) ? '<span style="margin-left:4px;font-size:11px">🏆</span>' : ''}
                          </span>
                        </td>
                        <td><span class="metric-value metric-good">${row.f1?.toFixed(3) ?? '—'}</span></td>
                        <td><span class="metric-value">${row.precision?.toFixed(3) ?? '—'}</span></td>
                        <td><span class="metric-value">${row.recall?.toFixed(3) ?? '—'}</span></td>
                      `}

                      <td>${predChips(row.predictions)}</td>
                      <td>
                        <button class="download-link download-model-btn" data-filename="${esc(row.download_filename)}" data-uri="${esc(row.download_uri)}">
                          📥 ${esc(row.download_label)}
                        </button>
                      </td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          </div>

          <div style="margin-top:28px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;padding-top:16px;border-top:1px solid var(--border)">
            <a href="#/" class="btn btn-primary" id="back-to-experiments-btn">← Back to Experiments</a>
            <div style="display:flex;gap:10px;align-items:center">
              <button id="rerun-comparison-btn" class="btn btn-secondary">↺ Re-run Comparison</button>
            </div>
          </div>
        `}
      </div>
    `

    const errDiv = document.getElementById('page-error')
    const setErr = msg => { errDiv.innerHTML = msg ? alert('warning', '⚠️', esc(msg)) : '' }

    // Download handlers
    document.querySelectorAll('.download-model-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const filename = btn.dataset.filename
        const uri = btn.dataset.uri
        triggerModelDownload(filename, uri)
      })
    })

    const runBtn = document.getElementById('run-comparison-btn') || document.getElementById('rerun-comparison-btn')
    runBtn?.addEventListener('click', async function() {
      setErr(null); this.disabled = true; this.innerHTML = `${spinner()} Running inference across all paths…`
      try {
        const res = await api.compare.run(id)
        if (res?.results) {
          exp = res
          renderPage()
          return
        }
        // Poll for async comparison completion in deployed environments
        const poll = setInterval(async () => {
          try {
            const latest = await api.experiments.get(id)
            if (latest.results || latest.status === 'completed') {
              clearInterval(poll)
              exp = latest
              renderPage()
            } else if (latest.status === 'failed') {
              clearInterval(poll)
              setErr(latest.error || 'Comparison failed')
              this.disabled = false
              this.innerHTML = '⚡ Run Comparison'
            }
          } catch {
            clearInterval(poll)
            this.disabled = false
            this.innerHTML = '⚡ Run Comparison'
          }
        }, 3000)
      } catch (e) {
        setErr(e.message)
        this.innerHTML = this.id === 'run-comparison-btn' ? '⚡ Run Comparison' : '↺ Re-run Comparison'
        this.disabled = false
      }
    })
  }

  renderPage()
}
