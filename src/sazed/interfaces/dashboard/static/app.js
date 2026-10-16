"use strict";
// Painel de Sazed: vanilla JS, no network beyond this server, data only via textContent.

const SVG_NS = "http://www.w3.org/2000/svg";
const NUM = new Intl.NumberFormat("pt-BR");
const NUM1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const NUM3 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

// ---------------------------------------------------------------- helpers

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  setAttrs(el, attrs);
  append(el, children);
  return el;
}

function s(tag, attrs, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  setAttrs(el, attrs);
  append(el, children);
  return el;
}

function setAttrs(el, attrs) {
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === "text") el.textContent = String(value);
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : String(value));
  }
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

function fmtBytes(n) {
  if (n === null || n === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i += 1; }
  return `${NUM1.format(v)} ${units[i]}`;
}
const fmtPct = (x, digits = 0) => (x === null || x === undefined ? "—"
  : `${new Intl.NumberFormat("pt-BR", { maximumFractionDigits: digits }).format(x)}%`);
const fmtScore = (x) => NUM3.format(x);
const pad = (n) => String(n).padStart(2, "0");

function fmtWhen(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso || "—";
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}
function fmtDay(isoDay) { const [, m, d] = isoDay.split("-"); return `${d}/${m}`; }
function fmtClock(epoch) { const d = new Date(epoch * 1000); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; }
function fmtDuration(sec) {
  if (sec === null || sec === undefined) return "—";
  const d = Math.floor(sec / 86400); const hh = Math.floor((sec % 86400) / 3600);
  const mm = Math.floor((sec % 3600) / 60); const ss = Math.floor(sec % 60);
  if (d) return `${d} d ${hh} h`;
  if (hh) return `${hh} h ${pad(mm)} min`;
  if (mm) return `${mm} min ${pad(ss)} s`;
  return `${ss} s`;
}

async function getJSON(path) {
  let response;
  try {
    response = await fetch(path, { cache: "no-store" });
  } catch {
    throw new Error("Não consegui falar com o painel. Ele ainda está em execução?");
  }
  let body;
  try { body = await response.json(); } catch { throw new Error("Resposta inválida do painel."); }
  if (!response.ok) throw new Error(body.error || "Falha ao consultar o painel.");
  return body;
}

const empty = (text, bad = false) => h("div", { class: bad ? "empty bad" : "empty", text });
const card = (title, ...children) => h("div", { class: "card" }, h("header", {}, h("h2", { text: title })), ...children);
function cardWith(title, tools, ...children) {
  return h("div", { class: "card" }, h("header", {}, h("h2", { text: title }), tools), ...children);
}
function unavailable(payload) { return payload && payload.available === false ? empty(payload.message) : null; }
function table(headers, rows, numeric = []) {
  return h("div", { class: "table-wrap" }, h("table", {},
    h("thead", {}, h("tr", {}, headers.map((t, i) => h("th", { class: numeric.includes(i) ? "num" : null, text: t })))),
    h("tbody", {}, rows.map((row) => h("tr", {}, row.map((cell, i) => h("td", { class: numeric.includes(i) ? "num" : "break" },
      cell instanceof Node ? cell : String(cell ?? "—"))))))));
}
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

const DECISION_CLASS = { Execute: "good", Confirm: "warn", AskSlot: "warn", NotUnderstood: "bad", error: "bad" };
const decisionBadge = (e) => h("span", { class: `badge ${DECISION_CLASS[e.decision] || ""}`, text: e.decision_label });
function outcomeBadges(e) {
  return [
    e.outcome ? h("span", { class: `badge ${e.failed ? "bad" : ""}`, text: e.outcome }) : null,
    e.failed && !e.outcome ? h("span", { class: "badge bad", text: "falha" }) : null,
    e.reaction_label ? h("span", { class: "badge accent", text: e.reaction_label }) : null,
  ];
}

// ---------------------------------------------------------------- writes

// The per-launch token is put in the page by the server; every POST must carry it.
const TOKEN = (document.querySelector('meta[name="sazed-token"]') || {}).content || "";
const MODEL_WRITES = new Set(["/api/write/example/add", "/api/write/example/edit", "/api/write/episode/label"]);

function button(text, onClick, cls = "btn") {
  const b = h("button", { class: cls, type: "button", text });
  b.addEventListener("click", onClick);
  return b;
}

// A form being filled must survive the live refresh: typing marks it dirty.
function dirty(el) { el.addEventListener("input", () => { el.dataset.dirty = "1"; }); return el; }
function panelBusy(panel) {
  if (panel.querySelector("[data-dirty]")) return true;
  const a = document.activeElement;
  return Boolean(a && panel.contains(a) && /^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName) && a.type !== "search");
}

