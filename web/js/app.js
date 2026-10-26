// Match Center: SSE replay on an SVG pitch, moment timeline, win-probability chart, persona cards (with English
// beside every translation), side-by-side compare, what-if panel, overlay cues and the agent trace.
import { api } from './api.js';
import { PitchView } from './pitch.js';
import { wpChart, whatifChart } from './charts.js';

const KIND = { goal: ['Goal', 'i-goal'], big_chance: ['Big chance', 'i-chance'], red_card: ['Red card', 'i-card'],
  momentum_shift: ['Momentum shift', 'i-momentum'], press_collapse: ['Press collapse', 'i-press'], sub_effect: ['Substitution effect', 'i-sub'] };
const DNA = [['press_intensity', 'Press'], ['tempo', 'Tempo'], ['directness', 'Direct'], ['width', 'Width']];
const MODES = { casual: 'Casual fan', analyst: 'Analyst', beginner: 'Beginner', audio: 'Audio description' };
const LANGS = { en: 'English', hi: 'हिन्दी', es: 'Español' };
const RTL = new Set(['ar']);
const DENSITY = ['light', 'normal', 'dense'];
const MARKER_PX = 34;
const TEAM_LABELS = ['Team', 'Team taking control', 'Pressing team'];
// Match stats: [key, label, unit]. Possession is the share of passes, the usual proxy without tracking data.
const STATS = [['poss', 'Possession', '%'], ['xg', 'Expected goals (xG)', ''], ['shots', 'Shots', ''], ['sot', 'On target', ''],
  ['pacc', 'Pass accuracy', '%'], ['corners', 'Corners', ''], ['fouls', 'Fouls', ''], ['cards', 'Cards', '']];

const $ = (id) => document.getElementById(id);
const S = {
  mid: null, d: null, persona: { mode: 'casual', lang: 'en', fav_club: '', fav_player: '', player_lock: false, analogy: 'none', stats_density: 1 },
  cards: [], cues: [], selected: null, t: 0, es: null, shownCues: '', compare: [{ mode: 'analyst', lang: 'en' }, { mode: 'beginner', lang: 'hi' }],
  cardCache: new Map(), chart: null, rerun: null,
};
const pitch = new PitchView($('pitch'));

function h(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else if (k === 'text') n.textContent = v;
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const k of kids.flat()) if (k !== null && k !== undefined) n.append(k);
  return n;
}

const SVG_NS = 'http://www.w3.org/2000/svg';
function icon(id, cls = 'ic') {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', cls);
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttribute('href', `#${id}`);
  svg.append(use);
  return svg;
}
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const skeletons = (n) => Array.from({ length: n }, () => h('div', { class: 'skel', 'aria-hidden': 'true' }, h('i'), h('i'), h('i')));
const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

// Shield crest drawn from the club's id; colour follows the side (home/away), as in every chart.
function crest(team, side) {
  return `<svg viewBox="0 0 50 56"><defs><linearGradient id="cg-${side}" x1="0" y1="0" x2="0" y2="1">`
    + `<stop offset="0" stop-color="var(--${side})"/><stop offset="1" stop-color="var(--${side})" stop-opacity=".55"/></linearGradient></defs>`
    + `<path d="M25 2 46 9v17c0 14-9 23-21 28C13 49 4 40 4 26V9z" fill="url(#cg-${side})" stroke="rgba(255,255,255,.35)" stroke-width="1.2"/>`
    + `<path d="M25 7 41 12.5V26c0 10.5-6.5 17.6-16 21.8" fill="none" stroke="rgba(255,255,255,.18)" stroke-width="1.2"/>`
    + `<text x="25" y="33" text-anchor="middle" font-family="Geist Mono, monospace" font-weight="600" font-size="12.5" fill="#0b1310">${esc(team.id)}</text></svg>`;
}

function dna(team, side) {
  return DNA.map(([k, label]) => h('span', { title: `${label} ${Math.round(team.style[k] * 100)}/100` }, label,
    h('i', { style: `--v:${team.style[k]};--team:var(--${side})` })));
}

// --- time helpers ------------------------------------------------------------------------------------------
function minuteOf(t) {
  const ps = S.d.periods;
  const p = [...ps].reverse().find((x) => t >= x.t0) || ps[0];
  return Math.max(0, p.minute0 + (t - p.t0) / 60);
}
const moment = (id) => S.d.moments.find((m) => m.id === id);
const evidence = (m, id) => m.evidence.find((e) => e.id === id);
const sideOf = (m) => {
  const team = m.evidence.find((e) => TEAM_LABELS.includes(e.label));
  return team && team.value === S.d.meta.away.name ? 'away' : 'home';
};
const scoreAt = (t) => {
  const g = S.d.meta.goals.filter((x) => x.t <= t);
  return [g.filter((x) => x.team === S.d.meta.home.id).length, g.filter((x) => x.team === S.d.meta.away.id).length];
};
const fmtUnit = (e) => (e.unit && !e.unit.startsWith('index') ? `${e.unit === '%' ? '' : ' '}${e.unit}` : '');
const kindTitle = (m) => `${Math.floor(minuteOf(m.t_start))}' ${KIND[m.kind][0]}`;

