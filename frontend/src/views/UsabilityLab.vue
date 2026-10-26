<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const config = ref(null)
const runs = ref([])
const selected = ref(null)
const selectedImage = ref(null)
const url = ref('')
const task = ref('')
const successText = ref('')
const error = ref('')
const loading = ref(false)
const question = ref('')
const activeTab = ref('findings')
let timer

const busy = computed(() => runs.value.some(r => ['queued', 'running'].includes(r.status) || r.interview_pending))
const running = computed(() => selected.value && ['queued', 'running'].includes(selected.value.status))
const terminal = computed(() => selected.value && !running.value)
const statusTitle = computed(() => ({ queued: 'Waiting to start', running: 'Exploring the flow', completed: 'Success signal found', stopped: 'Test stopped', failed: 'Test interrupted' })[selected.value?.status] || '')
const reasonText = computed(() => ({ starting: 'Starting an isolated browser', opening_website: 'Opening the website', choosing_action: 'The synthetic user is choosing its next action', observing_result: 'Checking the result of that action', success_text_observed: 'The success text appeared on the page.', participant_stopped: 'The synthetic user chose to stop.', step_limit: 'The user reached the test’s action limit.', cancelled: 'You stopped this test.', action_boundary: 'The next action needs human control.', network_boundary: 'The next page was outside the test boundary.', invalid_agent_action: 'The agent could not choose a valid control.', unsupported_agent_action: 'The agent requested an unsupported action.', startup_error: 'The browser or model could not start.', server_restarted: 'The app closed before this run finished.', timeout: 'The test reached its time limit.', browser_error: 'A browser or model error interrupted the run.' })[selected.value?.reason] || '')
const preview = computed(() => selectedImage.value || selected.value?.screenshots?.at(-1) || null)

async function api(path, options = {}) {
  const response = await fetch('/api/lab' + path, { ...options, headers: { 'Content-Type': 'application/json', 'X-Lab-Token': config.value?.token || '', ...options.headers } })
  let data
  try { data = await response.json() } catch { throw new Error('The local app did not return a valid response. Check the VS Code terminal.') }
  if (!response.ok) throw new Error(data.error || 'The request could not be completed.')
  return data
}

async function refresh() {
  try {
    const data = await api('/runs')
    runs.value = data.runs
    if (selected.value) selected.value = runs.value.find(r => r.id === selected.value.id) || selected.value
  } catch (e) { error.value = e.message }
}

function chooseRun(run) {
  selected.value = run
  selectedImage.value = null
  activeTab.value = 'findings'
  error.value = ''
}

async function start(demo = null) {
  if (loading.value || busy.value) return
  error.value = ''
  loading.value = true
  try {
    const payload = demo ? { demo, task: 'Book a vehicle service', success_text: 'Booking confirmed' } : { url: url.value.trim(), task: task.value.trim(), success_text: successText.value.trim() }
    const run = await api('/runs', { method: 'POST', body: JSON.stringify(payload) })
    chooseRun(run)
    runs.value.unshift(run)
    await nextTick()
    document.querySelector('#run-workspace')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}

async function cancel() {
  try { await api(`/runs/${selected.value.id}/cancel`, { method: 'POST', body: '{}' }); await refresh() }
  catch (e) { error.value = e.message }
}

async function ask(value = question.value) {
  if (!value.trim() || busy.value) return
  try {
    await api(`/runs/${selected.value.id}/interviews`, { method: 'POST', body: JSON.stringify({ question: value }) })
    question.value = ''
    selected.value.interview_pending = true
    activeTab.value = 'interview'
  } catch (e) { error.value = e.message }
}

function imageUrl(item) { return `/api/lab/runs/${selected.value.id}/files/${encodeURIComponent(item.file)}` }
function showEvidence(id) { selectedImage.value = selected.value.screenshots.find(s => s.evidence_id === id) || null }
function time(value) { return new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) }

