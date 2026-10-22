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
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);

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

// ── backend: the FastAPI server, or recorded answers when there is none (e.g. GitHub Pages) ──

const live = {
  isStatic: false,
  videoUrl: (id) => `/api/videos/${id}/file`,
  frameUrl: (id, file) => `/api/videos/${id}/frames/${file}`,
  openDemo: async () => (await api('/api/demo', { method: 'POST' })).id,
  info: (id) => api(`/api/videos/${id}`),
  ask: (id, question, m) => api(`/api/videos/${id}/ask`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, mode: m }),
  }),
  questions: (id) => (id === 'demo' ? DEMO_QUESTIONS : []),
};

function recorded(data) {
  return {
    isStatic: true,
    videoUrl: () => `demo/${data.video}`,
    frameUrl: (_, file) => `demo/frames/${file}`,
    openDemo: async () => 'demo',
    info: async () => ({
      id: 'demo', stage: 'ready', name: 'Rooftop Beekeeping (demo)', duration: data.duration,
      language: data.language, keyframes: data.keyframes, segments: data.segments,
    }),
    ask: async (_, question, m) => {
      const q = data.questions.find((x) => x.question === question);
      if (!q) throw new Error('This recorded demo can only replay its 19 questions. Run the app locally to ask your own.');
      await new Promise((r) => setTimeout(r, 250));
      return data.answers[`${q.id}:${m}`];
    },
    questions: () => data.questions.map((q) => q.question),
  };
}

let backend = live;

async function detectBackend() {
  try {
    const h = await api('/api/health');
    const el = $('#health');
    el.textContent = h.key_configured ? `Mistral · ${h.chat_model}` : 'No API key: add MISTRAL_API_KEY to .env';
    el.className = `health ${h.key_configured ? 'ok' : 'bad'}`;
    const limits = [h.max_video_seconds ? `up to ${Math.round(h.max_video_seconds / 60)} min` : null, `${h.max_upload_mb} MB max`].filter(Boolean).join(' · ');
    $('#drop span').textContent = `MP4, MOV, MKV or WebM · ${limits} · or drop it here`;
    if (h.public_mode) $('#demo').textContent = 'Try the demo video (instant)';
    return;
  } catch { /* no server: fall back to the recorded demo */ }
  try {
    const data = await (await fetch('demo/data.json')).json();
    backend = recorded(data);
    $('#health').textContent = 'Recorded demo';
    $('#health').className = 'health ok';
    $('#drop').classList.add('disabled');
    $('#drop').removeAttribute('tabindex');
    $('#drop strong').textContent = 'Upload your own video';
    $('#drop span').innerHTML = 'Needs the app running locally: <a href="https://github.com/assim-ben-ahmed/video-rag#run-it">see how</a>';
    $('#demo').textContent = 'Open the demo video';
    $('#static-note').hidden = false;
    $('#q').disabled = true;
    $('#q').placeholder = 'Recorded demo: pick one of the questions above';
  } catch {
    $('#health').textContent = 'API offline';
    $('#health').className = 'health bad';
  }
}

// ── pick a video ──
const drop = $('#drop');
const canUpload = () => !backend.isStatic;
drop.addEventListener('click', (e) => { if (!canUpload() && !e.target.closest('a')) e.preventDefault(); });
drop.addEventListener('keydown', (e) => { if (canUpload() && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); $('#file').click(); } });
drop.addEventListener('dragover', (e) => { e.preventDefault(); if (canUpload()) drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', (e) => { e.preventDefault(); drop.classList.remove('over'); if (canUpload() && e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
$('#file').addEventListener('change', (e) => { if (e.target.files[0]) upload(e.target.files[0]); });
$('#demo').addEventListener('click', async () => {
  $('#demo').disabled = true;
  try { await start(await backend.openDemo()); } catch (err) { alert(err.message); }
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
    const info = await backend.info(id);
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
function suggestions() {
  $('#suggest').innerHTML = backend.questions(videoId).map((q) => `<button type="button">${esc(q)}</button>`).join('');
}

function open(info) {
  show('workspace');
  $('#player').src = backend.videoUrl(info.id);
  $('#vmeta').textContent = `${info.name} · ${fmt(info.duration)} · ${info.keyframes.length} keyframes · speech: ${info.language}`;
  $('#frames').innerHTML = info.keyframes.map((k) =>
    `<button type="button" class="ts-frame" data-t="${k.time}"><img src="${backend.frameUrl(info.id, k.file)}" alt="Keyframe at ${fmt(k.time)}" loading="lazy"><span>${fmt(k.time)}</span></button>`).join('');
  $('#frames').onclick = (e) => { const b = e.target.closest('[data-t]'); if (b) seek(+b.dataset.t); };
  $('#transcript').innerHTML = info.segments.map((s) =>
    `<p><button type="button" class="ts" data-t="${s.start}">${fmt(s.start)}</button> ${esc(s.text)}</p>`).join('') || '<p class="muted">No speech detected.</p>';
  $('#chat').innerHTML = '';
  suggestions();
}

$('#suggest').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  $('#q').value = b.textContent;
  ask(b.textContent);
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
  const timing = [a.latency_s != null ? `${a.latency_s}s` : null, `${a.llm_calls} LLM calls`].filter(Boolean).join(' · ');
  const verdict = a.correct === undefined ? '' : `<span class="verdict ${a.correct ? 'ok' : 'bad'}">${a.correct ? 'Correct' : 'Missed'}</span>`;
  return `<div class="answer"><div class="head"><span>${a.mode} ${verdict}</span><span>${timing}</span></div><p>${render(a.answer)}</p>${trace}${sources}</div>`;
}

async function ask(question) {
  if (!question || !videoId) return;
  $('#q').value = '';
  if (!backend.isStatic) $('#suggest').innerHTML = '';
  const chat = $('#chat');
  chat.insertAdjacentHTML('beforeend', `<div class="msg user">${esc(question)}</div>`);
  const slot = document.createElement('div');
  slot.className = 'thinking';
  slot.textContent = mode === 'compare' ? 'Asking all three modes…' : 'Thinking…';
  chat.append(slot);
  chat.scrollTop = chat.scrollHeight;
  const modes = mode === 'compare' ? ['simple', 'multimodal', 'agentic'] : [mode];
  try {
    const answers = await Promise.all(modes.map((m) => backend.ask(videoId, question, m)));
    slot.className = modes.length > 1 ? 'compare' : '';
    slot.innerHTML = answers.map(answerCard).join('');
  } catch (err) {
    slot.className = 'error';
    slot.textContent = err.message;
  }
  chat.scrollTop = chat.scrollHeight;
}

$('#ask').addEventListener('submit', (e) => {
  e.preventDefault();
  ask($('#q').value.trim());
});

// start: find the backend, then reopen ?v=<id> if present
detectBackend().then(() => {
  const fromUrl = new URLSearchParams(location.search).get('v');
  if (fromUrl) start(fromUrl).catch(() => show('start')); else show('start');
});
