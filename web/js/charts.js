// Tiny inline-SVG charts: win probability over the match (with a hover crosshair) and the what-if interval.
import { el } from './pitch.js';

const W = 640, H = 200, PAD = { l: 38, r: 12, t: 14, b: 24 };
const SERIES = ['home', 'draw', 'away'];

export function wpChart(box, wp, moments, names, minuteOf, onPick) {
  box.replaceChildren();
  const maxMin = wp[wp.length - 1].minute;
  const X = (m) => PAD.l + (m / maxMin) * (W - PAD.l - PAD.r);
  const Y = (p) => PAD.t + (1 - p) * (H - PAD.t - PAD.b);
  const first = wp[0], last = wp[wp.length - 1];
  const pct = (p) => `${Math.round(p * 100)}%`;
  const label = { home: names.home, draw: 'Draw', away: names.away };
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `Win probability over the match. ${names.home}: ${pct(first.home)} at kick-off, ${pct(last.home)} at full time. `
      + `${names.away}: ${pct(first.away)} to ${pct(last.away)}. Draw: ${pct(first.draw)} to ${pct(last.draw)}.` }, box);
  for (const p of [0, 0.25, 0.5, 0.75, 1]) {
    el('line', { class: 'grid', x1: PAD.l, x2: W - PAD.r, y1: Y(p), y2: Y(p) }, svg);
    el('text', { class: 'axis', x: PAD.l - 8, y: Y(p) + 3.5, 'text-anchor': 'end' }, svg).textContent = `${p * 100}%`;
  }
  for (const m of [0, 15, 30, 45, 60, 75, 90].filter((m) => m <= maxMin)) {
    el('text', { class: 'axis', x: X(m), y: H - 6, 'text-anchor': 'middle' }, svg).textContent = `${m}'`;
  }
  for (const mo of moments) {
    const x = X(minuteOf(mo.t_start));
    el('line', { class: 'mline', x1: x, x2: x, y1: PAD.t, y2: H - PAD.b, 'data-id': mo.id }, svg);
    el('circle', { class: 'mdot', cx: x, cy: PAD.t - 4, r: 3 }, svg);
  }
  for (const k of ['draw', 'away', 'home']) {  // exactly three paths: one per outcome
    const path = el('path', { class: `l-${k} drawn`, d: wp.map((r, i) => `${i ? 'L' : 'M'}${X(r.minute).toFixed(1)},${Y(r[k]).toFixed(1)}`).join('') }, svg);
    path.style.setProperty('--len', Math.ceil(path.getTotalLength?.() || 2000));
    path.addEventListener('animationend', () => path.classList.remove('drawn'), { once: true });  // back to its own dash style
  }
  const ph = el('line', { class: 'ph', x1: PAD.l, x2: PAD.l, y1: PAD.t, y2: H - PAD.b }, svg);
  const xh = el('line', { class: 'xh', x1: PAD.l, x2: PAD.l, y1: PAD.t, y2: H - PAD.b }, svg);
  const dots = Object.fromEntries(SERIES.map((k) => [k, el('circle', { class: `xd ${k}`, r: 4, cx: PAD.l, cy: PAD.t }, svg)]));
  const hit = el('rect', { x: PAD.l, y: 0, width: W - PAD.l - PAD.r, height: H - PAD.b, fill: 'transparent' }, svg);

  const tip = document.createElement('div');
  tip.className = 'wp-tip';
  tip.setAttribute('aria-hidden', 'true');
  box.appendChild(tip);
  const toMinute = (ev) => {
    const r = svg.getBoundingClientRect();
    return Math.max(0, Math.min(maxMin, ((ev.clientX - r.left) / r.width * W - PAD.l) / (W - PAD.l - PAD.r) * maxMin));
  };
  hit.addEventListener('pointermove', (ev) => {
    const m = toMinute(ev);
    const row = wp.reduce((best, r) => (Math.abs(r.minute - m) < Math.abs(best.minute - m) ? r : best), wp[0]);
    const x = X(row.minute);
    xh.setAttribute('x1', x); xh.setAttribute('x2', x);
    for (const k of SERIES) { dots[k].setAttribute('cx', x); dots[k].setAttribute('cy', Y(row[k])); }
    tip.innerHTML = `<div class="m">${Math.floor(row.minute)}'</div>` + SERIES.map((k) =>
      `<div class="r"><span><i class="${k === 'draw' ? 'dash' : ''}" style="background:var(--${k})"></i>${label[k]}</span><b>${pct(row[k])}</b></div>`).join('');
    const bw = box.clientWidth, px = (x / W) * bw;
    tip.style.left = `${Math.max(0, Math.min(bw - tip.offsetWidth, px + (px > bw / 2 ? -tip.offsetWidth - 14 : 14)))}px`;
    box.classList.add('hover');
  });
  hit.addEventListener('pointerleave', () => box.classList.remove('hover'));
  hit.addEventListener('click', (ev) => onPick(toMinute(ev)));

  const legend = document.createElement('div');
  legend.className = 'legend';
  legend.innerHTML = `<span><i style="background:var(--home)"></i>${names.home}</span>`
    + `<span><i class="dash"></i>Draw</span><span><i style="background:var(--away)"></i>${names.away}</span>`;
  box.appendChild(legend);
  return { setMinute: (m) => { const x = X(Math.min(m, maxMin)); ph.setAttribute('x1', x); ph.setAttribute('x2', x); } };
}