// --- replay ------------------------------------------------------------------------------------------------
function setPlaying(on) {
  $('play').replaceChildren(icon(on ? 'i-pause' : 'i-play'), h('span', { text: on ? 'Pause' : 'Play' }));
  $('play').setAttribute('aria-pressed', on);
}

function play() {
  stop();
  const es = new EventSource(api.replayUrl(S.mid, S.t, $('speed').value));
  es.addEventListener('ev', (msg) => onEvent(JSON.parse(msg.data)));
  es.addEventListener('end', stop);
  es.onerror = stop;
  S.es = es;
  setPlaying(true);
}

function stop() {
  if (S.es) S.es.close();
  S.es = null;
  setPlaying(false);
}

function seek(t) {
  const playing = !!S.es;
  stop();
  S.t = Math.max(0, Math.min(t, S.d.meta.duration));
  pitch.reset();
  $('last-event').textContent = '';
  tick();
  if (playing) play();
}

function playerName(id) {
  for (const s of ['home', 'away']) {
    const p = S.d.meta[s].players.find((x) => x.id === id);
    if (p) return p.name;
  }
  return '';
}

function onEvent(e) {
  S.t = e.t;
  pitch.show(e);
  $('last-event').textContent = `${e.minute}' ${playerName(e.player_id)} · ${e.type.replace('_', ' ')}${e.outcome ? ` (${e.outcome})` : ''}`;
  if (e.type === 'goal') goalBurst(e);
  tick();
}

function goalBurst(e) {
  const box = $('goal-burst'), side = e.team === S.d.meta.home.id ? 'home' : 'away';
  box.style.setProperty('--team', `var(--${side})`);
  box.replaceChildren(h('div', {}, h('b', { text: 'Goal' }), h('span', { text: `${e.minute}' ${playerName(e.player_id)} · ${S.d.meta[side].name}` })));
  box.classList.remove('on');
  void box.offsetWidth;  // restart the animation
  box.classList.add('on');
}

function tick() {
  const t = S.t, min = minuteOf(t);
  const [a, b] = scoreAt(t);
  const score = `${a} – ${b}`, scoreEl = $('score');
  if (scoreEl.textContent !== score) {
    scoreEl.textContent = score;
    scoreEl.classList.remove('bump'); void scoreEl.offsetWidth; scoreEl.classList.add('bump');
  }
  $('clock').textContent = `${Math.floor(min)}'`;
  $('clock-bar').setAttribute('width', Math.min(120, (min / Math.max(S.maxMin, 90)) * 120).toFixed(1));
  const seekEl = $('seek');
  if (document.activeElement !== seekEl) seekEl.value = t;
  seekEl.style.setProperty('--p', `${(seekEl.value / seekEl.max) * 100}%`);
  seekEl.setAttribute('aria-valuetext', `minute ${Math.floor(min)}, score ${a} – ${b}`);
  S.chart?.setMinute(min);
  const ph = $('timeline').querySelector('.playhead');
  if (ph) ph.style.insetInlineStart = `${(min / S.maxMin) * 100}%`;
  showCues(t);
  showStats(t, min);
}

// --- match stats -------------------------------------------------------------------------------------------
// Running totals after every event, so any replay time is one binary search away.
function buildStats(evs) {
  const { home, away } = S.d.meta;
  const zero = () => ({ passes: 0, pok: 0, xg: 0, shots: 0, sot: 0, corners: 0, fouls: 0, cards: 0 });
  const acc = { [home.id]: zero(), [away.id]: zero() };
  const snaps = [{ t: -1, home: zero(), away: zero() }];
  for (const e of evs) {
    const s = acc[e.team];
    if (!s) continue;
    if (e.type === 'pass') { s.passes += 1; if (e.outcome === 'success') s.pok += 1; }
    else if (e.type === 'shot') { s.shots += 1; s.xg += e.xg || 0; if (e.outcome === 'goal' || e.outcome === 'saved') s.sot += 1; }
    else if (e.type === 'corner') s.corners += 1;
    else if (e.type === 'foul') s.fouls += 1;
    else if (e.type === 'card') s.cards += 1;
    snaps.push({ t: e.t, home: { ...acc[home.id] }, away: { ...acc[away.id] } });
  }
  S.stats = snaps;
  S.shownStats = '';
  $('stats').replaceChildren(...STATS.map(([k, label]) => h('div', { class: 'st', role: 'listitem', 'data-k': k },
    h('b', { class: 'v home' }), h('span', { class: 'lbl', text: label }), h('b', { class: 'v away' }),
    h('span', { class: 'bar', 'aria-hidden': 'true' }, h('i', { class: 'home' }), h('i', { class: 'away' })))));
}

