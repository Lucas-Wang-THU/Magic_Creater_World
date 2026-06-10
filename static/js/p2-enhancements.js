/** P2 Enhancements: Stats, Snapshots, Timing, Export, Character Viz */

import { $, toast, api, escapeHtml, formatDate } from "./utils.js";
import { state } from "./state.js";

// ═══════════════════════════════════════════════════════════════════
// P2-12: Writing Statistics Dashboard
// ═══════════════════════════════════════════════════════════════════

let _statsChart = null;

export async function renderStoryStats() {
  if (!state.world?.meta?.id) return;
  const pane = $("storyPaneStats");
  if (!pane) return;
  pane.innerHTML = `<div class="stats-loading"><span class="ms thinking-ic" aria-hidden="true">monitoring</span><p>加载统计数据…</p></div>`;
  try {
    const data = await api(`/api/worlds/${state.world.meta.id}/story/stats`);
    pane.innerHTML = _buildStatsHTML(data);
    _drawStatsCharts(data);
  } catch (e) {
    pane.innerHTML = `<p class="muted">加载失败：${escapeHtml(String(e.message || e))}</p>`;
  }
}

function _buildStatsHTML(d) {
  const prog = d.completion || {};
  const fs = d.foreshadowing || {};
  const statusLabels = { planned: "规划中", outline: "大纲", drafting: "草稿", revising: "修订中", locked: "已锁定", done: "已完成", archived: "归档" };
  const chRows = (d.chapter_progress || []).map(c => {
    const pct = d.total_words > 0 ? Math.round(c.word_count / Math.max(1, d.total_words) * 100) : 0;
    const st = statusLabels[c.status] || c.status || "规划中";
    return `<tr>
      <td class="stats-ch-order">${c.order}</td>
      <td>${escapeHtml(c.title || "")}</td>
      <td class="stats-ch-words">${c.word_count.toLocaleString()}</td>
      <td><span class="pill-sm pill-${c.status || 'planned'}">${st}</span></td>
      <td><div class="stats-mini-bar"><div class="stats-mini-bar-fill" style="width:${pct}%"></div></div></td>
    </tr>`;
  }).join("");

  // Completion progress: count chapters by status
  const chProgress = d.chapter_progress || [];
  const statusCount = {};
  for (const ch of chProgress) {
    const s = ch.status || "planned";
    statusCount[s] = (statusCount[s] || 0) + 1;
  }
  const doneCount = (statusCount.done || 0) + (statusCount.locked || 0);
  const totalCh = chProgress.length || 1;
  const donePct = Math.round(doneCount / totalCh * 100);
  const progressSegments = [
    { key: "done", count: statusCount.done || 0, cls: "stats-progress-fill--done" },
    { key: "locked", count: statusCount.locked || 0, cls: "stats-progress-fill--locked" },
    { key: "drafting", count: statusCount.drafting || 0, cls: "stats-progress-fill--drafting" },
    { key: "revising", count: statusCount.revising || 0, cls: "stats-progress-fill--revising" },
    { key: "planned", count: (statusCount.planned || 0) + (statusCount.outline || 0) + (statusCount.archived || 0), cls: "stats-progress-fill--planned" },
  ].filter(s => s.count > 0);
  const progressBar = totalCh > 0
    ? `<div class="stats-progress-bar">${progressSegments.map(s =>
        `<div class="stats-progress-fill ${s.cls}" style="width:${Math.round(s.count / totalCh * 100)}%" title="${statusLabels[s.key] || s.key}: ${s.count} 章"></div>`
      ).join("")}</div>`
    : "";

  return `<div class="stats-dashboard">
    <div class="stats-hero">
      <div class="stats-hero-card">
        <span class="stats-hero-num">${(d.total_words || 0).toLocaleString()}</span>
        <span class="stats-hero-label">总字数</span>
      </div>
      <div class="stats-hero-card">
        <span class="stats-hero-num">${d.chapter_count || 0}</span>
        <span class="stats-hero-label">章节数</span>
      </div>
      <div class="stats-hero-card">
        <span class="stats-hero-num">${fs.total || 0}</span>
        <span class="stats-hero-label">伏笔总数</span>
      </div>
      <div class="stats-hero-card">
        <span class="stats-hero-num">${donePct}%</span>
        <span class="stats-hero-label">完成度</span>
      </div>
    </div>
    ${progressBar ? `<div class="stats-card"><h3 class="stats-card-title"><span class="ms" aria-hidden="true">timeline</span>章节进度</h3>${progressBar}<p class="muted tiny" style="margin-top:4px">${doneCount}/${totalCh} 章已完成或锁定</p></div>` : ""}
    <div class="stats-grid">
      <div class="stats-card">
        <h3 class="stats-card-title"><span class="ms" aria-hidden="true">show_chart</span>章节字数分布</h3>
        <div class="stats-chart-wrap"><canvas id="statsWordsChart"></canvas></div>
      </div>
      <div class="stats-card">
        <h3 class="stats-card-title"><span class="ms" aria-hidden="true">sentiment_satisfied</span>情感分布</h3>
        <div class="stats-chart-wrap stats-chart-wrap--donut"><canvas id="statsSentimentChart"></canvas></div>
      </div>
    </div>
    <div class="stats-card">
      <h3 class="stats-card-title"><span class="ms" aria-hidden="true">list_alt</span>章节进度</h3>
      <div class="stats-table-wrap">
        <table class="stats-table"><thead><tr><th>#</th><th>标题</th><th>字数</th><th>状态</th><th>占比</th></tr></thead><tbody>${chRows || '<tr><td colspan="5" class="muted">暂无章节数据</td></tr>'}</tbody></table>
      </div>
    </div>
    ${fs.total > 0 ? `<div class="stats-card">
      <h3 class="stats-card-title"><span class="ms" aria-hidden="true">linear_scale</span>伏笔统计</h3>
      <div class="stats-fs-badges">
        <span class="stats-fs-badge stats-fs-open">开放：${fs.open || 0}</span>
        <span class="stats-fs-badge stats-fs-resolved">已回收：${fs.resolved || 0}</span>
        <span class="stats-fs-badge stats-fs-abandoned">废弃：${fs.abandoned || 0}</span>
      </div>
    </div>` : ""}
  </div>`;
}

