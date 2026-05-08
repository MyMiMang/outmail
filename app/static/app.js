// =====================================================================
// Outlook 邮箱取件 · 前端
// 数据全部存浏览器 localStorage，后端纯转发。
// =====================================================================

const LS_KEY_MAILBOXES = "wm.mailboxes.v1";
const LS_KEY_CONFIG = "wm.config.v1";

const state = {
  mailboxes: [],   // [{id, email, password, client_id, refresh_token, master_email, alias, label, last_status}]
  config: { apiBase: "", accessPassword: "" },
  currentId: null,
  messages: [],
  currentMsgId: null,
};

// ---------- utils ----------
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const uid = () => Math.random().toString(36).slice(2, 10) + Date.now().toString(36);

function load() {
  try { state.mailboxes = JSON.parse(localStorage.getItem(LS_KEY_MAILBOXES) || "[]"); } catch { state.mailboxes = []; }
  try { state.config = { ...state.config, ...JSON.parse(localStorage.getItem(LS_KEY_CONFIG) || "{}") }; } catch {}
}
function persist() {
  localStorage.setItem(LS_KEY_MAILBOXES, JSON.stringify(state.mailboxes));
  localStorage.setItem(LS_KEY_CONFIG, JSON.stringify(state.config));
}

function toast(msg, kind = "") {
  const div = document.createElement("div");
  div.className = "toast-item " + (kind === "error" ? "toast-error" : kind === "success" ? "toast-success" : "");
  div.textContent = msg;
  $("#toast").appendChild(div);
  setTimeout(() => div.remove(), 3500);
}

async function api(path, body) {
  const base = (state.config.apiBase || "").replace(/\/$/, "");
  const url = base + path;
  const headers = { "Content-Type": "application/json" };
  if (state.config.accessPassword) headers["X-Access-Password"] = state.config.accessPassword;
  let resp;
  try {
    resp = await fetch(url, { method: "POST", headers, body: JSON.stringify(body || {}) });
  } catch (e) {
    throw new Error("网络错误：" + e.message);
  }
  let data;
  try { data = await resp.json(); } catch { data = {}; }
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  return data;
}
async function apiGet(path) {
  const base = (state.config.apiBase || "").replace(/\/$/, "");
  const headers = {};
  if (state.config.accessPassword) headers["X-Access-Password"] = state.config.accessPassword;
  const r = await fetch(base + path, { headers });
  return r.json();
}

// ---------- mailbox CRUD ----------
function addMailboxes(items) {
  let added = 0;
  for (const it of items) {
    const exists = state.mailboxes.find(m => m.email.toLowerCase() === it.email.toLowerCase());
    if (exists) {
      Object.assign(exists, it);
    } else {
      state.mailboxes.push({ id: uid(), alias: "", label: "", ...it });
      added++;
    }
  }
  persist();
  renderMailboxes();
  return added;
}

function deleteMailbox(id) {
  state.mailboxes = state.mailboxes.filter(m => m.id !== id);
  if (state.currentId === id) { state.currentId = null; renderRight(); }
  persist();
  renderMailboxes();
}

function getCurrent() { return state.mailboxes.find(m => m.id === state.currentId); }

// ---------- render ----------
function renderMailboxes() {
  const ul = $("#mb-list");
  const q = ($("#mb-search").value || "").toLowerCase();
  const items = state.mailboxes.filter(m =>
    !q || m.email.toLowerCase().includes(q) || (m.label || "").toLowerCase().includes(q)
  );
  $("#mb-count").textContent = state.mailboxes.length;
  ul.innerHTML = "";
  if (!items.length) {
    ul.innerHTML = `<li class="p-6 text-center text-sm text-slate-400">暂无邮箱</li>`;
    return;
  }
  for (const m of items) {
    const li = document.createElement("li");
    li.className = "mb-item px-3 py-2 cursor-pointer flex items-center justify-between gap-2" + (m.id === state.currentId ? " active" : "");
    li.innerHTML = `
      <div class="min-w-0 flex-1">
        <div class="text-sm font-medium truncate">${escapeHtml(m.email)}</div>
        <div class="text-xs text-slate-500 truncate">${escapeHtml(m.last_status || m.label || m.client_id || "")}</div>
      </div>
      <button title="复制邮箱" class="text-slate-300 hover:text-blue-600 text-sm shrink-0" data-copy="${m.id}">📋</button>
      <button title="删除" class="text-slate-300 hover:text-red-500 text-sm shrink-0" data-del="${m.id}">✕</button>`;
    li.addEventListener("click", (e) => {
      if (e.target.closest("[data-del]") || e.target.closest("[data-copy]")) return;
      state.currentId = m.id; state.messages = []; state.currentMsgId = null;
      renderMailboxes(); renderRight();
    });
    ul.appendChild(li);
  }
  ul.querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", (e) => {
    e.stopPropagation();
    const mb = state.mailboxes.find(x => x.id === b.dataset.copy);
    if (mb) copyToClipboard(effectiveEmail(mb));
  }));
  ul.querySelectorAll("[data-del]").forEach(b => b.addEventListener("click", (e) => {
    e.stopPropagation();
    if (confirm("删除此邮箱？")) deleteMailbox(b.dataset.del);
  }));
}

