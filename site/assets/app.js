"use strict";

// 每页条数：避免一次性渲染几十万行
const PAGE_SIZE = 100;
// 与 CSV 列顺序一致
const COLUMNS = [
  ["mobile", "手机号", "mono"],
  ["password", "密码", "mono"],
  ["u2_user_id", "u2_user_id", "mono"],
  ["student_id", "学员ID", "mono"],
  ["student_code", "学员编号", "mono"],
  ["real_name", "姓名", ""],
  ["grade_name", "年级", ""],
  ["school_id", "学校ID", "mono"],
  ["school_name", "学校名", ""],
];

const state = {
  rows: [],
  filtered: [],
  page: 1,
  query: "",
  meta: null,
};

const el = {
  stats: document.getElementById("stats"),
  statCount: document.getElementById("stat-count"),
  statRange: document.getElementById("stat-range"),
  statUpdated: document.getElementById("stat-updated"),
  subtitle: document.getElementById("subtitle"),
  search: document.getElementById("search"),
  count: document.getElementById("count"),
  rows: document.getElementById("rows"),
  empty: document.getElementById("empty"),
  emptyHint: document.getElementById("empty-hint"),
  pager: document.getElementById("pager"),
  prev: document.getElementById("prev"),
  next: document.getElementById("next"),
  pageInfo: document.getElementById("page-info"),
  copyAll: document.getElementById("copy-all"),
  generated: document.getElementById("generated"),
  toast: document.getElementById("toast"),
};

const numberFormat = new Intl.NumberFormat("zh-CN");

function formatTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", { hour12: false });
}

function showToast(message) {
  el.toast.textContent = message;
  el.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => el.toast.classList.remove("show"), 1600);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (error) {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    area.remove();
  }
}

// 一行按 CSV 的管道符格式输出，方便直接贴回 txt
function rowText(row) {
  return COLUMNS.map(([key]) => row[key] || "").join("|");
}

function renderStats() {
  const meta = state.meta || {};
  el.statCount.textContent = numberFormat.format(state.rows.length);
  el.statRange.textContent = meta.range ? `${meta.range.start} ~ ${meta.range.end}` : "—";
  el.statUpdated.textContent = formatTime(meta.generated_at);
  el.stats.hidden = false;

  const parts = [];
  if (meta.env) parts.push(meta.env.toUpperCase());
  parts.push(`${numberFormat.format(state.rows.length)} 条记录`);
  el.subtitle.textContent = `XDFVAScanner · ${parts.join(" · ")}`;
  if (meta.generated_at) {
    el.generated.textContent = `最近更新：${formatTime(meta.generated_at)}`;
  }
}

function matches(row, query) {
  return row.search.includes(query);
}

function applyFilter() {
  const query = state.query.trim().toLowerCase();
  state.filtered = query ? state.rows.filter((row) => matches(row, query)) : state.rows.slice();
  state.page = 1;
}

function makeCopyButton(row) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "btn row-copy";
  button.title = "复制整行";
  button.setAttribute("aria-label", `复制 ${row.mobile} 的整行数据`);
  button.innerHTML =
    '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">' +
    '<path fill="currentColor" d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path>' +
    '<path fill="currentColor" d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path>' +
    "</svg>";
  button.addEventListener("click", async () => {
    await copyText(rowText(row));
    showToast(`已复制 ${row.mobile}`);
  });
  return button;
}

function renderTable() {
  const total = state.filtered.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  state.page = Math.min(state.page, pageCount);
  const start = (state.page - 1) * PAGE_SIZE;
  const pageItems = state.filtered.slice(start, start + PAGE_SIZE);

  el.count.textContent = state.query
    ? `匹配 ${numberFormat.format(total)} / ${numberFormat.format(state.rows.length)}`
    : `共 ${numberFormat.format(total)} 条`;

  const fragment = document.createDocumentFragment();
  pageItems.forEach((row) => {
    const tr = document.createElement("tr");
    COLUMNS.forEach(([key, , className]) => {
      const cell = document.createElement("td");
      const value = row[key] || "";
      if (className) cell.className = className;
      if (key === "mobile") cell.className = "mono col-mobile";
      cell.textContent = value || "—";
      if (value) cell.title = value;
      tr.appendChild(cell);
    });

    const actionCell = document.createElement("td");
    actionCell.className = "col-copy";
    actionCell.appendChild(makeCopyButton(row));
    tr.appendChild(actionCell);

    fragment.appendChild(tr);
  });

  el.rows.replaceChildren(fragment);
  el.empty.hidden = total > 0;
  if (!total) {
    el.emptyHint.textContent = state.query
      ? "没有匹配的账号，换个关键词试试。"
      : "等待第一次扫描完成后自动发布。";
  }

  el.pager.hidden = pageCount <= 1;
  el.pageInfo.textContent = `第 ${state.page} / ${pageCount} 页`;
  el.prev.disabled = state.page <= 1;
  el.next.disabled = state.page >= pageCount;
  el.copyAll.disabled = total === 0;
}

function render() {
  renderTable();
}

function bindEvents() {
  el.search.addEventListener("input", (event) => {
    state.query = event.target.value;
    applyFilter();
    render();
  });

  el.prev.addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      render();
      el.rows.closest(".table-wrap").scrollIntoView({ block: "start", behavior: "smooth" });
    }
  });

  el.next.addEventListener("click", () => {
    const pageCount = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
    if (state.page < pageCount) {
      state.page += 1;
      render();
      el.rows.closest(".table-wrap").scrollIntoView({ block: "start", behavior: "smooth" });
    }
  });

  el.copyAll.addEventListener("click", async () => {
    const MAX_COPY = 2000;
    const list = state.filtered.slice(0, MAX_COPY).map((row) => rowText(row));
    if (!list.length) return;
    await copyText(list.join("\n"));
    const suffix =
      state.filtered.length > MAX_COPY ? `（共 ${state.filtered.length} 条，仅复制前 ${MAX_COPY} 条）` : "";
    showToast(`已复制 ${list.length} 条${suffix}`);
  });
}

async function boot() {
  bindEvents();
  try {
    const response = await fetch("data/accounts.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    state.meta = {
      generated_at: data.generated_at || null,
      env: data.env || "",
      range: data.range || null,
    };
    state.rows = (Array.isArray(data.rows) ? data.rows : []).map((row) => ({
      ...row,
      search: [
        row.mobile,
        row.password,
        row.u2_user_id,
        row.student_id,
        row.student_code,
        row.real_name,
        row.grade_name,
        row.school_id,
        row.school_name,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase(),
    }));
  } catch (error) {
    state.rows = [];
    state.meta = null;
    el.empty.hidden = false;
    el.emptyHint.textContent = "数据还没发布，或加载失败，请稍后刷新。";
  }

  applyFilter();
  renderStats();
  render();
}

boot();