function statValues(s, o) {
  const passes = s.passes + o.passes;
  return { poss: passes ? Math.round((s.passes / passes) * 100) : 50, xg: s.xg.toFixed(2), shots: s.shots, sot: s.sot,
    pacc: s.passes ? Math.round((s.pok / s.passes) * 100) : 0, corners: s.corners, fouls: s.fouls, cards: s.cards };
}

function showStats(t, min) {
  if (!S.stats) return;
  let lo = 0, hi = S.stats.length - 1;  // last snapshot at or before t
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (S.stats[mid].t <= t) lo = mid; else hi = mid - 1; }
  const snap = S.stats[lo];
  const hv = statValues(snap.home, snap.away), av = statValues(snap.away, snap.home);
  const key = `${Math.floor(min)}|${JSON.stringify(hv)}|${JSON.stringify(av)}`;
  if (key === S.shownStats) return;
  S.shownStats = key;
  $('stats-at').textContent = `Counted from the event stream up to ${Math.floor(min)}'`;
  const { home, away } = S.d.meta;
  for (const [k, label, unit] of STATS) {
    const row = $('stats').querySelector(`[data-k="${k}"]`);
    const a = Number(hv[k]), b = Number(av[k]);
    const [vh, va] = row.querySelectorAll('.v'), [bh, ba] = row.querySelectorAll('.bar i');
    vh.textContent = `${hv[k]}${unit}`;
    va.textContent = `${av[k]}${unit}`;
    // fouls and cards: fewer is better, so the "lead" highlight is for the other side
    const better = k === 'fouls' || k === 'cards' ? -1 : 1;
    const lead = Math.sign((a - b) * better);
    for (const [n, on] of [[vh, lead > 0], [va, lead < 0], [bh, lead > 0], [ba, lead < 0]]) n.classList.toggle('lead', on);
    const total = a + b;
    bh.style.flexGrow = total ? a / total : 1;
    ba.style.flexGrow = total ? b / total : 1;
    row.setAttribute('aria-label', `${label}: ${home.name} ${hv[k]}${unit}, ${away.name} ${av[k]}${unit}`);
  }
}

function showCues(t) {
  const active = S.cues.filter((c) => c.in_t <= t && t < c.out_t);
  const key = active.map((c) => c.cue_id).join('|');
  if (key === S.shownCues) return;
  S.shownCues = key;
  const layer = $('overlay-layer');
  layer.replaceChildren(...active.map(cueEl));
  const lt = active.find((c) => c.template === 'lower_third');
  if (lt) {
    $('caption').textContent = lt.a11y.speech_text;
    $('caption').lang = lt.lang;
    $('caption').dir = RTL.has(lt.lang) ? 'rtl' : 'ltr';
    if (lt.payload.moment_id !== S.selected) select(lt.payload.moment_id, { follow: true });
  }
}

function cueEl(c) {
  const p = c.payload;
  const n = h('div', { class: `cue ${c.template}`, lang: c.lang, dir: RTL.has(c.lang) ? 'rtl' : 'ltr' });
  if (c.template === 'lower_third') n.append(h('b', { text: p.title }), p.text);
  else if (c.template === 'stat_bug') n.textContent = `${p.label}: ${p.value}${fmtUnit(p)}`;
  else if (c.template === 'wp_swing') n.textContent = `${p.club} win prob ${p.before}% → ${p.after}%`;
  else if (c.template === 'player_tag') n.textContent = p.club ? `${p.player} · ${p.club}` : p.player;
  else n.textContent = `${p.club} PPDA ${p.ppda_before} → ${p.ppda_after}`;
  return n;
}

// --- match load ----------------------------------------------------------------------------------------------
async function loadMatch(mid) {
  stop();
  S.mid = mid;
  S.cardCache.clear();
  $('cards').replaceChildren(...skeletons(4));
  const [d, evs] = await Promise.all([api.match(mid), api.events(mid)]);
  const apply = () => { renderMatch(mid, d); buildStats(evs); };
  // Cross-fade between fixtures where the browser supports view transitions.
  if (S.d && document.startViewTransition && !reducedMotion()) await document.startViewTransition(apply).updateCallbackDone;
  else apply();
  await refreshPersona();
  seek(0);
  $('caption').lang = 'en';
  $('caption').textContent = `${d.meta.title}: ${d.meta.story} Press play, or pick a moment on the timeline.`;
}

