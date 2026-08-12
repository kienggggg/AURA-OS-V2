// interface/web/app.js
// Dashboard Xưởng Kiếm Tiền — vanilla JS, không dependency. Poll /api/jobs mỗi 2s
// để hiện tiến độ live (đơn giản hơn WebSocket riêng cho dashboard; đủ nhanh cho
// job dài hàng chục phút).

const STATE_LABELS = {
  queued: "Đang chờ", running: "Đang chạy", done: "Xong",
  needs_review: "Cần duyệt", failed: "Lỗi", cancelled: "Đã hủy",
};

const HIRE_STATUS_LABELS = {
  needs_source: "thiếu nguồn", research_needed: "cần xác minh",
  needs_owner_approval: "chờ duyệt", approved_to_submit: "sẵn sàng nộp",
  submitted: "đã nộp", replied: "khách phản hồi", interview: "phỏng vấn",
  won: "trúng việc", delivering: "đang làm", delivered: "đã bàn giao",
  invoiced: "đã báo giá/invoice", paid: "đã nhận tiền", lost: "không thành",
  not_pursued: "không theo đuổi",
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, ch => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[ch]));
}

function safeActionUrl(value) {
  const url = String(value || "").trim();
  return url.startsWith("/") || /^https?:\/\//i.test(url) ? url : "";
}

function switchTab(tab) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.toggle("active", p.id === `tab-${tab}`));
}

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

function fieldHtml(tool, field) {
  const id = `f_${tool.name}_${field.key}`;
  const req = field.required ? "required" : "";
  let input;
  if (field.type === "textarea") {
    input = `<textarea id="${id}" name="${field.key}" placeholder="${field.placeholder || ""}" ${req}>${field.default || ""}</textarea>`;
  } else if (field.type === "select") {
    const opts = (field.choices || []).map(c => `<option value="${c}">${c}</option>`).join("");
    input = `<select id="${id}" name="${field.key}">${opts}</select>`;
  } else if (field.type === "checkbox") {
    input = `<input type="checkbox" id="${id}" name="${field.key}" ${field.default ? "checked" : ""}>`;
  } else {
    const t = field.type === "number" ? "number" : "text";
    input = `<input type="${t}" id="${id}" name="${field.key}" value="${field.default ?? ""}" placeholder="${field.placeholder || ""}" ${req}>`;
  }
  return `<div class="field"><label for="${id}">${field.label}</label>${input}</div>`;
}

function toolCardHtml(tool) {
  const badges = [
    tool.experimental ? `<span class="badge exp">THÍ NGHIỆM</span>` : "",
    !tool.enabled ? `<span class="badge off">Sắp có</span>` : "",
  ].join("");
  const fields = tool.form_fields.map(f => fieldHtml(tool, f)).join("");
  const btnDisabled = tool.enabled ? "" : "disabled";
  const btnClass = tool.enabled ? "run-btn" : "run-btn disabled-tool";
  return `
    <div class="tool-card" data-tool="${tool.name}">
      <h3>${tool.label_vi}${badges}</h3>
      <p class="desc">${tool.description}</p>
      <form onsubmit="return submitTool(event, '${tool.name}')">
        ${fields}
        <button type="submit" class="${btnClass}" ${btnDisabled}>Chạy</button>
      </form>
    </div>`;
}

async function loadTools() {
  const res = await fetch("/api/tools");
  const tools = await res.json();
  const el = document.getElementById("tools-list");
  el.innerHTML = tools.length
    ? tools.map(toolCardHtml).join("")
    : `<div class="empty-hint">Chưa có tool nào đăng ký.</div>`;
}

async function submitTool(evt, toolName) {
  evt.preventDefault();
  const form = evt.target;
  const data = new FormData(form);
  const params = {};
  for (const [k, v] of data.entries()) params[k] = v;
  // Checkbox không tick thì FormData bỏ qua field -> tự bổ sung false.
  form.querySelectorAll('input[type="checkbox"]').forEach(cb => { params[cb.name] = cb.checked; });

  const res = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool: toolName, params }),
  });
  if (res.ok) {
    switchTab("queue");
    refreshJobs();
  } else {
    const err = await res.json().catch(() => ({}));
    alert(`Không chạy được: ${err.error || res.statusText}`);
  }
  return false;
}