function _drawStatsCharts(d) {
  // Destroy previous chart
  if (_statsChart) { _statsChart.destroy(); _statsChart = null; }
  const chProgress = d.chapter_progress || [];
  if (chProgress.length > 0) {
    const ctx = document.getElementById("statsWordsChart");
    if (ctx) {
      _statsChart = new Chart(ctx, {
        type: "bar",
        data: {
          labels: chProgress.map(c => c.title || `Ch ${c.order}`),
          datasets: [{
            label: "字数",
            data: chProgress.map(c => c.word_count || 0),
            backgroundColor: "rgba(99, 132, 235, 0.6)",
            borderColor: "rgba(99, 132, 235, 1)",
            borderWidth: 1,
            borderRadius: 4,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { font: { size: 11 } } }, x: { ticks: { font: { size: 10 }, maxRotation: 45 } } },
        },
      });
    }
  }
  // Sentiment donut
  const sd = d.sentiment_distribution || {};
  const sEntries = Object.entries(sd);
  if (sEntries.length > 0) {
    const ctx2 = document.getElementById("statsSentimentChart");
    if (ctx2) {
      const toneColors = { positive: "#4caf50", negative: "#f44336", tense: "#ff9800", calm: "#2196f3", mixed: "#9c27b0" };
      new Chart(ctx2, {
        type: "doughnut",
        data: {
          labels: sEntries.map(([k]) => k),
          datasets: [{
            data: sEntries.map(([, v]) => v),
            backgroundColor: sEntries.map(([k]) => toneColors[k] || "#888"),
            borderWidth: 0,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: "bottom", labels: { font: { size: 10 }, padding: 12 } } },
        },
      });
    }
  }
}


// ═══════════════════════════════════════════════════════════════════
// P2-9: Chapter Version Snapshots UI
// ═══════════════════════════════════════════════════════════════════

export async function showChapterVersionHistory(chapterId) {
  if (!state.world?.meta?.id || !chapterId) return;
  const wid = state.world.meta.id;
  let snapshots = [];
  try {
    const res = await api(`/api/worlds/${wid}/story/chapters/${chapterId}/snapshots`);
    snapshots = res.snapshots || [];
  } catch (e) {
    toast("加载版本历史失败：" + e.message);
    return;
  }
  _renderVersionModal(chapterId, snapshots);
}

function _renderVersionModal(chapterId, snapshots) {
  // Remove existing modal if any
  const existing = document.querySelector(".snapshot-modal-overlay");
  if (existing) existing.remove();

  const rows = snapshots.length > 0
    ? snapshots.map(s => `<tr>
        <td>v${s.version}</td>
        <td>${formatDate(s.modified_at)}</td>
        <td>${(s.word_count || 0).toLocaleString()} 字</td>
        <td>${(s.size_bytes / 1024).toFixed(1)} KB</td>
        <td>
          <button class="ghost tiny btn-ic snapshot-view-btn" data-version="${s.version}"><span class="ms" aria-hidden="true">visibility</span>查看</button>
          <button class="ghost tiny btn-ic snapshot-diff-btn" data-version="${s.version}"><span class="ms" aria-hidden="true">difference</span>对比当前</button>
        </td>
      </tr>`).join("")
    : `<tr><td colspan="5" class="muted">暂无版本快照。每次保存章节文稿时自动创建。</td></tr>`;

  const overlay = document.createElement("div");
  overlay.className = "snapshot-modal-overlay";
  overlay.innerHTML = `<div class="snapshot-modal">
    <div class="snapshot-modal-head">
      <h3><span class="ms" aria-hidden="true">history</span>版本历史</h3>
      <button class="ghost btn-ic snapshot-modal-close" aria-label="关闭">&times;</button>
    </div>
    <div class="snapshot-modal-body">
      <table class="stats-table"><thead><tr><th>版本</th><th>时间</th><th>字数</th><th>大小</th><th>操作</th></tr></thead><tbody>${rows}</tbody></table>
    </div>
    <div class="snapshot-modal-diff" id="snapshotDiffArea" style="display:none">
      <div class="snapshot-diff-head">
        <h4><span class="ms" aria-hidden="true">difference</span>差异对比</h4>
        <button class="ghost tiny btn-ic" id="snapshotDiffBack"><span class="ms" aria-hidden="true">arrow_back</span>返回列表</button>
      </div>
      <pre id="snapshotDiffContent" class="snapshot-diff-pre"></pre>
    </div>
  </div>`;
  document.body.appendChild(overlay);

  // Close handlers
  overlay.querySelector(".snapshot-modal-close").addEventListener("click", () => overlay.remove());
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });

  // View snapshot
  overlay.querySelectorAll(".snapshot-view-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const v = parseInt(btn.dataset.version, 10);
      try {
        const res = await api(`/api/worlds/${state.world.meta.id}/story/chapters/${chapterId}/snapshots/${v}`);
        _showSnapshotContent(overlay, v, res.content);
      } catch (e) { toast("加载快照失败：" + e.message); }
    });
  });

  // Diff against current
  overlay.querySelectorAll(".snapshot-diff-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const v = parseInt(btn.dataset.version, 10);
      try {
        const res = await api(`/api/worlds/${state.world.meta.id}/story/chapters/${chapterId}/snapshots/diff?left=${v}&right=current`);
        _showSnapshotDiff(overlay, v, res);
      } catch (e) { toast("对比失败：" + e.message); }
    });
  });

  document.getElementById("snapshotDiffBack")?.addEventListener("click", () => {
    const body = overlay.querySelector(".snapshot-modal-body");
    const diffArea = overlay.querySelector(".snapshot-modal-diff");
    if (body) body.style.display = "";
    if (diffArea) diffArea.style.display = "none";
  });
}

