const state = {
  batchId: "",
  jobId: "",
  role: document.querySelector("main")?.dataset.role || "operator",
  llm: null,
  noticeTimer: null,
};

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
  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("请先登录");
  }
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    throw new Error((body && body.detail) || body || `请求失败：${response.status}`);
  }
  return body;
}

function notice(message, error = false) {
  const box = $("#notice");
  window.clearTimeout(state.noticeTimer);
  box.textContent = message;
  box.classList.remove("hidden", "error");
  if (error) box.classList.add("error");
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  state.noticeTimer = window.setTimeout(() => box.classList.add("hidden"), 6500);
}

function percent(value) {
  return `${Math.round((Number(value) || 0) * 100)}%`;
}

function setBusy(button, busy, busyLabel) {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = busyLabel;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  } else {
    button.textContent = button.dataset.label || button.textContent;
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

function renderTags(items, className = "") {
  return (items || [])
    .filter(Boolean)
    .slice(0, 4)
    .map((item) => `<span class="mini-tag ${className}">${esc(item)}</span>`)
    .join("");
}

async function loadLlmStatus() {
  const status = await api("/api/llm/status");
  state.llm = status;
  const card = $("#llm-status-card");
  const badge = $("#llm-state-badge");
  const routeStrip = $("#model-route");
  card.classList.remove("loading");
  routeStrip.classList.remove("loading", "warning");
  badge.classList.remove("neutral", "ready", "warning");

  $("#llm-route-name").textContent = `${status.provider} / ${status.model}`;
  if (status.configured) {
    badge.textContent = "LLM 已启用";
    badge.classList.add("ready");
    $("#llm-route-detail").textContent = `规则召回后复排 ${status.candidate_limit} 人 · 权重 ${Math.round(status.weight * 100)}%`;
    $("#model-route-title").textContent = `真实模型复排：${status.provider} / ${status.model}`;
    $("#model-route-copy").textContent = `复排权重 ${Math.round(status.weight * 100)}%，失败时明确报错且不覆盖旧结果`;
    $("#run-match span").textContent = "生成 AI Top10";
  } else {
    badge.textContent = "未配置密钥";
    badge.classList.add("warning");
    routeStrip.classList.add("warning");
    $("#llm-route-detail").textContent = "当前仅运行规则 + 本地文本相似度基线";
    $("#model-route-title").textContent = "大模型未启用：当前是规则基线";
    $("#model-route-copy").textContent = "服务端设置 LLM_API_KEY 后重启即可启用真实复排";
    $("#run-match span").textContent = "生成规则 Top10";
  }
}

async function loadBatches(prefer) {
  const batches = await api("/api/batches");
  const select = $("#batch-select");
  if (!batches.length) {
    select.innerHTML = '<option value="">暂无批次，请先导入数据</option>';
    select.disabled = true;
    state.batchId = "";
  } else {
    select.disabled = false;
    select.innerHTML = batches.map((item) => (
      `<option value="${esc(item.batch_id)}">${esc(item.batch_id)} · ${esc(item.person_count)} 人 / ${esc(item.job_count)} 岗</option>`
    )).join("");
    state.batchId = prefer && batches.some((item) => item.batch_id === prefer)
      ? prefer
      : batches[0].batch_id;
    select.value = state.batchId;
  }

  const current = batches.find((item) => item.batch_id === state.batchId);
  const summary = $("#batch-summary");
  summary.classList.remove("loading-block");
  if (current) {
    summary.innerHTML = `<div class="batch-facts">
      <span><small>数据来源</small><strong title="${esc(current.filename)}">${esc(current.filename)}</strong></span>
      <span><small>质量状态</small><strong>${esc(current.status === "ready" ? "校验通过" : current.status)}</strong></span>
      <span><small>校验记录</small><strong>${esc(current.errors.length)} 条</strong></span>
    </div>`;
  } else {
    summary.textContent = "暂无数据批次，请导入 Excel 快照。";
  }
  await loadJobs();
  await loadMetrics();
}

async function loadJobs() {
  const jobs = state.batchId
    ? await api(`/api/jobs?batch_id=${encodeURIComponent(state.batchId)}`)
    : [];
  const select = $("#job-select");
  if (!jobs.length) {
    select.innerHTML = '<option value="">当前批次没有有效岗位</option>';
    select.disabled = true;
    state.jobId = "";
  } else {
    select.disabled = false;
    select.innerHTML = jobs.map((item) => (
      `<option value="${esc(item.job_id)}">${esc(item.job_title)} · ${esc(item.employer_name)} · ${esc(item.region)}</option>`
    )).join("");
    state.jobId = jobs[0].job_id;
  }
  await loadMatches();
}

async function loadMatches() {
  if (!state.batchId || !state.jobId) {
    renderMatches([]);
    return;
  }
  const rows = await api(
    `/api/matches?batch_id=${encodeURIComponent(state.batchId)}&job_id=${encodeURIComponent(state.jobId)}`,
  );
  renderMatches(rows);
}

function reviewActions(matchId) {
  if (state.role !== "reviewer") return "";
  return `<div class="action-stack">
    <button data-review="accepted" data-id="${matchId}" class="button success">通过</button>
    <button data-review="needs_review" data-id="${matchId}" class="button warning">待复核</button>
    <button data-review="rejected" data-id="${matchId}" class="button danger">驳回</button>
  </div>`;
}

function feedbackActions(matchId) {
  return `<div class="action-stack">
    <button data-feedback="effective" data-id="${matchId}" class="button success">有效</button>
    <button data-feedback="follow_up" data-id="${matchId}" class="button warning">跟进</button>
    <button data-feedback="ineffective" data-id="${matchId}" class="button danger">无效</button>
  </div>`;
}

const decisionLabels = {
  accepted: "已通过",
  needs_review: "待复核",
  rejected: "已驳回",
  effective: "反馈有效",
  ineffective: "反馈无效",
  follow_up: "待跟进",
};

function renderMatches(rows) {
  $("#result-count").textContent = `${rows.length} 人`;
  const body = $("#match-rows");
  if (!rows.length) {
    $("#result-model").textContent = "尚未运行";
    body.innerHTML = '<tr><td colspan="6" class="empty"><strong>尚无当前岗位的候选结果</strong><span>确认批次和岗位后，点击匹配按钮生成结果</span></td></tr>';
    return;
  }

  const firstProvenance = rows[0].explanation?.provenance || {};
  $("#result-model").textContent = firstProvenance.llm_used
    ? `${firstProvenance.provider} / ${firstProvenance.model}`
    : "规则 + 本地基线";

  body.innerHTML = rows.map((row) => {
    const explanation = row.explanation || {};
    const provenance = explanation.provenance || {};
    const score = Math.max(0, Math.min(100, Number(row.score) || 0));
    const positives = renderTags(explanation.positives, "positive");
    const risks = renderTags(explanation.conflicts, "risk");
    const questions = renderTags(explanation.review_questions, "question");
    const review = row.review_decision || "unreviewed";
    const feedback = row.feedback_outcome || "unreported";
    const matchId = esc(row.match_id);
    const skillTags = renderTags((row.skills || []).slice(0, 3));
    const source = provenance.llm_used
      ? `LLM ${esc(provenance.provider)} / ${esc(provenance.model)}`
      : "未调用 LLM · 本地基线";
    return `<tr>
      <td><div class="candidate-cell"><span class="rank-number">${esc(row.rank_no)}</span><div><strong class="candidate-name">候选 ${esc(row.person_id)}</strong><div class="skill-list">${skillTags || '<span class="mini-tag">技能待补充</span>'}</div></div></div></td>
      <td><div class="score-value"><strong>${esc(score.toFixed(1))}</strong><span>/ 100</span></div><div class="score-track"><span style="width:${score}%"></span></div><div class="score-detail">规则 ${esc(row.rule_score)} · 语义 ${esc(row.semantic_score)}</div></td>
      <td><p class="explanation-summary">${esc(explanation.summary || "暂无模型摘要")}</p><div class="evidence-list">${positives || '<span class="mini-tag">暂无正向证据</span>'}</div><span class="provenance">${source}</span></td>
      <td><div class="evidence-list">${risks || '<span class="mini-tag positive">无明显硬性冲突</span>'}</div>${questions ? `<div class="evidence-list">${questions}</div>` : ""}</td>
      <td><span class="decision-badge ${esc(review)}">${esc(decisionLabels[review] || "未审核")}</span>${reviewActions(matchId)}</td>
      <td><span class="decision-badge ${esc(feedback)}">${esc(decisionLabels[feedback] || "未反馈")}</span>${feedbackActions(matchId)}</td>
    </tr>`;
  }).join("");
}

async function loadMetrics() {
  const metrics = state.batchId
    ? await api(`/api/metrics?batch_id=${encodeURIComponent(state.batchId)}`)
    : {};
  $("#metric-matches").textContent = metrics.matches || 0;
  $("#metric-review").textContent = percent(metrics.review_rate);
  $("#metric-feedback").textContent = percent(metrics.feedback_completion_rate);
  $("#metric-acceptance").textContent = percent(metrics.acceptance_rate);
}

async function loadPlugins() {
  const plugins = await api("/api/plugins");
  const stateLabels = {
    enabled: "运行中",
    degraded: "待配置",
    disabled: "已停用",
    failed: "异常",
  };
  $("#plugin-list").innerHTML = plugins.map((item) => (
    `<article class="plugin"><div class="plugin-head"><strong>${esc(item.name)}</strong><span class="status-${esc(item.state)}">${esc(stateLabels[item.state] || item.state)}</span></div><p>${esc(item.description)}</p><p class="plugin-capability">能力：${esc(item.provides.join(", "))}</p></article>`
  )).join("");
}

$("#xlsx-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  $("#file-name").textContent = file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)}MB` : "仅支持 .xlsx，最大 10MB";
});