function jobRowHtml(job) {
  const stateLabel = STATE_LABELS[job.state] || job.state;
  const cancelable = job.state === "queued" || job.state === "running";
  const hasQc = !!job.qc_path;
  return `
    <tr data-job="${job.id}">
      <td><code>${job.id}</code></td>
      <td>${job.tool}</td>
      <td><span class="state-tag state-${job.state}">${stateLabel}</span></td>
      <td>
        <div class="progress-bar"><div style="width:${job.progress}%"></div></div>
      </td>
      <td>${job.step}${job.error ? ` — <span style="color:var(--err)">${job.error}</span>` : ""}</td>
      <td>
        ${cancelable ? `<button class="cancel-btn" onclick="cancelJob('${job.id}')">Hủy</button>` : ""}
        ${hasQc ? `<button class="cancel-btn" style="border-color:var(--accent);color:var(--accent)" onclick="showQc('${job.id}')">QC</button>` : ""}
      </td>
    </tr>`;
}

async function showQc(jobId) {
  const res = await fetch(`/api/jobs/${jobId}/qc`);
  const el = document.getElementById("qc-detail");
  if (!res.ok) { el.innerHTML = ""; return; }
  const qc = await res.json();
  const rows = (qc.checks || []).map(c =>
    `<tr><td>${c.ok ? "✅" : "❌"}</td><td>${c.name}</td><td>${c.note || ""}</td></tr>`).join("");
  el.innerHTML = `
    <div class="tool-card" style="margin-top:16px">
      <h3>QC job ${jobId} — ${qc.passed ? "ĐẠT" : "CẦN XEM LẠI"}</h3>
      <table><tbody>${rows}</tbody></table>
    </div>`;
}

// ---- Sổ thu nhập ----
function fmtMoney(v) { return Number(v).toLocaleString("vi-VN"); }

async function refreshIncome() {
  const res = await fetch("/api/ledger/income");
  if (!res.ok) return;
  const data = await res.json();
  const s = data.summary;
  document.getElementById("income-month").textContent = `Tổng tháng ${s.month}`;
  const by = Object.entries(s.by_product_line)
    .map(([k, v]) => `${k}: ${fmtMoney(v)}`).join(" · ") || "chưa có";
  document.getElementById("income-summary").innerHTML =
    `<p>Về: <b style="color:var(--ok)">${fmtMoney(s.total_in)} ${s.currency}</b>
     — Chi: <b style="color:var(--err)">${fmtMoney(s.total_out)}</b>
     — Ròng: <b>${fmtMoney(s.net)}</b></p><p class="desc">${by}</p>`;
  document.getElementById("income-tbody").innerHTML = data.entries.map(r => `
    <tr>
      <td>${new Date(r.ts * 1000).toLocaleDateString("vi-VN")}</td>
      <td>${r.item}</td>
      <td>${r.product_line}</td>
      <td style="color:${r.direction === "out" ? "var(--err)" : "var(--ok)"}">
        ${r.direction === "out" ? "-" : "+"}${fmtMoney(r.amount)}</td>
      <td>${r.note || ""}</td>
    </tr>`).join("") || `<tr><td colspan="5" class="empty-hint">Sổ trống.</td></tr>`;
}

async function submitIncome(evt) {
  evt.preventDefault();
  const data = new FormData(evt.target);
  let amount = Number(data.get("amount"));
  const body = {
    item: data.get("item"), product_line: data.get("product_line"),
    note: data.get("note"), amount: Math.abs(amount),
    direction: amount < 0 ? "out" : "in",
  };
  const res = await fetch("/api/ledger/income", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) { evt.target.reset(); refreshIncome(); }
  else alert("Ghi sổ lỗi");
  return false;
}

// ---- Dòng tiền: báo có được đối soát trước khi cộng vào sổ thu nhập ----
const CASHFLOW_LABELS = {
  observed: "chờ đối soát", confirmed: "đã ghi sổ", ignored: "đã bỏ qua",
};