// cf: Counterfactual; ev(label) -> evidence value. Shows the paired change in home win chance (mean + 80% band)
// and the win chances as played vs with the change.
export function whatifChart(cf, ev, names) {
  const w = 560, h = 230, barW = w - 190;
  const svg = el('svg', { viewBox: `0 0 ${w} ${h}`, role: 'img',
    'aria-label': `Change in ${names.home} win chance: ${ev(`What-if: change in ${names.home} win chance`)} percentage points, `
      + `80% interval ${ev(`What-if: change in ${names.home} win chance, 80% interval low`)} to `
      + `${ev(`What-if: change in ${names.home} win chance, 80% interval high`)}.` });
  const lo = Math.min(-0.3, cf.wp_delta_p10 - 0.05), hi = Math.max(0.3, cf.wp_delta_p90 + 0.05);
  const X = (v) => 20 + (v - lo) / (hi - lo) * (w - 40);
  el('text', { x: 20, y: 14, class: 'muted' }, svg).textContent = `Change in ${names.home} win chance (pp), 80% interval`;
  el('rect', { class: 'track', x: 20, y: 40, width: w - 40, height: 16, rx: 8 }, svg);
  el('line', { class: 'zero', x1: X(0), x2: X(0), y1: 30, y2: 66 }, svg);
  el('rect', { class: 'band', x: X(cf.wp_delta_p10), y: 40, width: Math.max(4, X(cf.wp_delta_p90) - X(cf.wp_delta_p10)), height: 16, rx: 8 }, svg);
  el('circle', { class: 'mean', cx: X(cf.wp_delta_mean), cy: 48, r: 7 }, svg);
  el('text', { x: X(0), y: 80, 'text-anchor': 'middle', class: 'muted num' }, svg).textContent = '0';
  const d = ev(`What-if: change in ${names.home} win chance`);
  el('text', { x: X(cf.wp_delta_mean), y: 33, 'text-anchor': 'middle', class: 'num' }, svg).textContent = `${d > 0 ? '+' : ''}${d} pp`;
  let y = 112;
  for (const side of ['home', 'away']) {
    const a = ev(`What-if: ${names[side]} win chance as played`), b = ev(`What-if: ${names[side]} win chance with the change`);
    el('text', { x: 20, y: y - 8, class: 'muted' }, svg).textContent = `${names[side]} win chance`;
    for (const [v, cls, txt, dy] of [[a, 'bar-a', 'as played', 0], [b, 'bar-b', 'with the change', 19]]) {
      el('rect', { class: 'track', x: 20, y: y + dy, width: barW, height: 13, rx: 6.5 }, svg);
      el('rect', { class: cls, x: 20, y: y + dy, width: Math.max(4, v / 100 * barW), height: 13, rx: 6.5 }, svg);
      const t = el('text', { x: 30 + barW, y: y + dy + 11 }, svg);
      t.innerHTML = `<tspan class="num">${v}%</tspan><tspan class="muted"> ${txt}</tspan>`;
    }
    y += 60;
  }
  return svg;
}