function _showSnapshotContent(overlay, version, content) {
  const body = overlay.querySelector(".snapshot-modal-body");
  const diffArea = overlay.querySelector(".snapshot-modal-diff");
  const pre = overlay.querySelector("#snapshotDiffContent");
  if (body) body.style.display = "none";
  if (diffArea) diffArea.style.display = "";
  const h4 = diffArea?.querySelector("h4");
  if (h4) h4.innerHTML = `<span class="ms" aria-hidden="true">visibility</span>版本 v${version}`;
  if (pre) pre.textContent = content;
}

function _showSnapshotDiff(overlay, version, res) {
  const body = overlay.querySelector(".snapshot-modal-body");
  const diffArea = overlay.querySelector(".snapshot-modal-diff");
  const pre = overlay.querySelector("#snapshotDiffContent");
  if (body) body.style.display = "none";
  if (diffArea) diffArea.style.display = "";
  const h4 = diffArea?.querySelector("h4");
  if (h4) h4.innerHTML = `<span class="ms" aria-hidden="true">difference</span>v${version} → 当前`;
  if (pre && res.lines) {
    pre.innerHTML = res.lines.map(l => {
      const cls = l.kind === "add" ? "diff-add" : l.kind === "rem" ? "diff-rem" : "";
      return `<span class="${cls}">${escapeHtml(l.text)}</span>`;
    }).join("\n");
  }
}


// ═══════════════════════════════════════════════════════════════════
// P2-13: Timing Breakdown Panel
// ═══════════════════════════════════════════════════════════════════

export function showTimingBreakdown(timingData, containerId) {
  const container = $(containerId);
  if (!container || !Array.isArray(timingData) || !timingData.length) return;
  const totalMs = timingData.reduce((s, t) => s + (t.elapsed_ms || 0), 0);
  const rows = timingData.map(t => {
    const pct = totalMs > 0 ? Math.round((t.elapsed_ms || 0) / totalMs * 100) : 0;
    const label = t.label || "unknown";
    const sec = ((t.elapsed_ms || 0) / 1000).toFixed(1);
    return `<div class="timing-row">
      <span class="timing-label">${escapeHtml(label)}</span>
      <span class="timing-bar-wrap"><span class="timing-bar" style="width:${Math.max(1, pct)}%"></span></span>
      <span class="timing-val">${sec}s</span>
    </div>`;
  }).join("");
  const totalSec = (totalMs / 1000).toFixed(1);
  container.innerHTML = `<div class="timing-panel">
    <div class="timing-head">
      <span class="ms" aria-hidden="true">timer</span>
      <strong>耗时详情</strong>
      <span class="timing-total">总计 ${totalSec}s</span>
    </div>
    ${rows}
  </div>`;
  container.style.display = "";
}


// ═══════════════════════════════════════════════════════════════════
// P2-11: Export Dropdown Handler
// ═══════════════════════════════════════════════════════════════════

