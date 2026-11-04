// AICtrlProof front end. Vanilla JS. All scoring comes from the server (grc/assess.py).
// Two modes: team (logged in) and respondent (third party via /r/<token>, no login).
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
const LEVELS = ["0 Absent", "1 Initial", "2 Defined", "3 Evidenced"];
const PNAME = { core: "Core", app: "App", agent: "Agent", mcp: "MCP" };
const RTOKEN = (location.pathname.match(/^\/r\/([A-Za-z0-9_-]+)/) || [])[1];

const state = { mode: RTOKEN ? "resp" : "team", bank: null, cur: null, answers: {}, result: null, view: "list", list: [] };
document.body.classList.add(state.mode === "resp" ? "is-resp" : "is-team");

async function api(path, body) {
  const r = await fetch(path, body === undefined ? { credentials: "same-origin" } : {
    method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && state.mode === "team" && path !== "/api/login") { showLogin(); throw new Error("login required"); }
  return { ok: r.ok, status: r.status, data };
}
function toast(msg, bad = false) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast show" + (bad ? " bad" : "");
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.className = "toast"), 2400);
}
const sevOf = (f) => (f >= 0.66 ? "high" : f >= 0.33 ? "medium" : "low");
const pct = (x) => Math.round(x * 100);
const fmtDate = (t) => (t ? new Date(t * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "");

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
  e.preventDefault(); $("#loginErr").textContent = "";
  const user = $("#u").value.trim(), password = $("#p").value;
  if (!user || !password) { $("#loginErr").textContent = "Enter your username and password."; return; }
  const r = await api("/api/login", { user, password });
  if (!r.ok) { $("#loginErr").textContent = r.data.error || "Sign in failed."; return; }
  $("#p").value = ""; startTeam();
});
$("#logout").addEventListener("click", async () => { await api("/api/logout", {}); showLogin(); });

/* ---------------- boot ---------------- */
(async () => {
  if (state.mode === "resp") return startResp();
  const r = await fetch("/api/me", { credentials: "same-origin" });
  r.ok ? startTeam() : showLogin();
})();

async function startTeam() {
  $("#login").hidden = true; $("#app").hidden = false;
  state.bank = (await api("/api/bank")).data;
  renderTagsView();
  await loadList();
  setView("list");
}

async function startResp() {
  $("#login").hidden = true; $("#app").hidden = false;
  const r = await api(`/api/r/${RTOKEN}`);
  if (!r.ok) { $("main").innerHTML = `<div class="card slab3d empty"><h2>Link not available</h2><p class="muted">${esc(r.data.error || "This link is not valid.")}</p></div>`; return; }
  const d = r.data;
  state.bank = d.bank; state.answers = d.answers || {};
  state.cur = { name: d.name, org: d.org, status: d.status, lab: d.lab, profiles: [] };
  $("#respHead").innerHTML = `<span class="muted small">Security questionnaire for</span> <b>${esc(d.org)}</b>`;
  $("#respIntro").innerHTML = `<h2>${esc(d.name)}</h2>
    <p class="muted">Pick the option that best describes your current practice for each control, and add a short note with evidence (policy name, tool, test result).
    Answers save as you go. Mark a question not applicable only with a reason. When every question is answered, press Submit.</p>
    ${d.status === "submitted" ? `<p class="done-note">Submitted. Thank you. Ask the requester to reopen it if you need to change an answer.</p>` : ""}`;
  $$(".view").forEach((s) => (s.hidden = s.id !== "view-assess"));
  renderAssessment();
}

/* ---------------- tabs ---------------- */
$$(".tab").forEach((t) => t.addEventListener("click", () => setView(t.dataset.view)));
function setView(v) {
  if (v !== "list" && !state.cur) { toast("Open an assessment first"); v = "list"; }
  state.view = v;
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === v));
  $$(".view").forEach((s) => (s.hidden = s.id !== "view-" + v));
  if (v === "list") loadList();
  if (v === "dash") refresh();
  if (v === "assess") renderAssessment();
  if (v === "tags") { refresh().then(renderHits); }
  window.scrollTo({ top: 0, behavior: REDUCE ? "auto" : "smooth" });
}

