const state = { batchId: "", jobId: "", role: document.querySelector("main")?.dataset.role || "operator" };

const $ = (selector) => document.querySelector(selector);

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (response.status === 401) { window.location.href = "/login"; throw new Error("请先登录"); }
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(body.detail || body || `请求失败：${response.status}`);
  return body;
}

function notice(message, error = false) {
  const box = $("#notice");
  box.textContent = message;
  box.classList.remove("hidden", "error");
  if (error) box.classList.add("error");
  window.setTimeout(() => box.classList.add("hidden"), 5000);
}

function percent(value) { return `${Math.round((value || 0) * 100)}%`; }

async function loadBatches(prefer) {
  const batches = await api("/api/batches");
  const select = $("#batch-select");
  select.innerHTML = batches.map((item) => `<option value="${esc(item.batch_id)}">${esc(item.batch_id)} · ${esc(item.status)} · ${esc(item.person_count)}人/${esc(item.job_count)}岗</option>`).join("");
  state.batchId = prefer || batches[0]?.batch_id || "";
  select.value = state.batchId;
  const current = batches.find((item) => item.batch_id === state.batchId);
  $("#batch-summary").textContent = current ? `来源：${current.filename}｜状态：${current.status}｜问题/提示：${current.errors.length} 条` : "暂无批次，请导入 Excel 快照";
  await loadJobs();
  await loadMetrics();
}

async function loadJobs() {
  const jobs = state.batchId ? await api(`/api/jobs?batch_id=${encodeURIComponent(state.batchId)}`) : [];
  const select = $("#job-select");
  select.innerHTML = jobs.map((item) => `<option value="${esc(item.job_id)}">${esc(item.job_id)} · ${esc(item.job_title)} · ${esc(item.employer_name)}</option>`).join("");
  state.jobId = jobs[0]?.job_id || "";
  await loadMatches();
}

async function loadMatches() {
  if (!state.batchId || !state.jobId) { renderMatches([]); return; }
  const rows = await api(`/api/matches?batch_id=${encodeURIComponent(state.batchId)}&job_id=${encodeURIComponent(state.jobId)}`);
  renderMatches(rows);
}

function renderMatches(rows) {
  $("#result-count").textContent = `${rows.length} 人`;
  const body = $("#match-rows");
  if (!rows.length) { body.innerHTML = '<tr><td colspan="7" class="empty">尚未生成该岗位的匹配结果</td></tr>'; return; }
  body.innerHTML = rows.map((row) => {
    const positives = (row.explanation.positives || []).join("；") || "—";
    const conflicts = (row.explanation.conflicts || []).join("；") || "无明显冲突";
    const review = row.review_decision || "未审核";
    const feedback = row.feedback_outcome || "未反馈";
    const matchId = esc(row.match_id);
    const reviewButtons = state.role === "reviewer" ? `<div class="action-stack"><button data-review="accepted" data-id="${matchId}" class="secondary">通过</button><button data-review="needs_review" data-id="${matchId}" class="ghost">待复核</button><button data-review="rejected" data-id="${matchId}" class="danger">驳回</button></div>` : "";
    return `<tr><td>${esc(row.rank_no)}</td><td><strong>${esc(row.person_id)}</strong><br><small>${esc((row.skills || []).join("、"))}</small></td><td><strong class="score">${esc(row.score)}</strong><br><small>规则 ${esc(row.rule_score)} / 语义 ${esc(row.semantic_score)}</small></td><td>${esc(positives)}</td><td>${esc(conflicts)}</td><td>${esc(review)}<br>${reviewButtons}</td><td>${esc(feedback)}<br><div class="action-stack"><button data-feedback="effective" data-id="${matchId}" class="secondary">有效</button><button data-feedback="ineffective" data-id="${matchId}" class="danger">无效</button><button data-feedback="follow_up" data-id="${matchId}" class="ghost">跟进</button></div></td></tr>`;
  }).join("");
}

async function loadMetrics() {
  const metrics = state.batchId ? await api(`/api/metrics?batch_id=${encodeURIComponent(state.batchId)}`) : {};
  $("#metric-matches").textContent = metrics.matches || 0;
  $("#metric-review").textContent = percent(metrics.review_rate);
  $("#metric-feedback").textContent = percent(metrics.feedback_completion_rate);
  $("#metric-acceptance").textContent = percent(metrics.acceptance_rate);
}

async function loadPlugins() {
  const plugins = await api("/api/plugins");
  $("#plugin-list").innerHTML = plugins.map((item) => `<article class="plugin"><div class="plugin-head"><strong>${esc(item.name)}</strong><span class="status-${esc(item.state)}">${esc(item.state)}</span></div><p>${esc(item.description)}</p><p>提供：${esc(item.provides.join(", "))}</p></article>`).join("");
}

$("#batch-select").addEventListener("change", async (event) => { state.batchId = event.target.value; await loadBatches(state.batchId); });
$("#job-select").addEventListener("change", async (event) => { state.jobId = event.target.value; await loadMatches(); });

$("#import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("#xlsx-file").files[0];
  if (!file) return;
  const data = new FormData(); data.append("file", file);
  try { const result = await api("/api/import", { method: "POST", body: data }); notice(`批次 ${result.batch_id}：${result.status}`); await loadBatches(result.batch_id); }
  catch (error) { notice(error.message, true); }
});

$("#run-match").addEventListener("click", async () => {
  if (!state.batchId || !state.jobId) { notice("请先选择有效批次和岗位", true); return; }
  try {
    const rows = await api("/api/matches/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ batch_id: state.batchId, job_id: state.jobId, top_n: Number($("#top-n").value || 10) }) });
    renderMatches(rows); await loadMetrics(); notice(`已生成 ${rows.length} 条候选结果`);
  } catch (error) { notice(error.message, true); }
});

$("#export").addEventListener("click", () => {
  if (!state.batchId || !state.jobId) { notice("请先选择岗位", true); return; }
  window.location.href = `/api/export?batch_id=${encodeURIComponent(state.batchId)}&job_id=${encodeURIComponent(state.jobId)}`;
});

$("#match-rows").addEventListener("click", async (event) => {
  const button = event.target.closest("button"); if (!button) return;
  try {
    if (button.dataset.review) {
      const reason = button.dataset.review === "accepted" ? "" : (window.prompt("请填写理由（必填）") || "");
      if (button.dataset.review !== "accepted" && !reason) return;
      await api("/api/reviews", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ match_id: button.dataset.id, decision: button.dataset.review, reason }) });
    }
    if (button.dataset.feedback) {
      const reason = window.prompt("可填写反馈说明（选填）") || "";
      await api("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ match_id: button.dataset.id, outcome: button.dataset.feedback, reason }) });
    }
    await loadMatches(); await loadMetrics(); notice("记录已保存");
  } catch (error) { notice(error.message, true); }
});

Promise.all([loadBatches(), loadPlugins()]).catch((error) => notice(error.message, true));
