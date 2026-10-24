// SVG pitch (105 x 68 m). Events arrive in the acting team's frame (attacking +x); away events are rotated
// 180 degrees so the home team always attacks to the right.

export const NS = 'http://www.w3.org/2000/svg';
const TRAIL = 8;

export function el(tag, attrs = {}, parent = null) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}

function drawLines(svg) {
  const defs = el('defs', {}, svg);
  const glow = el('radialGradient', { id: 'ball-glow' }, defs);
  el('stop', { offset: '0%', 'stop-color': '#f4ffe0', 'stop-opacity': '.55' }, glow);
  el('stop', { offset: '100%', 'stop-color': '#b5e86a', 'stop-opacity': '0' }, glow);
  el('rect', { class: 'turf', x: -2, y: -2, width: 109, height: 72 }, svg);
  for (let i = 0; i < 10; i += 2) el('rect', { class: 'stripe', x: i * 10.5, y: 0, width: 10.5, height: 68 }, svg);
  const zones = el('g', { class: 'zones' }, svg);  // the simulator's 12 x 8 zone grid
  for (let i = 1; i < 12; i++) el('line', { x1: i * 105 / 12, y1: 0, x2: i * 105 / 12, y2: 68 }, zones);
  for (let j = 1; j < 8; j++) el('line', { x1: 0, y1: j * 8.5, x2: 105, y2: j * 8.5 }, zones);
  const g = el('g', { class: 'lines' }, svg);
  el('rect', { x: 0, y: 0, width: 105, height: 68 }, g);
  el('line', { x1: 52.5, y1: 0, x2: 52.5, y2: 68 }, g);
  el('circle', { cx: 52.5, cy: 34, r: 9.15 }, g);
  el('circle', { class: 'spot', cx: 52.5, cy: 34, r: 0.45 }, g);
  for (const [x, dir] of [[0, 1], [105, -1]]) {
    el('rect', { x: dir > 0 ? 0 : 105 - 16.5, y: 13.84, width: 16.5, height: 40.32 }, g);
    el('rect', { x: dir > 0 ? 0 : 105 - 5.5, y: 24.84, width: 5.5, height: 18.32 }, g);
    el('circle', { class: 'spot', cx: x + dir * 11, cy: 34, r: 0.45 }, g);
    el('path', { d: `M ${x + dir * 16.5} 26.69 A 9.15 9.15 0 0 ${dir > 0 ? 1 : 0} ${x + dir * 16.5} 41.31` }, g);
    el('rect', { x: dir > 0 ? -1.5 : 105, y: 30.34, width: 1.5, height: 7.32 }, g);
  }
}

export class PitchView {
  constructor(svg) {
    this.svg = svg;
    drawLines(svg);
    this.trail = el('g', { class: 'trail' }, svg);
    this.dots = el('g', {}, svg);
    this.flashG = el('g', {}, svg);
    this.glow = el('circle', { class: 'ball-glow', cx: 52.5, cy: 34, r: 4.5 }, svg);
    this.ball = el('circle', { class: 'ball', cx: 52.5, cy: 34, r: 1.1 }, svg);
    this.homeId = null;
  }

  setHome(id) { this.homeId = id; this.reset(); }

  xy(e, x, y) {
    const home = e.team === this.homeId;
    return [(home ? x : 100 - x) * 1.05, (home ? y : 100 - y) * 0.68];
  }

  reset() {
    this.trail.replaceChildren();
    this.dots.replaceChildren();
    this.flashG.replaceChildren();
    this.moveBall(52.5, 34);
  }

  moveBall(x, y) {
    for (const n of [this.ball, this.glow]) { n.setAttribute('cx', x); n.setAttribute('cy', y); }
  }

  show(e) {
    const side = e.team === this.homeId ? 'home' : 'away';
    const [x, y] = this.xy(e, e.x, e.y);
    let bx = x, by = y;
    if (e.end_x !== null && e.end_x !== undefined) {
      [bx, by] = this.xy(e, e.end_x, e.end_y);
      this.svg.querySelector('.trail .new')?.classList.remove('new');
      el('line', { class: `${side} new`, x1: x, y1: y, x2: bx, y2: by }, this.trail);
    }
    this.svg.querySelector('.dot.new')?.classList.remove('new');
    el('circle', { class: `dot ${side} new`, cx: x, cy: y, r: 0.95 }, this.dots);
    for (const g of [this.trail, this.dots]) {
      while (g.childNodes.length > TRAIL) g.firstChild.remove();
      [...g.childNodes].forEach((n, i, all) => n.setAttribute('opacity', ((i + 1) / all.length).toFixed(2)));
    }
    if (e.type === 'shot' || e.type === 'goal') this.flash(side === 'home' ? 105 : 0, 34, e.type === 'goal');
    this.moveBall(bx, by);
  }

  flash(x, y, big) {
    this.flashG.replaceChildren();
    for (const [r, delay] of big ? [[6, 0], [9, 180], [12, 360]] : [[3.5, 0]]) {
      const c = el('circle', { class: `flash${big ? ' goal' : ''}`, cx: x, cy: y, r, style: `animation-delay:${delay}ms` }, this.flashG);
      setTimeout(() => c.remove(), 1300 + delay);
    }
  }
}
