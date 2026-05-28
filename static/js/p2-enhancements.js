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
  const chRows = (d.chapter_progress || []).map(c => {
    const pct = d.total_words > 0 ? Math.round(c.word_count / Math.max(1, d.total_words) * 100) : 0;
    const statusLabels = { locked: "已锁定", completed: "已完成", drafting: "草稿", outline: "大纲" };
    const st = statusLabels[c.status] || c.status || "大纲";
    return `<tr>
      <td class="stats-ch-order">${c.order}</td>
      <td>${escapeHtml(c.title || "")}</td>
      <td class="stats-ch-words">${c.word_count.toLocaleString()}</td>
      <td><span class="pill-sm pill-${c.status || 'outline'}">${st}</span></td>
      <td><div class="stats-mini-bar"><div class="stats-mini-bar-fill" style="width:${pct}%"></div></div></td>
    </tr>`;
  }).join("");

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
        <span class="stats-hero-num">${prog.completed || 0}/${prog.locked || 0}</span>
        <span class="stats-hero-label">完成/锁定</span>
      </div>
    </div>
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
      edgeList.push({
        from: e.id,
        to: r.target_id,
        label: r.type || "",
        color: { color: RELATION_COLORS[r.type] || DEFAULT_EDGE_COLOR, highlight: "#000" },
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
    edgeList.push({
      from: r.source_id,
      to: r.target_id,
      label: r.type || "",
      color: { color: RELATION_COLORS[r.type] || DEFAULT_EDGE_COLOR, highlight: "#000" },
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
  ally: "#4caf50",
  enemy: "#f44336",
  neutral: "#ff9800",
  complex: "#9c27b0",
};
const DEFAULT_NODE_COLOR = "#607d8b";
const DEFAULT_EDGE_COLOR = "#90a4ae";

let _charNetwork = null;

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
      edgeList.push({
        from: e.id,
        to: r.target_id,
        label: r.type || "",
        color: { color: RELATION_COLORS[r.type] || DEFAULT_EDGE_COLOR, highlight: "#000" },
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
    edgeList.push({
      from: r.source_id,
      to: r.target_id,
      label: r.type || "",
      color: { color: RELATION_COLORS[r.type] || DEFAULT_EDGE_COLOR, highlight: "#000" },
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