function cashflowMoney(event) {
  const amount = `${fmtMoney(event.amount)} ${escapeHtml(event.currency || "VND")}`;
  return `<span style="color:var(--ok)">+${amount}</span>`;
}

function cashflowActions(event) {
  if (event.status !== "observed") return "";
  const id = escapeHtml(event.id);
  return `<button class="cancel-btn hire-approve" onclick="confirmCashflow('${id}')">Xác nhận tiền về</button>
    <button class="cancel-btn" onclick="ignoreCashflow('${id}')">Bỏ qua</button>`;
}

async function refreshCashflow() {
  const res = await fetch("/api/cashflow");
  if (!res.ok) return;
  const data = await res.json();
  const s = data.summary || {};
  const sum = obj => Object.entries(obj || {}).map(([c, amount]) => `${fmtMoney(amount)} ${escapeHtml(c)}`).join(" · ") || "0";
  document.getElementById("cashflow-summary").innerHTML =
    `<p>Chờ đối soát: <b style="color:var(--warn)">${s.pending_count || 0} giao dịch · ${sum(s.pending_by_currency)}</b>
      — Đã ghi sổ: <b style="color:var(--ok)">${s.confirmed_count || 0} giao dịch · ${sum(s.confirmed_by_currency)}</b></p>`;
  const events = data.events || [];
  document.getElementById("cashflow-tbody").innerHTML = events.length
    ? events.map(event => `<tr>
      <td>${new Date((event.received_at || event.created_at) * 1000).toLocaleString("vi-VN")}</td>
      <td>${escapeHtml(event.source || "—")}</td>
      <td>${escapeHtml(event.description || "Báo có ngân hàng")}</td>
      <td>${cashflowMoney(event)}</td>
      <td><span class="state-tag state-${escapeHtml(event.status)}">${escapeHtml(CASHFLOW_LABELS[event.status] || event.status)}</span></td>
      <td>${cashflowActions(event)}</td>
    </tr>`).join("")
    : `<tr><td colspan="6" class="empty-hint">Chưa có báo có nào. Khi kết nối nguồn ngân hàng, AURA sẽ báo qua loa và hiện ở đây.</td></tr>`;
}

async function confirmCashflow(eventId) {
  if (!confirm("Bạn xác nhận tiền đã thật sự về tài khoản? AURA sẽ ghi vào sổ thu nhập.")) return;
  const res = await fetch(`/api/cashflow/${encodeURIComponent(eventId)}/confirm`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed_by_owner: true, product_line: "khac" }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.error || "Không đối soát được báo có.");
    return;
  }
  refreshCashflow();
  refreshIncome();
}

async function ignoreCashflow(eventId) {
  if (!confirm("Bỏ qua báo có này? AURA sẽ không ghi doanh thu.")) return;
  const res = await fetch(`/api/cashflow/${encodeURIComponent(eventId)}/ignore`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed_by_owner: true }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.error || "Không bỏ qua được báo có.");
    return;
  }
  refreshCashflow();
}

// ---- Rải CV ----
async function refreshCv() {
  const res = await fetch("/api/applications");
  if (!res.ok) return;
  const rows = await res.json();
  document.getElementById("cv-tbody").innerHTML = rows.map(r => `
    <tr>
      <td>${new Date(r.ts * 1000).toLocaleDateString("vi-VN")}</td>
      <td>${r.title || ""}</td>
      <td><span class="state-tag state-${r.status === "applied" ? "running" : "queued"}">${r.status}</span></td>
      <td>${r.url ? `<a href="${r.url}" target="_blank" style="color:var(--accent)">mở</a>` : ""}</td>
    </tr>`).join("") || `<tr><td colspan="4" class="empty-hint">Chưa ứng tuyển gì.</td></tr>`;
}