/* ---------------- assessments list ---------------- */
async function loadList() {
  const r = await api("/api/assessments");
  state.list = r.data || [];
  const st = { draft: "n", sent: "a", "in progress": "a", submitted: "v" };
  $("#cards").innerHTML = state.list.map((a) => {
    const prog = a.total ? a.answered / a.total : 0;
    return `<article class="card slab3d tilt acard ${state.cur?.id === a.id ? "active" : ""}" data-id="${a.id}">
      <div class="acard-top">
        <span class="kind ${a.kind === "internal" ? "int" : "ext"}">${a.kind === "internal" ? "Internal" : "Third party"}</span>
        <span class="badge ${st[a.status] || "n"}">${esc(a.status)}</span>
      </div>
      <div class="acard-main">
        <div class="mini-gauge ${a.overall_sev}" style="--v:${pct(a.overall_residual)}"><span>${a.answered ? pct(a.overall_residual) + "%" : "-"}</span></div>
        <div><h3>${esc(a.org)}</h3><p class="muted small">${esc(a.name)}</p>
          <p class="small scope">${["core", ...a.profiles].map((p) => PNAME[p]).join(", ")}</p></div>
      </div>
      <div class="progress"><div class="progress-fill" style="transform:scaleX(${prog})"></div></div>
      <p class="muted small">${a.answered} of ${a.total} answered${a.submitted_at ? `, submitted ${fmtDate(a.submitted_at)}` : ""}</p>
      <div class="acard-actions">
        <button class="btn primary small" data-act="open">Open</button>
        ${a.kind !== "internal" ? `<button class="btn ghost small" data-act="share">${a.shared ? "Copy link" : "Send link"}</button>` : ""}
        ${a.status === "submitted" ? `<button class="btn ghost small" data-act="reopen">Reopen</button>` : ""}
      </div>
    </article>`;
  }).join("") || `<div class="card empty"><p class="muted">No assessments yet. Create one on the left.</p></div>`;
  $$(".acard").forEach((c) => {
    const id = c.dataset.id;
    c.querySelector("[data-act=open]").onclick = () => openAssessment(id, "dash");
    const sh = c.querySelector("[data-act=share]"); if (sh) sh.onclick = () => shareLink(id);
    const ro = c.querySelector("[data-act=reopen]"); if (ro) ro.onclick = async () => { await api(`/api/assessments/${id}/reopen`, {}); toast("Reopened for the vendor"); loadList(); };
  });
  bindTilt();
}
async function shareLink(id) {
  const r = await api(`/api/assessments/${id}/share`, {});
  if (!r.ok) { toast(r.data.error || "Could not create link", true); return; }
  const url = location.origin + r.data.path;
  try { await navigator.clipboard.writeText(url); toast("Link copied. Send it to the vendor."); }
  catch { prompt("Copy this link and send it to the vendor:", url); }
  loadList();
}
async function openAssessment(id, view = "dash") {
  const r = await api(`/api/assessments/${id}`);
  if (!r.ok) { toast("Could not open", true); return; }
  state.cur = r.data; state.answers = r.data.answers || {};
  $("#current").innerHTML = `<span class="muted small">Open:</span> <b>${esc(state.cur.org)}</b> <span class="muted small">${esc(state.cur.name)}</span>`;
  setView(view);
}