function renderMatch(mid, d) {
  S.d = d;
  const { meta } = d;
  history.replaceState(null, '', `#${mid}`);
  $('home-name').textContent = meta.home.name;
  $('away-name').textContent = meta.away.name;
  $('home-crest').innerHTML = crest(meta.home, 'home');
  $('away-crest').innerHTML = crest(meta.away, 'away');
  $('home-dna').replaceChildren(...dna(meta.home, 'home'));
  $('away-dna').replaceChildren(...dna(meta.away, 'away'));
  $('match-title').textContent = meta.title;
  $('story').textContent = meta.story;
  pitch.setHome(meta.home.id);
  S.maxMin = S.d.wp[S.d.wp.length - 1].minute;
  $('seek').max = Math.ceil(meta.duration);
  fillPersonaOptions();
  buildTimeline();
  S.chart = wpChart($('wp-chart'), S.d.wp, S.d.moments, { home: meta.home.name, away: meta.away.name }, minuteOf, (m) => {
    const near = [...S.d.moments].sort((x, y) => Math.abs(minuteOf(x.t_start) - m) - Math.abs(minuteOf(y.t_start) - m))[0];
    if (near) select(near.id, { seek: true });
  });
  S.t = 0;
  S.selected = [...S.d.moments].sort((x, y) => y.importance - x.importance)[0]?.id;
  const kinds = [...new Set(S.d.moments.map((m) => m.kind))];
  $('kind-legend').replaceChildren(...kinds.map((k) => h('span', {}, icon(KIND[k][1]), KIND[k][0])));
}

function buildTimeline() {
  const tl = $('timeline');
  tl.replaceChildren(h('div', { class: 'half', style: `inset-inline-start:${(45 / S.maxMin) * 100}%`, 'aria-hidden': 'true' }),
    h('div', { class: 'playhead', 'aria-hidden': 'true' }));
  const lanes = [];  // stack markers that would overlap on this screen width
  const minGap = (MARKER_PX / Math.max(tl.clientWidth, 200)) * 100;
  for (const m of [...S.d.moments].sort((a, b) => a.t_start - b.t_start)) {
    const x = (minuteOf(m.t_start) / S.maxMin) * 100;
    let lane = lanes.findIndex((last) => x - last >= minGap);
    if (lane < 0) lane = lanes.length;
    lanes[lane] = x;
    const [label, ic] = KIND[m.kind];
    const team = m.evidence.find((e) => TEAM_LABELS.includes(e.label));
    tl.append(h('button', {
      class: `mk ${sideOf(m)}`, type: 'button', role: 'listitem', 'data-id': m.id, 'data-kind': m.kind,
      style: `inset-inline-start:${x}%;top:${9 + lane * 36}px`,
      'aria-label': `Minute ${Math.floor(minuteOf(m.t_start))}: ${label}${team ? `, ${team.value}` : ''}`,
      'data-tip': `${kindTitle(m)}${team ? ` · ${team.value}` : ''}`,
      'aria-current': m.id === S.selected,
      onclick: () => select(m.id, { seek: true }),
    }, icon(ic)));
  }
  tl.style.height = `${18 + lanes.length * 36}px`;
}

function fillPersonaOptions() {
  const f = $('persona-form');
  const { home, away } = S.d.meta;
  f.fav_club.replaceChildren(h('option', { value: '', text: 'None' }), ...[home, away].map((t) => h('option', { value: t.id, text: t.name })));
  S.persona.fav_club = '';
  S.persona.fav_player = '';
  fillPlayers();
}

function fillPlayers() {
  const f = $('persona-form');
  const { home, away } = S.d.meta;
  const teams = [home, away].filter((t) => !S.persona.fav_club || t.id === S.persona.fav_club);
  f.fav_player.replaceChildren(h('option', { value: '', text: 'None' }),
    ...teams.flatMap((t) => t.players.map((p) => h('option', { value: p.id, text: `${p.name} (${t.id} #${p.number})` }))));
  f.fav_player.value = S.persona.fav_player;
  if (f.fav_player.value !== S.persona.fav_player) S.persona.fav_player = '';
}