function renderRight() {
  const cur = getCurrent();
  if (!cur) {
    $("#empty-state").classList.remove("hidden");
    $("#mailbox-panel").classList.add("hidden");
    return;
  }
  $("#empty-state").classList.add("hidden");
  $("#mailbox-panel").classList.remove("hidden");
  $("#cur-email").textContent = cur.email;
  $("#cur-cid").textContent = cur.client_id || "-";
  $("#alias-input").value = cur.alias || "";
  $("#cur-status").textContent = "";
  $("#cur-code").classList.add("hidden");
  renderMessages();
  $("#msg-detail").classList.add("hidden");
}

function renderMessages() {
  const ul = $("#msg-list");
  $("#msg-count").textContent = state.messages.length;
  ul.innerHTML = "";
  if (!state.messages.length) {
    ul.innerHTML = `<li class="p-6 text-center text-sm text-slate-400">点击"拉取邮件"开始</li>`;
    return;
  }
  for (const m of state.messages) {
    const li = document.createElement("li");
    li.className = "msg-row px-4 py-2 cursor-pointer hover:bg-slate-50" + (m.id === state.currentMsgId ? " active" : "");
    li.innerHTML = `
      <div class="flex items-center justify-between gap-3">
        <div class="text-sm font-medium truncate flex-1">${escapeHtml(m.subject || "(无主题)")}</div>
        <div class="text-xs text-slate-400 shrink-0">${escapeHtml(formatDate(m.date))}</div>
      </div>
      <div class="text-xs text-slate-500 truncate mt-0.5">
        <span class="font-medium">${escapeHtml(m.from || "")}</span> · ${escapeHtml((m.preview || "").slice(0, 120))}
      </div>`;
    li.addEventListener("click", () => openMessage(m.id));
    ul.appendChild(li);
  }
}

function openMessage(id) {
  const m = state.messages.find(x => x.id === id);
  if (!m) return;
  state.currentMsgId = id;
  renderMessages();
  $("#msg-detail").classList.remove("hidden");
  $("#d-subject").textContent = m.subject || "(无主题)";
  $("#d-from").textContent = m.from_name ? `${m.from_name} <${m.from}>` : m.from;
  $("#d-date").textContent = formatDate(m.date) + "  ·  " + (m.source || "");
  showTab("html", m);
}

function showTab(kind, m) {
  m = m || state.messages.find(x => x.id === state.currentMsgId);
  if (!m) return;
  $("#d-tab-html").classList.toggle("bg-slate-100", kind === "html");
  $("#d-tab-text").classList.toggle("bg-slate-100", kind === "text");
  $("#d-tab-raw").classList.toggle("bg-slate-100", kind === "raw");
  const iframe = $("#d-iframe");
  const pre = $("#d-pre");
  if (kind === "html" && m.body_html) {
    iframe.classList.remove("hidden"); pre.classList.add("hidden");
    iframe.srcdoc = m.body_html;
  } else if (kind === "text") {
    iframe.classList.add("hidden"); pre.classList.remove("hidden");
    pre.textContent = m.body_text || m.preview || "(空)";
  } else {
    iframe.classList.add("hidden"); pre.classList.remove("hidden");
    pre.textContent = JSON.stringify(m, null, 2);
  }
}

// ---------- actions ----------
async function doFetch() {
  const cur = getCurrent(); if (!cur) return;
  cur.alias = $("#alias-input").value.trim();
  persist();
  $("#cur-status").textContent = "拉取中…";
  try {
    const data = await api("/api/messages", {
      email: cur.email, password: cur.password, client_id: cur.client_id,
      refresh_token: cur.refresh_token, master_email: cur.master_email || cur.email,
      alias: cur.alias,
      folder: $("#folder-sel").value, top: parseInt($("#top-sel").value, 10),
    });
    state.messages = data.messages || [];
    cur.last_status = `✓ ${data.count} 封 · ${data.channel}`;
    persist(); renderMailboxes();
    $("#cur-status").innerHTML = `共 <b>${data.count}</b> 封 · 通道 <span class="px-1.5 py-0.5 rounded bg-slate-100 text-xs">${data.channel}</span>`;
    $("#channel-badge").textContent = data.channel;
    $("#channel-badge").className = "text-xs px-2 py-0.5 rounded-full " + (data.channel === "graph" ? "bg-blue-100 text-blue-700" : "bg-amber-100 text-amber-700");
    $("#channel-badge").classList.remove("hidden");
    renderMessages();
  } catch (e) {
    cur.last_status = `✗ ${e.message}`;
    persist(); renderMailboxes();
    $("#cur-status").innerHTML = `<span class="text-red-600">失败：${escapeHtml(e.message)}</span>`;
    toast(e.message, "error");
  }
}