$("#batch-select").addEventListener("change", async (event) => {
  state.batchId = event.target.value;
  await loadBatches(state.batchId);
});

$("#job-select").addEventListener("change", async (event) => {
  state.jobId = event.target.value;
  await loadMatches();
});

$("#import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = $("#xlsx-file").files[0];
  if (!file) return;
  const button = $("#import-button");
  const data = new FormData();
  data.append("file", file);
  setBusy(button, true, "正在校验…");
  try {
    const result = await api("/api/import", { method: "POST", body: data });
    notice(`批次 ${result.batch_id} 已完成校验，状态：${result.status}`);
    await loadBatches(result.batch_id);
  } catch (error) {
    notice(error.message, true);
  } finally {
    setBusy(button, false);
  }
});

$("#run-match").addEventListener("click", async () => {
  if (!state.batchId || !state.jobId) {
    notice("请先选择有效的数据批次和目标岗位", true);
    return;
  }
  const button = $("#run-match");
  const busyLabel = state.llm?.configured ? "大模型复排中…" : "规则计算中…";
  setBusy(button, true, busyLabel);
  try {
    const rows = await api("/api/matches/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        batch_id: state.batchId,
        job_id: state.jobId,
        top_n: Number($("#top-n").value || 10),
      }),
    });
    renderMatches(rows);
    await loadMetrics();
    const mode = rows[0]?.explanation?.provenance?.llm_used ? "大模型语义复排" : "规则基线";
    notice(`已通过${mode}生成 ${rows.length} 条候选结果`);
  } catch (error) {
    notice(error.message, true);
  } finally {
    setBusy(button, false);
  }
});