function personaFromForm() {
  const f = $('persona-form');
  const club = f.fav_club.value;
  if (club !== S.persona.fav_club) { S.persona.fav_club = club; fillPlayers(); }
  Object.assign(S.persona, {
    mode: f.mode.value, lang: f.lang.value, fav_player: f.fav_player.value, player_lock: f.player_lock.checked,
    analogy: f.analogy.checked ? 'cricket' : 'none', stats_density: Number(f.stats_density.value),
  });
  f.stats_density.setAttribute('aria-valuetext', DENSITY[S.persona.stats_density]);
}

async function refreshPersona() {
  const [c, o] = await Promise.all([api.cards(S.mid, S.persona), api.overlays(S.mid, S.persona)]);
  S.cards = c.cards;
  S.cues = o.cues;
  S.shownCues = '';
  renderCards();
  renderCues();
  renderCompare();
  renderTrace();
  renderWhatif();
  tick();
}

// --- selection -------------------------------------------------------------------------------------------
function select(id, { seek: doSeek = false, follow = false } = {}) {
  if (!id) return;
  S.selected = id;
  S.rerun = null;
  for (const b of $('timeline').querySelectorAll('.mk')) b.setAttribute('aria-current', b.dataset.id === id);
  for (const c of $('cards').querySelectorAll('.card')) c.setAttribute('aria-current', c.dataset.id === id);
  if (follow) revealCard(id);
  if (doSeek) seek(moment(id).t_start);  // opens the moment's overlay window
  if (!follow || !document.querySelector('#panel-story:not([hidden])')) {
    renderCompare(); renderWhatif(); renderTrace();
  }
  renderCues();
}

// While the replay runs, keep the active card in view inside the side panel (desktop, where it scrolls).
function revealCard(id) {
  const box = document.querySelector('.panels'), card = $('cards').querySelector(`.card[data-id="${id}"]`);
  if (!card || box.scrollHeight <= box.clientHeight) return;
  box.scrollTo({ top: card.offsetTop - box.offsetTop - 12, behavior: reducedMotion() ? 'auto' : 'smooth' });
}

// --- cards -----------------------------------------------------------------------------------------------
function sentenceEl(s, m, lang) {
  const cites = h('span', {});
  const pop = h('div', { class: 'ev-pop', hidden: true });
  for (const id of s.evidence_ids) {
    const e = evidence(m, id);
    cites.append(h('button', {
      class: 'cite', type: 'button', text: id.split('.').pop(), 'aria-expanded': 'false',
      'aria-label': `Evidence ${id}${e ? `: ${e.label}` : ''}`,
      onclick: (ev) => {
        const open = ev.currentTarget.getAttribute('aria-expanded') === 'true';
        for (const b of cites.children) b.setAttribute('aria-expanded', 'false');
        pop.hidden = open;
        if (!open) {
          ev.currentTarget.setAttribute('aria-expanded', 'true');
          pop.textContent = e ? `${id} · ${e.label}: ${e.value}${fmtUnit(e)}` : `${id} (analogy pack)`;
        }
      },
    }));
  }
  const main = h('p', { class: 'sent', lang, dir: RTL.has(lang) ? 'rtl' : 'ltr' }, s.text, cites);
  if (lang === 'en' || !s.en_text) return h('div', {}, main, pop);
  return h('div', {}, h('div', { class: 'bi' },
    h('div', {}, h('span', { class: 'lang-tag', text: LANGS[lang] || lang }), main),
    h('div', { class: 'en', lang: 'en', dir: 'ltr' }, h('span', { class: 'lang-tag', text: 'English' }), h('p', { class: 'sent', text: s.en_text }))),
  s.back_translation ? h('p', { class: 'bt', lang: 'en', text: `Back-translation check: ${s.back_translation}` }) : null, pop);
}

function cardEl(c, { watch = true } = {}) {
  const m = moment(c.moment_id);
  const chip = (cls, ic, text) => h('span', { class: `chip ${cls}` }, ic ? icon(ic) : null, text);
  const chips = h('span', { class: 'chips' },
    c.verified ? chip('ok', 'i-check', 'verified') : chip('bad', 'i-alert', 'unverified'),
    c.degraded ? chip('warn', 'i-alert', c.lang !== (c.wanted_lang || S.persona.lang) ? 'English fallback' : 'template fallback') : null,
    c.analogy ? chip('', null, 'cricket analogy') : null,
    c.fav_club ? chip('', 'i-star', 'your club') : null,
    c.fav_player ? chip('', 'i-star', 'your player') : null);
  return h('article', { class: 'card', 'data-id': c.moment_id, 'data-side': sideOf(m), 'aria-current': c.moment_id === S.selected, lang: c.lang },
    h('header', {}, h('span', { class: `k ${m.kind}` }, icon(KIND[m.kind][1])),
      h('span', { class: 'min', text: `${Math.floor(minuteOf(m.t_start))}'` }), h('span', { class: 't', text: KIND[m.kind][0] }), chips,
      watch ? h('button', { type: 'button', 'aria-label': `Watch ${kindTitle(m)}`, onclick: () => select(c.moment_id, { seek: true }) }, icon('i-play'), 'Watch') : null),
    c.sentences.map((s) => sentenceEl(s, m, c.lang)),
    c.audio ? h('audio', { controls: true, preload: 'none', src: api.audioUrl(S.mid, c.audio), 'aria-label': `Audio description, ${kindTitle(m)}` }) : null);
}