// ---- Work-for-hire: AURA chuẩn bị, Sếp là người duy nhất gửi/xác nhận tiền ----
function hireButtons(deal) {
  const id = escapeHtml(deal.id);
  const btn = (label, status, css = "") =>
    `<button class="cancel-btn ${css}" onclick="advanceHireDeal('${id}', '${status}')">${label}</button>`;
  switch (deal.status) {
    case "needs_source":
    case "research_needed": return btn("Đã xác minh nguồn", "needs_owner_approval");
    case "needs_owner_approval": return btn("Duyệt để tự nộp", "approved_to_submit", "hire-approve");
    case "approved_to_submit": return btn("Tôi đã tự nộp", "submitted", "hire-approve");
    case "submitted": return `${btn("Có phản hồi", "replied")} ${btn("Trúng việc", "won", "hire-approve")}`;
    case "replied": return `${btn("Hẹn phỏng vấn", "interview")} ${btn("Trúng việc", "won", "hire-approve")}`;
    case "interview": return btn("Trúng việc", "won", "hire-approve");
    case "won": return btn("Bắt đầu làm", "delivering");
    case "delivering": return btn("Đã bàn giao", "delivered");
    case "delivered": return btn("Đã gửi invoice", "invoiced");
    case "invoiced": return btn("Tiền đã về", "paid", "hire-paid");
    default: return "";
  }
}

function outputArtifactLink(artifact) {
  const normalized = String(artifact || "").replaceAll("\\", "/");
  const marker = "/data/outputs/";
  const at = normalized.toLowerCase().lastIndexOf(marker);
  if (at < 0) return "—";
  const relative = normalized.slice(at + marker.length)
    .split("/").filter(Boolean).map(encodeURIComponent).join("/");
  return `<a href="/files/outputs/${relative}" target="_blank" style="color:var(--accent)">mở hồ sơ</a>`;
}

async function advanceHireDeal(dealId, status) {
  const body = { status };
  if (status === "needs_owner_approval") {
    const url = prompt("Dán URL tin tuyển dụng đã tự kiểm tra:");
    if (!url) return;
    body.url = url;
    body.confirmed_by_owner = true;
  }
  if (status === "submitted") {
    if (!confirm("Bạn đã tự gửi hồ sơ trên nền tảng? AURA sẽ chỉ ghi sổ, không gửi gì cả.")) return;
    body.confirmed_by_owner = true;
  }
  if (status === "paid") {
    const amount = prompt("Số tiền thực đã nhận:");
    if (!amount || Number(amount) <= 0) return;
    const currency = prompt("Đơn vị tiền (VND hoặc USD):", "VND") || "VND";
    if (!confirm("Xác nhận tiền đã về tài khoản?")) return;
    body.confirmed_by_owner = true;
    body.amount = Number(amount);
    body.currency = currency;
  }
  const res = await fetch(`/api/work-for-hire/${encodeURIComponent(dealId)}/status`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.error || "Không cập nhật được trạng thái.");
    return;
  }
  refreshWorkForHire();
}

async function refreshWorkForHire() {
  const res = await fetch("/api/work-for-hire");
  if (!res.ok) return;
  const data = await res.json();
  const s = data.summary || {};
  const paid = Object.entries(s.paid_by_currency || {})
    .map(([currency, amount]) => `${fmtMoney(amount)} ${escapeHtml(currency)}`).join(" · ") || "0";
  document.getElementById("workforhire-summary").innerHTML =
    `<p>Đang mở: <b>${s.open || 0}</b> · Chờ duyệt: <b>${s.needs_owner || 0}</b> · ` +
    `Sẵn sàng nộp: <b>${s.ready_to_submit || 0}</b> · Đã nộp: <b>${s.submitted || 0}</b> · ` +
    `Trúng việc: <b>${s.won || 0}</b> · Đã nhận: <b style="color:var(--ok)">${paid}</b></p>`;

  const actions = data.actions || [];
  document.getElementById("workforhire-actions").innerHTML = actions.length
    ? `<ol class="action-list">${actions.map(d => `<li><b>${escapeHtml(d.title)}</b> — ${escapeHtml(d.next_action)}</li>`).join("")}</ol>`
    : `<p class="empty-hint">Chưa có cơ hội nào cần bạn xử lý.</p>`;

  const deals = data.deals || [];
  document.getElementById("workforhire-tbody").innerHTML = deals.length
    ? deals.map(d => {
      const link = d.url ? `<a href="${escapeHtml(d.url)}" target="_blank" rel="noopener" style="color:var(--accent)">tin gốc</a>` : "—";
      const artifact = outputArtifactLink(d.artifact);
      return `<tr><td><b>${escapeHtml(d.title)}</b><br><small>${link}</small></td>` +
        `<td>${escapeHtml(d.fit_score || 0)}/100</td><td><span class="state-tag state-${escapeHtml(d.status)}">${escapeHtml(HIRE_STATUS_LABELS[d.status] || d.status)}</span></td>` +
        `<td>${artifact}</td><td>${hireButtons(d)}</td></tr>`;
    }).join("")
    : `<tr><td colspan="5" class="empty-hint">AURA chưa có hồ sơ từ một tin việc đã xác minh.</td></tr>`;
}

