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
  for (let i = 0; i < 10; i += 2) el('rect', { class: 'stripe', x: i * 10.5, y: 0, width: 10.5, height: 68 }, svg);
  const g = el('g', { class: 'lines' }, svg);
  el('rect', { x: 0, y: 0, width: 105, height: 68 }, g);
  el('line', { x1: 52.5, y1: 0, x2: 52.5, y2: 68 }, g);
  el('circle', { cx: 52.5, cy: 34, r: 9.15 }, g);
  el('circle', { cx: 52.5, cy: 34, r: 0.4 }, g);
  for (const [x, dir] of [[0, 1], [105, -1]]) {
    el('rect', { x: dir > 0 ? 0 : 105 - 16.5, y: 13.84, width: 16.5, height: 40.32 }, g);
    el('rect', { x: dir > 0 ? 0 : 105 - 5.5, y: 24.84, width: 5.5, height: 18.32 }, g);
    el('circle', { cx: x + dir * 11, cy: 34, r: 0.4 }, g);
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
    this.ball.setAttribute('cx', 52.5);
    this.ball.setAttribute('cy', 34);
  }

  show(e) {
    const side = e.team === this.homeId ? 'home' : 'away';
    const [x, y] = this.xy(e, e.x, e.y);
    let bx = x, by = y;
    if (e.end_x !== null && e.end_x !== undefined) {
      [bx, by] = this.xy(e, e.end_x, e.end_y);
      el('line', { class: side, x1: x, y1: y, x2: bx, y2: by }, this.trail);
    }
    el('circle', { class: `dot ${side}`, cx: x, cy: y, r: 0.9 }, this.dots);
    for (const g of [this.trail, this.dots]) {
      while (g.childNodes.length > TRAIL) g.firstChild.remove();
      [...g.childNodes].forEach((n, i, all) => n.setAttribute('opacity', ((i + 1) / all.length).toFixed(2)));
    }
    if (e.type === 'shot' || e.type === 'goal') this.flash(side === 'home' ? 105 : 0, 34, e.type === 'goal');
    this.ball.setAttribute('cx', bx);
    this.ball.setAttribute('cy', by);
  }

  flash(x, y, big) {
    this.flashG.replaceChildren();
    const c = el('circle', { class: 'flash', cx: x, cy: y, r: big ? 6 : 3 }, this.flashG);
    setTimeout(() => c.remove(), 1200);
  }
}