export async function exportStoryFormat(format) {
  if (!state.world?.meta?.id) return;
  const wid = state.world.meta.id;
  const name = state.world.meta.name || "story";
  try {
    const resp = await fetch(`/api/worlds/${wid}/story/export?format=${format}`);
    if (!resp.ok) {
      const err = await resp.text();
      throw new Error(err || resp.statusText);
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const exts = { md: "md", epub: "epub", docx: "docx" };
    a.download = `${name}.${exts[format] || format}`;
    a.href = url;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast(`已导出 ${format.toUpperCase()}`);
  } catch (e) {
    toast(`导出失败：${e.message}`);
    if (e.message && e.message.includes("ebooklib")) {
      toast("请先安装：pip install ebooklib");
    }
    if (e.message && e.message.includes("python-docx")) {
      toast("请先安装：pip install python-docx");
    }
  }
}


// ═══════════════════════════════════════════════════════════════════
// P2-10: Interactive Character Relationship Graph (vis.js)
// ═══════════════════════════════════════════════════════════════════

/** Render a character relation network using vis.js from parsed entities + relations arrays.
 *  Used by the existing refreshCharRelationNetworkViz in app.js. */
export function renderCharacterNetworkFromData(entities, relations, containerId) {
  const container = $(containerId);
  if (!container) return;
  if (!entities || !entities.length) {
    container.innerHTML = `<p class="muted" style="padding:1rem;text-align:center">暂无角色数据</p>`;
    return;
  }
  const validEntities = entities.filter(e => e && typeof e === "object" && e.id);
  const nodes = new vis.DataSet(validEntities.map(e => ({
    id: e.id,
    label: e.name || e.id || "?",
    color: { background: CAST_ROLE_COLORS[e.cast_role] || DEFAULT_NODE_COLOR, border: "#333" },
    font: { size: 13, color: "#333", strokeWidth: 0 },
    shape: "dot",
    size: e.cast_role === "protagonist_core" ? 30 : e.cast_role === "antagonist" ? 25 : 20,
    title: _buildNodeTooltip(e),
  })));

  const edgeList = [];
  const seenEdges = new Set();
  for (const e of validEntities) {
    const rels = Array.isArray(e.relations) ? e.relations : [];
    for (const r of rels) {
      if (!r || !r.target_id) continue;
      const key = [e.id, r.target_id].sort().join("|") + "|" + (r.type || "neutral");
      if (seenEdges.has(key)) continue;
      seenEdges.add(key);
      const label = r.notes ? `${r.type || ""}: ${r.notes}` : (r.type || "");
      edgeList.push({
        from: e.id,
        to: r.target_id,
        label,
        color: { color: _edgeColorForType(r.type), highlight: "#000" },
        arrows: "to",
        width: 2,
      });
    }
  }
  // Global relations array
  const globalRels = Array.isArray(relations) ? relations : [];
  for (const r of globalRels) {
    if (!r || !r.source_id || !r.target_id) continue;
    const key = [r.source_id, r.target_id].sort().join("|") + "|" + (r.type || "neutral");
    if (seenEdges.has(key)) continue;
    seenEdges.add(key);
    const label = r.notes ? `${r.type || ""}: ${r.notes}` : (r.type || "");
    edgeList.push({
      from: r.source_id,
      to: r.target_id,
      label,
      color: { color: _edgeColorForType(r.type), highlight: "#000" },
      arrows: "to",
      width: 2,
    });
  }
  const edges = new vis.DataSet(edgeList);

  if (_charNetwork) { _charNetwork.destroy(); _charNetwork = null; }
  container.innerHTML = "";

  const data = { nodes, edges };
  const options = {
    physics: { solver: "forceAtlas2Based", stabilization: { iterations: 100 } },
    edges: { smooth: { type: "continuous" }, font: { size: 9, strokeWidth: 0 } },
    interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true },
    nodes: { borderWidth: 2, shadow: { enabled: true, size: 6 } },
  };
  _charNetwork = new vis.Network(container, data, options);

  _charNetwork.on("click", function (params) {
    if (params.edges.length > 0) {
      const edge = edges.get(params.edges[0]);
      if (edge) {
        const fromNode = nodes.get(edge.from);
        const toNode = nodes.get(edge.to);
        toast(`${fromNode?.label || edge.from} → ${toNode?.label || edge.to}: ${edge.label || "关系"}`);
      }
    }
  });
}

const CAST_ROLE_COLORS = {
  protagonist_core: "#4caf50",
  supporting_major: "#2196f3",
  supporting_minor: "#9c27b0",
  antagonist: "#f44336",
};
const RELATION_COLORS = {
  // English
  ally: "#4caf50",  enemy: "#f44336",
  neutral: "#ff9800",  complex: "#9c27b0",
  rival: "#ef4444",  debtor: "#f59e0b",
  secret: "#8b5cf6",  vassal: "#6366f1",
  // Chinese (common in user data)
  "盟友": "#4caf50",  "敌对": "#f44336",
  "中立": "#ff9800",  "复杂": "#9c27b0",
  "对手": "#ef4444",  "债务": "#f59e0b",
  "秘密": "#8b5cf6",  "附庸": "#6366f1",
  "航道": "#0ea5e9",  "邻接": "#84cc16",
  "调查轴": "#f97316", "合作": "#22c55e",
  "贸易": "#eab308",  "从属": "#a78bfa",
  "竞争": "#f43f5e",  "宗主": "#3b82f6",
  "朝贡": "#d946ef",  "同盟": "#10b981",
  "交战": "#dc2626",  "冷战": "#64748b",
};
const DEFAULT_NODE_COLOR = "#607d8b";
const DEFAULT_EDGE_COLOR = "#3b82f6";
// Color hash for unknown relation types (keeps them distinguishable)
function _edgeColorForType(type) {
  if (!type) return DEFAULT_EDGE_COLOR;
  if (RELATION_COLORS[type]) return RELATION_COLORS[type];
  // Generate a stable color from the type string
  let hash = 0;
  for (let i = 0; i < type.length; i++) hash = type.charCodeAt(i) + ((hash << 5) - hash);
  const h = Math.abs(hash) % 360;
  return `hsl(${h}, 60%, 45%)`;
}

const FAC_CULT_NODE_COLOR = "#3d5a80";
const FAC_CULT_ROOT_COLOR = "#2c4a6e";
const FAC_CULT_PEER_COLOR = "#607d8b";
const FAC_CULT_EXT_COLOR = "#b8860b";

const CULTURE_KIND_COLORS = {
  culture: "#3d5a80",
  religion: "#7b1fa2",
  syncretic: "#00838f",
};

const CULTURE_RELATION_COLORS = {
  influence: "#4caf50",
  conflict: "#f44336",
  syncretic: "#9c27b0",
  fusion: "#9c27b0",
  subordinate: "#2196f3",
  dominant: "#e91e63",
  tension: "#ff9800",
  neutral: "#90a4ae",
};