async function doCode() {
  const cur = getCurrent(); if (!cur) return;
  cur.alias = $("#alias-input").value.trim(); persist();
  $("#cur-status").textContent = "提取中…";
  $("#cur-code").classList.add("hidden");
  try {
    const data = await api("/api/code", {
      email: cur.email, password: cur.password, client_id: cur.client_id,
      refresh_token: cur.refresh_token, master_email: cur.master_email || cur.email,
      alias: cur.alias,
      folder: $("#folder-sel").value, top: parseInt($("#top-sel").value, 10),
      only_latest: false,
    });
    if (data.code) {
      $("#cur-code-text").textContent = data.code;
      $("#cur-code-meta").textContent = `主题：${data.matched_subject || "-"}  ·  来自：${data.matched_from || "-"}`;
      $("#cur-code").classList.remove("hidden");
      $("#cur-status").innerHTML = `通道 <b>${data.channel}</b> · 扫描 ${data.scanned} 封`;
      cur.last_status = `验证码：${data.code}`;
    } else {
      $("#cur-status").innerHTML = `<span class="text-amber-600">未找到验证码（扫描 ${data.scanned} 封）</span>`;
      cur.last_status = `未取到`;
    }
    persist(); renderMailboxes();
  } catch (e) {
    $("#cur-status").innerHTML = `<span class="text-red-600">失败：${escapeHtml(e.message)}</span>`;
    toast(e.message, "error");
  }
}

async function doTestToken() {
  const cur = getCurrent(); if (!cur) return;
  $("#cur-status").textContent = "测试 refresh_token…";
  try {
    const d = await api("/api/refresh", { email: cur.email, client_id: cur.client_id, refresh_token: cur.refresh_token });
    $("#cur-status").innerHTML = `✓ token 有效 · 类型 <b>${d.token_type}</b> · scope: <code class="text-xs">${escapeHtml(d.scope || "")}</code>`;
    toast("token 有效", "success");
  } catch (e) {
    $("#cur-status").innerHTML = `<span class="text-red-600">token 失败：${escapeHtml(e.message)}</span>`;
    toast(e.message, "error");
  }
}

// ---------- import ----------
async function importBundles() {
  const text = $("#import-text").value;
  if (!text.trim()) { toast("请粘贴或选择文件", "error"); return; }
  $("#import-status").textContent = "解析中…";
  try {
    const data = await api("/api/parse_bundle", { text });
    if (data.errors && data.errors.length) {
      toast(`解析失败 ${data.errors.length} 行，已跳过`, "error");
    }
    const added = addMailboxes(data.items);
    toast(`成功导入 ${added} 个新邮箱（已存在 ${data.items.length - added} 个被更新）`, "success");
    closeModal("modal-import");
    $("#import-text").value = "";
    $("#import-status").textContent = "";
  } catch (e) {
    $("#import-status").textContent = "";
    toast(e.message, "error");
  }
}

// ---------- batch ----------
async function batchRun() {
  const items = state.mailboxes;
  if (!items.length) { toast("没有邮箱", "error"); return; }
  $("#batch-status").textContent = `运行中（${items.length}）…`;
  $("#batch-result").innerHTML = "";
  try {
    const data = await api("/api/batch_code", {
      mailboxes: items.map(m => ({
        email: m.email, password: m.password, client_id: m.client_id,
        refresh_token: m.refresh_token, master_email: m.master_email || m.email,
        alias: m.alias || "",
      })),
      folder: $("#batch-folder").value,
      sender_contains: $("#batch-sender").value.trim(),
      subject_contains: $("#batch-subject").value.trim(),
      top: 10,
    });
    const tb = $("#batch-result"); tb.innerHTML = "";
    let ok = 0, codeFound = 0;
    for (const r of data.results) {
      if (r.ok) ok++;
      if (r.code) codeFound++;
      const tr = document.createElement("tr");
      tr.className = "border-t";
      tr.innerHTML = `
        <td class="p-2 truncate max-w-[220px]">${escapeHtml(r.email)}${r.alias ? ` <span class="text-xs text-slate-400">(${escapeHtml(r.alias)})</span>` : ""}</td>
        <td class="p-2">${r.channel || "-"}</td>
        <td class="p-2 font-mono ${r.code ? "text-emerald-700 font-bold" : "text-slate-400"}">${r.code || "-"}</td>
        <td class="p-2 text-slate-500 truncate max-w-[260px]">${escapeHtml(r.matched_subject || "")}</td>
        <td class="p-2">${r.ok ? `<span class="text-emerald-600">OK</span>` : `<span class="text-red-600" title="${escapeHtml(r.error || "")}">失败</span>`}</td>`;
      tb.appendChild(tr);
    }
    $("#batch-status").textContent = `完成 · ${ok}/${data.count} 成功 · ${codeFound} 个取到验证码`;
  } catch (e) {
    $("#batch-status").innerHTML = `<span class="text-red-600">${escapeHtml(e.message)}</span>`;
  }
}