async function postJSON(path, body) {
  let response;
  try {
    response = await fetch(path, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Sazed-Token": TOKEN },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error("Não consegui falar com o painel. Ele ainda está em execução?");
  }
  let data;
  try { data = await response.json(); } catch { throw new Error("Resposta inválida do painel."); }
  if (!response.ok) throw new Error(data.error || "Não consegui gravar.");
  return data;
}

function notice(message, kind = "", actions = []) {
  const box = document.getElementById("notice");
  const close = button("Fechar", () => { box.hidden = true; }, "btn small");
  box.replaceChildren(h("div", { class: `notice ${kind}` }, h("span", { class: "msg", text: message }), actions, close));
  box.hidden = false;
}

// Every write goes through here: it explains the result, offers "guardar mesmo assim" on a
// conflict and "desfazer" after a forget, then lets the caller refresh its view.
async function write(path, body, onDone) {
  if (MODEL_WRITES.has(path)) {
    let state = "ready";
    try { state = (await getJSON("/api/editor")).state; } catch { /* the POST will say what is wrong */ }
    notice(state === "ready" ? "Gravando…" : "Carregando o modelo de linguagem (só na primeira vez; alguns segundos)…", "warn");
  } else {
    notice("Gravando…");
  }
  let r;
  try { r = await postJSON(path, body); } catch (err) { notice(err.message, "bad"); return null; }
  const actions = [];
  if (r.needs_force) actions.push(button("Guardar mesmo assim", () => write(path, { ...body, force: true }, onDone)));
  if (r.undo) actions.push(button("Desfazer", () => write("/api/write/undo", { undo: r.undo }, onDone)));
  notice(r.message, r.ok ? "good" : r.needs_force ? "warn" : "bad", actions);
  if (r.ok && onDone) onDone(r);
  return r;
}

function intentSelect(intents, selected, label = "Pedido") {
  const select = h("select", { "aria-label": label }, h("option", { value: "", text: "escolha o pedido…" }),
    intents.map((i) => h("option", {
      value: i.id, selected: i.id === selected, disabled: !i.learnable,
      text: i.learnable ? `${i.id} — ${i.description}` : `${i.id} — nunca aprendido`,
    })));
  return dirty(select);
}

function notesView(target, targetId, notes, onChange) {
  const items = notes.map((n) => {
    const li = h("li", {});
    const show = () => li.replaceChildren(h("span", { text: n.text }),
      h("span", { class: "updated", text: ` · ${fmtWhen(n.updated_at || n.created_at)}${n.updated_at ? " (editada)" : ""} ` }),
      button("Editar", () => {
        const area = dirty(h("textarea", { rows: 2, "aria-label": "Editar nota", maxlength: 2000 }));
        area.value = n.text;
        li.replaceChildren(area, h("div", { class: "toolbar" },
          button("Salvar", () => write("/api/write/note/edit", { id: n.id, text: area.value }, onChange)),
          button("Cancelar", show)));
        area.focus();
      }, "btn small"),
      button("Remover", () => {
        if (window.confirm("Remover esta nota?")) write("/api/write/note/remove", { id: n.id }, onChange);
      }, "btn small"));
    show();
    return li;
  });
  const area = dirty(h("textarea", { rows: 2, maxlength: 2000, "aria-label": "Nova nota", placeholder: "Uma nota para você (Sazed não lê notas)…" }));
  return h("div", { class: "notes" }, h("h3", { text: `Notas (${notes.length})` }),
    items.length ? h("ul", { class: "plain" }, items) : null,
    h("div", { class: "toolbar" }, area,
      button("Adicionar nota", () => write("/api/write/note/add", { target, target_id: targetId, text: area.value }, onChange))));
}

function forgetButton(ref, text, onChange) {
  return button("Esquecer", () => {
    if (window.confirm(`Esquecer ${ref} “${text}”? As notas dele vão junto. Dá para desfazer logo em seguida.`)) {
      write("/api/write/forget", { ref }, onChange);
    }
  }, "btn small");
}

// ---------------------------------------------------------------- charts

function tooltip(chart) { const tip = h("div", { class: "tip", hidden: true }); chart.append(tip); return tip; }
function placeTip(chart, tip, x, lines) {
  tip.replaceChildren(...lines.map((l) => h("div", {}, l)));
  tip.hidden = false;
  const w = chart.clientWidth; const tw = tip.offsetWidth;
  tip.style.left = `${Math.max(0, Math.min(w - tw, x + 12))}px`;
  tip.style.top = "4px";
}

function yTicks(max) {
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  return ticks;
}

// series: [{label, cls, points: [[x, y|null], ...]}]
function lineChart({ series, yMax, yFmt, xFmt, height = 180 }) {
  const W = 600; const H = height; const L = 46; const R = 10; const T = 10; const B = 22;
  const all = series.flatMap((ser) => ser.points);
  const xs = all.map((p) => p[0]);
  const chart = h("div", { class: "chart" });
  if (!xs.length) { chart.append(empty("Ainda sem dados.")); return chart; }
  const x0 = Math.min(...xs); const x1 = Math.max(...xs);
  const ys = all.map((p) => p[1]).filter((y) => y !== null);
  const top = yMax ?? Math.max(1, ...ys) * 1.1;
  const X = (x) => (x1 === x0 ? L + (W - L - R) / 2 : L + ((x - x0) / (x1 - x0)) * (W - L - R));
  const Y = (y) => T + (1 - y / top) * (H - T - B);
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": series.map((x) => x.label).join(", ") });
  for (const t of yTicks(top)) {
    svg.append(s("line", { class: "gridline", x1: L, x2: W - R, y1: Y(t), y2: Y(t) }));
    svg.append(s("text", { class: "axis", x: L - 6, y: Y(t) + 3, "text-anchor": "end", text: yFmt(t) }));
  }
  svg.append(s("text", { class: "axis", x: L, y: H - 6, text: xFmt(x0) }));
  svg.append(s("text", { class: "axis", x: W - R, y: H - 6, "text-anchor": "end", text: xFmt(x1) }));
  for (const ser of series) {
    let d = ""; let pen = false;
    for (const [x, y] of ser.points) {
      if (y === null) { pen = false; continue; }
      d += `${pen ? "L" : "M"}${X(x).toFixed(1)},${Y(y).toFixed(1)}`;
      pen = true;
    }
    if (d) svg.append(s("path", { class: `series ${ser.cls}`, d }));
    const last = [...ser.points].reverse().find((p) => p[1] !== null);
    if (last && series.length <= 4) {
      svg.append(s("circle", { cx: X(last[0]), cy: Y(last[1]), r: 4, class: ser.cls }));
    }
  }
  const cross = s("line", { class: "cross", y1: T, y2: H - B, visibility: "hidden" });
  const hit = s("rect", { class: "hit", x: L, y: T, width: W - L - R, height: H - T - B });
  svg.append(cross, hit);
  chart.append(svg);
  const tip = tooltip(chart);
  const points = series[0].points;
  hit.addEventListener("mousemove", (ev) => {
    const box = svg.getBoundingClientRect();
    const vx = ((ev.clientX - box.left) / box.width) * W;
    let best = 0;
    points.forEach((p, i) => { if (Math.abs(X(p[0]) - vx) < Math.abs(X(points[best][0]) - vx)) best = i; });
    const x = points[best][0];
    cross.setAttribute("x1", X(x)); cross.setAttribute("x2", X(x)); cross.setAttribute("visibility", "visible");
    placeTip(chart, tip, (X(x) / W) * box.width, [
      h("strong", { text: xFmt(x) }),
      ...series.map((ser) => {
        const p = ser.points[best];
        return h("span", {}, h("span", { class: `swatch line ${ser.cls}` }), `${ser.label}: ${p && p[1] !== null ? yFmt(p[1]) : "—"}`);
      }),
    ]);
  });
  hit.addEventListener("mouseleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); });
  return chart;
}

// stacks: [{label, cls, values: []}] aligned with categories
function stackedBars({ categories, stacks, yFmt = (v) => NUM.format(v), catFmt = (c) => c, height = 190 }) {
  const W = 600; const H = height; const L = 36; const R = 6; const T = 10; const B = 22;
  const totals = categories.map((_, i) => stacks.reduce((sum, st) => sum + st.values[i], 0));
  const top = Math.max(1, ...totals);
  const chart = h("div", { class: "chart" });
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": stacks.map((x) => x.label).join(", ") });
  const Y = (v) => T + (1 - v / top) * (H - T - B);
  for (const t of yTicks(top)) {
    svg.append(s("line", { class: "gridline", x1: L, x2: W - R, y1: Y(t), y2: Y(t) }));
    svg.append(s("text", { class: "axis", x: L - 6, y: Y(t) + 3, "text-anchor": "end", text: Number.isInteger(t) ? yFmt(t) : "" }));
  }
  const slot = (W - L - R) / Math.max(1, categories.length);
  const bw = Math.max(2, Math.min(28, slot - 2));
  const tip = tooltip(chart);
  categories.forEach((cat, i) => {
    const cx = L + slot * i + (slot - bw) / 2;
    let base = 0;
    for (const st of stacks) {
      const v = st.values[i];
      if (v > 0) {
        svg.append(s("rect", { class: st.cls, x: cx, width: bw, y: Y(base + v), height: Math.max(0, Y(base) - Y(base + v)), rx: 2 }));
      }
      base += v;
    }
    const hit = s("rect", { class: "hit", x: L + slot * i, width: slot, y: T, height: H - T - B });
    hit.addEventListener("mousemove", () => {
      const box = svg.getBoundingClientRect();
      placeTip(chart, tip, ((L + slot * i) / W) * box.width, [
        h("strong", { text: catFmt(cat) }),
        ...stacks.map((st) => h("span", {}, h("span", { class: `swatch ${st.cls}` }), `${st.label}: ${yFmt(st.values[i])}`)),
      ]);
    });
    hit.addEventListener("mouseleave", () => { tip.hidden = true; });
    svg.append(hit);
  });
  const step = Math.ceil(categories.length / 8);
  categories.forEach((cat, i) => {
    if (i % step === 0 || i === categories.length - 1) {
      svg.append(s("text", { class: "axis", x: L + slot * i + slot / 2, y: H - 6, "text-anchor": "middle", text: catFmt(cat) }));
    }
  });
  chart.prepend(svg);
  return chart;
}

const legend = (items) => h("div", { class: "legend" }, items.map(([label, cls, line]) =>
  h("span", {}, h("span", { class: `swatch ${cls} ${line ? "line" : ""}` }), label)));
function tableView(headers, rows, numeric) {
  return h("details", { class: "tableview" }, h("summary", { text: "Ver como tabela" }), table(headers, rows, numeric));
}

// ---------------------------------------------------------------- status pill

async function refreshStatus() {
  const pill = document.getElementById("status");
  try {
    const r = await getJSON("/api/resources");
    const sazed = r.sazed;
    if (sazed.running) {
      const rss = sazed.main.reduce((sum, m) => sum + m.rss, 0);
      pill.className = "badge good";
      pill.replaceChildren(h("span", { class: "dot" }), ` Sazed em execução · ${fmtBytes(rss)}`);
    } else {
      pill.className = "badge";
      pill.replaceChildren(h("span", { class: "dot" }), " Sazed não está em execução");
    }
  } catch (err) {
    pill.className = "badge bad";
    pill.textContent = err.message;
  }
}

// ---------------------------------------------------------------- overview

async function renderOverview(panel) {
  const o = await getJSON("/api/overview");
  const c = o.coppermind; const r = o.resources; const d = o.dev;
  const tiles = h("div", { class: "grid" });
  const tile = (label, value, sub) => h("div", { class: "card tile" },
    h("div", { class: "label", text: label }), h("div", { class: "value", text: value }), h("div", { class: "sub", text: sub }));
  const main = r.sazed.main;
  tiles.append(tile("Sazed", r.sazed.running ? "em execução" : "parado",
    r.sazed.running ? `${fmtBytes(main.reduce((a, m) => a + m.rss, 0))} · CPU ${fmtPct(main.reduce((a, m) => a + m.cpu, 0), 1)} · há ${fmtDuration(main[0].uptime_s)}`
      : r.sazed.message));
  if (c.available) {
    const t = c.totals;
    tiles.append(tile("Comandos hoje", NUM.format(t.today), `${NUM.format(t.commands)} comandos no total`));
    tiles.append(tile("Falhas", t.commands ? fmtPct((100 * t.failures) / t.commands, 1) : "—",
      `${NUM.format(t.failures)} de ${NUM.format(t.commands)} comandos`));
    tiles.append(tile("Aprendido", NUM.format(c.learned.examples + c.learned.aliases),
      `${NUM.format(c.learned.examples)} exemplos · ${NUM.format(c.learned.aliases)} apelidos`));
  } else {
    tiles.append(tile("Mente de cobre", "indisponível", c.message));
  }
  tiles.append(tile("Desenvolvimento", d.plan ? `${d.done}/${d.total} tarefas` : "—",
    d.current_task ? `Agora: Task ${d.current_task.number} — ${d.current_task.title}` : (d.message || "Nenhuma tarefa em andamento.")));
  tiles.append(tile("PC", `CPU ${fmtPct(r.system.cpu)}`, `RAM ${fmtPct(r.system.ram.percent)} de ${fmtBytes(r.system.ram.total)}`));

  const recent = o.recent.length
    ? table(["Quando", "Frase", "Decisão", "Pedido", "Resultado"],
      o.recent.map((e) => [fmtWhen(e.at), e.utterance, decisionBadge(e), e.intent ? h("code", { text: e.intent }) : "—",
        h("span", { class: "kv" }, outcomeBadges(e))]))
    : empty(c.available ? "Nenhum comando registrado ainda." : c.message);
  const commit = d.last_commit
    ? h("div", {}, h("div", { text: d.last_commit.subject }),
      h("div", { class: "updated" }, h("code", { text: d.last_commit.sha.slice(0, 8) }), ` · ${fmtWhen(d.last_commit.date)} · ${d.last_commit.author}`,
        d.branch ? ` · ramo ${d.branch}` : ""))
    : empty("Sem histórico do git.");
  panel.replaceChildren(tiles,
    h("div", { class: "grid-2" }, card("Comandos recentes (ao vivo)", recent), card("Último commit", commit)));
}

// ---------------------------------------------------------------- reasoning

const reasoning = { q: "", decision: "", intent: "", offset: 0, limit: 20, live: true, seen: new Set(), open: new Set(), built: false, intents: null };

function rankingView(e, th) {
  if (!e.ranking.length) return empty("Sem ranking (não houve comparação com pedidos conhecidos).");
  const rows = e.ranking.map((r, i) => {
    const fill = h("div", { class: "fill" }); fill.style.width = `${Math.max(0, Math.min(1, r.score)) * 100}%`;
    const m1 = h("div", { class: "mark", title: `limiar de confirmação ${th.t_confirm}` }); m1.style.left = `${th.t_confirm * 100}%`;
    const m2 = h("div", { class: "mark", title: `limiar de execução ${th.t_exec}` }); m2.style.left = `${th.t_exec * 100}%`;
    return h("div", { class: `rank ${i === 0 ? "top" : ""}` }, h("code", { class: "name", text: r.intent, title: r.intent }),
      h("div", { class: "track" }, fill, m1, m2), h("span", { class: "score", text: fmtScore(r.score) }));
  });
  return h("div", { class: "ranking" }, rows);
}

function episodeView(e, th, intents, onChange) {
  const det = h("details", { class: `episode ${reasoning.seen.size && !reasoning.seen.has(e.id) ? "fresh" : ""}` });
  if (reasoning.open.has(e.id)) det.open = true;
  det.addEventListener("toggle", () => { if (det.open) reasoning.open.add(e.id); else reasoning.open.delete(e.id); });
  const slots = Object.entries(e.slots);
  det.append(
    h("summary", {}, h("span", { class: "when", text: `#${e.id} · ${fmtWhen(e.at)}` }), h("span", { class: "utt", text: `“${e.utterance}”` }),
      h("span", { class: "tags" }, decisionBadge(e), outcomeBadges(e))),
    h("div", { class: "body" },
      h("h3", { text: "Ranking de pedidos" }), rankingView(e, th),
      h("h3", { text: "Detalhes extraídos" }),
      slots.length ? h("div", { class: "kv" }, slots.map(([k, v]) => h("span", { class: "badge" }, h("code", { text: k }), ` = ${v}`))) : h("div", { class: "updated", text: "nenhum" }),
      h("h3", { text: "Decisão e motivo" }),
      h("div", { class: "reason" }, h("strong", { text: `${e.decision_label}${e.intent ? ` → ${e.intent}` : ""}. ` }), e.reason),
      h("h3", { text: "Resultado e reação" }),
      h("div", { class: "kv" }, e.outcome ? h("span", { class: `badge ${e.failed ? "bad" : "good"}`, text: e.outcome }) : h("span", { class: "updated", text: "sem ação executada" }),
        e.failed ? h("span", { class: "badge bad", text: "conta como falha" }) : null,
        h("span", { class: "badge", text: e.reaction_label ? `reação: ${e.reaction_label}` : "sem reação do usuário" })),
      h("h3", { text: "O que aprendi com isso" }),
      e.learned.length ? h("ul", { class: "plain" }, e.learned.map((l) => h("li", { text: l }))) : h("div", { class: "updated", text: "nada guardado" }),
      teachView(e, intents, onChange),
      notesView("episode", e.id, e.notes || [], onChange)));
  return det;
}

function teachView(e, intents, onChange) {
  const intent = intentSelect(intents, "", "Pedido certo");
  return h("div", {}, h("h3", { text: "Ensinar o que este comando queria dizer" }),
    h("div", { class: "toolbar" }, intent,
      button("Ensinar", () => write("/api/write/episode/label", { episode_id: e.id, intent: intent.value }, onChange))),
    h("div", { class: "updated", text: "Igual a: sazed revisar --rotular. A frase vira um exemplo do pedido escolhido." }));
}

async function loadIntents() {
  if (reasoning.intents) return reasoning.intents;
  try {
    const cap = await getJSON("/api/capabilities");
    reasoning.intents = cap.skills.flatMap((sk) => sk.intents.map((i) => ({ id: i.id, description: i.description, learnable: i.learnable })));
  } catch { reasoning.intents = []; }
  return reasoning.intents;
}

function episodeFilters(state, onChange, decisions, intents) {
  const search = h("input", { type: "search", placeholder: "Buscar frase…", value: state.q, "aria-label": "Buscar frase" });
  search.addEventListener("input", debounce(() => { state.q = search.value; state.offset = 0; onChange(); }, 300));
  const dec = h("select", { "aria-label": "Decisão" }, h("option", { value: "", text: "todas as decisões" }),
    Object.entries(decisions).map(([k, v]) => h("option", { value: k, text: v, selected: state.decision === k })));
  dec.addEventListener("change", () => { state.decision = dec.value; state.offset = 0; onChange(); });
  const intent = h("select", { "aria-label": "Pedido" }, h("option", { value: "", text: "todos os pedidos" }),
    intents.map((i) => h("option", { value: i.id, text: i.id, selected: state.intent === i.id })));
  intent.addEventListener("change", () => { state.intent = intent.value; state.offset = 0; onChange(); });
  return [search, dec, intent];
}

function pager(state, total, onChange) {
  const from = total ? state.offset + 1 : 0; const to = Math.min(total, state.offset + state.limit);
  const prev = h("button", { class: "btn", text: "← Mais novos", disabled: state.offset === 0 });
  prev.addEventListener("click", () => { state.offset = Math.max(0, state.offset - state.limit); onChange(); });
  const next = h("button", { class: "btn", text: "Mais antigos →", disabled: to >= total });
  next.addEventListener("click", () => { state.offset += state.limit; onChange(); });
  return h("div", { class: "pager" }, `Mostrando ${from}–${to} de ${NUM.format(total)}`, prev, next);
}

function episodeQuery(state) {
  const p = new URLSearchParams({ limit: state.limit, offset: state.offset });
  if (state.q) p.set("q", state.q);
  if (state.decision) p.set("decision", state.decision);
  if (state.intent) p.set("intent", state.intent);
  return p.toString();
}

async function renderReasoning(panel, manual = false) {
  if (!manual && reasoning.built && !reasoning.live) return;
  const data = await getJSON(`/api/episodes?${episodeQuery(reasoning)}`);
  const intents = await loadIntents();
  const rerender = () => renderReasoning(panel, true).catch((err) => panel.replaceChildren(empty(err.message, true)));
  const live = h("button", { class: "btn", "aria-pressed": String(reasoning.live), text: reasoning.live ? "● Ao vivo" : "Ao vivo pausado" });
  live.addEventListener("click", () => { reasoning.live = !reasoning.live; rerender(); });
  const intro = h("div", { class: "updated" },
    "Cada comando: o ranking de pedidos com suas pontuações, os detalhes extraídos, a decisão e o porquê. ",
    data.thresholds ? `Limiares atuais: confirmação ${data.thresholds.t_confirm}, execução ${data.thresholds.t_exec}, folga mínima ${data.thresholds.g_min}. ` : "",
    "O motivo é reconstruído com os limiares atuais.");
  const tools = h("div", { class: "toolbar" }, data.available === false ? [] : episodeFilters(reasoning, rerender, data.decisions || {}, intents), live);
  const keepFocus = document.activeElement && document.activeElement.type === "search";
  let body;
  if (data.available === false) body = empty(data.message);
  else if (!data.items.length) body = empty("Nenhum comando encontrado.");
  else body = h("div", { class: "episodes" }, data.items.map((e) => episodeView(e, data.thresholds, intents, rerender)));
  if (data.items && reasoning.offset === 0 && !reasoning.open.size && data.items[0]) reasoning.open.add(data.items[0].id);
  for (const e of data.items || []) reasoning.seen.add(e.id);
  panel.replaceChildren(h("div", { class: "card" }, h("header", {}, h("h2", { text: "Raciocínio de Sazed" }), tools), intro), body,
    data.available === false ? null : pager(reasoning, data.total, rerender));
  if (keepFocus) { const input = panel.querySelector("input[type=search]"); input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
  reasoning.built = true;
}

// ---------------------------------------------------------------- development

const STATUS = { done: ["concluída", "good"], active: ["em andamento", "warn"], pending: ["pendente", ""] };

async function renderDev(panel) {
  const d = await getJSON("/api/dev");
  const parts = [];
  const bar = h("div", { class: "progress" }, h("div", {}));
  bar.firstChild.style.width = d.total ? `${(100 * d.done) / d.total}%` : "0%";
  parts.push(card("Plano ativo",
    d.plan ? h("div", { class: "stack" },
      h("div", {}, h("code", { text: d.plan.name }), d.plan.ledger_plan ? h("span", { class: "updated", text: ` · registro aponta para ${d.plan.ledger_plan}` }) : null),
      bar, h("div", { text: `${d.done} de ${d.total} tarefas concluídas` }),
      d.current_task ? h("div", { class: "reason" }, h("strong", { text: `Tarefa atual: Task ${d.current_task.number} — ` }), d.current_task.title)
        : h("div", { class: "updated", text: "Nenhuma tarefa em andamento." }))
      : empty(d.message || "Nenhum plano ativo."),
    h("div", { class: "updated", text: `Repositório lido: ${d.root}` })));
  if (d.tasks.length) {
    parts.push(card("Tarefas", h("ul", { class: "tasks" }, d.tasks.map((t) => h("li", {},
      h("span", { class: "n", text: `#${t.number}` }),
      h("div", {}, h("div", { text: t.title }),
        t.commits || t.tests_result ? h("div", { class: "detail" }, t.commits ? h("code", { text: t.commits }) : null,
          t.tests_result ? ` · testes: ${t.tests_command || "?"} → ${t.tests_result}` : "") : null,
        t.rulings.length ? h("ul", { class: "plain detail" }, t.rulings.map((r) => h("li", { text: `Decisão: ${r}` }))) : null),
      h("span", { class: `badge ${STATUS[t.status][1]}`, text: STATUS[t.status][0] }))))));
  }
  const by = (kind) => d.entries.filter((e) => e.kind === kind);
  const rulings = by("ruling");
  parts.push(h("div", { class: "grid-2" },
    card("Decisões do agente (rulings)", rulings.length ? h("ul", { class: "plain" }, rulings.map((r) =>
      h("li", {}, h("span", { class: "badge accent", text: r.scope || "geral" }), " ", r.text))) : empty("Nenhuma decisão registrada.")),
    card("Finalização", by("deferred").length || by("fixed").length ? h("div", { class: "stack" },
      by("fixed").length ? h("div", {}, h("h3", { text: "Corrigido" }), h("ul", { class: "plain" }, by("fixed").map((e) => h("li", { text: e.text })))) : null,
      by("deferred").length ? h("div", {}, h("h3", { text: "Adiado (menor)" }), h("ul", { class: "plain" }, by("deferred").map((e) => h("li", { text: e.text })))) : null)
      : empty("Nada registrado ainda."))));
  const raw = by("raw");
  if (raw.length) parts.push(card("Outras linhas do registro", h("div", { class: "raw", text: raw.map((e) => e.line).join("\n") })));
  const commits = d.commits;
  parts.push(card(`Commits recentes${commits.branch ? ` · ramo ${commits.branch}` : ""}`,
    commits.available ? table(["Commit", "Quando", "Autor", "Mensagem"], commits.items.map((cm) => [h("code", { text: cm.sha.slice(0, 8) }), fmtWhen(cm.date), cm.author, cm.subject]))
      : empty(commits.message)));
  parts.push(h("div", { class: "grid-2" },
    card("Provas de discriminação", d.proofs.length ? h("div", { class: "stack" }, d.proofs.map((p) =>
      h("details", {}, h("summary", {}, h("code", { text: p.name }), p.title ? ` — ${p.title}` : ""),
        h("ul", { class: "plain" }, p.sections.map((x) => h("li", { text: x })))))) : empty("Nenhum arquivo de provas.")),
    card("Planos", d.plans.length ? table(["Plano", "Tarefas"], d.plans.map((p) => [
      h("span", {}, h("code", { text: p.name }), d.plan && d.plan.name === p.name ? h("span", { class: "badge accent", text: "ativo" }) : null), p.tasks]), [1])
      : empty("Nenhum plano encontrado."))));
  panel.replaceChildren(...parts);
}

// ---------------------------------------------------------------- learning

const learning = { days: 30 };

async function renderLearning(panel) {
  const data = await getJSON(`/api/learning?days=${learning.days}`);
  const select = h("select", { "aria-label": "Período" }, [7, 30, 90, 365].map((n) => h("option", { value: n, text: `últimos ${n} dias`, selected: n === learning.days })));
  select.addEventListener("change", () => { learning.days = Number(select.value); refresh(); });
  const header = h("div", { class: "card" }, h("header", {}, h("h2", { text: "Aprendizado ao longo do tempo" }), select),
    h("div", { class: "updated", text: "Contagens por dia. Itens esquecidos (esquece isso, sazed aprendizado --esquecer) não aparecem mais." }));
  const bad = unavailable(data);
  if (bad) { panel.replaceChildren(header, bad); return; }
  const a = data.activity; const l = data.learned;
  const days = a.map((x) => x.day);
  const decisions = stackedBars({ categories: days, catFmt: fmtDay, stacks: [
    { label: "executados", cls: "s1", values: a.map((x) => x.executed) },
    { label: "perguntou (confirmação ou detalhe)", cls: "s2", values: a.map((x) => x.asked) },
    { label: "não entendidos", cls: "s3", values: a.map((x) => x.not_understood) }] });
  const failure = lineChart({ series: [{ label: "taxa de falhas", cls: "s2", points: a.map((x, i) => [i, x.failure_rate === null ? null : 100 * x.failure_rate]) }],
    yMax: 100, yFmt: (v) => fmtPct(v), xFmt: (i) => fmtDay(days[i] || days[0]) });
  const learned = stackedBars({ categories: days, catFmt: fmtDay, stacks: [
    { label: "exemplos", cls: "s1", values: l.map((x) => x.examples) },
    { label: "apelidos", cls: "s2", values: l.map((x) => x.aliases) }] });
  const cumulative = lineChart({ series: [
    { label: "exemplos (total)", cls: "s1", points: l.map((x, i) => [i, x.total_examples]) },
    { label: "apelidos (total)", cls: "s2", points: l.map((x, i) => [i, x.total_aliases]) }],
  yFmt: (v) => NUM1.format(v), xFmt: (i) => fmtDay(days[i] || days[0]) });
  panel.replaceChildren(header, h("div", { class: "grid-2" },
    card("Decisões por dia", legend([["executados", "s1"], ["perguntou", "s2"], ["não entendidos", "s3"]]), decisions,
      tableView(["Dia", "Executados", "Perguntou", "Não entendidos", "Controle", "Falhas"], a.map((x) => [fmtDay(x.day), x.executed, x.asked, x.not_understood, x.control, x.failures]), [1, 2, 3, 4, 5])),
    card("Taxa de falhas por dia", h("div", { class: "updated", text: "Falha: não entendido, erro, resultado com falha, ou reação negada/corrigida. Dias sem comandos ficam em branco." }), failure,
      tableView(["Dia", "Comandos", "Falhas", "Taxa"], a.map((x) => [fmtDay(x.day), x.commands, x.failures, x.failure_rate === null ? "—" : fmtPct(100 * x.failure_rate, 1)]), [1, 2, 3])),
    card("Aprendido por dia", legend([["exemplos", "s1"], ["apelidos", "s2"]]), learned,
      tableView(["Dia", "Exemplos", "Apelidos"], l.map((x) => [fmtDay(x.day), x.examples, x.aliases]), [1, 2])),
    card("Total aprendido", legend([["exemplos", "s1", true], ["apelidos", "s2", true]]), cumulative,
      tableView(["Dia", "Exemplos (total)", "Apelidos (total)"], l.map((x) => [fmtDay(x.day), x.total_examples, x.total_aliases]), [1, 2]))));
}

// ---------------------------------------------------------------- resources

async function renderResources(panel) {
  const r = await getJSON("/api/resources");
  const hist = r.history;
  const sazed = r.sazed;
  const proc = sazed.running ? table(["PID", "Memória (RSS)", "CPU (% de um núcleo)", "Em execução há", "Linha de comando"],
    sazed.main.map((m) => [m.pid, fmtBytes(m.rss), fmtPct(m.cpu, 1), fmtDuration(m.uptime_s), h("code", { text: m.cmdline })]), [0, 1, 2])
    : empty(sazed.message);
  const chain = sazed.chain.length ? h("div", { class: "updated", text: `Cadeia de processos: ${sazed.chain.map((p) => `${p.name} (${p.pid})`).join(" → ")}` }) : null;
  const t = (p) => p.t;
  const mb = (v) => `${NUM.format(Math.round(v / 2 ** 20))} MB`;
  const charts = h("div", { class: "grid-2" },
    card("Memória de Sazed", lineChart({ series: [{ label: "RSS", cls: "s1", points: hist.map((p) => [t(p), p.sazed_rss]) }], yFmt: mb, xFmt: fmtClock })),
    card("CPU de Sazed (% de um núcleo)", lineChart({ series: [{ label: "CPU", cls: "s1", points: hist.map((p) => [t(p), p.sazed_cpu]) }], yFmt: (v) => fmtPct(v), xFmt: fmtClock })),
    card("CPU do PC", lineChart({ series: [{ label: "CPU", cls: "s2", points: hist.map((p) => [t(p), p.cpu]) }], yMax: 100, yFmt: (v) => fmtPct(v), xFmt: fmtClock })),
    card("RAM do PC", lineChart({ series: [{ label: "RAM", cls: "s3", points: hist.map((p) => [t(p), p.ram]) }], yMax: 100, yFmt: (v) => fmtPct(v), xFmt: fmtClock })));
  const disks = r.system.disks.length ? h("div", { class: "stack" }, r.system.disks.map((dk) => {
    const meter = h("div", { class: `meter ${dk.percent >= 90 ? "high" : ""}` }, h("div", {}));
    meter.firstChild.style.width = `${dk.percent}%`;
    return h("div", {}, h("div", { class: "toolbar" }, h("strong", { text: dk.mount }),
      h("span", { class: "updated", text: `${fmtBytes(dk.used)} usados de ${fmtBytes(dk.total)} (${fmtPct(dk.percent)})` })), meter);
  })) : empty("Nenhum disco encontrado.");
  const ram = r.system.ram;
  panel.replaceChildren(
    card("Processo de Sazed", proc, chain),
    charts,
    h("div", { class: "grid-2" },
      card("Discos", disks),
      card("Máquina", table(["Item", "Valor"], [
        ["Núcleos lógicos", r.system.cpu_count], ["CPU agora", fmtPct(r.system.cpu)],
        ["RAM", `${fmtBytes(ram.used)} de ${fmtBytes(ram.total)} (${fmtPct(ram.percent)})`],
        ["Ligado desde", fmtWhen(new Date(r.system.boot_time * 1000).toISOString())],
        ["Este painel (RSS)", fmtBytes(r.dashboard.rss)],
        ["Histórico", `${hist.length} amostras enquanto a página está aberta (máx. 150)`]]))));
}

// ---------------------------------------------------------------- coppermind

const copper = { view: "episodes", q: "", decision: "", intent: "", offset: 0, limit: 50 };
const appNames = { list: null, loading: null };

async function loadAppNames() {
  if (appNames.list) return appNames.list;
  if (!appNames.loading) {
    appNames.loading = getJSON("/api/catalog").then((d) => { appNames.list = (d.items || []).map((e) => e.name); return appNames.list; })
      .catch(() => { appNames.loading = null; return []; });
  }
  return appNames.loading;
}

function appInput(value, label) {
  const id = `apps-${Math.random().toString(36).slice(2)}`;
  const list = h("datalist", { id });
  const input = dirty(h("input", { type: "text", list: id, value: value || "", "aria-label": label, placeholder: "programa ou site do catálogo", maxlength: 200 }));
  input.addEventListener("focus", async () => {
    if (list.childElementCount) return;
    const names = await loadAppNames();
    list.replaceChildren(...names.map((n) => h("option", { value: n })));
  }, { once: true });
  return [input, list];
}

function exampleItem(x, intents, rerender) {
  const box = h("div", { class: "item" });
  const view = () => box.replaceChildren(
    h("div", { class: "item-head" }, h("code", { text: `e${x.id}` }), h("strong", { text: `“${x.text}”` }), " → ", h("code", { text: x.intent_id }),
      h("span", { class: "updated", text: ` · ${x.origin} · lote ${x.batch} · ${fmtWhen(x.created_at)}` })),
    h("div", { class: "toolbar" }, button("Corrigir", edit, "btn small"), forgetButton(`e${x.id}`, x.text, rerender)),
    h("details", {}, h("summary", { text: `Notas (${x.notes.length})` }), notesView("example", x.id, x.notes, rerender)));
  const edit = () => {
    const text = dirty(h("input", { type: "text", value: x.text, "aria-label": "Frase", maxlength: 300 }));
    const intent = intentSelect(intents, x.intent_id);
    box.replaceChildren(h("div", { class: "toolbar" }, h("code", { text: `e${x.id}` }), text, intent,
      button("Salvar", () => write("/api/write/example/edit", { id: x.id, text: text.value, intent: intent.value }, rerender)),
      button("Cancelar", view)));
    text.focus();
  };
  view();
  return box;
}

function aliasItem(a, rerender) {
  const box = h("div", { class: "item" });
  const view = () => box.replaceChildren(
    h("div", { class: "item-head" }, h("code", { text: `a${a.id}` }), h("strong", { text: `“${a.alias}”` }), " → ", a.value,
      h("span", { class: "updated", text: ` · ${a.slot} · lote ${a.batch} · ${fmtWhen(a.created_at)}` })),
    h("div", { class: "toolbar" }, button("Corrigir destino", edit, "btn small"), forgetButton(`a${a.id}`, a.alias, rerender)),
    h("details", {}, h("summary", { text: `Notas (${a.notes.length})` }), notesView("alias", a.id, a.notes, rerender)));
  const edit = () => {
    const [target, list] = appInput(a.value, "Destino");
    box.replaceChildren(h("div", { class: "toolbar" }, h("code", { text: `a${a.id}` }), `“${a.alias}” →`, target, list,
      button("Salvar", () => write("/api/write/alias/edit", { id: a.id, target: target.value }, rerender)),
      button("Cancelar", view)));
    target.focus();
  };
  view();
  return box;
}

async function renderCoppermind(panel) {
  const rerender = () => renderCoppermind(panel).catch((err) => panel.replaceChildren(empty(err.message, true)));
  const views = { episodes: "Episódios", examples: "Exemplos aprendidos", aliases: "Apelidos" };
  const subtabs = h("div", { class: "subtabs" }, Object.entries(views).map(([k, v]) => {
    const b = h("button", { class: "btn", "aria-pressed": String(copper.view === k), text: v });
    b.addEventListener("click", () => { copper.view = k; copper.q = ""; copper.offset = 0; rerender(); });
    return b;
  }));
  let body; let tools = []; let form = null;
  const keepFocus = document.activeElement && document.activeElement.type === "search";
  const intents = await loadIntents();
  if (copper.view === "episodes") {
    const data = await getJSON(`/api/episodes?${episodeQuery(copper)}`);
    if (data.available === false) body = empty(data.message);
    else {
      tools = episodeFilters(copper, rerender, data.decisions, intents);
      body = h("div", {}, data.items.length ? table(["#", "Quando", "Frase", "Decisão", "Pedido", "Melhor pontuação", "Resultado", "Reação", "Notas"],
        data.items.map((e) => [e.id, fmtWhen(e.at), e.utterance, decisionBadge(e), e.intent || "—",
          e.ranking.length ? fmtScore(e.ranking[0].score) : "—", e.outcome || "—", e.reaction_label || "—", e.notes.length || "—"]), [0, 5, 8])
        : empty("Nenhum episódio encontrado."), pager(copper, data.total, rerender),
      h("div", { class: "updated", text: "Para ensinar o que um comando queria dizer ou anotar algo nele, abra-o na aba Raciocínio." }));
    }
  } else {
    const search = h("input", { type: "search", placeholder: "Buscar…", value: copper.q, "aria-label": "Buscar" });
    search.addEventListener("input", debounce(() => { copper.q = search.value; rerender(); }, 300));
    tools = [search];
    const q = copper.q ? `?q=${encodeURIComponent(copper.q)}` : "";
    const data = await getJSON(`/api/${copper.view}${q}`);
    if (copper.view === "examples") {
      const text = dirty(h("input", { type: "text", placeholder: "Frase que deve significar o pedido", "aria-label": "Nova frase", maxlength: 300 }));
      const intent = intentSelect(intents, "");
      form = h("div", { class: "card" }, h("h2", { text: "Ensinar uma frase" }), h("div", { class: "toolbar" }, text, intent,
        button("Ensinar", () => write("/api/write/example/add", { text: text.value, intent: intent.value }, rerender))),
      h("div", { class: "updated", text: "A frase é normalizada como no aprendizado ao vivo. Pedidos de energia nunca são aprendidos." }));
    } else if (copper.view === "aliases") {
      const alias = dirty(h("input", { type: "text", placeholder: "apelido (ex.: zap)", "aria-label": "Novo apelido", maxlength: 80 }));
      const [target, list] = appInput("", "Programa");
      form = h("div", { class: "card" }, h("h2", { text: "Novo apelido de programa" }), h("div", { class: "toolbar" }, alias, "→", target, list,
        button("Guardar", () => write("/api/write/alias/add", { alias: alias.value, target: target.value }, rerender))));
    }
    if (data.available === false) body = empty(data.message);
    else if (!data.items.length) body = empty("Nada encontrado.");
    else if (copper.view === "examples") body = h("div", { class: "stack" }, data.items.map((x) => exampleItem(x, intents, rerender)));
    else body = h("div", { class: "stack" }, data.items.map((a) => aliasItem(a, rerender)));
  }
  panel.replaceChildren(cardWith("Mente de cobre", subtabs, h("div", { class: "toolbar" }, tools),
    h("div", { class: "updated", text: "Mudanças valem a partir do próximo início do Sazed: o Sazed em execução mantém o que já carregou." })),
  form, h("div", { class: "card" }, body));
  if (keepFocus) { const input = panel.querySelector("input[type=search]"); if (input) { input.focus(); input.setSelectionRange(input.value.length, input.value.length); } }
}

// ---------------------------------------------------------------- capabilities & config

const catalog = { loaded: false, q: "" };

async function renderCatalog(box) {
  const data = await getJSON(`/api/catalog${catalog.q ? `?q=${encodeURIComponent(catalog.q)}` : ""}`);
  if (data.available === false) { box.replaceChildren(empty(data.message)); return; }
  box.replaceChildren(h("div", { class: "updated", text: `${data.items.length} de ${data.total} programas` }),
    table(["Nome", "Alvo"], data.items.map((e) => [e.name, h("code", { text: e.target })])));
}

async function renderCapabilities(panel) {
  const c = await getJSON("/api/capabilities");
  const intents = c.skills.flatMap((sk) => sk.intents.map((i) => [sk.id, i]));
  const skills = table(["Habilidade", "Pedido", "Descrição", "Exemplos", "Detalhes (slots)", "Confirmação", "Aprendível", "Repetível (de novo)"], intents.map(([sk, i]) => [
    sk, h("code", { text: i.id }), i.description,
    h("details", {}, h("summary", { text: String(i.examples) }), h("ul", { class: "plain" }, i.example_texts.map((x) => h("li", { text: x })))),
    i.slots.length ? h("div", {}, i.slots.map((sl) => h("div", {}, h("code", { text: sl.name }), sl.required ? " (obrigatório)" : " (opcional)", h("div", { class: "updated", text: sl.question })))) : "—",
    i.confirmation, i.learnable ? "sim" : "nunca", i.repeatable ? "sim" : "não"]));
  const ports = table(["Porta", "Habilidade", "Métodos", "O que faz", "Adaptador"], c.ports.map((p) => [
    h("code", { text: p.name }), p.skill, p.methods.join(", "), p.description, h("code", { text: p.adapter })]));
  const access = h("ul", { class: "plain" },
    h("li", { text: "Programas: lista os atalhos do Menu Iniciar, abre programas e fecha janelas (WM_CLOSE; nunca encerra à força)." }),
    h("li", { text: "Áudio: lê e altera o volume principal e o mudo." }),
    h("li", { text: "Arquivos: lê config.toml e o modelo; Sazed grava a mente de cobre e os logs. Este painel só lê a mente de cobre (SQLite em modo somente leitura) e escreve apenas o próprio log." }),
    h("li", { text: "Rede: nenhuma. Sazed não usa APIs externas; este painel escuta apenas em 127.0.0.1 e não carrega nada de fora." }));
  const cfg = c.config;
  const config = h("div", {},
    h("div", { class: "updated" }, h("code", { text: cfg.path }), cfg.exists ? " (lido)" : " (não existe: valem os padrões)"),
    table(["Chave", "Valor", "Origem"], cfg.rows.map((r) => [h("code", { text: r.key }), typeof r.value === "object" ? JSON.stringify(r.value) : String(r.value),
      h("span", { class: `badge ${r.origin === "arquivo" ? "accent" : ""}`, text: r.origin })])));
  const paths = table(["Item", "Caminho", "Existe", "Tamanho"], c.paths.map((p) => [p.label, h("code", { text: p.path }),
    h("span", { class: `badge ${p.exists ? "good" : "warn"}`, text: p.exists ? "sim" : "não" }), p.size === null ? "—" : fmtBytes(p.size)]), [3]);
  const catBox = h("div", {});
  const search = h("input", { type: "search", placeholder: "Filtrar programas…", value: catalog.q, "aria-label": "Filtrar programas" });
  search.addEventListener("input", debounce(() => { catalog.q = search.value; renderCatalog(catBox).catch((e) => catBox.replaceChildren(empty(e.message, true))); }, 300));
  const load = h("button", { class: "btn", text: catalog.loaded ? "Recarregar lista" : "Carregar catálogo" });
  load.addEventListener("click", () => { catalog.loaded = true; catBox.replaceChildren(empty("Lendo o Menu Iniciar…")); renderCatalog(catBox).catch((e) => catBox.replaceChildren(empty(e.message, true))); });
  if (catalog.loaded) renderCatalog(catBox).catch((e) => catBox.replaceChildren(empty(e.message, true)));
  else catBox.append(empty("O catálogo é lido do Menu Iniciar sob demanda."));
  panel.replaceChildren(
    card("Habilidades e pedidos", skills),
    h("div", { class: "grid-2" }, card("O que Sazed pode tocar", access), card("Portas e adaptadores", ports)),
    card("Configuração efetiva (config.toml + padrões; chaves sensíveis ocultas)", config),
    card("Pastas e arquivos", paths),
    cardWith("Catálogo de programas", h("div", { class: "toolbar" }, search, load), catBox));
}

// ---------------------------------------------------------------- tabs and polling

const TABS = {
  geral: { render: renderOverview, every: 3000 },
  raciocinio: { render: renderReasoning, every: 3000 },
  desenvolvimento: { render: renderDev, every: 10000 },
  aprendizado: { render: renderLearning, every: 30000 },
  recursos: { render: renderResources, every: 2000 },
  coppermind: { render: renderCoppermind, every: 0 },
  capacidades: { render: renderCapabilities, every: 0 },
};
let active = "geral";
let timer = null;
let busy = false;

async function refresh(auto = false) {
  clearTimeout(timer);
  if (busy) return;
  busy = true;
  const panel = document.getElementById(active);
  const tab = active;
  try {
    if (auto && panelBusy(panel)) return; // a form is being filled: do not wipe it
    await TABS[tab].render(panel);
    const now = new Date();
    document.getElementById("updated").textContent = `atualizado às ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  } catch (err) {
    panel.replaceChildren(empty(err.message, true));
  } finally {
    busy = false;
    const every = TABS[tab].every;
    if (every && tab === active && !document.hidden) timer = setTimeout(() => refresh(true), every);
  }
}

function show(tab) {
  if (!TABS[tab]) tab = "geral";
  active = tab;
  for (const button of document.querySelectorAll("nav.tabs button")) {
    button.setAttribute("aria-selected", String(button.dataset.tab === tab));
  }
  for (const panel of document.querySelectorAll("section.panel")) panel.hidden = panel.id !== tab;
  if (location.hash !== `#${tab}`) history.replaceState(null, "", `#${tab}`);
  const panel = document.getElementById(tab);
  if (!panel.childElementCount) panel.append(empty("Carregando…"));
  busy = false;
  refresh();
}

function setupTheme() {
  const select = document.getElementById("theme");
  let saved = "auto";
  try { saved = localStorage.getItem("sazed-theme") || "auto"; } catch { /* storage may be blocked */ }
  const apply = (v) => { if (v === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = v; };
  select.value = saved; apply(saved);
  select.addEventListener("change", () => { apply(select.value); try { localStorage.setItem("sazed-theme", select.value); } catch { /* ignore */ } });
}

document.querySelectorAll("nav.tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
window.addEventListener("hashchange", () => show(location.hash.slice(1)));
document.addEventListener("visibilitychange", () => { if (!document.hidden) { refresh(); refreshStatus(); } });
setupTheme();
show(location.hash.slice(1) || "geral");
refreshStatus();
setInterval(() => { if (!document.hidden) refreshStatus(); }, 5000);