let _charNetwork = null;
let _facGlobalNet = null;
let _cultGlobalNet = null;
let _facCardNets = [];
let _cultCardNets = [];

export function renderCharacterNetwork(containerId) {
  const container = $(containerId);
  if (!container) return;
  if (!state.world?.characters?.entities?.length) {
    container.innerHTML = `<p class="muted" style="padding:1rem;text-align:center">暂无角色数据，请先在「人物生成」或「主角团/重要配角」页添加角色。</p>`;
    return;
  }
  // Build nodes and edges from character entities and relations
  const entities = state.world.characters.entities.filter(e => e && typeof e === "object");
  const nodes = new vis.DataSet(entities.map(e => ({
    id: e.id || "",
    label: e.name || e.id || "?",
    color: { background: CAST_ROLE_COLORS[e.cast_role] || DEFAULT_NODE_COLOR, border: "#333" },
    font: { size: 13, color: "#333" },
    shape: "dot",
    size: e.cast_role === "protagonist_core" ? 30 : e.cast_role === "antagonist" ? 25 : 20,
    title: _buildNodeTooltip(e),
  })));
  // Extract edges from relations within entities
  const edgeList = [];
  const seenEdges = new Set();
  for (const e of entities) {
    const rels = e.relations || [];
    for (const r of rels) {
      if (!r.target_id) continue;
      const key = [e.id, r.target_id].sort().join("|") + "|" + (r.type || "neutral");
      if (seenEdges.has(key)) continue;
      seenEdges.add(key);
      const label = r.notes ? `${r.type || ""}: ${r.notes}` : (r.type || "");
      edgeList.push({
        from: e.id,
        to: r.target_id,
        label,
        color: { color: _edgeColorForType(r.type), highlight: "#000" },
        arrows: "to",
        width: 2,
      });
    }
  }
  // Also add relations from characters.relations array
  const charRels = state.world.characters.relations || [];
  for (const r of charRels) {
    if (!r || !r.source_id || !r.target_id) continue;
    const key = [r.source_id, r.target_id].sort().join("|") + "|" + (r.type || "neutral");
    if (seenEdges.has(key)) continue;
    seenEdges.add(key);
    const label = r.notes ? `${r.type || ""}: ${r.notes}` : (r.type || "");
    edgeList.push({
      from: r.source_id,
      to: r.target_id,
      label,
      color: { color: _edgeColorForType(r.type), highlight: "#000" },
      arrows: "to",
      width: 2,
    });
  }
  const edges = new vis.DataSet(edgeList);

  // Dispose previous network
  if (_charNetwork) { _charNetwork.destroy(); _charNetwork = null; }
  container.innerHTML = "";

  const data = { nodes, edges };
  const options = {
    physics: { solver: "forceAtlas2Based", stabilization: { iterations: 100 } },
    edges: { smooth: { type: "continuous" }, font: { size: 9, strokeWidth: 0 } },
    interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true },
    nodes: { borderWidth: 2, shadow: { enabled: true, size: 6 } },
  };
  _charNetwork = new vis.Network(container, data, options);

  // Click handler for edge → show relationship details
  _charNetwork.on("click", function (params) {
    if (params.edges.length > 0) {
      const edgeId = params.edges[0];
      const edge = edges.get(edgeId);
      if (edge) {
        const fromNode = nodes.get(edge.from);
        const toNode = nodes.get(edge.to);
        toast(`${fromNode?.label || edge.from} → ${toNode?.label || edge.to}: ${edge.label || "关系"}`);
      }
    }
  });
}

function _buildNodeTooltip(entity) {
  const parts = [];
  if (entity.name) parts.push(`<strong>${escapeHtml(entity.name)}</strong>`);
  if (entity.cast_role) parts.push(`角色：${escapeHtml(entity.cast_role)}`);
  if (entity.runtime_state) {
    const rs = entity.runtime_state;
    if (rs.location) parts.push(`位置：${escapeHtml(rs.location)}`);
    if (rs.emotion) parts.push(`情绪：${escapeHtml(rs.emotion)}`);
    if (rs.goal) parts.push(`目标：${escapeHtml(rs.goal)}`);
  }
  return parts.join("<br>");
}


// ═══════════════════════════════════════════════════════════════════
// Faction & Culture Interactive Relationship Graphs (vis.js)
// ═══════════════════════════════════════════════════════════════════

function _factionEdgeLabel(r) {
  const t = r.type || "";
  const n = r.notes || "";
  if (t && n) return `${t}: ${n}`;
  if (t) return t;
  if (n) return n;
  return "关联";
}

function _cultureEdgeLabel(r) {
  return _factionEdgeLabel(r);
}

function _factionNodeTooltip(e) {
  const parts = [];
  if (e.name) parts.push(`<strong>${escapeHtml(e.name)}</strong>`);
  if (e.id) parts.push(`ID: ${escapeHtml(e.id)}`);
  if (e.goals) parts.push(`目标: ${escapeHtml(String(e.goals).slice(0, 80))}`);
  if (e.territory) parts.push(`地盘: ${escapeHtml(String(e.territory).slice(0, 80))}`);
  return parts.join("<br>");
}

