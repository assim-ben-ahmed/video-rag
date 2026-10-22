const $ = (s) => document.querySelector(s);
const STAGES = ['audio', 'transcribe', 'keyframes', 'vision', 'index'];
const DEMO_QUESTIONS = [
  'How many hives are on the roof?',
  'What is the total price of the beginner kit?',
  'Which breed is the queen, and when was she marked?',
  'What should you do if you get stung?',
];
let videoId = null;
let mode = 'agentic';

const fmt = (s) => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const esc = (t) => t.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

function show(id) {
  for (const s of ['start', 'processing', 'workspace']) $(`#${s}`).hidden = s !== id;
}

function seek(seconds) {
  const v = $('#player');
  v.currentTime = seconds;
  v.play().catch(() => {});
}

// Answer text -> HTML: **bold** and clickable [mm:ss] / [mm:ss–mm:ss]
function render(text) {
  return esc(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[(\d{1,2}):(\d{2})(?:\s*[–-]\s*(\d{1,2}):(\d{2}))?\]/g, (m, a, b) =>
      `<button type="button" class="ts" data-t="${+a * 60 + +b}">${m.slice(1, -1)}</button>`)
    .replace(/\n/g, '<br>');
}

document.addEventListener('click', (e) => {
  const ts = e.target.closest('.ts');
  if (ts) seek(+ts.dataset.t);
});

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body;
}

// ── health ──
api('/api/health').then((h) => {
  const el = $('#health');
  el.textContent = h.key_configured ? `Mistral · ${h.chat_model}` : 'No API key: add MISTRAL_API_KEY to .env';
  el.className = `health ${h.key_configured ? 'ok' : 'bad'}`;
}).catch(() => { $('#health').textContent = 'API offline'; $('#health').className = 'health bad'; });

// ── pick a video ──
const drop = $('#drop');
drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); $('#file').click(); } });
drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('over'); if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
$('#file').addEventListener('change', (e) => { if (e.target.files[0]) upload(e.target.files[0]); });
$('#demo').addEventListener('click', async () => {
  $('#demo').disabled = true;
  try { await start((await api('/api/demo', { method: 'POST' })).id); } catch (err) { alert(err.message); }
  $('#demo').disabled = false;
});
$('#another').addEventListener('click', () => { history.replaceState(null, '', location.pathname); videoId = null; show('start'); });

async function upload(file) {
  show('processing');
  $('#proc-title').textContent = `Uploading ${file.name}`;
  const form = new FormData();
  form.append('file', file);
  try { await start((await api('/api/videos', { method: 'POST', body: form })).id); } catch (err) { $('#proc-msg').innerHTML = `<span class="error">${esc(err.message)}</span>`; }
}

async function start(id) {
  videoId = id;
  history.replaceState(null, '', `?v=${id}`);
  show('processing');
  $('#proc-title').textContent = 'Processing the video';
  for (;;) {
    const info = await api(`/api/videos/${id}`);
    if (info.stage === 'ready') return open(info);
    if (info.stage === 'error') { $('#proc-msg').innerHTML = `<span class="error">${esc(info.message || 'Failed')}</span>`; return; }
    $('#proc-bar').style.width = `${Math.round((info.progress || 0) * 100)}%`;
    $('#proc-msg').textContent = info.message || '';
    const at = STAGES.indexOf(info.stage);
    document.querySelectorAll('#steps li').forEach((li, i) => {
      li.className = i < at ? 'done' : i === at ? 'active' : '';
    });
    await new Promise((r) => setTimeout(r, 1000));
  }
}

// ── workspace ──
function open(info) {
  show('workspace');
  $('#player').src = `/api/videos/${info.id}/file`;
  $('#vmeta').textContent = `${info.name} · ${fmt(info.duration)} · ${info.keyframes.length} keyframes · speech: ${info.language}`;
  $('#frames').innerHTML = info.keyframes.map((k) =>
    `<button type="button" class="ts-frame" data-t="${k.time}"><img src="/api/videos/${info.id}/frames/${k.file}" alt="Keyframe at ${fmt(k.time)}" loading="lazy"><span>${fmt(k.time)}</span></button>`).join('');
  $('#frames').onclick = (e) => { const b = e.target.closest('[data-t]'); if (b) seek(+b.dataset.t); };
  $('#transcript').innerHTML = info.segments.map((s) =>
    `<p><button type="button" class="ts" data-t="${s.start}">${fmt(s.start)}</button> ${esc(s.text)}</p>`).join('') || '<p class="muted">No speech detected.</p>';
  $('#chat').innerHTML = '';
  $('#suggest').innerHTML = (info.id === 'demo' ? DEMO_QUESTIONS : []).map((q) => `<button type="button">${esc(q)}</button>`).join('');
}

$('#suggest').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (b) { $('#q').value = b.textContent; $('#ask').requestSubmit(); }
});

document.querySelectorAll('.modes button').forEach((b) => b.addEventListener('click', () => {
  mode = b.dataset.mode;
  document.querySelectorAll('.modes button').forEach((x) => x.setAttribute('aria-checked', String(x === b)));
}));

function answerCard(a) {
  const trace = a.trace?.length
    ? `<details><summary>How it found this (${a.trace.length} tool call${a.trace.length > 1 ? 's' : ''})</summary><ol>${a.trace.map((t) =>
      `<li><b>${esc(t.tool)}</b> ${esc(JSON.stringify(t.args))}</li>`).join('')}</ol></details>`
    : '';
  const sources = a.evidence?.length
    ? `<details><summary>Evidence (${a.evidence.length})</summary><ol>${a.evidence.map((e) =>
      `<li><button type="button" class="ts" data-t="${e.start}">${fmt(e.start)}</button> <i>${e.kind === 'speech' ? 'speech' : 'screen'}</i> ${esc(e.text.slice(0, 220))}</li>`).join('')}</ol></details>`
    : '';
  return `<div class="answer"><div class="head"><span>${a.mode}</span><span>${a.latency_s}s · ${a.llm_calls} LLM calls</span></div><p>${render(a.answer)}</p>${trace}${sources}</div>`;
}

$('#ask').addEventListener('submit', async (e) => {
  e.preventDefault();
  const question = $('#q').value.trim();
  if (!question || !videoId) return;
  $('#q').value = '';
  $('#suggest').innerHTML = '';
  const chat = $('#chat');
  chat.insertAdjacentHTML('beforeend', `<div class="msg user">${esc(question)}</div>`);
  const slot = document.createElement('div');
  slot.className = 'thinking';
  slot.textContent = mode === 'compare' ? 'Asking all three modes…' : 'Thinking…';
  chat.append(slot);
  chat.scrollTop = chat.scrollHeight;
  const modes = mode === 'compare' ? ['simple', 'multimodal', 'agentic'] : [mode];
  try {
    const answers = await Promise.all(modes.map((m) => api(`/api/videos/${videoId}/ask`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, mode: m }),
    })));
    slot.className = modes.length > 1 ? 'compare' : '';
    slot.innerHTML = answers.map(answerCard).join('');
  } catch (err) {
    slot.className = 'error';
    slot.textContent = err.message;
  }
  chat.scrollTop = chat.scrollHeight;
});

// reopen ?v=<id>
const fromUrl = new URLSearchParams(location.search).get('v');
if (fromUrl) start(fromUrl).catch(() => show('start')); else show('start');