$("#export").addEventListener("click", () => {
  if (!state.batchId || !state.jobId) {
    notice("请先选择岗位", true);
    return;
  }
  window.location.href = `/api/export?batch_id=${encodeURIComponent(state.batchId)}&job_id=${encodeURIComponent(state.jobId)}`;
});

$("#match-rows").addEventListener("click", async (event) => {
  const button = event.target.closest("button");
  if (!button) return;
  setBusy(button, true, "保存中…");
  try {
    if (button.dataset.review) {
      const reason = button.dataset.review === "accepted"
        ? ""
        : (window.prompt("请填写审核理由（必填）") || "").trim();
      if (button.dataset.review !== "accepted" && !reason) return;
      await api("/api/reviews", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          match_id: button.dataset.id,
          decision: button.dataset.review,
          reason,
        }),
      });
    }
    if (button.dataset.feedback) {
      const reason = (window.prompt("可填写业务反馈说明（选填）") || "").trim();
      await api("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          match_id: button.dataset.id,
          outcome: button.dataset.feedback,
          reason,
        }),
      });
    }
    await loadMatches();
    await loadMetrics();
    notice("记录已保存");
  } catch (error) {
    notice(error.message, true);
  } finally {
    setBusy(button, false);
  }
});

Promise.all([loadLlmStatus(), loadBatches(), loadPlugins()])
  .catch((error) => notice(error.message, true));