function _cultureNodeTooltip(e) {
  const parts = [];
  const kindLabel = { culture: "文化", religion: "宗教", syncretic: "融合" };
  if (e.name) parts.push(`<strong>${escapeHtml(e.name)}</strong>`);
  if (e.kind) parts.push(`类型: ${kindLabel[e.kind] || e.kind}`);
  if (e.id) parts.push(`ID: ${escapeHtml(e.id)}`);
  if (e.summary) parts.push(`${escapeHtml(String(e.summary).slice(0, 100))}`);
  return parts.join("<br>");
}

/** Render faction global relationship network using vis.js. */
export function renderFactionGlobalNetwork(entities, containerId) {
  const container = $(containerId);
  if (!container) return;
  if (!entities?.length) {
    container.innerHTML = `<p class="muted" style="padding:1rem;text-align:center">暂无派系数据</p>`;
    return;
  }
  const valid = entities.filter(e => e && typeof e === "object" && e.id);
  if (!valid.length) {
    container.innerHTML = `<p class="muted" style="padding:1rem;text-align:center">暂无派系数据</p>`;
    return;
  }
  const nodesArr = valid.map(e => ({
    id: e.id,
    label: (e.name || e.id || "?").slice(0, 20),
    color: { background: FAC_CULT_NODE_COLOR, border: "#2c4a6e" },
    font: { size: 13, color: "#1a1a1a", strokeWidth: 0 },
    shape: "dot",
    size: 22,
    title: _factionNodeTooltip(e),
  }));

  // Collect all target IDs referenced in relations but not in entities
  const nodeIds = new Set(nodesArr.map(n => n.id));
  const missingNodes = new Map();

  const edgeList = [];
  const seen = new Set();
  for (const e of valid) {
    const rels = Array.isArray(e.relations) ? e.relations : [];
    for (const r of rels) {
      if (!r || !r.target_id || r.target_id === e.id) continue;
      const key = [e.id, r.target_id].sort().join("|") + "|" + (r.type || "");
      if (seen.has(key)) continue;
      seen.add(key);

      // Add missing target as gray node if not in entities
      if (!nodeIds.has(r.target_id) && !missingNodes.has(r.target_id)) {
        missingNodes.set(r.target_id, {
          id: r.target_id,
          label: (r.target_id || "?").slice(0, 20),
          color: { background: "#94a3b8", border: "#64748b" },
          font: { size: 11, color: "#64748b", strokeWidth: 0 },
          shape: "dot", size: 16,
          title: `ID: ${r.target_id}（未在派系列表中建档）`,
        });
      }

      const label = _factionEdgeLabel(r);
      const edgeColor = _edgeColorForType(r.type);
      edgeList.push({
        from: e.id,
        to: r.target_id,
        label,
        color: { color: edgeColor, highlight: "#000" },
        arrows: "to",
        width: 2.5,
        font: { color: "#1565c0", strokeWidth: 0, background: "rgba(255,255,255,0.9)", size: 10 },
      });
    }
  }
  // Append missing nodes BEFORE creating DataSet
  for (const mn of missingNodes.values()) nodesArr.push(mn);

  const nodes = new vis.DataSet(nodesArr);
  const edges = new vis.DataSet(edgeList);

  if (_facGlobalNet) { _facGlobalNet.destroy(); _facGlobalNet = null; }
  container.innerHTML = "";

  // Guard: check vis library is loaded
  if (typeof vis === "undefined" || !vis.Network || !vis.DataSet) {
    container.innerHTML = `<p class="muted" style="padding:1rem;text-align:center">vis-network 库未加载，请刷新页面重试</p>`;
    console.error("[MCW-VIZ] vis-network not loaded — cannot render faction network");
    return;
  }

  const data = { nodes, edges };
  const options = {
    physics: { solver: "forceAtlas2Based", stabilization: { iterations: 100 } },
    edges: { smooth: { type: "continuous" }, font: { size: 9, strokeWidth: 0, color: "#1565c0" } },
    interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true },
    nodes: { borderWidth: 2, shadow: { enabled: true, size: 6 }, font: { color: "#1a1a1a" } },
  };

  try {
    _facGlobalNet = new vis.Network(container, data, options);
  } catch (e) {
    console.error("[MCW-VIZ] Failed to create faction network:", e);
    container.innerHTML = `<p class="muted" style="padding:1rem;text-align:center">派系网络渲染失败：${escapeHtml(String(e.message||e))}</p>`;
    return;
  }

  // Force redraw after attach (fixes height:0 when rendered in hidden tab)
  setTimeout(() => { if (_facGlobalNet) _facGlobalNet.redraw(); }, 100);
  setTimeout(() => { if (_facGlobalNet) _facGlobalNet.fit(); }, 300);

  _facGlobalNet.on("click", function (params) {
    if (params.edges.length > 0) {
      const edge = edges.get(params.edges[0]);
      if (edge) {
        const fromN = nodes.get(edge.from);
        const toN = nodes.get(edge.to);
        toast(`${fromN?.label || edge.from} → ${toN?.label || edge.to}: ${edge.label || "关系"}`);
      }
    }
  });
}