// new assessment form
$$("#nKind button").forEach((b) => b.addEventListener("click", () => { $$("#nKind button").forEach((x) => x.classList.toggle("on", x === b)); }));
$$("#nProf button").forEach((b) => b.addEventListener("click", () => b.classList.toggle("on")));
$("#newForm").addEventListener("submit", async (e) => {
  e.preventDefault(); $("#newErr").textContent = "";
  const body = { name: $("#nName").value.trim(), org: $("#nOrg").value.trim(),
    kind: $("#nKind .on").dataset.k, profiles: $$("#nProf .on").map((b) => b.dataset.p) };
  if (!body.name || !body.org) { $("#newErr").textContent = "Enter a name and an organisation."; return; }
  const r = await api("/api/assessments", body);
  if (!r.ok) { $("#newErr").textContent = r.data.error || "Could not create."; return; }
  $("#nName").value = ""; $("#nOrg").value = "";
  toast("Assessment created"); loadList();
});

/* ---------------- dashboard ---------------- */
async function refresh() {
  if (!state.cur || state.mode !== "team") return;
  const r = await api(`/api/assessments/${state.cur.id}/assess`, {});
  if (!r.ok) { toast(r.data.error || "Scoring failed", true); return; }
  state.result = r.data;
  if (state.view === "dash") renderDash();
}

function renderDash() {
  const d = state.result, a = state.cur;
  const v = pct(d.overall_residual), g = $("#gauge");
  g.style.setProperty("--c", `var(--${d.overall_sev === "medium" ? "med" : d.overall_sev})`);
  animateNum($("#gaugeVal"), v, "%"); animateGauge(g, v);
  $("#gaugeSev").textContent = d.overall_sev;
  const scope = (d.profiles === "all" ? ["core", "app", "agent", "mcp"] : d.profiles).map((p) => PNAME[p]);
  $("#scopeLine").innerHTML = `<b>${esc(a.org)}</b>, ${esc(a.name)}.<br>${a.kind === "internal" ? "Internal, lab evidence on" : "Third party, self-reported"}. Scope: ${scope.join(", ")}.
    ${d.questions.length} controls scored, ${d.not_applicable.length} not applicable.`;

  const answered = d.questions.filter((q) => q.answered).length;
  const polIds = Object.keys(d.policy), polMet = polIds.filter((k) => d.policy[k].compliant).length;
  const gaps = d.questions.filter((q) => q.maturity < 2).length;
  const k1 = a.kind === "internal" ? [d.verified_count, "Verified by lab", `of ${d.tested_count} testable controls`]
    : [`${answered}/${d.questions.length}`, "Vendor answered", a.status === "submitted" ? `submitted ${fmtDate(a.submitted_at)}` : a.status];
  $("#kpis").innerHTML = [
    ["accent", ...k1],
    ["", `${answered}/${d.questions.length}`, "Controls answered", "attested plus lab evidence"],
    ["", `${polMet}/${polIds.length}`, "Policy clauses met", "every control at maturity 2+"],
    ["", gaps, "Open gaps", "controls below maturity 2"],
  ].map(([c, val, l, s], i) => `<div class="card slab3d tilt kpi ${c}" style="--i:${i}"><div class="l">${l}</div><div class="v">${val}</div><div class="s">${esc(s)}</div></div>`).join("");

  // 3D towers: one bar per domain, height = residual
  $("#domains").innerHTML = `<div class="tower-floor">` + Object.entries(d.domains).sort((x, y) => y[1].frac - x[1].frac).map(([n, x]) => `
    <div class="tower ${x.sev}" title="${esc(n)}: ${pct(x.frac)}% residual, ${x.gaps} gaps">
      <div class="tw-col" data-h="${Math.max(3, pct(x.frac))}">
        <div class="tw-bar"><i class="face front"></i><i class="face side"></i></div>
        <div class="tw-cap"><span class="tw-val">${pct(x.frac)}%</span><i class="top"></i></div></div>
      <div class="tw-name">${esc(n)}</div>
    </div>`).join("") + `</div>`;

  $("#policy").innerHTML = polIds.map((k) => { const p = d.policy[k]; return `
    <div class="pol ${p.compliant ? "ok" : "no"}" title="Evidenced by ${esc(p.questions.join(", "))}">
      <span class="id">${k}</span><span class="t">${esc(p.title)}</span>
      <span class="m">${p.met}/${p.questions.length} controls at 2+${p.verified ? `, ${p.verified} verified` : ""}</span></div>`; }).join("");

  $("#frameworks").innerHTML = Object.entries(d.frameworks).sort().map(([fw, f]) => {
    const cov = f.total ? Math.round((100 * f.addressed) / f.total) : 0;
    return `<button class="fwc" data-fw="${esc(fw)}" title="Open in standards map"><span class="ring" style="--p:${cov}"><b>${cov}%</b></span>
      <span class="n">${esc(fw)}</span>
      <span class="sub">${f.addressed}/${f.total} clauses addressed, ${f.verified} verified, ${f.gaps} gaps</span></button>`;
  }).join("");
  $$(".fwc").forEach((el) => el.addEventListener("click", () => { $("#fwSel").value = el.dataset.fw; fillClauses(); setView("tags"); }));

  $("#findings").innerHTML = [...d.questions].sort((x, y) => y.residual - x.residual).slice(0, 6).map((q) => `
    <div class="find"><span class="id">${q.id}</span>
      <div><div class="q">${esc(q.question)}</div><div class="muted small">${esc(q.evidence)}</div></div>
      <span class="pill ${sevOf(q.residual / q.max)}">${q.residual.toFixed(1)}</span></div>`).join("") || `<p class="muted">No findings.</p>`;

  $("#nist").innerHTML = Object.entries(d.nist_metrics).flatMap(([sc, ms]) => ms.map((m) => `
    <div class="nm"><span class="sc">${esc(sc)}</span><div>${esc(m.metric)}<div class="tg">${m.id}, target ${esc(m.target)}</div></div>
      ${m.measured ? `<span class="badge v" title="${esc(m.evidence)}">measured</span>` : `<span class="badge n">to define</span>`}</div>`)).join("");

  renderReview();
  requestAnimationFrame(() => requestAnimationFrame(() =>
    $$(".tw-col[data-h]").forEach((c, i) => {
      const h = c.dataset.h / 100, bar = c.querySelector(".tw-bar"), cap = c.querySelector(".tw-cap"), d = REDUCE ? "0s" : `${i * 40}ms`;
      bar.style.transitionDelay = cap.style.transitionDelay = d;
      bar.style.transform = `scaleY(${h})`; cap.style.transform = `translateY(${-200 * h}px)`;
    })));
  bindTilt();
}