// ---------- modals ----------
function openModal(id) { $("#" + id).classList.remove("hidden"); }
function closeModal(id) { $("#" + id).classList.add("hidden"); }

// ---------- helpers ----------
function effectiveEmail(mb) {
  // 别名场景下拼成 user+alias@domain；否则原样返回
  if (!mb || !mb.alias) return mb ? mb.email : "";
  const at = mb.email.indexOf("@");
  if (at <= 0) return mb.email;
  return mb.email.slice(0, at) + "+" + mb.alias + mb.email.slice(at);
}

async function copyToClipboard(text, label) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // 老浏览器 / 非 HTTPS 降级
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); } catch {}
    document.body.removeChild(ta);
  }
  toast("已复制 " + (label || text), "success");
}

function escapeHtml(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}
function formatDate(s) {
  if (!s) return "";
  try {
    const d = new Date(s);
    if (isNaN(d)) return s;
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    if (sameDay) return d.toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
    return d.toLocaleString([], {month:"2-digit", day:"2-digit", hour:"2-digit", minute:"2-digit"});
  } catch { return s; }
}

// ---------- bind ----------
function bind() {
  $("#btn-add").addEventListener("click", () => openModal("modal-import"));
  $("#btn-batch").addEventListener("click", () => openModal("modal-batch"));
  $("#btn-settings").addEventListener("click", () => {
    $("#cfg-api").value = state.config.apiBase || "";
    $("#cfg-pass").value = state.config.accessPassword || "";
    openModal("modal-settings");
  });
  $$("[data-close-modal]").forEach(b => b.addEventListener("click", () => closeModal(b.dataset.closeModal)));
  $("#btn-save-settings").addEventListener("click", () => {
    state.config.apiBase = $("#cfg-api").value.trim();
    state.config.accessPassword = $("#cfg-pass").value;
    persist();
    closeModal("modal-settings");
    checkServer();
    toast("已保存", "success");
  });
  $("#btn-clear-all").addEventListener("click", () => {
    if (confirm("确定清空所有本地凭据？此操作不可撤销。")) {
      state.mailboxes = []; state.currentId = null;
      persist(); renderMailboxes(); renderRight();
      toast("已清空", "success");
    }
  });
  $("#btn-import-confirm").addEventListener("click", importBundles);
  $("#btn-pick-file").addEventListener("click", () => $("#import-file").click());
  $("#import-file").addEventListener("change", async (e) => {
    const f = e.target.files[0]; if (!f) return;
    $("#import-text").value = await f.text();
    $("#import-status").textContent = `已加载 ${f.name}`;
  });

  $("#btn-fetch").addEventListener("click", doFetch);
  $("#btn-code").addEventListener("click", doCode);
  $("#btn-test-token").addEventListener("click", doTestToken);
  $("#btn-copy-code").addEventListener("click", () => {
    copyToClipboard($("#cur-code-text").textContent);
  });

  $("#mb-search").addEventListener("input", renderMailboxes);

  $("#d-tab-html").addEventListener("click", () => showTab("html"));
  $("#d-tab-text").addEventListener("click", () => showTab("text"));
  $("#d-tab-raw").addEventListener("click", () => showTab("raw"));

  $("#btn-batch-run").addEventListener("click", batchRun);

  $("#btn-export").addEventListener("click", () => {
    const lines = state.mailboxes.map(m => `${m.email}----${m.password}----${m.client_id}----${m.refresh_token}`);
    const blob = new Blob([lines.join("\n")], {type: "text/plain"});
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "mailboxes.txt";
    a.click();
  });
}

async function checkServer() {
  try {
    const d = await apiGet("/api/health");
    $("#server-status").innerHTML = d.auth_required && !state.config.accessPassword
      ? `<span class="text-amber-600">服务端已启用密码，请在设置中填写</span>`
      : `<span class="text-emerald-600">● 服务正常</span>`;
  } catch (e) {
    $("#server-status").innerHTML = `<span class="text-red-600">● 无法连接服务端</span>`;
  }
}

// ---------- init ----------
load();
bind();
renderMailboxes();
renderRight();
checkServer();
