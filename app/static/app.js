// AICtrlProof front end. Vanilla JS. All scoring comes from the server (grc/assess.py).
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
const LEVELS = ["0 Absent", "1 Initial", "2 Defined", "3 Evidenced"];

const state = { bank: null, answers: {}, profiles: new Set(["app", "agent", "mcp"]), result: null, view: "dash" };

async function api(path, body) {
  const r = await fetch(path, body === undefined ? { credentials: "same-origin" } : {
    method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && path !== "/api/login") { showLogin(); throw new Error("login required"); }
  return { ok: r.ok, status: r.status, data };
}

function toast(msg, bad = false) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.className = "toast"), 2200);
}

/* ---------------- login ---------------- */
function showLogin() {
  $("#app").hidden = true; $("#login").hidden = false; $("#u").focus();
  fetch("/api/demo").then((r) => r.json()).then((d) => {
    if (!d.demo) return;
    $("#dUser").textContent = d.user; $("#dPass").textContent = d.password; $("#demoHint").hidden = false;
    $("#dFill").onclick = () => { $("#u").value = d.user; $("#p").value = d.password; $("#loginForm").requestSubmit(); };
  }).catch(() => {});
}
$("#loginForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#loginErr").textContent = "";
  const user = $("#u").value.trim(), password = $("#p").value;
  if (!user || !password) { $("#loginErr").textContent = "Enter your username and password."; return; }
  const r = await api("/api/login", { user, password });
  if (!r.ok) { $("#loginErr").textContent = r.data.error || "Sign in failed."; return; }
  $("#p").value = ""; start();
});
$("#logout").addEventListener("click", async () => { await api("/api/logout", {}); showLogin(); });

/* ---------------- boot ---------------- */
async function start() {
  $("#login").hidden = true; $("#app").hidden = false;
  const [b, a] = await Promise.all([api("/api/bank"), api("/api/answers")]);
  state.bank = b.data; state.answers = a.data || {};
  renderProfiles(); renderAssessment(); renderTagsView(); await refresh();
}
(async () => { const r = await fetch("/api/me", { credentials: "same-origin" }); r.ok ? start() : showLogin(); })();

/* ---------------- tabs + profiles ---------------- */
$$(".tab").forEach((t) => t.addEventListener("click", () => setView(t.dataset.view)));
function setView(v) {
  state.view = v;
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === v));
  $$(".view").forEach((s) => (s.hidden = s.id !== "view-" + v));
  if (v === "dash") refresh();
  if (v === "tags") renderHits();
}
function renderProfiles() {
  const p = state.bank.meta.profiles, box = $("#profiles");
  box.innerHTML = Object.keys(p).map((k) => k === "core"
    ? `<button class="chip on" disabled title="${esc(p[k])}">Core</button>`
    : `<button class="chip ${state.profiles.has(k) ? "on" : ""}" data-p="${k}" title="${esc(p[k])}" aria-pressed="${state.profiles.has(k)}">${k === "mcp" ? "MCP" : k[0].toUpperCase() + k.slice(1)}</button>`).join("");
  $$("[data-p]", box).forEach((b) => b.addEventListener("click", () => {
    const k = b.dataset.p; state.profiles.has(k) ? state.profiles.delete(k) : state.profiles.add(k);
    renderProfiles(); renderAssessment(); refresh();
  }));
}
const inScope = (q) => q.applies_to.some((a) => a === "core" || state.profiles.has(a));

/* ---------------- dashboard ---------------- */
async function refresh() {
  const r = await api("/api/assess", { profiles: [...state.profiles] });
  if (!r.ok) { toast(r.data.error || "Scoring failed", true); return; }
  state.result = r.data; renderDash();
}
function sevOf(f) { return f >= 0.66 ? "high" : f >= 0.33 ? "medium" : "low"; }