/* AI review panel (inserted at top of dashboard when the server supports it) */
function renderReview() {
  let box = $("#reviewBox");
  if (!box) {
    box = document.createElement("div"); box.id = "reviewBox"; box.className = "card slab3d review";
    $("#view-dash").insertBefore(box, $("#view-dash").children[1]);
  }
  const rv = state.cur.review;
  const actions = `<div class="rv-actions">
      <button class="btn primary small" id="rvRun">${rv ? "Re-run AI review" : "Run AI review"}</button>
      <button class="btn ghost small" id="rvOpen">Open report</button>
      <button class="btn ghost small" id="rvShare">Share report link</button></div>`;
  if (!rv) {
    box.innerHTML = `<div class="rv-head"><div><h3>AI review</h3><p class="muted small">Reads the answers and notes, flags weak evidence, and drafts follow-up questions for the vendor.</p></div>${actions}</div>`;
  } else {
    box.innerHTML = `<div class="rv-head"><div><h3>AI review <span class="badge ${rv.rating === "low" ? "v" : rv.rating === "high" ? "g" : "a"}">${esc(rv.rating)} risk</span></h3>
        <p class="muted small">${rv.mode === "claude" ? `Model: ${esc(rv.model)}` : "Rule-based analysis (no AI model configured)"}, ${fmtDate(rv.generated_at)}</p></div>${actions}</div>
      <p class="rv-sum">${esc(rv.summary)}</p>
      <div class="rv-grid">
        <div><h4>Top risks</h4>${(rv.top_risks || []).map((t) => `<div class="rv-item"><b>${esc(t.id)}</b> ${esc(t.title)}<div class="muted small">${esc(t.why)}</div><div class="fix">Fix: ${esc(t.fix)}</div></div>`).join("") || `<p class="muted small">None.</p>`}</div>
        <div><h4>Red flags in the answers</h4>${(rv.red_flags || []).map((t) => `<div class="rv-item flag"><b>${esc(t.id)}</b> ${esc(t.issue)}</div>`).join("") || `<p class="muted small">None found.</p>`}
          <h4>Ask the vendor next</h4><ol class="rv-q">${(rv.follow_up_questions || []).map((q) => `<li>${esc(q)}</li>`).join("")}</ol></div>
      </div>`;
  }
  $("#rvRun").onclick = async () => {
    $("#rvRun").disabled = true; $("#rvRun").textContent = "Reviewing...";
    const r = await api(`/api/assessments/${state.cur.id}/review`, {});
    if (!r.ok) { toast(r.data.error || "Review failed", true); $("#rvRun").disabled = false; return; }
    state.cur.review = r.data; renderReview(); toast("AI review ready");
  };
  $("#rvOpen").onclick = () => window.open(`/api/assessments/${state.cur.id}/report`, "_blank");
  $("#rvShare").onclick = async () => {
    const r = await api(`/api/assessments/${state.cur.id}/share-report`, {});
    if (!r.ok) { toast(r.data.error || "Could not share", true); return; }
    const url = location.origin + r.data.path;
    try { await navigator.clipboard.writeText(url); toast("Report link copied"); } catch { prompt("Report link:", url); }
  };
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
function bindTilt() {
  if (REDUCE || !matchMedia("(hover: hover)").matches) return;
  $$(".tilt").forEach((el) => {
    if (el._tilt) return; el._tilt = true;
    el.addEventListener("pointermove", (e) => {
      const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      el.style.transform = `perspective(1000px) rotateX(${(-y * 5).toFixed(2)}deg) rotateY(${(x * 6).toFixed(2)}deg) translateZ(8px)`;
    });
    el.addEventListener("pointerleave", () => (el.style.transform = ""));
  });
}

/* ---------------- questions ---------------- */
const answerable = (q) => q.type !== "tested" || (state.mode === "resp" ? state.cur.lab === false : state.cur.kind !== "internal");
const inScope = (q) => state.mode === "resp" || q.applies_to.some((x) => x === "core" || (state.cur.profiles || []).includes(x));
const isDone = (q) => !answerable(q) || state.answers[q.id];
const locked = () => state.mode === "resp" && state.cur.status === "submitted";

function tagChips(q) {
  const pol = Object.fromEntries(state.bank.policy.map((p) => [p.id, p.title]));
  const chips = q.policy.map((p) => `<span class="tag pol" title="${esc(pol[p] || "")}">AI policy ${p}</span>`);
  for (const [fw, cls] of Object.entries(q.tags)) chips.push(`<span class="tag"><b>${esc(fw)}</b> ${esc(cls.join(", "))}</span>`);
  if (q.nist_metric) chips.push(`<span class="tag nist" title="${esc(q.nist_metric.metric)}, target ${esc(q.nist_metric.target)}">NIST ${esc(q.nist_metric.subcategory)}: ${esc(q.nist_metric.metric)}</span>`);
  return `<div class="tags">${chips.join("")}</div>`;
}
function statusBadge(q) {
  if (!answerable(q)) return `<span class="badge v">lab tested</span>`;
  const a = state.answers[q.id];
  if (!a) return `<span class="badge g">unanswered</span>`;
  if (a.na) return `<span class="badge n">not applicable</span>`;
  return `<span class="badge a">answered ${a.maturity}/3</span>`;
}
function labEvidence(q) {
  const r = state.result?.questions.find((x) => x.id === q.id);
  if (!r) return `<div class="lab-ev none">Lab evidence loads with the dashboard.</div>`;
  return r.verified ? `<div class="lab-ev">Verified by the lab: maturity ${r.maturity}/3. ${esc(r.evidence)}</div>`
    : `<div class="lab-ev none">No lab evidence yet (${esc(r.evidence)}).</div>`;
}
function renderAssessment() {
  const qs = state.bank.questions.filter(inScope), byDom = {};
  qs.forEach((q) => (byDom[q.domain] ??= []).push(q));
  $("#qlist").innerHTML = Object.entries(byDom).map(([dom, list]) =>
    `<div class="dom-h" id="dom-${slug(dom)}">${esc(dom)}</div>` + list.map(qCard).join("")).join("");
  $("#domainNav").innerHTML = Object.entries(byDom).map(([dom, list]) =>
    `<button class="dn" data-dom="${slug(dom)}">${esc(dom)}<b>${list.filter(isDone).length}/${list.length}</b></button>`).join("");
  $$(".dn").forEach((b) => b.addEventListener("click", () => $("#dom-" + b.dataset.dom).scrollIntoView({ behavior: REDUCE ? "auto" : "smooth", block: "start" })));
  bindQuestions(); updateProgress();
}
const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-");
function qCard(q) {
  const a = state.answers[q.id] || {}, ans = answerable(q), lk = locked();
  const opts = q.options.map((o, i) => `
    <button class="opt ${ans && !a.na && a.maturity === i ? "sel" : ""}" data-q="${q.id}" data-m="${i}" ${!ans || a.na || lk ? "disabled" : ""} aria-pressed="${a.maturity === i}">
      <span class="lv">${LEVELS[i]}</span><span class="tx">${esc(o)}</span></button>`).join("");
  return `<article class="card slab3d q ${state.answers[q.id] ? "answered" : ""}" id="q-${q.id}">
    <div class="q-head"><span class="q-id">${q.id}</span>
      <div><div class="q-title">${esc(q.question)}</div><div class="q-guid">${esc(q.guidance)}</div></div>
      <span class="q-status">${statusBadge(q)}</span></div>
    <div class="opts">${opts}</div>
    ${!ans ? labEvidence(q) : `<div class="q-foot">
      <input data-note="${q.id}" placeholder="Evidence or note (required for not applicable)" value="${esc(a.note || "")}" aria-label="Note for ${q.id}" ${lk ? "disabled" : ""}>
      <label class="na"><input type="checkbox" data-na="${q.id}" ${a.na ? "checked" : ""} ${lk ? "disabled" : ""}> Not applicable</label></div>
      <p class="q-err" id="err-${q.id}"></p>`}
    ${tagChips(q)}
  </article>`;
}
function bindQuestions() {
  $$(".opt[data-q]:not([disabled])").forEach((b) => (b.onclick = () => {
    const id = b.dataset.q; save(id, { maturity: +b.dataset.m, note: $(`[data-note="${id}"]`)?.value || "" });
  }));
  $$("[data-na]").forEach((c) => (c.onchange = () => {
    const id = c.dataset.na, note = $(`[data-note="${id}"]`).value.trim();
    if (c.checked) {
      if (!note) { c.checked = false; $("#err-" + id).textContent = "Add a note saying why this does not apply, then tick Not applicable."; $(`[data-note="${id}"]`).focus(); return; }
      save(id, { na: true, note });
    } else save(id, null);
  }));
  $$("[data-note]").forEach((i) => (i.onchange = () => { const id = i.dataset.note, cur = state.answers[id]; if (cur) save(id, { ...cur, note: i.value }); }));
}
async function save(id, ans) {
  const url = state.mode === "resp" ? `/api/r/${RTOKEN}/answers` : `/api/assessments/${state.cur.id}/answers`;
  const r = await api(url, { [id]: ans });
  const errEl = $("#err-" + id);
  if (!r.ok) { const m = r.data.errors?.[id] || r.data.error || "Not saved"; if (errEl) errEl.textContent = m; toast(m, true); return; }
  if (errEl) errEl.textContent = "";
  if (ans === null) delete state.answers[id]; else state.answers[id] = ans;
  const q = state.bank.questions.find((x) => x.id === id);
  $("#q-" + id).outerHTML = qCard(q); bindQuestions(); updateProgress(); navCounts();
  toast(`${id} saved and validated`);
  if (state.mode === "team") refresh();
}
function navCounts() {
  const qs = state.bank.questions.filter(inScope), byDom = {};
  qs.forEach((q) => (byDom[q.domain] ??= []).push(q));
  $$(".dn").forEach((b) => { const list = Object.entries(byDom).find(([d]) => slug(d) === b.dataset.dom)?.[1] || [];
    b.querySelector("b").textContent = `${list.filter(isDone).length}/${list.length}`; });
}
function updateProgress() {
  const qs = state.bank.questions.filter(inScope), done = qs.filter(isDone).length;
  $("#progFill").style.transform = `scaleX(${qs.length ? done / qs.length : 0})`;
  $("#progText").textContent = `${done} of ${qs.length} controls complete`;
}
$("#resetBtn").addEventListener("click", async () => {
  const b = $("#resetBtn");
  if (!b.dataset.confirm) { b.dataset.confirm = "1"; b.textContent = "Click again to clear"; setTimeout(() => { delete b.dataset.confirm; b.textContent = "Clear all answers"; }, 3000); return; }
  await api(`/api/assessments/${state.cur.id}/reset`, {}); state.answers = {}; delete b.dataset.confirm; b.textContent = "Clear all answers";
  renderAssessment(); refresh(); toast("All answers cleared");
});
$("#submitBtn").addEventListener("click", async () => {
  const r = await api(`/api/r/${RTOKEN}/submit`, {});
  if (!r.ok) {
    toast(r.data.error || "Could not submit", true);
    const first = r.data.missing?.[0]; if (first) $("#q-" + first)?.scrollIntoView({ behavior: REDUCE ? "auto" : "smooth", block: "center" });
    return;
  }
  state.cur.status = "submitted"; startResp(); toast("Submitted. Thank you.");
});

/* ---------------- standards map ---------------- */
function renderTagsView() {
  const fws = Object.keys(state.bank.meta.clauses);
  $("#fwSel").innerHTML = [`<option value="AI policy">AI policy</option>`, ...fws.map((f) => `<option>${esc(f)}</option>`)].join("");
  $("#fwSel").value = "EU AI Act";
  $("#fwSel").onchange = fillClauses; $("#clSel").onchange = renderHits;
  fillClauses();
}
function fillClauses() {
  const fw = $("#fwSel").value;
  const cls = fw === "AI policy" ? state.bank.policy.map((p) => p.id) : state.bank.meta.clauses[fw];
  const label = (c) => (fw === "AI policy" ? `${c} ${state.bank.policy.find((p) => p.id === c).title}` : c);
  $("#clSel").innerHTML = `<option value="">All clauses</option>` + cls.map((c) => `<option value="${esc(c)}">${esc(label(c))}</option>`).join("");
  renderHits();
}
function renderHits() {
  const fw = $("#fwSel").value, cl = $("#clSel").value;
  const hits = state.bank.questions.filter((q) => { const cls = fw === "AI policy" ? q.policy : q.tags[fw]; return cls && (!cl || cls.includes(cl)); });
  const rows = Object.fromEntries((state.result?.questions || []).map((r) => [r.id, r]));
  $("#tagHits").innerHTML = hits.map((q) => {
    const r = rows[q.id], cls = fw === "AI policy" ? q.policy : q.tags[fw];
    const st = !r ? `<span class="badge n">out of scope</span>` : r.verified ? `<span class="badge v">verified ${r.maturity}/3</span>`
      : r.answered ? `<span class="badge a">answered ${r.maturity}/3</span>` : `<span class="badge g">gap</span>`;
    return `<div class="hit"><b>${q.id}</b><div>${esc(q.question)}<div class="muted small">${esc(cls.join(", "))}</div></div>${st}</div>`;
  }).join("") || `<p class="muted">No questions map to this clause yet.</p>`;
}