/** Render culture global relationship network using vis.js. */
export function renderCultureGlobalNetwork(entities, containerId) {
  const container = $(containerId);
  if (!container) return;
  if (!entities?.length) {
    container.innerHTML = `<p class="muted" style="padding:1rem;text-align:center">暂无文化/宗教数据</p>`;
    return;
  }
  const valid = entities.filter(e => e && typeof e === "object" && e.id);
  if (!valid.length) {
    container.innerHTML = `<p class="muted" style="padding:1rem;text-align:center">暂无文化/宗教数据</p>`;
    return;
  }
  const nodesArr = valid.map(e => ({
    id: e.id,
    label: (e.name || e.id || "?").slice(0, 20),
    color: { background: CULTURE_KIND_COLORS[e.kind] || FAC_CULT_NODE_COLOR, border: "#333" },
    font: { size: 13, color: "#1a1a1a", strokeWidth: 0 },
    shape: "dot",
    size: 22,
    title: _cultureNodeTooltip(e),
  }));
  const nodes = new vis.DataSet(nodesArr);

  const edgeList = [];
  const seen = new Set();
  for (const e of valid) {
    const rels = Array.isArray(e.relations) ? e.relations : [];
    for (const r of rels) {
      if (!r || !r.target_id || r.target_id === e.id) continue;
      const key = [e.id, r.target_id].sort().join("|") + "|" + (r.type || "");
      if (seen.has(key)) continue;
      seen.add(key);
      const label = _cultureEdgeLabel(r);
      edgeList.push({
        from: e.id,
        to: r.target_id,
        label,
        color: { color: _edgeColorForType(r.type), highlight: "#000" },
        arrows: "to",
        width: 2,
        font: { color: "#1565c0", strokeWidth: 0, background: "rgba(255,255,255,0.85)" },
      });
    }
  }
  const edges = new vis.DataSet(edgeList);

  if (_cultGlobalNet) { _cultGlobalNet.destroy(); _cultGlobalNet = null; }
  container.innerHTML = "";

  const data = { nodes, edges };
  const options = {
    physics: { solver: "forceAtlas2Based", stabilization: { iterations: 100 } },
    edges: { smooth: { type: "continuous" }, font: { size: 9, strokeWidth: 0, color: "#1565c0" } },
    interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true },
    nodes: { borderWidth: 2, shadow: { enabled: true, size: 6 }, font: { color: "#1a1a1a" } },
  };
  _cultGlobalNet = new vis.Network(container, data, options);

  _cultGlobalNet.on("click", function (params) {
    if (params.edges.length > 0) {
      const edge = edges.get(params.edges[0]);
      if (edge) {
        const fromN = nodes.get(edge.from);
        const toN = nodes.get(edge.to);
        toast(`${fromN?.label || edge.from} → ${toN?.label || edge.to}: ${edge.label || "关系"}`);
      }
    }
  });
}

/** Render a single faction's ego-centric relationship network. */
export function renderSingleFactionNetwork(entity, allEntities, container) {
  if (!container || !entity) return;
  const all = Array.isArray(allEntities) ? allEntities : [];
  const nodesArr = [];
  const edgeList = [];
  const seen = new Set();

  // Root node
  const rootId = entity.id || "root";
  const rootLabel = (entity.name || rootId || "?").slice(0, 20);
  nodesArr.push({
    id: rootId,
    label: rootLabel,
    color: { background: FAC_CULT_NODE_COLOR, border: "#2c4a6e" },
    font: { size: 14, color: "#1a1a1a", strokeWidth: 0 },
    shape: "dot",
    size: 26,
    title: _factionNodeTooltip(entity),
  });

  const rels = Array.isArray(entity.relations) ? entity.relations : [];
  for (const r of rels) {
    const tid = r?.target_id;
    if (!tid || tid === rootId) continue;
    const key = [rootId, tid].sort().join("|") + "|" + (r.type || "");
    if (seen.has(key)) continue;
    seen.add(key);

    const target = all.find(x => x.id === tid);
    const isKnown = !!target;
    const peerLabel = isKnown ? (target.name || tid).slice(0, 20) : `${(tid || "?").slice(0, 16)}…`;
    nodesArr.push({
      id: tid,
      label: peerLabel,
      color: {
        background: isKnown ? FAC_CULT_PEER_COLOR : FAC_CULT_EXT_COLOR,
        border: isKnown ? "#455a64" : "#8b6914",
      },
      font: { size: 12, color: "#1a1a1a", strokeWidth: 0 },
      shape: "dot",
      size: isKnown ? 18 : 14,
      title: target ? _factionNodeTooltip(target) : `ID: ${escapeHtml(tid)}（未建档）`,
    });

    const label = _factionEdgeLabel(r);
    edgeList.push({
      from: rootId,
      to: tid,
      label,
      color: { color: _edgeColorForType(r.type), highlight: "#000" },
      arrows: "to",
      width: isKnown ? 2.5 : 1.5,
      dashes: !isKnown,
      font: { color: "#1565c0", strokeWidth: 0, background: "rgba(255,255,255,0.85)" },
    });
  }

  if (edgeList.length === 0) {
    container.innerHTML = `<p class="muted" style="padding:0.5rem;text-align:center;font-size:12px">暂无关系边</p>`;
    return;
  }

  // Clean up previous network in this container
  const idx = _facCardNets.findIndex(n => n.container === container);
  if (idx >= 0) {
    _facCardNets[idx].net.destroy();
    _facCardNets.splice(idx, 1);
  }

  container.innerHTML = "";
  const nodes = new vis.DataSet(nodesArr);
  const edges = new vis.DataSet(edgeList);
  const data = { nodes, edges };
  const options = {
    physics: { solver: "forceAtlas2Based", stabilization: { iterations: 80 } },
    edges: { smooth: { type: "continuous" }, font: { size: 8, strokeWidth: 0, color: "#1565c0" } },
    interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true },
    nodes: { borderWidth: 2, font: { color: "#1a1a1a" } },
  };
  const net = new vis.Network(container, data, options);
  _facCardNets.push({ container, net });

  net.on("click", function (params) {
    if (params.edges.length > 0) {
      const edge = edges.get(params.edges[0]);
      if (edge) {
        const fromN = nodes.get(edge.from);
        const toN = nodes.get(edge.to);
        toast(`${fromN?.label || edge.from} → ${toN?.label || edge.to}: ${edge.label || "关系"}`);
      }
    }
  });
}