function renderCards() {
  const box = $('cards');
  box.replaceChildren(...(S.cards.length
    ? S.cards.map((c, i) => { const n = cardEl(c); n.style.setProperty('--i', i); return n; })
    : [h('div', { class: 'empty' }, h('p', { text: 'No moments for this persona.' }),
      h('p', { class: 'hint', text: 'Player-lock keeps only your player’s moments. Pick another player or switch it off.' }))]));
}

// --- compare ---------------------------------------------------------------------------------------------
async function slotCards(slot) {
  const p = { ...S.persona, ...slot };
  const key = JSON.stringify(p);
  if (!S.cardCache.has(key)) S.cardCache.set(key, api.cards(S.mid, p).then((r) => r.cards));
  return S.cardCache.get(key);
}

async function renderCompare() {
  const box = $('compare');
  const sel = S.selected;
  const slots = await Promise.all(S.compare.map(async (slot, i) => {
    const cards = await slotCards(slot);
    const c = cards.find((x) => x.moment_id === sel);
    const pick = (name, opts) => h('select', { 'aria-label': `Viewer ${i + 1} ${name}`, onchange: (ev) => { slot[name] = ev.target.value; renderCompare(); } },
      Object.entries(opts).map(([v, t]) => h('option', { value: v, text: t, selected: slot[name] === v })));
    return h('div', { class: 'slot' }, h('span', { class: 'who', text: `Viewer ${'AB'[i]}` }), h('div', { class: 'row' }, pick('mode', MODES), pick('lang', LANGS)),
      c ? cardEl(c, { watch: false }) : h('p', { class: 'hint', text: 'No card for this moment.' }));
  }));
  if (sel === S.selected) box.replaceChildren(...slots);
}

// --- what if ---------------------------------------------------------------------------------------------
async function renderWhatif(live = false) {
  const box = $('whatif');
  const sel = S.selected, m = moment(sel);
  box.replaceChildren(...(live ? [h('p', { class: 'hint', text: 'Running 200 simulated rest-of-match rollouts for each scenario…' })] : []), ...skeletons(2));
  const r = await api.whatif(S.mid, sel, live);
  if (sel !== S.selected) return;
  const head = h('h3', { text: kindTitle(m) });
  if (!r.counterfactual) {
    box.replaceChildren(head, h('p', { text: 'No what-if was precomputed for this moment.' }),
      h('button', { type: 'button', onclick: (ev) => { ev.currentTarget.disabled = true; renderWhatif(true); } }, icon('i-flask'), 'Simulate now (200 rollouts, ~5 s)'));
    return;
  }
  const cf = r.counterfactual;
  const ev = (label) => r.evidence.find((e) => e.label === label)?.value;
  const names = { home: S.d.meta.home.name, away: S.d.meta.away.name };
  const d = ev(`What-if: change in ${names.home} win chance`);
  box.replaceChildren(head, h('p', { class: 'wi-desc', text: `${cf.description}?` }),
    h('p', { text: `Simulations suggest ${names.home}'s win chance would change by about ${d > 0 ? '+' : ''}${d} pp `
      + `(80% interval ${ev(`What-if: change in ${names.home} win chance, 80% interval low`)} to `
      + `${ev(`What-if: change in ${names.home} win chance, 80% interval high`)} pp).` }),
    h('div', { class: 'wi' }, whatifChart(cf, ev, names)),
    h('p', { class: 'hint', text: `${r.source === 'live' ? 'Simulated just now' : 'Precomputed'}: ${cf.n_rollouts} rollouts per scenario, seed ${cf.seed}, `
      + 'same random streams in both arms. Change type: ' + cf.change.replace('_', ' ') + '.' }));
}