onMounted(async () => {
  try {
    config.value = await api('/config')
    await refresh()
    timer = setInterval(refresh, 2000)
  } catch (e) { error.value = e.message }
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="lab-shell">
    <header class="lab-header">
      <a href="/" class="brand"><span class="brand-mark">u<span>↗</span></span><span>Usability Lab<small>LOCAL WORKSPACE</small></span></a>
      <div class="model-state"><span></span>{{ config?.model || 'Connecting to local model' }}</div>
    </header>

    <main>
      <section class="intro" aria-labelledby="page-title">
        <div class="intro-copy"><p class="eyebrow">SEE WHERE THE FLOW BREAKS</p><h1 id="page-title">A fresh pair of eyes.<br><span>Before your next release.</span></h1><p class="description">Give a synthetic user a goal. Watch what it tries, find possible gaps, and ask about the evidence.</p><div class="intro-note"><span class="note-dot"></span>Runs on your computer. No model API key.</div></div>
        <form class="test-form" @submit.prevent="start()">
          <div class="form-heading"><h2>Start a test</h2><span>1 synthetic user</span></div>
          <label for="website">Website or preview URL</label><input id="website" v-model="url" type="url" placeholder="https://your-preview.com" required :disabled="busy" />
          <label for="task">What should the user do?</label><textarea id="task" v-model="task" placeholder="Find the service options and start a booking." required minlength="3" maxlength="2000" rows="3" :disabled="busy"></textarea>
          <details><summary>Add a success signal <span>Optional</span></summary><label for="success">Text that should appear when the task is done</label><input id="success" v-model="successText" placeholder="e.g. Booking confirmed" maxlength="300" :disabled="busy" /><p>Without a signal, the outcome stays open for your review.</p></details>
          <button class="primary" type="submit" :disabled="!config || busy || loading">{{ loading ? 'Starting…' : busy ? 'A test or interview is running' : 'Run test' }}<span aria-hidden="true">↗</span></button>
          <p class="boundary-note">Form submissions and recognised payment controls are blocked. Use a test site first.</p>
        </form>
      </section>

      <div class="demo-strip"><div><strong>See it in action</strong><span>Try a working flow or a button that does nothing.</span></div><div class="demo-actions"><button @click="start('working')" :disabled="busy || loading || !config">Working demo <span>↗</span></button><button @click="start('broken')" :disabled="busy || loading || !config">Broken demo <span>↗</span></button></div></div>
      <p v-if="error" class="error-banner" role="alert">{{ error }}</p>

      <section v-if="selected" id="run-workspace" class="workspace" aria-labelledby="run-title">
        <div class="workspace-heading"><div><p class="eyebrow">TEST SESSION</p><h2 id="run-title">{{ selected.task }}</h2><p class="run-url">{{ selected.url }}</p></div><button v-if="running" class="stop-button" @click="cancel">Stop test</button></div>
        <div class="run-progress" role="status" aria-live="polite"><div><span class="status-dot" :class="selected.status"></span><strong>{{ statusTitle }}</strong><span class="step-counter">{{ selected.step || 0 }} / {{ selected.max_steps }} steps</span></div><p>{{ reasonText }}</p><small v-if="running">Local image processing can take a minute per step. You can leave this page open.</small></div>
        <div class="workspace-grid">
          <div class="evidence-pane"><div class="pane-title"><h3>What the user saw</h3><span v-if="preview">Screen {{ preview.step }}</span></div><div class="screen-frame"><img v-if="preview" :src="imageUrl(preview)" :alt="`Captured screen ${preview.step}`" /><div v-else class="empty-screen"><span class="empty-icon">◎</span><p>{{ running ? 'Opening the browser…' : 'No screen was captured.' }}</p></div></div><div v-if="selected.screenshots.length" class="screen-strip" aria-label="Captured screens"><button v-for="shot in selected.screenshots" :key="shot.evidence_id" @click="selectedImage = shot" :class="{ chosen: preview?.evidence_id === shot.evidence_id }" :aria-label="`View screen ${shot.step}`"><img :src="imageUrl(shot)" alt="" /><span>{{ shot.step }}</span></button></div><a v-if="terminal && selected.screenshots.length" class="trace-link" :href="`/api/lab/runs/${selected.id}/files/trace.zip`" download>Download full browser trace ↓</a></div>
          <div class="review-pane"><nav class="review-tabs" aria-label="Run details"><button v-for="tab in ['findings', 'actions', 'interview']" :key="tab" @click="activeTab = tab" :class="{ active: activeTab === tab }">{{ tab }}<span v-if="tab === 'findings' && selected.findings.length">{{ selected.findings.length }}</span></button></nav>
            <div v-if="activeTab === 'findings'" class="tab-content">
              <div v-if="!selected.findings.length" class="empty-review"><h3>{{ running ? 'Collecting evidence' : selected.status === 'completed' ? 'The success signal appeared' : 'No confirmed design issue yet' }}</h3><p>{{ running ? 'Findings appear as the user moves through the flow.' : 'A stopped run can reflect the design, the task, or the agent. Use the screenshots and action log to check what happened.' }}</p></div>
              <article v-for="(finding, index) in selected.findings" :key="index" class="finding"><p class="finding-kind">{{ finding.category.replaceAll('_', ' ') }}</p><h3>{{ finding.title }}</h3><p>{{ finding.detail }}</p><div class="citations"><button v-for="id in finding.evidence_ids" :key="id" @click="showEvidence(id)">View evidence ↗</button></div></article>
              <div v-if="selected.blocks.length" class="limits-box"><h3>Test boundaries</h3><p v-for="block in selected.blocks" :key="block">{{ block }}</p></div>
            </div>
            <ol v-else-if="activeTab === 'actions'" class="tab-content action-list"><li v-for="(action, index) in selected.actions" :key="index"><span class="action-number">{{ action.step }}</span><div><strong>{{ action.kind }}{{ action.target_label ? ` · ${action.target_label}` : '' }}</strong><small>{{ action.status.replaceAll('_', ' ') }}</small><button @click="showEvidence(action.evidence_id)">See screen ↗</button></div></li><p v-if="!selected.actions.length" class="quiet">Actions will appear here as the test runs.</p></ol>
            <div v-else class="tab-content interview-panel"><p class="interview-note">Ask the synthetic user about this recorded session. Interpretations are labelled and remain unverified.</p><div class="question-shortcuts"><button @click="ask('What did the final screen show?')" :disabled="busy || !terminal || !selected.screenshots.length">What did you see?</button><button @click="ask('What might have blocked progress? Separate recorded facts from your interpretation.')" :disabled="busy || !terminal || !selected.screenshots.length">What blocked progress?</button></div><article v-for="(answer, index) in selected.interviews" :key="index" class="answer"><h3>{{ answer.question }}</h3><div v-for="(statement, number) in answer.statements" :key="number" class="statement"><span :class="statement.kind">{{ statement.kind === 'inference' ? 'Interpretation · unverified' : statement.kind }}</span><p>{{ statement.text }}</p><div class="citations"><button v-for="id in statement.evidence_ids" :key="id" @click="showEvidence(id)">View evidence ↗</button></div></div></article><p v-if="selected.interview_pending" class="thinking" role="status">Reading the session and checking the answer…</p><p v-if="selected.interview_error" class="error-banner" role="alert">{{ selected.interview_error }}</p><form class="ask-form" @submit.prevent="ask()"><label for="question">Your follow-up question</label><textarea id="question" v-model="question" rows="2" placeholder="What happened after you clicked the booking button?" :disabled="busy || !terminal" maxlength="4000"></textarea><button class="primary" :disabled="busy || !terminal || !question.trim() || !selected.screenshots.length">Ask user <span>↗</span></button></form></div>
          </div>
        </div>
      </section>

      <section class="history" aria-labelledby="history-title"><div class="history-heading"><h2 id="history-title">Your tests</h2><span>{{ runs.length }} {{ runs.length === 1 ? 'session' : 'sessions' }}</span></div><div v-if="!runs.length" class="history-empty"><span>↗</span><p>Your first test starts above.<small>Start with a demo, or use a public preview URL.</small></p></div><button v-for="run in runs" :key="run.id" class="history-row" @click="chooseRun(run)"><div><strong>{{ run.task }}</strong><small>{{ run.url }}</small></div><span class="history-status"><i class="status-dot" :class="run.status"></i>{{ run.status }}</span><time>{{ time(run.created_at) }}</time><span aria-hidden="true">↗</span></button></section>
      <footer class="lab-footer"><span>Built on MiroFish · powered by local Qwen</span><span>Synthetic feedback helps you prepare. Validate findings with people.</span></footer>
    </main>
  </div>
</template>

<style scoped>
.lab-shell{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f5ef;color:#203f36;min-height:100vh;font-size:15px}.lab-header{max-width:1344px;margin:auto;padding:26px 48px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #dce2d9}.brand{display:flex;align-items:center;gap:12px;text-decoration:none;color:inherit;font-size:19px;font-weight:600}.brand small{display:block;font-size:9px;letter-spacing:2px;font-weight:500;color:#7a867b;margin-top:4px}.brand-mark{display:flex;width:42px;height:42px;border-radius:13px;background:#224d3f;color:#e4efbb;align-items:center;justify-content:center;font-size:30px;position:relative;font-weight:400}.brand-mark>span{font-size:18px;position:absolute;right:5px;top:1px}.model-state{font-size:12px;display:flex;gap:8px;align-items:center;color:#657367}.model-state>span,.note-dot{width:6px;height:6px;border-radius:100%;background:#6f9162;display:inline-block}main{max-width:1344px;margin:auto;padding:0 48px}.intro{display:grid;grid-template-columns:1.15fr 1fr;gap:80px;padding:72px 0 36px;align-items:center}.eyebrow{font-size:10px;letter-spacing:2px;font-weight:600;color:#66806b;margin-bottom:20px}h1{font-size:clamp(34px,4.2vw,58px);font-weight:500;line-height:1.12;letter-spacing:-2.7px}h1>span{color:#85947e}.description{font-size:17px;line-height:1.7;color:#6b786b;max-width:420px;margin-top:24px}.intro-note{font-size:12px;color:#778374;display:flex;align-items:center;gap:8px;margin-top:42px}.test-form{background:#fff;border:1px solid #dce2d9;padding:28px;border-radius:22px;box-shadow:0 12px 40px #30493205}.form-heading{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:24px}h2{font-size:21px;font-weight:500;letter-spacing:-.5px}.form-heading>span{font-size:10px;color:#6c7d68;background:#f0f4eb;border-radius:20px;padding:6px 10px}label{display:block;font-size:12px;font-weight:500;margin-bottom:9px;margin-top:18px}input,textarea{display:block;font:inherit;color:#203f36;width:100%;border:1px solid #d8dfd5;background:#fcfcf9;border-radius:9px;padding:12px 14px;outline-offset:3px;resize:vertical;font-size:13px}input::placeholder,textarea::placeholder{color:#8c9689}input:focus,textarea:focus{outline:2px solid #6d8b62}button{cursor:pointer;font:inherit}button:disabled{opacity:.45;cursor:wait}button:focus-visible,a:focus-visible{outline:2px solid #527951;outline-offset:4px}details{margin:20px 0}summary{font-size:12px;color:#60705e;cursor:pointer}summary>span{color:#8b9688;font-size:10px;margin-left:6px}details p{font-size:11px;line-height:1.5;color:#73816e;margin-top:8px}.primary{width:100%;display:flex;justify-content:space-between;background:#254f40;color:#f3f7e7;border:0;border-radius:10px;padding:14px 17px;font-size:13px;font-weight:500;margin-top:22px}.primary>span{font-size:17px}.boundary-note{font-size:10px;line-height:1.6;color:#7a8575;margin-top:12px}.demo-strip{display:flex;align-items:center;justify-content:space-between;border-top:1px solid #dce2d9;border-bottom:1px solid #dce2d9;padding:22px 0;gap:20px}.demo-strip strong{display:block;font-weight:500;font-size:13px}.demo-strip>div>span{display:block;font-size:12px;color:#7b8775;margin-top:5px}.demo-actions{display:flex;gap:10px}.demo-actions button{background:transparent;border:1px solid #cdd8c5;border-radius:8px;padding:10px 14px;color:#3d5e48;font-size:12px}.demo-actions button>span{margin-left:20px}.error-banner{padding:13px 16px;background:#fff0eb;color:#9a4939;font-size:13px;border-radius:9px;margin:16px 0;line-height:1.5}.workspace{margin-top:48px;scroll-margin-top:24px}.workspace-heading{display:flex;justify-content:space-between;gap:24px;margin-bottom:24px}.workspace-heading .eyebrow{margin-bottom:10px}.workspace-heading h2{font-size:27px}.run-url{font-size:12px;color:#7a8677;overflow-wrap:anywhere;margin-top:8px}.stop-button{align-self:center;border:1px solid #d5b9a9;background:#fff9f3;color:#8a5d48;padding:10px 16px;border-radius:8px;font-size:12px}.run-progress{background:#ebf0e3;border-radius:12px;padding:18px 22px;margin-bottom:22px}.run-progress>div{display:flex;align-items:center;gap:9px}.run-progress strong{font-size:13px;font-weight:500}.run-progress p{font-size:12px;color:#6e7b63;margin:8px 0 0 16px}.run-progress small{display:block;font-size:11px;color:#788368;margin:8px 0 0 16px}.status-dot{width:7px;height:7px;background:#a9b0a1;border-radius:50%;display:inline-block;flex-shrink:0}.status-dot.running,.status-dot.completed{background:#618c55}.status-dot.stopped{background:#be9b59}.status-dot.failed{background:#b26c58}.step-counter{margin-left:auto;font-size:11px;color:#748367}.workspace-grid{display:grid;grid-template-columns:1.15fr 1fr;gap:24px;align-items:start}.evidence-pane,.review-pane{min-width:0;background:#fff;border:1px solid #dce2d9;border-radius:15px;overflow:hidden}.pane-title{display:flex;justify-content:space-between;align-items:center;padding:18px 20px}.pane-title h3{font-size:13px;font-weight:500}.pane-title>span{font-size:11px;color:#8a9582}.screen-frame{background:#eef0e9;min-height:230px;display:flex;align-items:center;justify-content:center;border-top:1px solid #e3e7dd;border-bottom:1px solid #e3e7dd}.screen-frame>img{display:block;width:100%;height:auto}.empty-screen{text-align:center;color:#92a08b;padding:60px 20px;font-size:12px}.empty-icon{font-size:36px;display:block;margin-bottom:15px}.screen-strip{display:flex;gap:8px;flex-wrap:wrap;padding:16px}.screen-strip>button{width:66px;background:#f6f7f2;border:1px solid #d9dfd1;padding:3px;border-radius:7px;color:#7a876d}.screen-strip>button.chosen{border-color:#4c7953;outline:1px solid #4c7953}.screen-strip img{width:100%;display:block}.screen-strip span{font-size:9px;display:block;padding:3px}.trace-link{display:block;margin:0 18px 18px;font-size:11px;color:#688058}.review-tabs{display:flex;border-bottom:1px solid #e3e7dd;padding:6px 16px 0;gap:12px}.review-tabs button{border:0;background:transparent;padding:15px 5px;color:#8c9783;font-size:12px;text-transform:capitalize;display:flex;gap:8px}.review-tabs button.active{color:#365d41;border-bottom:2px solid #365d41}.review-tabs button>span{font-size:10px;background:#edf2e6;border-radius:10px;padding:1px 5px}.tab-content{padding:22px;min-height:230px}.empty-review{padding:20px 0}.empty-review h3{font-size:16px;font-weight:500;margin-bottom:12px}.empty-review p,.finding>p,.limits-box p{font-size:12px;line-height:1.8;color:#7a8772}.finding{padding:0 0 20px;margin-bottom:20px;border-bottom:1px solid #edf0e7}.finding:last-child{margin-bottom:0}.finding .finding-kind{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:#929567;margin-bottom:7px}.finding h3{font-size:15px;font-weight:500;line-height:1.5;margin-bottom:8px}.citations{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}.citations>button,.action-list button{border:0;background:#eff4e7;color:#6a8257;padding:5px 8px;border-radius:5px;font-size:10px}.limits-box{background:#f8f3e8;padding:16px;border-radius:9px;margin-top:16px}.limits-box h3{font-size:12px;font-weight:500;margin-bottom:8px}.action-list{list-style:none}.action-list li{display:flex;gap:14px;padding:14px 0;border-bottom:1px solid #edf0e7}.action-number{font-size:11px;color:#8b9b7e;width:24px;height:24px;border-radius:100%;background:#f0f4e8;display:flex;align-items:center;justify-content:center}.action-list strong{font-size:12px;font-weight:500;overflow-wrap:anywhere}.action-list small{font-size:10px;display:block;color:#8b957f;margin-top:5px;margin-bottom:7px}.quiet,.interview-note{font-size:12px;color:#7e8976;line-height:1.7}.question-shortcuts{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0 24px}.question-shortcuts button{font-size:10px;border:1px solid #dce3d3;background:#f8faf4;color:#6c7c5d;padding:8px;border-radius:6px}.answer{padding:20px 0;border-top:1px solid #e5eadd}.answer h3{font-size:13px;font-weight:500;margin-bottom:16px}.statement{margin-bottom:16px}.statement>span{font-size:9px;text-transform:uppercase;letter-spacing:1px;color:#6c8759}.statement>span.inference{color:#a2854e}.statement>span.unknown{color:#8b9480}.statement>p{font-size:13px;line-height:1.8;margin-top:6px}.ask-form{border-top:1px solid #e5eadd;margin-top:22px}.ask-form .primary{margin-top:12px}.thinking{font-size:12px;color:#718460;padding:12px 0}.history{padding:48px 0}.history-heading{display:flex;justify-content:space-between;align-items:center;padding-bottom:22px}.history-heading>span{font-size:11px;color:#8c9784}.history-empty{border:1px dashed #cfd9c4;border-radius:12px;padding:30px;display:flex;align-items:center;gap:20px;color:#718568}.history-empty>span{font-size:30px}.history-empty p{font-size:13px}.history-empty small{display:block;font-size:11px;color:#8a967d;margin-top:6px}.history-row{display:flex;align-items:center;width:100%;gap:20px;text-align:left;border:0;border-top:1px solid #dce2d3;background:transparent;padding:20px 4px;color:inherit}.history-row>div{flex:1;min-width:0}.history-row strong{font-size:13px;font-weight:500;display:block}.history-row small{font-size:11px;color:#87927d;display:block;margin-top:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.history-status{display:flex;align-items:center;gap:6px;font-size:11px;text-transform:capitalize;min-width:85px}.history-row time{font-size:10px;color:#8c9783}.lab-footer{border-top:1px solid #dce2d3;display:flex;justify-content:space-between;gap:20px;padding:24px 0 32px;font-size:10px;color:#8a967e}@media(max-width:960px){.intro{gap:36px}.lab-header{padding:24px}.intro h1{letter-spacing:-1.8px}main{padding:0 24px}.workspace-grid{grid-template-columns:1fr}.description{font-size:15px}.model-state{font-size:10px}}@media(max-width:680px){.lab-header{padding:20px;align-items:flex-start}.model-state{max-width:125px;line-height:1.6}.brand{font-size:16px}.brand-mark{width:35px;height:35px;font-size:25px}main{padding:0 20px}.intro{grid-template-columns:1fr;padding-top:36px;gap:30px}.intro-copy h1{font-size:39px}.intro-note{margin-top:22px}.description{max-width:none}.test-form{padding:22px}.demo-strip{align-items:flex-start;flex-direction:column}.demo-actions{width:100%}.demo-actions button{flex:1}.history-row{gap:12px}.history-row time{display:none}.workspace-heading h2{font-size:23px}.lab-footer{flex-direction:column;gap:8px}.workspace-heading{gap:12px}.run-progress{padding:16px}.step-counter{white-space:nowrap}}
</style>