function renderDash() {
  const d = state.result;
  const pct = Math.round(d.overall_residual * 100);
  const g = $("#gauge");
  g.style.setProperty("--c", `var(--${d.overall_sev === "medium" ? "med" : d.overall_sev})`);
  animateNum($("#gaugeVal"), pct, "%");
  g.style.setProperty("--v", 0);
  requestAnimationFrame(() => animateGauge(g, pct));
  $("#gaugeSev").textContent = d.overall_sev + " residual risk";
  const scope = ["Core", ...[...state.profiles].map((p) => (p === "mcp" ? "MCP" : p[0].toUpperCase() + p.slice(1)))];
  $("#scopeLine").textContent = `Scope: ${scope.join(", ")}. ${d.questions.length} controls scored, ${d.not_applicable.length} not applicable.`;

  const answered = d.questions.filter((q) => q.answered).length;
  const polIds = Object.keys(d.policy), polMet = polIds.filter((k) => d.policy[k].compliant).length;
  const gaps = d.questions.filter((q) => q.maturity < 2).length;
  $("#kpis").innerHTML = [
    ["accent", d.verified_count, "Verified by lab", `of ${d.tested_count} testable controls`],
    ["", `${answered}/${d.questions.length}`, "Controls answered", "attested plus lab evidence"],
    ["", `${polMet}/${polIds.length}`, "Policy clauses met", "every control at maturity 2+"],
    ["", gaps, "Open gaps", "controls below maturity 2"],
  ].map(([c, v, l, s]) => `<div class="card tilt kpi ${c}"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join("");

  $("#domains").innerHTML = Object.entries(d.domains).sort((a, b) => b[1].frac - a[1].frac).map(([n, x]) => `
    <div class="bar"><div class="name">${esc(n)}<em>${x.gaps} gap${x.gaps === 1 ? "" : "s"}</em></div>
      <div class="track"><div class="fill ${x.sev}" data-w="${Math.round(x.frac * 100)}"></div></div>
      <div class="pct">${Math.round(x.frac * 100)}%</div></div>`).join("");

  $("#policy").innerHTML = polIds.map((k) => { const p = d.policy[k]; return `
    <div class="pol ${p.compliant ? "ok" : "no"}" title="Evidenced by ${esc(p.questions.join(", "))}">
      <span class="id">${k}</span><span class="t">${esc(p.title)}</span>
      <span class="m">${p.met}/${p.questions.length} controls at 2+${p.verified ? `, ${p.verified} verified` : ""}</span></div>`; }).join("");

  $("#frameworks").innerHTML = Object.entries(d.frameworks).sort().map(([fw, f]) => {
    const cov = f.total ? Math.round((100 * f.addressed) / f.total) : 0;
    return `<div class="fw" data-fw="${esc(fw)}" title="Open in standards map"><div><span class="ring" style="--p:${cov}"></span>
      <div class="n">${esc(fw)}</div><div class="big">${cov}%</div></div>
      <div class="sub">${f.addressed} of ${f.total} clauses addressed, ${f.verified} verified, ${f.gaps} gaps</div></div>`;
  }).join("");
  $$(".fw").forEach((el) => el.addEventListener("click", () => { $("#fwSel").value = el.dataset.fw; fillClauses(); setView("tags"); }));

  $("#findings").innerHTML = [...d.questions].sort((a, b) => b.residual - a.residual).slice(0, 6).map((q) => `
    <div class="find"><span class="id">${q.id}</span>
      <div><div class="q">${esc(q.question)}</div><div class="muted small">${esc(q.evidence)}</div></div>
      <span class="pill ${sevOf(q.residual / q.max)}">${q.residual.toFixed(1)}</span></div>`).join("") || `<p class="muted">No findings.</p>`;

  $("#nist").innerHTML = Object.entries(d.nist_metrics).flatMap(([sc, ms]) => ms.map((m) => `
    <div class="nm"><span class="sc">${esc(sc)}</span><div>${esc(m.metric)}<div class="tg">${m.id}, target ${esc(m.target)}</div></div>
      ${m.measured ? `<span class="badge v" title="${esc(m.evidence)}">measured</span>` : `<span class="badge n">to define</span>`}</div>`)).join("");

  requestAnimationFrame(() => $$(".fill[data-w]").forEach((f) => (f.style.transform = `scaleX(${f.dataset.w / 100})`)));
  bindTilt();
}
function animateGauge(g, target) {
  if (REDUCE) { g.style.setProperty("--v", target); return; }
  const t0 = performance.now(), dur = 900;
  const step = (t) => { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    g.style.setProperty("--v", (target * e).toFixed(1)); if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}
function animateNum(el, target, suffix = "") {
  if (REDUCE) { el.textContent = target + suffix; return; }
  const t0 = performance.now(), dur = 900;
  const step = (t) => { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.textContent = Math.round(target * e) + suffix; if (k < 1) requestAnimationFrame(step); };
  requestAnimationFrame(step);
}

/* soft 3D tilt, pointer devices only, off under reduced motion */
function bindTilt() {
  if (REDUCE || !matchMedia("(hover: hover)").matches) return;
  $$(".tilt").forEach((el) => {
    if (el._tilt) return; el._tilt = true;
    el.addEventListener("pointermove", (e) => {
      const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      el.style.transform = `perspective(1100px) rotateX(${(-y * 3).toFixed(2)}deg) rotateY(${(x * 4).toFixed(2)}deg) translateY(-3px)`;
    });
    el.addEventListener("pointerleave", () => (el.style.transform = ""));
  });
}

/* ---------------- assessment ---------------- */
function tagChips(q) {
  const pol = Object.fromEntries(state.bank.policy.map((p) => [p.id, p.title]));
  const chips = q.policy.map((p) => `<span class="tag pol" title="${esc(pol[p] || "")}">AI policy ${p}</span>`);
  for (const [fw, cls] of Object.entries(q.tags)) chips.push(`<span class="tag fw"><b>${esc(fw)}</b> ${esc(cls.join(", "))}</span>`);
  if (q.nist_metric) chips.push(`<span class="tag nist" title="${esc(q.nist_metric.metric)}, target ${esc(q.nist_metric.target)}">NIST ${esc(q.nist_metric.subcategory)}: ${esc(q.nist_metric.metric)}</span>`);
  return `<div class="tags">${chips.join("")}</div>`;
}
function statusBadge(q) {
  if (q.type === "tested") return `<span class="badge v">lab tested</span>`;
  const a = state.answers[q.id];
  if (!a) return `<span class="badge g">unanswered</span>`;
  if (a.na) return `<span class="badge n">not applicable</span>`;
  return `<span class="badge a">attested ${a.maturity}/3</span>`;
}
function labEvidence(q) {
  const r = state.result?.questions.find((x) => x.id === q.id);
  if (!r) return `<div class="lab-ev none">Out of scope for the selected system types.</div>`;
  return r.verified ? `<div class="lab-ev">Verified by the lab: maturity ${r.maturity}/3. ${esc(r.evidence)}</div>`
    : `<div class="lab-ev none">No lab evidence yet (${esc(r.evidence)}). Run a lab study to verify this control.</div>`;
}

function renderAssessment() {
  const qs = state.bank.questions.filter(inScope);
  const byDom = {};
  qs.forEach((q) => (byDom[q.domain] ??= []).push(q));
  $("#qlist").innerHTML = Object.entries(byDom).map(([dom, list]) => `
    <div class="dom-h" id="dom-${slug(dom)}">${esc(dom)}</div>` + list.map((q) => qCard(q)).join("")).join("");
  $("#domainNav").innerHTML = Object.entries(byDom).map(([dom, list]) => {
    const done = list.filter((q) => q.type === "tested" || state.answers[q.id]).length;
    return `<button class="dn" data-dom="${slug(dom)}">${esc(dom)}<b>${done}/${list.length}</b></button>`;
  }).join("");
  $$(".dn").forEach((b) => b.addEventListener("click", () => $("#dom-" + b.dataset.dom).scrollIntoView({ behavior: REDUCE ? "auto" : "smooth", block: "start" })));
  bindQuestions(); updateProgress();
}
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-");

function qCard(q) {
  const a = state.answers[q.id] || {};
  const tested = q.type === "tested";
  const opts = q.options.map((o, i) => `
    <button class="opt ${!tested && !a.na && a.maturity === i ? "sel" : ""} ${tested ? "lab" : ""}" data-q="${q.id}" data-m="${i}" ${tested || a.na ? "disabled" : ""} aria-pressed="${a.maturity === i}">
      <span class="lv">${LEVELS[i]}</span><span class="tx">${esc(o)}</span></button>`).join("");
  return `<article class="card q ${state.answers[q.id] ? "answered" : ""}" id="q-${q.id}">
    <div class="q-head"><span class="q-id">${q.id}</span>
      <div><div class="q-title">${esc(q.question)}</div><div class="q-guid">${esc(q.guidance)}</div></div>
      <span class="q-status">${statusBadge(q)}</span></div>
    <div class="opts">${opts}</div>
    ${tested ? labEvidence(q) : `<div class="q-foot">
      <input data-note="${q.id}" placeholder="Evidence or note (required for not applicable)" value="${esc(a.note || "")}" aria-label="Note for ${q.id}">
      <label class="na"><input type="checkbox" data-na="${q.id}" ${a.na ? "checked" : ""}> Not applicable</label></div>
      <p class="q-err" id="err-${q.id}"></p>`}
    ${tagChips(q)}
  </article>`;
}

function bindQuestions() {
  $$(".opt[data-q]:not([disabled])").forEach((b) => b.addEventListener("click", () => {
    const id = b.dataset.q, m = +b.dataset.m, note = $(`[data-note="${id}"]`)?.value || "";
    save(id, { maturity: m, note });
  }));
  $$("[data-na]").forEach((c) => c.addEventListener("change", () => {
    const id = c.dataset.na, note = $(`[data-note="${id}"]`).value.trim();
    if (c.checked) {
      if (!note) { c.checked = false; $("#err-" + id).textContent = "Add a note saying why this does not apply, then tick Not applicable."; $(`[data-note="${id}"]`).focus(); return; }
      save(id, { na: true, note });
    } else save(id, null);
  }));
  $$("[data-note]").forEach((i) => i.addEventListener("change", () => {
    const id = i.dataset.note, cur = state.answers[id];
    if (cur) save(id, { ...cur, note: i.value });
  }));
}

async function save(id, ans) {
  const r = await api("/api/answers", { [id]: ans });
  const errEl = $("#err-" + id);
  if (!r.ok) { const m = r.data.errors?.[id] || r.data.error || "Not saved"; if (errEl) errEl.textContent = m; toast(m, true); return; }
  if (errEl) errEl.textContent = "";
  if (ans === null) delete state.answers[id]; else state.answers[id] = ans;
  const card = $("#q-" + id), q = state.bank.questions.find((x) => x.id === id);
  card.outerHTML = qCard(q); bindQuestions(); updateProgress();
  renderNavCounts();
  toast(`${id} saved and validated`);
  refresh();
}
function renderNavCounts() {
  const qs = state.bank.questions.filter(inScope), byDom = {};
  qs.forEach((q) => (byDom[q.domain] ??= []).push(q));
  $$(".dn").forEach((b) => {
    const list = Object.entries(byDom).find(([d]) => slug(d) === b.dataset.dom)?.[1] || [];
    b.querySelector("b").textContent = `${list.filter((q) => q.type === "tested" || state.answers[q.id]).length}/${list.length}`;
  });
}
function updateProgress() {
  const qs = state.bank.questions.filter(inScope);
  const done = qs.filter((q) => q.type === "tested" || state.answers[q.id]).length;
  $("#progFill").style.transform = `scaleX(${qs.length ? done / qs.length : 0})`;
  $("#progText").textContent = `${done} of ${qs.length} controls complete`;
}
$("#resetBtn").addEventListener("click", async () => {
  if (!$("#resetBtn").dataset.confirm) { $("#resetBtn").dataset.confirm = "1"; $("#resetBtn").textContent = "Click again to clear"; setTimeout(() => { delete $("#resetBtn").dataset.confirm; $("#resetBtn").textContent = "Clear all answers"; }, 3000); return; }
  await api("/api/reset", {}); state.answers = {}; delete $("#resetBtn").dataset.confirm; $("#resetBtn").textContent = "Clear all answers";
  renderAssessment(); refresh(); toast("All answers cleared");
});

/* ---------------- standards map ---------------- */
function renderTagsView() {
  const fws = Object.keys(state.bank.meta.clauses);
  $("#fwSel").innerHTML = [`<option value="AI policy">AI policy</option>`, ...fws.map((f) => `<option>${esc(f)}</option>`)].join("");
  $("#fwSel").value = "EU AI Act";
  $("#fwSel").addEventListener("change", fillClauses);
  $("#clSel").addEventListener("change", renderHits);
  fillClauses();
}
function fillClauses() {
  const fw = $("#fwSel").value;
  const cls = fw === "AI policy" ? state.bank.policy.map((p) => p.id) : state.bank.meta.clauses[fw];
  const label = (c) => fw === "AI policy" ? `${c} ${state.bank.policy.find((p) => p.id === c).title}` : c;
  $("#clSel").innerHTML = `<option value="">All clauses</option>` + cls.map((c) => `<option value="${esc(c)}">${esc(label(c))}</option>`).join("");
  renderHits();
}
function renderHits() {
  const fw = $("#fwSel").value, cl = $("#clSel").value;
  const hits = state.bank.questions.filter((q) => {
    const cls = fw === "AI policy" ? q.policy : q.tags[fw];
    return cls && (!cl || cls.includes(cl));
  });
  const rows = Object.fromEntries((state.result?.questions || []).map((r) => [r.id, r]));
  $("#tagHits").innerHTML = hits.map((q) => {
    const r = rows[q.id], cls = fw === "AI policy" ? q.policy : q.tags[fw];
    const st = !r ? `<span class="badge n">out of scope</span>` : r.verified ? `<span class="badge v">verified ${r.maturity}/3</span>`
      : r.answered ? `<span class="badge a">attested ${r.maturity}/3</span>` : `<span class="badge g">gap</span>`;
    return `<div class="hit"><b>${q.id}</b><div>${esc(q.question)}<div class="muted small">${esc(cls.join(", "))}</div></div>${st}</div>`;
  }).join("") || `<p class="muted">No questions map to this clause yet.</p>`;
}