/** Render a single culture's ego-centric relationship network. */
export function renderSingleCultureNetwork(entity, allEntities, container) {
  if (!container || !entity) return;
  const all = Array.isArray(allEntities) ? allEntities : [];
  const nodesArr = [];
  const edgeList = [];
  const seen = new Set();

  const rootId = entity.id || "root";
  const rootLabel = (entity.name || rootId || "?").slice(0, 20);
  nodesArr.push({
    id: rootId,
    label: rootLabel,
    color: { background: CULTURE_KIND_COLORS[entity.kind] || FAC_CULT_NODE_COLOR, border: "#333" },
    font: { size: 14, color: "#1a1a1a", strokeWidth: 0 },
    shape: "dot",
    size: 26,
    title: _cultureNodeTooltip(entity),
  });

  const rels = Array.isArray(entity.relations) ? entity.relations : [];
  for (const r of rels) {
    const tid = r?.target_id;
    if (!tid || tid === rootId) continue;
    const key = [rootId, tid].sort().join("|") + "|" + (r.type || "");
    if (seen.has(key)) continue;
    seen.add(key);

    const target = all.find(x => x.id === tid);
    const isKnown = !!target;
    const peerLabel = isKnown ? (target.name || tid).slice(0, 20) : `${(tid || "?").slice(0, 16)}…`;
    const kindColor = target ? (CULTURE_KIND_COLORS[target.kind] || FAC_CULT_PEER_COLOR) : FAC_CULT_EXT_COLOR;
    nodesArr.push({
      id: tid,
      label: peerLabel,
      color: {
        background: isKnown ? kindColor : FAC_CULT_EXT_COLOR,
        border: isKnown ? "#333" : "#8b6914",
      },
      font: { size: 12, color: "#1a1a1a", strokeWidth: 0 },
      shape: "dot",
      size: isKnown ? 18 : 14,
      title: target ? _cultureNodeTooltip(target) : `ID: ${escapeHtml(tid)}（未建档）`,
    });

    const label = _cultureEdgeLabel(r);
    edgeList.push({
      from: rootId,
      to: tid,
      label,
      color: { color: _edgeColorForType(r.type), highlight: "#000" },
      arrows: "to",
      width: isKnown ? 2 : 1,
      dashes: !isKnown,
      font: { color: "#1565c0", strokeWidth: 0, background: "rgba(255,255,255,0.85)" },
    });
  }

  if (edgeList.length === 0) {
    container.innerHTML = `<p class="muted" style="padding:0.5rem;text-align:center;font-size:12px">暂无关系边</p>`;
    return;
  }

  const idx = _cultCardNets.findIndex(n => n.container === container);
  if (idx >= 0) {
    _cultCardNets[idx].net.destroy();
    _cultCardNets.splice(idx, 1);
  }

  container.innerHTML = "";
  const nodes = new vis.DataSet(nodesArr);
  const edges = new vis.DataSet(edgeList);
  const data = { nodes, edges };
  const options = {
    physics: { solver: "forceAtlas2Based", stabilization: { iterations: 80 } },
    edges: { smooth: { type: "continuous" }, font: { size: 8, strokeWidth: 0, color: "#1565c0" } },
    interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true },
    nodes: { borderWidth: 2, font: { color: "#1a1a1a" } },
  };
  const net = new vis.Network(container, data, options);
  _cultCardNets.push({ container, net });

  net.on("click", function (params) {
    if (params.edges.length > 0) {
      const edge = edges.get(params.edges[0]);
      if (edge) {
        const fromN = nodes.get(edge.from);
        const toN = nodes.get(edge.to);
        toast(`${fromN?.label || edge.from} → ${toN?.label || edge.to}: ${edge.label || "关系"}`);
      }
    }
  });
}


// ═══════════════════════════════════════════════════════════════════
// Init: wire up P2 UI elements
// ═══════════════════════════════════════════════════════════════════

export function initP2Enhancements() {
  // Export dropdown buttons
  document.querySelectorAll(".export-format-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const fmt = btn.dataset.format;
      if (fmt) void exportStoryFormat(fmt);
    });
  });

  // Version history button — delegate click
  document.addEventListener("click", (e) => {
    if (e.target.closest("#btnChapterVersionHistory")) {
      if (state.storyActiveChapterId) void showChapterVersionHistory(state.storyActiveChapterId);
    }
  });

  // Character relation network — render when host becomes visible
  const charNetHost = document.getElementById("charNetworkHost");
  if (charNetHost) {
    const observer = new MutationObserver(() => {
      if (charNetHost.offsetParent !== null && state.world?.characters?.entities?.length) {
        renderCharacterNetwork("charNetworkHost");
      }
    });
    observer.observe(charNetHost, { attributes: true, attributeFilter: ["class", "style"] });
    // Also observe parent for display changes
    const parent = charNetHost.parentElement;
    if (parent) {
      observer.observe(parent, { attributes: true, attributeFilter: ["class", "style"] });
    }
  }
}