// --- overlays --------------------------------------------------------------------------------------------
function cuesShown() {
  return $('cues-moment').checked ? S.cues.filter((c) => c.payload.moment_id === S.selected) : S.cues;
}
const JSON_TOKEN = /("(?:\\.|[^"\\])*")(\s*:)?|(-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)|\b(true|false|null)\b/g;
function renderCues() {  // pretty JSON with light syntax colouring
  const box = $('cues-json'), json = JSON.stringify(cuesShown(), null, 2);
  box.replaceChildren();
  let last = 0;
  for (const m of json.matchAll(JSON_TOKEN)) {
    box.append(json.slice(last, m.index));
    const cls = m[1] ? (m[2] ? 'k' : 's') : m[3] ? 'n' : 'b';
    box.append(h('span', { class: cls, text: m[1] || m[3] || m[4] }), m[2] || '');
    last = m.index + m[0].length;
  }
  box.append(json.slice(last));
}

$('cues-download').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(cuesShown(), null, 2)], { type: 'application/json' });
  const a = h('a', { href: URL.createObjectURL(blob), download: `${S.mid}-overlays-${S.persona.mode}-${S.persona.lang}.json` });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
});
$('cues-moment').addEventListener('change', renderCues);

// --- agent trace -----------------------------------------------------------------------------------------
function stepClass(s) {
  if (/error|rejected|blocked/.test(s.action)) return 'bad';
  if (/fallback|used|retry/.test(s.action) || s.agent === 'template_fallback') return 'warn';
  if (/verified|passed|done|checked|drafted/.test(s.action)) return 'ok';
  return '';
}

function stepEl(s, i = 0) {
  const extra = s.detail || (s.notes?.length ? s.notes.join('; ') : '')
    || (s.stats ? Object.entries(s.stats).map(([k, v]) => `${k} ${v}`).join(', ') : '')
    || (s.engine ? `engine: ${s.engine}` : '');
  return h('li', { class: stepClass(s), style: `--i:${i}` }, h('span', { class: 'agent', text: s.agent.replaceAll('_', ' ') }),
    h('span', { class: 'act', text: `${s.action}${s.attempt ? ` · attempt ${s.attempt}` : ''}${s.backend ? ` · ${s.backend}` : ''}` }),
    extra ? h('span', { class: 'detail', text: extra }) : null);
}

async function renderTrace() {
  const sel = S.selected, { mode, lang } = S.persona;
  const box = $('trace');
  if (S.rerun) return;
  const r = await api.trace(S.mid, sel, mode, lang);
  if (sel !== S.selected || S.rerun) return;
  $('trace-hint').textContent = `Golden run for ${kindTitle(moment(sel))}, ${MODES[mode]} (explainer backend: ${r.backend}).`;
  box.replaceChildren(h('li', { class: 'sep', text: 'Explain' }), ...r.explain.map((s, i) => stepEl(s, i)),
    ...(lang !== 'en' && r.localize.length ? [h('li', { class: 'sep', text: `Localize (${LANGS[lang]}, ${r.localize_backend})` }),
      ...r.localize.map((s, i) => stepEl(s, r.explain.length + i))] : []));
  $('rerun-out').replaceChildren();
}

$('rerun').addEventListener('click', async (ev) => {
  const btn = ev.currentTarget, kill = $('kill').checked, live = !kill && $('live').checked, sel = S.selected;
  btn.disabled = true;
  try {
    $('trace-hint').textContent = live ? 'Running the agents on Microsoft Foundry…' : 'Re-running the agents…';
    const r = await api.explain(S.mid, { moment_id: sel, mode: S.persona.mode, kill, live });
    S.rerun = r;
    $('trace-hint').textContent = `Live re-run for ${kindTitle(moment(sel))}, ${MODES[S.persona.mode]} (backend: ${r.backend}${kill ? ', Explainer killed' : ''}${r.stored ? `, stored in ${r.stored.store}` : ''}).`;
    $('trace').replaceChildren(...r.trace.map((s, i) => stepEl(s, i)));
    const e = r.explanation;
    $('rerun-out').replaceChildren(h('h3', { text: 'Result' }), cardEl({ ...e, persona: e.persona_key, lang: 'en', wanted_lang: 'en', analogy: false }, { watch: false }));
  } catch (err) {
    $('trace-hint').textContent = `Re-run failed (${err.message}). The golden trace is unchanged.`;
  } finally {
    btn.disabled = false;
  }
});

// --- tabs, keyboard, wiring ------------------------------------------------------------------------------
const tabs = [...document.querySelectorAll('[role="tab"]')];
function moveInk() {  // the sliding highlight behind the selected tab
  const t = tabs.find((x) => x.getAttribute('aria-selected') === 'true');
  if (!t) return;
  $('tab-ink').style.width = `${t.offsetWidth}px`;
  $('tab-ink').style.transform = `translateX(${t.offsetLeft}px)`;
}

