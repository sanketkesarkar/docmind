'use strict';

const PAGE_W = 595.28, PAGE_H = 841.89; // A4 points, from pdfinfo
const PAGES = ['Company and service overview', 'Plans, limits and pricing', 'Onboarding and access roles', 'PDF ingestion and recovery',
  'Retrieval, answers and citations', 'Security and regional boundaries', 'Retention, deletion and exports', 'Support and incident response',
  'Billing and worked examples', 'Operating scenarios and roadmap'];

// Highlight boxes are line bounding boxes from `pdftotext -bbox-layout`, in PDF points.
const examples = {
  pricing: {
    question: 'What does a Team plan with 18 seats cost?',
    page: 9, box: [54, 162, 541, 248],
    label: 'SAMPLE ANSWER', title: '$226 per month',
    answer: 'The base plan covers 15 seats. With 18 active seats, the 3 additional seats add $27: $199 + $27 = $226 before tax.',
    note: 'Based on the answer observed in the local DocMind test, shortened for display.'
  },
  annual: {
    question: 'What is the annual cost for 18 Team seats?',
    page: 9, box: [54, 255, 541, 356],
    label: 'SAMPLE ANSWER', title: '$2,353.80 per year',
    answer: 'The discounted annual base is $2,029.80. Three additional seats cost $324 for the year, giving a total of $2,353.80 before tax.',
    note: 'Prepared sample answer from the handbook. This annual question has not been shown in the live API test.'
  },
  missing: {
    question: 'What is the CEO’s favorite food?',
    page: null,
    label: 'ANSWER-TEXT REFUSAL', title: 'Not enough information',
    answer: "I don't have enough information in the provided documents to answer this question.",
    note: 'Answer text observed in the local API test. The API still returned citations and abstaining=false; that metadata mismatch remains unresolved.'
  }
};

const $ = id => document.getElementById(id);
const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const wait = ms => new Promise(r => setTimeout(r, reduce ? 0 : ms));
let run = 0;

// ---------- Document viewer ----------
function buildStrip() {
  $('strip').innerHTML = PAGES.map((t, i) => `<li><button data-page="${i + 1}" aria-label="Page ${i + 1}: ${t}" title="${i + 1}. ${t}">
    <img src="assets/pages/page-${String(i + 1).padStart(2, '0')}.jpg" alt="" loading="lazy"><span>${i + 1}</span></button></li>`).join('');
}

function showPage(n, box) {
  const img = $('page-img');
  const src = `assets/pages/page-${String(n).padStart(2, '0')}.jpg`;
  if (!img.src.endsWith(src)) img.src = src;
  img.alt = `Page ${n} of the CloudHarbor handbook`;
  $('page-caption').textContent = `Page ${n} of 10 · ${PAGES[n - 1]}`;
  document.querySelectorAll('[data-page]').forEach(b => b.classList.toggle('on', Number(b.dataset.page) === n));
  const hl = $('hl');
  hl.classList.remove('show');
  if (box) {
    const [x1, y1, x2, y2] = box;
    Object.assign(hl.style, { left: `${x1 / PAGE_W * 100}%`, top: `${y1 / PAGE_H * 100}%`, width: `${(x2 - x1) / PAGE_W * 100}%`, height: `${(y2 - y1) / PAGE_H * 100}%` });
    requestAnimationFrame(() => requestAnimationFrame(() => hl.classList.add('show')));
    // Scroll the highlight into view inside the viewer.
    const wrap = $('viewer');
    const target = (y1 / PAGE_H) * $('page-wrap').offsetHeight - 40;
    wrap.scrollTo({ top: Math.max(0, target), behavior: reduce ? 'auto' : 'smooth' });
  }
}

// ---------- Pipeline ----------
function setStep(step, status) {
  const li = document.querySelector(`[data-step="${step}"]`);
  li.className = status;
}
function resetPipeline() {
  document.querySelectorAll('[data-step]').forEach(li => { li.className = ''; });
}

async function typeQuestion(text, id) {
  const q = $('demo-q');
  q.classList.add('typing');
  q.textContent = '';
  for (let i = 1; i <= text.length; i++) {
    if (id !== run) return false;
    q.textContent = text.slice(0, i);
    await wait(16);
  }
  q.classList.remove('typing');
  return true;
}

