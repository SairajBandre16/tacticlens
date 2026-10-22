// Tiny inline-SVG charts: win probability over the match and the what-if interval.
import { el } from './pitch.js';

const W = 640, H = 190, PAD = { l: 36, r: 10, t: 10, b: 24 };

export function wpChart(box, wp, moments, names, minuteOf, onPick) {
  box.replaceChildren();
  const maxMin = wp[wp.length - 1].minute;
  const X = (m) => PAD.l + (m / maxMin) * (W - PAD.l - PAD.r);
  const Y = (p) => PAD.t + (1 - p) * (H - PAD.t - PAD.b);
  const first = wp[0], last = wp[wp.length - 1];
  const pct = (p) => `${Math.round(p * 100)}%`;
  const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img',
    'aria-label': `Win probability over the match. ${names.home}: ${pct(first.home)} at kick-off, ${pct(last.home)} at full time. `
      + `${names.away}: ${pct(first.away)} to ${pct(last.away)}. Draw: ${pct(first.draw)} to ${pct(last.draw)}.` }, box);
  for (const p of [0, 0.25, 0.5, 0.75, 1]) {
    el('line', { class: 'grid', x1: PAD.l, x2: W - PAD.r, y1: Y(p), y2: Y(p) }, svg);
    el('text', { class: 'axis', x: PAD.l - 6, y: Y(p) + 4, 'text-anchor': 'end' }, svg).textContent = `${p * 100}%`;
  }
  for (const m of [0, 15, 30, 45, 60, 75, 90].filter((m) => m <= maxMin)) {
    el('text', { class: 'axis', x: X(m), y: H - 6, 'text-anchor': 'middle' }, svg).textContent = `${m}'`;
  }
  for (const mo of moments) {
    const x = X(minuteOf(mo.t_start));
    const ln = el('line', { class: 'mline', x1: x, x2: x, y1: PAD.t, y2: H - PAD.b }, svg);
    ln.dataset.id = mo.id;
  }
  for (const k of ['draw', 'away', 'home']) {
    el('path', { class: `l-${k}`, d: wp.map((r, i) => `${i ? 'L' : 'M'}${X(r.minute).toFixed(1)},${Y(r[k]).toFixed(1)}`).join('') }, svg);
  }
  const ph = el('line', { class: 'ph', x1: PAD.l, x2: PAD.l, y1: PAD.t, y2: H - PAD.b }, svg);
  svg.addEventListener('click', (ev) => {
    const r = svg.getBoundingClientRect();
    const m = ((ev.clientX - r.left) / r.width * W - PAD.l) / (W - PAD.l - PAD.r) * maxMin;
    if (m >= 0 && m <= maxMin) onPick(m);
  });
  const legend = document.createElement('div');
  legend.className = 'legend';
  legend.innerHTML = `<span><i style="background:var(--home)"></i>${names.home}</span>`
    + `<span><i style="background:var(--draw)"></i>Draw</span><span><i style="background:var(--away)"></i>${names.away}</span>`;
  box.appendChild(legend);
  return { setMinute: (m) => { const x = X(Math.min(m, maxMin)); ph.setAttribute('x1', x); ph.setAttribute('x2', x); } };
}

// cf: Counterfactual; ev(label) -> evidence value. Shows the paired change in home win chance (mean + 80% band)
// and the win chances as played vs with the change.
export function whatifChart(cf, ev, names) {
  const w = 560, h = 210;
  const svg = el('svg', { viewBox: `0 0 ${w} ${h}`, role: 'img',
    'aria-label': `Change in ${names.home} win chance: ${ev(`What-if: change in ${names.home} win chance`)} percentage points, `
      + `80% interval ${ev(`What-if: change in ${names.home} win chance, 80% interval low`)} to `
      + `${ev(`What-if: change in ${names.home} win chance, 80% interval high`)}.` });
  const lo = Math.min(-0.3, cf.wp_delta_p10 - 0.05), hi = Math.max(0.3, cf.wp_delta_p90 + 0.05);
  const X = (v) => 20 + (v - lo) / (hi - lo) * (w - 40);
  el('text', { x: 20, y: 16, class: 'muted' }, svg).textContent = `Change in ${names.home} win chance (pp)`;
  el('line', { class: 'zero', x1: X(0), x2: X(0), y1: 26, y2: 70 }, svg);
  el('rect', { class: 'band', x: X(cf.wp_delta_p10), y: 38, width: Math.max(2, X(cf.wp_delta_p90) - X(cf.wp_delta_p10)), height: 20, rx: 4 }, svg);
  el('circle', { class: 'mean', cx: X(cf.wp_delta_mean), cy: 48, r: 6 }, svg);
  el('text', { x: X(0), y: 84, 'text-anchor': 'middle', class: 'muted' }, svg).textContent = '0';
  el('text', { x: X(cf.wp_delta_mean), y: 32, 'text-anchor': 'middle' }, svg).textContent =
    `${ev(`What-if: change in ${names.home} win chance`)} pp`;
  let y = 110;
  for (const side of ['home', 'away']) {
    const a = ev(`What-if: ${names[side]} win chance as played`), b = ev(`What-if: ${names[side]} win chance with the change`);
    el('text', { x: 20, y: y - 6, class: 'muted' }, svg).textContent = `${names[side]} win chance`;
    el('rect', { class: 'bar-a', x: 20, y, width: Math.max(1, a / 100 * (w - 140)), height: 14, rx: 3 }, svg);
    el('text', { x: 26 + a / 100 * (w - 140), y: y + 11 }, svg).textContent = `${a}% as played`;
    el('rect', { class: 'bar-b', x: 20, y: y + 18, width: Math.max(1, b / 100 * (w - 140)), height: 14, rx: 3 }, svg);
    el('text', { x: 26 + b / 100 * (w - 140), y: y + 29 }, svg).textContent = `${b}% with the change`;
    y += 56;
  }
  return svg;
}