function openTab(tab) {
  for (const t of tabs) {
    const on = t === tab;
    t.setAttribute('aria-selected', on);
    t.tabIndex = on ? 0 : -1;
    $(t.getAttribute('aria-controls')).hidden = !on;
  }
  moveInk();
  const strip = tab.parentElement;  // keep the tab visible on narrow screens without scrolling the page
  strip.scrollTo({ left: tab.offsetLeft - (strip.clientWidth - tab.offsetWidth) / 2, behavior: reducedMotion() ? 'auto' : 'smooth' });
  document.querySelector('.panels').scrollTop = 0;
  if (tab.id !== 'tab-story') { renderCompare(); renderWhatif(); renderTrace(); }
}
for (const t of tabs) {
  t.addEventListener('click', () => openTab(t));
  t.addEventListener('keydown', (e) => {
    const i = tabs.indexOf(t), dir = document.documentElement.dir === 'rtl' ? -1 : 1;
    const next = { ArrowRight: i + dir, ArrowLeft: i - dir, Home: 0, End: tabs.length - 1 }[e.key];
    if (next === undefined) return;
    e.preventDefault();
    const n = tabs[(next + tabs.length) % tabs.length];
    n.focus(); openTab(n);
  });
}

function stepMoment(dir) {
  const ms = [...S.d.moments].sort((a, b) => a.t_start - b.t_start);
  const i = ms.findIndex((m) => m.id === S.selected);
  const n = ms[Math.max(0, Math.min(ms.length - 1, i + dir))];
  if (n) select(n.id, { seek: true });
}

document.addEventListener('keydown', (e) => {
  if (e.target.closest('input, select, textarea, button, [role="tab"], audio') || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === ' ') { e.preventDefault(); S.es ? stop() : play(); }
  else if (e.key === 'ArrowRight') seek(S.t + 30);
  else if (e.key === 'ArrowLeft') seek(S.t - 30);
  else if (e.key === ']') stepMoment(1);
  else if (e.key === '[') stepMoment(-1);
});

// How-it-works guide: each stage opens its tab or scrolls to its view, then briefly lights it up.
const store = {
  get: (k) => { try { return localStorage.getItem(k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode: the guide just shows again */ } },
};
if (store.get('tl-flow-hidden')) $('flow').hidden = true;
$('flow-x').addEventListener('click', () => { $('flow').hidden = true; store.set('tl-flow-hidden', '1'); });
for (const b of $('flow').querySelectorAll('[data-go]')) {
  b.addEventListener('click', () => {
    const target = $(b.dataset.go);
    const tab = tabs.includes(target) ? target : null;
    if (tab) openTab(tab);
    const box = tab ? document.querySelector('.side') : target;
    box.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block: 'nearest' });
    box.classList.remove('spotlit'); void box.offsetWidth; box.classList.add('spotlit');
  });
}

$('play').addEventListener('click', () => (S.es ? stop() : play()));
$('speed').addEventListener('change', () => { if (S.es) play(); });
$('seek').addEventListener('change', (e) => seek(Number(e.target.value)));
$('persona-form').addEventListener('change', () => { personaFromForm(); refreshPersona(); });
$('persona-form').addEventListener('submit', (e) => e.preventDefault());
$('match-select').addEventListener('change', (e) => loadMatch(e.target.value));
let resizeTimer;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { moveInk(); if (S.d) { buildTimeline(); select(S.selected); tick(); } }, 200);
});

async function init() {
  const params = new URLSearchParams(location.search);
  if (params.get('dir') === 'rtl') document.documentElement.dir = 'rtl';
  const [list, health] = await Promise.all([api.matches(), api.health()]);
  $('live-wrap').hidden = !health.live;
  if (health.live) {
    $('mode-badge').classList.add('live');
    $('mode-text').textContent = 'Live agents on Foundry';
    $('mode-badge').title = 'Replays use golden data; the Agent trace tab can re-run the agents live on Microsoft Foundry';
  }
  moveInk();
  document.fonts?.ready.then(moveInk);
  const sel = $('match-select');
  sel.replaceChildren(...list.map((m) => h('option', { value: m.match_id, text: `${m.title} · ${m.home} ${m.score} ${m.away}` })));
  const want = location.hash.slice(1);
  sel.value = list.some((m) => m.match_id === want) ? want : list[0].match_id;
  await loadMatch(sel.value);
  document.body.dataset.ready = 'true';
}

init().catch((err) => {
  $('caption').textContent = `Could not load match data (${err.message}). Check that the server is running, then reload.`;
  $('cards').replaceChildren(h('div', { class: 'empty' }, h('p', { text: 'Match data did not load.' })));
  console.error(err);
});