// ---- Hộp 1%: tiền cần đối soát -> proposal cần gửi -> nội dung cần đăng tay ----
async function refreshActionBox() {
  const res = await fetch("/api/action-box");
  if (!res.ok) return;
  const data = await res.json();
  const summary = data.summary || {};
  const byType = summary.by_type || {};
  document.getElementById("actionbox-summary").innerHTML =
    `<p>Đang chờ: <b style="color:var(--warn)">${summary.pending || 0}</b> · ` +
    `Báo có: <b>${byType.cashflow_confirmation || 0}</b> · ` +
    `Proposal: <b>${byType.proposal || 0}</b> · ` +
    `Đăng tay: <b>${byType.manual_publish || 0}</b></p>`;

  const priorityLabels = { 0: "Ngay", 1: "Sớm", 2: "Khi thuận tiện" };
  const typeLabels = {
    cashflow_confirmation: "Đối soát tiền",
    proposal: "Gửi proposal",
    manual_publish: "Đăng nội dung",
  };
  const items = data.items || [];
  document.getElementById("actionbox-tbody").innerHTML = items.length
    ? items.map(item => {
      const artifactUrl = safeActionUrl(item.artifact_url);
      const publishUrl = safeActionUrl(item.publish_url);
      const artifact = artifactUrl
        ? `<a href="${escapeHtml(artifactUrl)}" target="_blank" rel="noopener" style="color:var(--accent)">xem file</a>`
        : "—";
      const open = publishUrl
        ? `<a href="${escapeHtml(publishUrl)}" target="_blank" rel="noopener" class="run-btn" style="display:inline-block;text-decoration:none">Mở xử lý</a>`
        : "—";
      return `<tr><td>${escapeHtml(priorityLabels[item.priority] || item.priority)}</td>` +
        `<td>${escapeHtml(typeLabels[item.type] || item.type)}</td>` +
        `<td><b>${escapeHtml(item.title)}</b></td><td>${escapeHtml(item.action)}</td>` +
        `<td>${artifact}</td><td>${open}</td></tr>`;
    }).join("")
    : `<tr><td colspan="6" class="empty-hint">Không có việc 1% nào đang chờ bạn.</td></tr>`;
}

// ---- Desktop Autopilot: một lần bật, tự chạy trong các phạm vi cục bộ ít rủi ro ----
let desktopAutopilotStatus = {};

function desktopStateLabel(status) {
  if (status.emergency_stop) return "ĐÃ DỪNG KHẨN CẤP";
  if (!status.owner_enabled) return "CHƯA BẬT";
  if (status.paused) return "ĐANG TẠM DỪNG";
  if (status.runtime_enabled) return "ĐANG TỰ HOẠT ĐỘNG";
  return "CHỜ AURA KHỞI ĐỘNG";
}