async function streamText(el, text, id) {
  el.textContent = '';
  const words = text.split(' ');
  for (let i = 1; i <= words.length; i++) {
    if (id !== run) return false;
    el.textContent = words.slice(0, i).join(' ');
    await wait(40);
  }
  return true;
}

async function select(key) {
  const id = ++run;
  const item = examples[key];
  document.querySelectorAll('[data-example]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.example === key)));
  resetPipeline();
  $('answer').className = 'answer';
  $('answer-label').textContent = 'THINKING';
  $('answer-title').textContent = '';
  $('answer-body').textContent = '';
  $('citations').innerHTML = '';
  $('answer-foot').textContent = '';
  $('hl').classList.remove('show');
  $('viewer').classList.remove('none');
  document.querySelectorAll('[data-page]').forEach(b => b.classList.remove('scan', 'dim'));

  if (!(await typeQuestion(item.question, id))) return;

  for (const step of ['embed', 'search', 'fuse']) {
    setStep(step, 'active');
    if (step === 'search') {
      // Sweep the page strip while retrieval runs.
      const btns = [...document.querySelectorAll('[data-page]')];
      for (const b of btns) { if (id !== run) return; b.classList.add('scan'); await wait(45); b.classList.remove('scan'); }
    } else {
      await wait(380);
    }
    if (id !== run) return;
    setStep(step, 'done');
  }

  setStep('check', 'active');
  await wait(420);
  if (id !== run) return;
  const checkNote = document.querySelector('[data-step="check"] small');
  if (item.page) {
    setStep('check', 'done');
    checkNote.textContent = 'Cosine similarity threshold';
  } else {
    // Observed behavior: weak evidence still passed and the model refused in text.
    setStep('check', 'warn');
    checkNote.textContent = 'Passed, though no passage was relevant';
  }

  if (item.page) {
    showPage(item.page, item.box);
  } else {
    document.querySelectorAll('[data-page]').forEach(b => b.classList.add('dim'));
    $('viewer').classList.add('none');
  }

  setStep('stream', 'active');
  $('answer-label').textContent = item.label;
  $('answer-pill').textContent = item.page ? 'Sample answer' : 'Observed refusal';
  $('answer').classList.add(item.page ? 'found' : 'refused');
  $('answer-title').textContent = item.title;
  if (!(await streamText($('answer-body'), item.answer, id))) return;
  setStep('stream', 'done');

  $('citations').innerHTML = item.page
    ? `<button class="citation" data-cite="${key}">📄 Source: page ${item.page}</button><a class="citation ghost" target="_blank" rel="noopener" href="assets/CloudHarbor_Operations_Handbook.pdf#page=${item.page}">Open in PDF ↗</a>`
    : '';
  $('answer-foot').textContent = item.note;
}

// ---------- Hero: one orchestrated moment ----------
async function heroLoop() {
  const q = 'What does a Team plan with 18 seats cost?';
  const el = $('hero-q');
  const ans = $('hero-answer');
  if (reduce) { el.textContent = q; ans.classList.add('show'); return; }
  await new Promise(r => setTimeout(r, 600));
  for (let i = 1; i <= q.length; i++) { el.textContent = q.slice(0, i); await new Promise(r => setTimeout(r, 38)); }
  await new Promise(r => setTimeout(r, 450));
  ans.classList.add('show');
}

// ---------- Events ----------
document.addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  if (b.dataset.example) select(b.dataset.example);
  else if (b.dataset.page) {
    const n = Number(b.dataset.page);
    $('viewer').classList.remove('none');
    const active = Object.values(examples).find(x => x.page === n && document.querySelector(`[data-example][aria-pressed="true"]`) && examples[document.querySelector('[data-example][aria-pressed="true"]').dataset.example] === x);
    showPage(n, active ? active.box : null);
  } else if (b.dataset.cite) {
    const item = examples[b.dataset.cite];
    $('viewer').classList.remove('none');
    showPage(item.page, item.box);
    if (window.innerWidth < 980) document.querySelector('.doc-panel').scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
  }
});

buildStrip();
showPage(1, null);
heroLoop();

// Run the first question when the demo scrolls into view.
let started = false;
const start = () => { if (!started) { started = true; select('pricing'); } };
if ('IntersectionObserver' in window) {
  new IntersectionObserver((entries, obs) => { if (entries.some(x => x.isIntersecting)) { start(); obs.disconnect(); } }, { threshold: 0.3 }).observe($('ask'));
} else start();
