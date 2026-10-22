// Thin client for the TacticLens API. Relative URLs so the app also works behind a path prefix.

function url(path, params = {}) {
  const u = new URL(path, document.baseURI);
  for (const [k, v] of Object.entries(params)) {
    if (v !== '' && v !== null && v !== undefined && v !== false) u.searchParams.set(k, v);
  }
  return u;
}

async function get(path, params) {
  const r = await fetch(url(path, params));
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

async function post(path, body) {
  const r = await fetch(url(path), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${r.status} ${path}`);
  return r.json();
}

export const api = {
  health: () => get('api/health'),
  matches: () => get('api/matches'),
  match: (id) => get(`api/matches/${id}`),
  cards: (id, persona) => get(`api/matches/${id}/cards`, persona),
  overlays: (id, persona) => get(`api/matches/${id}/overlays`, persona),
  trace: (id, momentId, mode, lang) => get(`api/matches/${id}/trace/${momentId}`, { mode, lang }),
  whatif: (id, momentId, live = false) => get(`api/matches/${id}/whatif/${momentId}`, { live }),
  explain: (id, body) => post(`api/matches/${id}/explain`, body),
  replayUrl: (id, fromT, speed) => url(`api/matches/${id}/replay`, { from_t: fromT.toFixed(1), speed }).toString(),
  audioUrl: (id, file) => url(`golden/${id}/${file}`).toString(),
};