async function refreshDesktopAutopilot() {
  const [statusRes, contextRes] = await Promise.all([
    fetch("/api/desktop-autopilot"),
    fetch("/api/desktop-autopilot/context"),
  ]);
  if (!statusRes.ok) return;
  const status = await statusRes.json();
  desktopAutopilotStatus = status;
  const counts = status.task_counts || {};
  document.getElementById("desktopauto-summary").innerHTML =
    `<div class="desktop-status-grid">` +
    `<div>Trạng thái<b>${escapeHtml(desktopStateLabel(status))}</b></div>` +
    `<div>Cửa sổ gần nhất<b>${escapeHtml(status.last_window || "chưa quan sát")}</b></div>` +
    `<div>Phân loại<b>${escapeHtml(status.last_window_category || "unknown")}</b></div>` +
    `<div>Hàng đợi<b>${counts.queued || 0} chờ · ${counts.running || 0} đang chạy</b></div>` +
    `<div>Phạm vi đã cấp<b>${escapeHtml((status.approved_scopes || []).join(", "))}</b></div>` +
    `<div>Ảnh lưu xuống đĩa<b>${status.screenshot_retention ? "có" : "không"}</b></div>` +
    `</div>`;

  if (contextRes.ok) {
    const context = await contextRes.json();
    const self = context.self || {};
    const memory = context.memory || {};
    document.getElementById("desktopauto-context").innerHTML =
      `<div class="desktop-status-grid">` +
      `<div>Tệp AURA đọc được<b>${self.source_file_count || 0}</b></div>` +
      `<div>Tài liệu lõi đã nạp<b>${self.readable_file_count || 0}</b></div>` +
      `<div>Bộ nhớ AI<b>${memory.connected ? "đã nối" : "chưa nối"}</b></div>` +
      `<div>Mẩu nhớ tìm thấy<b>${memory.record_count || 0}</b></div>` +
      `</div>`;
  }
}

async function controlDesktopAutopilot(action) {
  const message = action === "emergency_stop"
    ? "Dừng ngay mọi tác vụ màn hình của AURA?"
    : "Xác nhận đổi trạng thái tự thao tác của AURA?";
  if (!confirm(message)) return;
  const res = await fetch("/api/desktop-autopilot/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action, confirmed_by_owner: true }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.error || "Không đổi được trạng thái tự thao tác.");
    return;
  }
  await refreshDesktopAutopilot();
}

async function toggleDesktopAutopilotPause() {
  await controlDesktopAutopilot(desktopAutopilotStatus.paused ? "resume" : "pause");
}

async function inspectDesktopAutopilot() {
  const res = await fetch("/api/desktop-autopilot/inspect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ include_ocr: false }),
  });
  const el = document.getElementById("desktopauto-observation");
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    el.textContent = err.error || "Không quan sát được cửa sổ.";
    return;
  }
  const data = await res.json();
  el.innerHTML =
    `<div class="desktop-status-grid">` +
    `<div>Cửa sổ<b>${escapeHtml(data.window_title || "không xác định")}</b></div>` +
    `<div>Phân loại<b>${escapeHtml(data.window_category || "unknown")}</b></div>` +
    `<div>Kích thước màn hình<b>${escapeHtml((data.screen_size || []).join(" × "))}</b></div>` +
    `<div>OCR<b>${data.ocr_performed ? "đã đọc" : "không đọc"}</b></div>` +
    `</div>`;
  await refreshDesktopAutopilot();
}

// ---- Bàn đăng tay: chỉ mở file/trang đích; Chủ vẫn là người công khai nội dung ----
async function refreshManualPublish() {
  const res = await fetch("/api/manual-publish");
  if (!res.ok) return;
  const data = await res.json();
  const s = data.summary || {};
  const byPlatform = Object.entries(s.by_platform || {}).map(([k, v]) => `${escapeHtml(k)}: ${v}`).join(" · ") || "trống";
  document.getElementById("manualpublish-summary").innerHTML =
    `<p>Đang chờ: <b style="color:var(--warn)">${s.pending || 0}</b> · ${byPlatform}</p>`;
  const items = data.items || [];
  document.getElementById("manualpublish-tbody").innerHTML = items.length
    ? items.map(item => {
      const artifact = item.artifact_url
        ? `<a href="${escapeHtml(item.artifact_url)}" target="_blank" rel="noopener" style="color:var(--accent)">xem file</a>`
        : "—";
      const platform = item.publish_url
        ? `<a href="${escapeHtml(item.publish_url)}" target="_blank" rel="noopener" style="color:var(--accent)">mở trang đăng</a>`
        : "—";
      return `<tr><td>${escapeHtml(item.platform)}</td><td><b>${escapeHtml(item.title)}</b></td>` +
        `<td>${escapeHtml(item.action)}</td><td>${artifact}</td><td>${platform}</td>` +
        `<td><button class="cancel-btn hire-approve" onclick="finishManualPublish('${escapeHtml(item.id)}')">Đã xử lý</button></td></tr>`;
    }).join("")
    : `<tr><td colspan="6" class="empty-hint">Không còn nội dung nào cần bạn đăng tay.</td></tr>`;
}

async function finishManualPublish(itemId) {
  if (!confirm("Bạn đã tự công khai/xử lý mục này trên nền tảng? AURA sẽ chỉ lưu xác nhận, không kiểm soát nền tảng thay bạn.")) return;
  const res = await fetch(`/api/manual-publish/${encodeURIComponent(itemId)}/done`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirmed_by_owner: true }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    alert(err.error || "Không cập nhật được bàn đăng tay.");
    return;
  }
  refreshManualPublish();
}

async function refreshJobs() {
  const res = await fetch("/api/jobs?limit=50");
  const jobs = await res.json();
  const tbody = document.getElementById("jobs-tbody");
  tbody.innerHTML = jobs.length
    ? jobs.map(jobRowHtml).join("")
    : `<tr><td colspan="6" class="empty-hint">Hàng đợi trống — chạy một tool ở tab Xưởng.</td></tr>`;
}

async function cancelJob(jobId) {
  await fetch(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  refreshJobs();
}

// ---- Sổ kênh ----
async function refreshChannels() {
  const res = await fetch("/api/channels");
  if (!res.ok) return;
  const chans = await res.json();
  document.getElementById("channels-list").innerHTML = chans.map(c => {
    const yt = c.platform === "youtube"
      ? (c.authorized ? `<span class="state-tag state-done">đã cấp quyền</span>`
                      : `<span class="state-tag state-failed">chưa cấp quyền</span>`)
      : "";
    const types = (c.content_types || []).join(", ");
    return `<div class="tool-card" style="cursor:pointer" onclick='fillChannel(${JSON.stringify(c)})'>
      <h3>${c.name} <small style="color:var(--muted)">(${c.key})</small> ${yt}</h3>
      <p class="desc"><b>${c.platform}</b> · ngách: ${c.niche || "—"}</p>
      <p class="desc">Nội dung: ${types || "—"} · Giọng: ${c.style || "—"}</p>
    </div>`;
  }).join("") || `<p class="empty-hint">Chưa có kênh. Thêm bên dưới.</p>`;
}

function fillChannel(c) {
  const f = document.querySelector("#tab-channels form");
  f.key.value = c.key || ""; f.name.value = c.name || "";
  f.platform.value = c.platform || "youtube"; f.niche.value = c.niche || "";
  f.content_types.value = (c.content_types || []).join(", "); f.style.value = c.style || "";
  document.getElementById("channel-form-title").textContent = `Sửa kênh: ${c.name}`;
}

async function submitChannel(evt) {
  evt.preventDefault();
  const d = new FormData(evt.target);
  const body = {
    key: d.get("key").trim(), name: d.get("name"), platform: d.get("platform"),
    niche: d.get("niche"), style: d.get("style"), enabled: true,
    yt_channel: d.get("key").trim(),
    content_types: d.get("content_types").split(",").map(s => s.trim()).filter(Boolean),
  };
  const res = await fetch("/api/channels", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) { evt.target.reset();
    document.getElementById("channel-form-title").textContent = "Thêm / sửa kênh";
    refreshChannels(); loadTools(); }
  else alert("Lưu kênh lỗi");
  return false;
}

loadTools();
refreshJobs();
refreshIncome();
refreshCashflow();
refreshCv();
refreshChannels();
refreshWorkForHire();
refreshActionBox();
refreshManualPublish();
refreshDesktopAutopilot();
if (location.hash) {
  const requestedTab = location.hash.slice(1);
  if (document.getElementById(`tab-${requestedTab}`)) switchTab(requestedTab);
}
window.addEventListener("hashchange", () => {
  const requestedTab = location.hash.slice(1);
  if (document.getElementById(`tab-${requestedTab}`)) switchTab(requestedTab);
});
setInterval(refreshJobs, 2000);
setInterval(() => {
  refreshIncome();
  refreshCashflow();
  refreshCv();
  refreshWorkForHire();
  refreshActionBox();
  refreshManualPublish();
  refreshDesktopAutopilot();
}, 15000);
