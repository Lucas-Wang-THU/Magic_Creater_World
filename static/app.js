const $ = (id) => document.getElementById(id);

const state = {
  world: null,
  messages: [],
  dirty: false,
  activeView: "chat",
  /** 境界页子页：system | trees | professions */
  powerSubView: "system",
  /** 各世界观子页是否允许编辑表单（默认开启） */
  worldviewEditMode: {
    geo: true,
    powers: true,
    attributes: true,
    items: true,
    cultures: true,
    factions: true,
    history: true,
  },
};

const API = "";

/** 切换世界时清空搜索 UI，避免命中仍显示上一世界 */
let _searchPanelWorldId = null;

const VIEW_TO_SCOPE = {
  geo: "geography",
  powers: "power_system",
  attributes: "attribute_system",
  items: "item_quality_system",
  cultures: "cultures",
  factions: "factions",
  history: "history",
};

/** 主导航中「世界观」各子页（不含对话 / 大纲 / 文件） */
const WORLDVIEW_EDIT_PANEL_IDS = [
  "geo",
  "powers",
  "attributes",
  "items",
  "cultures",
  "factions",
  "history",
];

const WORLDVIEW_EDIT_LABELS = {
  geo: "地理",
  powers: "境界体系",
  attributes: "通用人物属性",
  items: "物品品质",
  cultures: "文化与宗教",
  factions: "派系",
  history: "历史",
};

function isWorldviewPanelEditEnabled(panelId) {
  return state.worldviewEditMode[panelId] !== false;
}

function shouldSkipWorldviewEditLock(el, panelRoot) {
  if (!el || !panelRoot || !panelRoot.contains(el)) return true;
  if (el.closest("[data-edit-mode-toolbar]")) return true;
  if (el.closest(".mermaid-zoom-toolbar")) return true;
  if (el.closest(".panel-subtabs")) return true;
  return false;
}

function applyWorldviewPanelEditMode(panelId) {
  const enabled = isWorldviewPanelEditEnabled(panelId);
  const root = document.getElementById(`view-${panelId}`);
  if (!root) return;
  root.classList.toggle("worldview-panel--readonly", !enabled);
  const sw = document.getElementById(`editModeSwitch-${panelId}`);
  if (sw) sw.checked = enabled;
  root.querySelectorAll("textarea").forEach((el) => {
    if (shouldSkipWorldviewEditLock(el, root)) return;
    el.readOnly = !enabled;
  });
  root.querySelectorAll("select").forEach((el) => {
    if (shouldSkipWorldviewEditLock(el, root)) return;
    el.disabled = !enabled;
  });
  root.querySelectorAll("input").forEach((el) => {
    if (shouldSkipWorldviewEditLock(el, root)) return;
    if (el.type === "hidden") return;
    const t = (el.type || "text").toLowerCase();
    if (t === "checkbox" || t === "radio") el.disabled = !enabled;
    else if (t === "button" || t === "submit" || t === "reset") el.disabled = !enabled;
    else el.readOnly = !enabled;
  });
  root.querySelectorAll("button").forEach((btn) => {
    if (shouldSkipWorldviewEditLock(btn, root)) return;
    if (btn.closest(".panel-subtabs")) return;
    if (btn.closest(".mermaid-zoom-toolbar")) return;
    btn.disabled = !enabled;
  });
}

function applyAllWorldviewEditModes() {
  for (const id of WORLDVIEW_EDIT_PANEL_IDS) applyWorldviewPanelEditMode(id);
}

function ensureWorldviewEditModeToolbars() {
  for (const panelId of WORLDVIEW_EDIT_PANEL_IDS) {
    const root = document.getElementById(`view-${panelId}`);
    if (!root) continue;
    const card = root.querySelector(".card");
    if (!card || card.querySelector("[data-edit-mode-toolbar]")) continue;
    const bar = document.createElement("div");
    bar.className = "edit-mode-toolbar";
    bar.dataset.editModeToolbar = "1";
    const swId = `editModeSwitch-${panelId}`;
    const lab = WORLDVIEW_EDIT_LABELS[panelId] || panelId;
    bar.innerHTML = `<label class="edit-mode-toggle lbl-ic" title="关闭后本页设定为只读展示，避免误改；关系图仍可缩放。">
      <span class="ms edit-mode-ic" aria-hidden="true">edit_note</span>
      <span class="edit-mode-label">编辑模式</span>
      <input type="checkbox" id="${swId}" class="edit-mode-cb" aria-label="${lab}：允许编辑设定" />
    </label>`;
    const h2 = card.querySelector("h2");
    if (h2) h2.insertAdjacentElement("afterend", bar);
    else card.prepend(bar);
    const cb = document.getElementById(swId);
    if (cb) {
      cb.checked = isWorldviewPanelEditEnabled(panelId);
      cb.addEventListener("change", () => {
        state.worldviewEditMode[panelId] = cb.checked;
        applyWorldviewPanelEditMode(panelId);
      });
    }
  }
  applyAllWorldviewEditModes();
}

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2800);
}

const GENRE_MODE_HINTS = {
  "": "未选择时：对话仍用通用架构师；若世界已保存载体，则对话/同步/大纲会沿用该载体。",
  novel: "小说：叙事弧线、人物动机与伏笔；地理请按 geography（summary / regions 的 id·relations·短名列表）写，便于同步与关系图。",
  game: "游戏：成长与任务链、系统边界；地理请按 regions[].id 与 relations 写，便于任务引用与区域解锁。",
  coc: "CoC：调查链、理智与神话代价；地理请把可调查点与压力写进 regions[].landmarks / notes，短名列表利落后端归一。",
  dnd: "DnD：冒险引导、遭遇与对抗边界；地理请写清 regions[].terrain、notes 与 relations，便于裁定旅行与遭遇。",
};

function updateGenreModeHint() {
  const el = $("genreModeHint");
  const sel = $("genreMode");
  if (!el || !sel) return;
  el.textContent = GENRE_MODE_HINTS[sel.value] ?? GENRE_MODE_HINTS[""];
}

/** 文化·宗教页：字段说明 + 随创作模式变化的写作/同步侧重 */
const CULTURE_MODULE_HINT =
  "每条实体须有唯一 id；relations 的 target_id 指向另一文化实体 id。kind：文化=习俗与族群叙事，宗教=教团/神话组织，融合=综摄或混血传统。对话后结构化同步的顶层键为 cultures。";

const CULTURE_GENRE_HINTS = {
  "": "未选创作模式：仍可写民俗、禁忌、教团；同步会按通用规则写入 cultures。",
  novel:
    "小说侧重：信仰如何塑造日常选择、仪式与秘密教义的叙事张力；与派系/地理挂钩时请用稳定 id，便于关系图与第二路 JSON。",
  game:
    "游戏侧重：节日与声望系统、阵营 Buff 文案、可做成活动或副本的圣地；实体可对应可刷新的「文化标签」或势力声望。",
  coc:
    "CoC 侧重：民间禁忌、密教变体、调查员易忽视的「正常中的异常」；教团与神话线索可与 factions 并行，勿把一切都写成战斗数值。",
  dnd:
    "DnD 侧重：神殿网络、圣徽、阵营意识形态、可扮演钩子；与派系据点、任务发布者交叉时用 id 引用，便于 DM 快速裁定。",
};

function updateCultureHint() {
  const el = $("cultureHintPanel");
  const sel = $("genreMode");
  if (!el) return;
  const g = sel?.value ?? "";
  el.textContent = `${CULTURE_MODULE_HINT} ${CULTURE_GENRE_HINTS[g] ?? CULTURE_GENRE_HINTS[""]}`;
}

async function api(path, opts = {}) {
  const r = await fetch(API + path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  const text = await r.text();
  let data;
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { _raw: text };
  }
  if (!r.ok) {
    const detail = data.detail ?? data._raw ?? r.statusText;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function setDirty(v) {
  state.dirty = v;
  const el = $("saveStatus");
  if (!el) return;
  const icon = v ? "edit_note" : "cloud_done";
  const label = v ? "有未保存更改" : "已同步";
  el.innerHTML = `<span class="ms status-ic" aria-hidden="true">${icon}</span>${label}`;
  el.classList.toggle("dirty", v);
}

function syncScopeForRequest() {
  if (!$("syncScopeToView")?.checked) return "all";
  return VIEW_TO_SCOPE[state.activeView] || "all";
}

function hasWorldsInSelect() {
  const sel = $("worldSelect");
  if (!sel || !sel.options.length) return false;
  const v = sel.value;
  return Boolean(v && v.trim());
}

function updateEmptyState() {
  const main = $("mainArea");
  const empty = $("emptyState");
  if (!main || !empty) return;
  const has = hasWorldsInSelect();
  main.classList.toggle("main--empty", !has);
  const layout = document.querySelector(".layout");
  if (layout) layout.classList.toggle("layout--no-world", !has);
  const sel = $("worldSelect");
  if (sel) sel.disabled = !has;
}

async function createWorldFlow() {
  const name = prompt("新世界名称？", "我的世界观");
  if (!name || !name.trim()) return;
  const data = await api("/api/worlds", {
    method: "POST",
    body: JSON.stringify({ name: name.trim() }),
  });
  await refreshWorldSelect(data.world.meta.id);
  updateEmptyState();
  await loadWorld(data.world.meta.id);
  toast("世界已创建");
}

async function renameCurrentWorldFlow() {
  if (!state.world) return toast("请先选择世界");
  const cur = state.world.meta.name;
  const name = prompt("新的世界显示名称？", cur);
  if (!name || !name.trim()) return;
  const trimmed = name.trim();
  if (trimmed === cur) return;
  const w = await api(`/api/worlds/${state.world.meta.id}`, {
    method: "PATCH",
    body: JSON.stringify({ name: trimmed }),
  });
  state.world = w;
  worldToForm(w);
  setDirty(false);
  await refreshWorldSelect(w.meta.id);
  refreshContextPanel();
  refreshOutlineHeader();
  refreshFilesView();
  refreshSearchView();
  refreshWorldTabTitle();
  toast("已重命名（目录 id 未变）");
}

async function deleteCurrentWorldFlow() {
  if (!state.world) return toast("请先选择世界");
  const id = state.world.meta.id;
  const name = state.world.meta.name;
  if (
    !confirm(
      `确定删除世界「${name}」？\n目录：worlds/${id}/\n将删除 world.json、world.md、大纲与对话记录等全部文件，且不可恢复。`
    )
  )
    return;
  await api(`/api/worlds/${id}`, { method: "DELETE" });
  toast("世界已删除");
  state.messages = [];
  renderMessages();
  await refreshWorldSelect();
  updateEmptyState();
  if (hasWorldsInSelect()) await loadWorld($("worldSelect").value);
  else {
    state.world = null;
    worldToForm(null);
    setDirty(false);
    refreshWorldTabTitle();
  }
}

/** 派系图：不压缩宽度、略放大字号，便于阅读 */
function mermaidFactionInit() {
  return (
    "%%{init:" +
    JSON.stringify({
      flowchart: {
        useMaxWidth: false,
        padding: 22,
        nodeSpacing: 56,
        rankSpacing: 58,
        curve: "basis",
      },
      themeVariables: {
        fontSize: "16px",
        fontFamily: "system-ui, 'Noto Sans SC', sans-serif",
      },
    }) +
    "}%%\n"
  );
}

function mermaidEscape(s) {
  return String(s || "")
    .replace(/"/g, "'")
    .replace(/[[\]]/g, " ")
    .replace(/\n/g, " ")
    .replace(/\|/g, "·")
    .slice(0, 56);
}

function buildFactionMermaid(entities) {
  if (!entities?.length) return mermaidFactionInit() + 'flowchart TB\n  empty["（无派系）"]';
  const lines = [
    "flowchart LR",
    "  classDef fvN fill:#f0f4f8,color:#1e293b,stroke:#94a3b8",
  ];
  entities.forEach((e, i) => {
    lines.push(`  N${i}["${mermaidEscape(e.name || e.id)}"]`);
  });
  entities.forEach((e, i) => {
    (e.relations || []).forEach((r) => {
      const j = entities.findIndex((x) => x.id === r.target_id);
      if (j < 0 || j === i) return;
      const lab = mermaidEscape(`${r.type || "关联"}${r.notes ? " · " + r.notes : ""}`);
      lines.push(`  N${i} -->|"${lab}"| N${j}`);
    });
  });
  const cls = entities.map((_, i) => `N${i}`).join(",");
  if (cls) lines.push(`  class ${cls} fvN`);
  return mermaidFactionInit() + lines.join("\n");
}

function buildCultureMermaid(entities) {
  if (!entities?.length) return mermaidFactionInit() + 'flowchart TB\n  empty["（无文化/宗教条目）"]';
  const lines = [
    "flowchart LR",
    "  classDef cvN fill:#f5f0f8,color:#1e293b,stroke:#94a3b8",
  ];
  entities.forEach((e, i) => {
    const k = e.kind === "religion" ? "宗" : e.kind === "syncretic" ? "融" : "文";
    const lab = mermaidEscape(`${k}·${e.name || e.id}`);
    lines.push(`  K${i}["${lab}"]`);
  });
  entities.forEach((e, i) => {
    (e.relations || []).forEach((r) => {
      const j = entities.findIndex((x) => x.id === r.target_id);
      if (j < 0 || j === i) return;
      const lab = mermaidEscape(`${r.type || "关联"}${r.notes ? " · " + r.notes : ""}`);
      lines.push(`  K${i} -->|"${lab}"| K${j}`);
    });
  });
  const cls = entities.map((_, i) => `K${i}`).join(",");
  if (cls) lines.push(`  class ${cls} cvN`);
  return mermaidFactionInit() + lines.join("\n");
}

/** 职业晋升：相邻境界相同 professions[].id 视为同线晋升；跨多境为虚线 */
function buildProfessionPromotionMermaid(tiers, ps) {
  const init = mermaidFactionInit();
  const tierList = Array.isArray(tiers) ? tiers : [];
  const byTier = Array.isArray(ps?.by_tier) ? ps.by_tier : [];
  const n = tierList.length;
  if (!n) return init + 'flowchart TB\n  promoEmpty["（无境界数据）"]';

  const lines = ["flowchart TB"];
  lines.push("  classDef profNode fill:#eef2ff,color:#1e293b,stroke:#6366f1,stroke-width:1.2px");
  lines.push("  classDef profFaction fill:#fffbeb,color:#92400e,stroke:#f59e0b,stroke-width:1.2px");
  lines.push("  classDef profGhost fill:#f1f5f9,color:#64748b,stroke:#94a3b8,stroke-dasharray:4 3");

  const factionClassNodes = [];
  const normalClassNodes = [];
  const ghostClassNodes = [];
  const idToOccurrences = new Map();

  for (let i = 0; i < n; i++) {
    const tierName = (tierList[i]?.name || "").trim() || `境 ${i + 1}`;
    const profs = (byTier[i]?.professions) || [];
    const seenRid = new Set();
    const rows = [];
    for (let j = 0; j < profs.length; j++) {
      const p = profs[j] || {};
      const rawId = String(p.id ?? "").trim();
      if (rawId) {
        if (seenRid.has(rawId)) continue;
        seenRid.add(rawId);
      }
      rows.push({ p, rawId });
    }

    const subLabel = mermaidEscape(`${i + 1}·${tierName}`);
    lines.push(`  subgraph sg${i}["${subLabel}"]`);
    if (!rows.length) {
      const eid = `sg${i}_empty`;
      lines.push(`    ${eid}["（本境无职业）"]`);
      ghostClassNodes.push(eid);
    } else {
      rows.forEach((row, k) => {
        const nodeId = `pr${i}_${k}`;
        const { p, rawId } = row;
        const nm = (p.name || "").trim();
        const dispName = mermaidEscape(nm || rawId || "未命名");
        const idPart = rawId ? mermaidEscape(rawId.slice(0, 44)) : "无id";
        let label = `${dispName}<br/>id·${idPart}`;
        const fac = String(p.exclusive_faction_id ?? "").trim();
        if (fac) label += `<br/>派系 ${mermaidEscape(fac.slice(0, 26))}`;
        lines.push(`    ${nodeId}["${label}"]`);
        if (fac) factionClassNodes.push(nodeId);
        else normalClassNodes.push(nodeId);

        if (rawId) {
          const arr = idToOccurrences.get(rawId) || [];
          arr.push({ tierIdx: i, nodeId });
          idToOccurrences.set(rawId, arr);
        }
      });
    }
    lines.push("  end");
  }

  let edgeCount = 0;
  idToOccurrences.forEach((occ) => {
    occ.sort((a, b) => a.tierIdx - b.tierIdx);
    for (let k = 1; k < occ.length; k++) {
      const prev = occ[k - 1];
      const cur = occ[k];
      const gap = cur.tierIdx - prev.tierIdx;
      if (gap < 1) continue;
      if (gap === 1) {
        lines.push(`  ${prev.nodeId} -->|"晋升"| ${cur.nodeId}`);
        edgeCount++;
      } else if (gap > 1) {
        const gl = mermaidEscape(`跨${gap}境`);
        lines.push(`  ${prev.nodeId} -.->|"${gl}"| ${cur.nodeId}`);
        edgeCount++;
      }
    }
  });

  if (ghostClassNodes.length) lines.push(`  class ${ghostClassNodes.join(",")} profGhost`);
  if (normalClassNodes.length) lines.push(`  class ${normalClassNodes.join(",")} profNode`);
  if (factionClassNodes.length) lines.push(`  class ${factionClassNodes.join(",")} profFaction`);

  if (!idToOccurrences.size) {
    lines.push('  promoHint["（各境职业均未填写 id，无法推断晋升线）"]');
  } else if (edgeCount === 0) {
    lines.push('  promoHint2["相邻境界暂无相同 id；多境复用同一 id 即可显示晋升箭头"]');
  }

  return init + lines.join("\n");
}

function refreshProfessionPromotionViz() {
  const host = $("vizProfessionPromoHost");
  if (!host) return;
  const w = state.world;
  if (!w?.power_system?.tiers?.length) {
    host.innerHTML = "";
    return;
  }
  const tiers = w.power_system.tiers;
  const ps = w.power_system.profession_system || {};
  void drawMermaidHost(host, buildProfessionPromotionMermaid(tiers, ps));
}

const TIER_BLOCK_ICONS = {
  caps: "bolt",
  lims: "gavel",
  ex: "emoji_objects",
  mean: "diamond",
  fx: "flare",
  bind: "link",
};

function tierBlockHead(title, variant) {
  const ic = TIER_BLOCK_ICONS[variant] || "label";
  const v = variant ? escapeHtml(variant) : "";
  return `<header class="tier-viz-block__head">
    <span class="ms tier-viz-block__ic" aria-hidden="true">${ic}</span>
    <h4 class="tier-viz-h">${escapeHtml(title)}</h4>
  </header>`;
}

/** 看板：列表字段块（带图标头） */
function htmlStrListBlock(title, items, emptyHint, variant) {
  const arr = Array.isArray(items) ? items.map((x) => String(x).trim()).filter(Boolean) : [];
  const vcls = variant ? ` tier-viz-block--${variant}` : "";
  const dataV = variant ? ` data-variant="${escapeHtml(variant)}"` : "";
  if (!arr.length) {
    return `<section class="tier-viz-block${vcls}"${dataV}>
      ${tierBlockHead(title, variant)}
      <div class="tier-viz-block__body"><p class="tier-viz-empty">${escapeHtml(emptyHint)}</p></div>
    </section>`;
  }
  return `<section class="tier-viz-block${vcls}"${dataV}>
    ${tierBlockHead(title, variant)}
    <div class="tier-viz-block__body">
      <ul class="tier-viz-ul">${arr.map((x) => `<li class="tier-viz-li"><span class="tier-viz-li-text">${escapeHtml(x)}</span></li>`).join("")}</ul>
    </div>
  </section>`;
}

function htmlProseBlock(title, text, emptyHint, variant) {
  const t = (text || "").trim();
  const vcls = variant ? ` tier-viz-block--${variant}` : "";
  const dataV = variant ? ` data-variant="${escapeHtml(variant)}"` : "";
  if (!t) {
    return `<section class="tier-viz-block${vcls}"${dataV}>
      ${tierBlockHead(title, variant)}
      <div class="tier-viz-block__body"><p class="tier-viz-empty">${escapeHtml(emptyHint)}</p></div>
    </section>`;
  }
  return `<section class="tier-viz-block${vcls}"${dataV}>
    ${tierBlockHead(title, variant)}
    <div class="tier-viz-block__body"><p class="tier-viz-prose">${escapeHtml(t).replace(/\n/g, "<br/>")}</p></div>
  </section>`;
}

function escapeAttr(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;");
}

/** 物品档位卡片内：可编辑字段（与 collectItemGradesFromViz 的 data-item-field 对应） */
function htmlItemGradeEditableField(fieldKey, title, value, placeholder, variant) {
  const v = (value ?? "").toString();
  const vcls = variant ? ` tier-viz-block--${variant}` : "";
  const dataV = variant ? ` data-variant="${escapeHtml(variant)}"` : "";
  const ph = escapeHtml(placeholder || "");
  const rows = fieldKey === "examples" ? 4 : 5;
  return `<section class="tier-viz-block item-grade-edit-block${vcls}"${dataV}>
    ${tierBlockHead(title, variant)}
    <div class="tier-viz-block__body">
      <textarea class="item-grade-edit-ta" rows="${rows}" data-item-field="${escapeHtml(
    fieldKey
  )}" spellcheck="true" placeholder="${ph}">${escapeHtml(v)}</textarea>
    </div>
  </section>`;
}

function collectItemGradesFromViz() {
  const root = $("vizItemGradesRoot");
  if (!root) return null;
  const cards = [...root.querySelectorAll(".item-grade-viz[data-item-grade-index]")].sort(
    (a, b) =>
      Number.parseInt(a.getAttribute("data-item-grade-index") || "0", 10) -
      Number.parseInt(b.getAttribute("data-item-grade-index") || "0", 10)
  );
  if (!cards.length) return null;
  return cards.map((card) => {
    const valOf = (field) =>
      (
        card.querySelector(`textarea[data-item-field="${field}"],input[data-item-field="${field}"]`)
          ?.value ?? ""
      ).toString();
    const name = valOf("name").trim() || "未命名档位";
    const examples = valOf("examples")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    return {
      name,
      rarity_narrative: valOf("rarity_narrative").trim(),
      typical_effects: valOf("typical_effects").trim(),
      binding_rules: valOf("binding_rules").trim(),
      examples,
    };
  });
}

let _itemGradeVizSyncTimer;
function scheduleSyncItemGradesFromVizToStateAndJson() {
  clearTimeout(_itemGradeVizSyncTimer);
  _itemGradeVizSyncTimer = setTimeout(() => {
    const g = collectItemGradesFromViz();
    if (g == null || !state.world) return;
    state.world.item_quality_system = state.world.item_quality_system || {};
    state.world.item_quality_system.grades = g;
    const ta = $("itemGradesJson");
    if (ta) ta.value = JSON.stringify(g, null, 2);
    setDirty(true);
  }, 200);
}

function scheduleItemGradesVizFromForm() {
  try {
    const grades = JSON.parse($("itemGradesJson")?.value || "[]");
    if (!state.world || !Array.isArray(grades)) return;
    const w = structuredClone(state.world);
    w.item_quality_system = w.item_quality_system || {};
    w.item_quality_system.grades = grades;
    renderItemGradeDashboardModules(w);
    applyAllWorldviewEditModes();
  } catch (_) {
    /* JSON 未完成输入时不刷新卡片 */
  }
}

/** 境界体系卡片：可编辑字段（data-power-field） */
function htmlPowerTierEditableField(fieldKey, title, value, placeholder, variant, rows) {
  const v = (value ?? "").toString();
  const vcls = variant ? ` tier-viz-block--${variant}` : "";
  const dataV = variant ? ` data-variant="${escapeHtml(variant)}"` : "";
  const ph = escapeHtml(placeholder || "");
  const r = rows || 4;
  return `<section class="tier-viz-block power-tier-edit-block${vcls}"${dataV}>
    ${tierBlockHead(title, variant)}
    <div class="tier-viz-block__body">
      <textarea class="power-tier-edit-ta" rows="${r}" data-power-field="${escapeHtml(
    fieldKey
  )}" spellcheck="true" placeholder="${ph}">${escapeHtml(v)}</textarea>
    </div>
  </section>`;
}

function collectPowerTiersFromViz() {
  const sysRoot = $("vizPowerSystemModules");
  if (!sysRoot) return null;
  const sysCards = [...sysRoot.querySelectorAll(".power-tier-viz--editable[data-power-tier-index]")].sort(
    (a, b) =>
      Number.parseInt(a.getAttribute("data-power-tier-index") || "0", 10) -
      Number.parseInt(b.getAttribute("data-power-tier-index") || "0", 10)
  );
  if (!sysCards.length) return null;
  const treeRoot = $("vizPowerSkillTreeModules");
  let base = [];
  try {
    const p = JSON.parse($("powerTiersJson")?.value || "[]");
    if (Array.isArray(p)) base = structuredClone(p);
  } catch {
    base = Array.isArray(state.world?.power_system?.tiers)
      ? structuredClone(state.world.power_system.tiers)
      : [];
  }
  const strOf = (card, f) =>
    (
      card.querySelector(`textarea[data-power-field="${f}"],input[data-power-field="${f}"]`)?.value ?? ""
    ).toString();
  const splitLines = (card, f) =>
    strOf(card, f)
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
  return sysCards.map((card) => {
    const idx = Number.parseInt(card.getAttribute("data-power-tier-index") || "0", 10);
    const prev = base[idx] && typeof base[idx] === "object" ? base[idx] : {};
    const name = strOf(card, "name").trim() || `境 ${idx + 1}`;
    const description = strOf(card, "description").trim();
    let skill_tree = Array.isArray(prev.skill_tree) ? prev.skill_tree : [];
    let subclass_paths = Array.isArray(prev.subclass_paths) ? prev.subclass_paths : [];
    const treeCard = treeRoot?.querySelector(
      `.power-tier-viz--trees[data-power-tier-index="${idx}"]`
    );
    if (treeCard) {
      const skTxt = treeCard.querySelector('[data-power-tree-part="skill_tree"]')?.value ?? "";
      try {
        const parsed = JSON.parse(skTxt.trim() || "[]");
        if (Array.isArray(parsed)) skill_tree = parsed;
      } catch (_) {
        /* 保持原 skill_tree */
      }
      const scTxt = treeCard.querySelector('[data-power-tree-part="subclass_paths"]')?.value ?? "";
      try {
        const parsed = JSON.parse(scTxt.trim() || "[]");
        if (Array.isArray(parsed)) subclass_paths = parsed;
      } catch (_) {
        /* 保持原 subclass_paths */
      }
    }
    return {
      ...prev,
      name,
      description,
      typical_capabilities: splitLines(card, "typical_capabilities"),
      limitations: splitLines(card, "limitations"),
      examples: splitLines(card, "examples"),
      skill_tree,
      subclass_paths,
    };
  });
}

let _powerTierVizSyncTimer;
function scheduleSyncPowerTiersFromVizToStateAndJson() {
  clearTimeout(_powerTierVizSyncTimer);
  _powerTierVizSyncTimer = setTimeout(() => {
    const tiers = collectPowerTiersFromViz();
    if (tiers == null || !state.world) return;
    state.world.power_system = state.world.power_system || {};
    state.world.power_system.tiers = tiers;
    const ta = $("powerTiersJson");
    if (ta) ta.value = JSON.stringify(tiers, null, 2);
    setDirty(true);
    document.querySelectorAll("#vizPowerSkillTreeModules .power-tier-viz--trees").forEach((el) => {
      const idx = Number.parseInt(el.getAttribute("data-power-tier-index") || "0", 10);
      const tn = tiers[idx]?.name;
      const titleEl = el.querySelector(".viz-module-title");
      if (titleEl && tn != null) titleEl.textContent = tn || `境 ${idx + 1}`;
    });
    updatePowerTierSkillTreePreviews(tiers);
    updatePowerProfessionPreviews(tiers, state.world.power_system.profession_system);
    document.querySelectorAll("#vizPowerProfessionModules .power-tier-viz--professions").forEach((el) => {
      const idx = Number.parseInt(el.getAttribute("data-power-tier-index") || "0", 10);
      const tn = tiers[idx]?.name;
      const titleEl = el.querySelector(".viz-module-title");
      if (titleEl && tn != null) titleEl.textContent = tn || `境 ${idx + 1}`;
    });
  }, 220);
}

function collectHistoryEventsFromViz() {
  const root = $("historyMajorTimeline");
  if (!root) return null;
  const rows = [...root.querySelectorAll(".hist-tl-row--editable[data-history-event-index]")].sort(
    (a, b) =>
      Number.parseInt(a.getAttribute("data-history-event-index") || "0", 10) -
      Number.parseInt(b.getAttribute("data-history-event-index") || "0", 10)
  );
  if (!rows.length) return null;
  let base = [];
  try {
    const p = JSON.parse($("historyJson")?.value || "[]");
    if (Array.isArray(p)) base = structuredClone(p);
  } catch {
    base = Array.isArray(state.world?.history?.events)
      ? structuredClone(state.world.history.events)
      : [];
  }
  const val = (row, f) =>
    (row.querySelector(`[data-hist-field="${f}"]`)?.value ?? "").toString();
  const splitLines = (row, f) =>
    val(row, f)
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
  return rows.map((row) => {
    const idx = Number.parseInt(row.getAttribute("data-history-event-index") || "0", 10);
    const prev = base[idx] && typeof base[idx] === "object" ? base[idx] : {};
    return {
      ...prev,
      when: val(row, "when").trim(),
      title: val(row, "title").trim(),
      summary: val(row, "summary").trim(),
      consequences: splitLines(row, "consequences"),
      linked_faction_ids: splitLines(row, "linked_faction_ids"),
    };
  });
}

let _histTimelineSyncTimer;
function scheduleSyncHistoryEventsFromVizToStateAndJson() {
  clearTimeout(_histTimelineSyncTimer);
  _histTimelineSyncTimer = setTimeout(() => {
    const events = collectHistoryEventsFromViz();
    if (events == null || !state.world) return;
    state.world.history = state.world.history || {};
    state.world.history.events = events;
    const ta = $("historyJson");
    if (ta) ta.value = JSON.stringify(events, null, 2);
    setDirty(true);
    void drawMermaidHost($("vizHistoryHost"), buildHistoryMermaid(events));
  }, 220);
}

function clampRefPercent(n) {
  const x = Number(n);
  if (Number.isFinite(x)) return Math.min(100, Math.max(0, Math.round(x)));
  return 55;
}

function htmlSkillTreeSection(title, nodes) {
  const list = Array.isArray(nodes) ? nodes : [];
  if (!list.length) return "";
  const lis = list
    .map((node) => {
      const pr = (node.prereq_ids || []).filter(Boolean).join("、");
      const br = node.branch
        ? `<span class="skill-branch">${escapeHtml(String(node.branch))}</span>`
        : "";
      const sum = (node.summary || "").trim();
      return `<li class="skill-node-li"><code class="skill-id">${escapeHtml(
        (node.id || "").toString()
      )}</code> <strong>${escapeHtml((node.name || "").toString())}</strong> ${br}${
        pr ? `<div class="muted tiny skill-prereq">前置：${escapeHtml(pr)}</div>` : ""
      }${
        sum
          ? `<div class="skill-sum">${escapeHtml(sum).replace(/\n/g, "<br/>")}</div>`
          : ""
      }</li>`;
    })
    .join("");
  return `<div class="skill-tree-section"><h4 class="skill-tree-h">${escapeHtml(title)}</h4><ul class="skill-tree-ul">${lis}</ul></div>`;
}

function htmlSubclassPaths(subs) {
  const list = Array.isArray(subs) ? subs : [];
  if (!list.length) return "";
  const cards = list
    .map((sc) => {
      const title = `${(sc.name || sc.id || "子类").toString()} · 技能树`;
      const inner = htmlSkillTreeSection(title, sc.skill_tree);
      const tag = (sc.tagline || "").toString().trim();
      const fl = (sc.flavor || "").toString().trim();
      return `<div class="subclass-card"><div class="subclass-card-head"><strong>${escapeHtml(
        (sc.name || sc.id || "").toString()
      )}</strong>${
        tag ? `<span class="muted tiny subclass-tagline">${escapeHtml(tag)}</span>` : ""
      }</div>${
        fl ? `<p class="subclass-flavor">${escapeHtml(fl).replace(/\n/g, "<br/>")}</p>` : ""
      }${inner}</div>`;
    })
    .join("");
  return `<div class="subclass-paths-wrap"><h4 class="skill-tree-h">子类职业</h4><div class="subclass-cards">${cards}</div></div>`;
}

/** 通用技能树：仅预览区内部 HTML（无外层标题，便于嵌入分栏） */
function htmlSkillTreePreviewInner(nodes) {
  const list = Array.isArray(nodes) ? nodes : [];
  if (!list.length) {
    return `<div class="skill-tree-preview-empty muted tiny">尚无节点。JSON 中每项建议含 id、name、summary、prereq_ids（前置节点 id 数组）、branch。</div>`;
  }
  const lis = list
    .map((node) => {
      const pr = (node.prereq_ids || []).filter(Boolean).join("、");
      const br = node.branch
        ? `<span class="skill-branch">${escapeHtml(String(node.branch))}</span>`
        : "";
      const sum = (node.summary || "").trim();
      return `<li class="skill-node-li"><code class="skill-id">${escapeHtml(
        (node.id || "").toString()
      )}</code> <strong>${escapeHtml((node.name || "").toString())}</strong> ${br}${
        pr ? `<div class="muted tiny skill-prereq">前置：${escapeHtml(pr)}</div>` : ""
      }${
        sum
          ? `<div class="skill-sum">${escapeHtml(sum).replace(/\n/g, "<br/>")}</div>`
          : ""
      }</li>`;
    })
    .join("");
  return `<ul class="skill-tree-ul skill-tree-ul--preview">${lis}</ul>`;
}

function professionMapFromList(list) {
  const m = Object.create(null);
  for (const p of list || []) {
    const id = String(p?.id ?? "").trim();
    if (id) m[id] = p;
  }
  return m;
}

function resolveFactionLabel(w, fid) {
  const id = String(fid ?? "").trim();
  if (!id) return "";
  const ent = w?.factions?.entities?.find((e) => String(e?.id ?? "").trim() === id);
  if (ent && (ent.name || "").trim()) return `${String(ent.name).trim()}（${id}）`;
  return id;
}

function htmlProfessionsPreviewInner(professions, world) {
  const list = Array.isArray(professions) ? professions : [];
  if (!list.length) {
    return `<div class="skill-tree-preview-empty muted tiny">尚无职业。JSON 每项建议含 id、name、可选 tagline、flavor、exclusive_faction_id（派系 id）、notes。</div>`;
  }
  return list
    .map((p) => {
      const fid = String(p.exclusive_faction_id ?? "").trim();
      const fac = fid
        ? `<span class="profession-fac-badge" title="派系专属职业">派系：${escapeHtml(resolveFactionLabel(world, fid))}</span>`
        : "";
      const tg = (p.tagline || "").toString().trim();
      const fl = (p.flavor || "").toString().trim();
      const notes = (p.notes || "").toString().trim();
      return `<div class="profession-card--preview"><div class="profession-card-head"><code class="skill-id">${escapeHtml(
        (p.id || "").toString()
      )}</code> <strong>${escapeHtml((p.name || "").toString())}</strong>${fac ? ` ${fac}` : ""}</div>${
        tg ? `<span class="muted tiny subclass-tagline">${escapeHtml(tg)}</span>` : ""
      }${
        fl ? `<p class="subclass-flavor">${escapeHtml(fl).replace(/\n/g, "<br/>")}</p>` : ""
      }${
        notes ? `<p class="muted tiny">${escapeHtml(notes).replace(/\n/g, "<br/>")}</p>` : ""
      }</div>`;
    })
    .join("");
}

function htmlSubclassPathsPreviewInner(subs, tierProfessions, world) {
  const list = Array.isArray(subs) ? subs : [];
  const pmap = professionMapFromList(tierProfessions);
  if (!list.length) {
    return `<div class="skill-tree-preview-empty muted tiny">尚无子类。每项含 id、name、可选 tagline、flavor、profession_id（对齐本境职业 id）、skill_tree。</div>`;
  }
  const cards = list
    .map((sc) => {
      const inner = htmlSkillTreePreviewInner(sc.skill_tree);
      const tag = (sc.tagline || "").toString().trim();
      const fl = (sc.flavor || "").toString().trim();
      const pid = String(sc.profession_id ?? "").trim();
      let profLine = "";
      if (pid) {
        const hit = pmap[pid];
        const cls = hit ? "subclass-prof-line" : "subclass-prof-line subclass-prof-line--warn";
        const txt = hit
          ? `职业体系：${escapeHtml((hit.name || pid).toString())}（id：${escapeHtml(pid)}）`
          : `profession_id：${escapeHtml(pid)}（本境职业表中未找到）`;
        profLine = `<div class="muted tiny ${cls}">← ${txt}</div>`;
      }
      return `<div class="subclass-card subclass-card--preview"><div class="subclass-card-head"><strong>${escapeHtml(
        (sc.name || sc.id || "").toString()
      )}</strong>${
        tag ? `<span class="muted tiny subclass-tagline">${escapeHtml(tag)}</span>` : ""
      }</div>${profLine}${
        fl ? `<p class="subclass-flavor">${escapeHtml(fl).replace(/\n/g, "<br/>")}</p>` : ""
      }${inner}</div>`;
    })
    .join("");
  return `<div class="subclass-cards subclass-cards--preview">${cards}</div>`;
}

function updatePowerTierSkillTreePreviews(tiers) {
  if (!Array.isArray(tiers)) return;
  const root = $("vizPowerSkillTreeModules");
  if (!root) return;
  const w = state.world;
  const byProf = w?.power_system?.profession_system?.by_tier;
  tiers.forEach((tier, idx) => {
    const card = root.querySelector(`.power-tier-viz--trees[data-power-tier-index="${idx}"]`);
    if (!card) return;
    const tierProfs = (byProf && byProf[idx] && byProf[idx].professions) || [];
    const g = card.querySelector('[data-skill-preview="general"]');
    if (g) {
      g.innerHTML = `<div class="skill-tree-preview-surface">${htmlSkillTreePreviewInner(tier.skill_tree)}</div>`;
    }
    const s = card.querySelector('[data-skill-preview="subclasses"]');
    if (s) {
      s.innerHTML = `<div class="skill-tree-preview-surface skill-tree-preview-surface--sub">${htmlSubclassPathsPreviewInner(
        tier.subclass_paths,
        tierProfs,
        w
      )}</div>`;
    }
  });
}

function updatePowerProfessionPreviews(tiers, professionSystem) {
  if (!Array.isArray(tiers)) return;
  const root = $("vizPowerProfessionModules");
  if (!root) return;
  const w = state.world;
  const byProf = professionSystem?.by_tier || [];
  tiers.forEach((tier, idx) => {
    const card = root.querySelector(`.power-tier-viz--professions[data-power-tier-index="${idx}"]`);
    if (!card) return;
    const wrap = card.querySelector('[data-profession-preview="list"]');
    if (!wrap) return;
    const profs = (byProf[idx] && byProf[idx].professions) || [];
    wrap.innerHTML = `<div class="profession-preview-surface">${htmlProfessionsPreviewInner(profs, w)}</div>`;
  });
}

/** 从助手回复里的 Markdown 代码块解析 attribute_system（支持根级包一层 attribute_system 或直接 summary+stats）。 */
function parseAttributeSystemFromAssistantReply(reply) {
  if (!reply || typeof reply !== "string") return null;
  const re = /```(?:json)?\s*([\s\S]*?)```/gi;
  const blocks = [];
  let m;
  while ((m = re.exec(reply)) !== null) blocks.push(m[1].trim());
  for (let i = blocks.length - 1; i >= 0; i--) {
    try {
      const obj = JSON.parse(blocks[i]);
      if (!obj || typeof obj !== "object") continue;
      if (obj.attribute_system && typeof obj.attribute_system === "object") {
        return obj.attribute_system;
      }
      if (
        Array.isArray(obj.stats) &&
        !obj.tiers &&
        !obj.grades &&
        !obj.entities &&
        !obj.regions &&
        !obj.geography &&
        !obj.events &&
        !obj.factions
      ) {
        if (
          obj.stats.length > 0 ||
          typeof obj.summary === "string" ||
          typeof obj.design_notes === "string" ||
          (Array.isArray(obj.tier_average_profiles) && obj.tier_average_profiles.length > 0)
        ) {
          return obj;
        }
      }
    } catch (_) {
      /* 非 JSON 块 */
    }
  }
  return null;
}

function normalizeAttrStatFromExtract(row, idx) {
  if (!row || typeof row !== "object") return null;
  const id = String(row.id ?? row.key ?? `stat_${idx}`).trim().slice(0, 80);
  const name = String(row.name ?? row.title ?? row.label ?? id).trim().slice(0, 200);
  if (!name) return null;
  const abbreviation = String(row.abbreviation ?? row.abbr ?? "").trim().slice(0, 32);
  const intro = String(row.intro ?? row.brief ?? "").trim().slice(0, 800);
  const description = String(row.description ?? row.desc ?? "").trim().slice(0, 4000);
  const scale = String(row.scale ?? "").trim().slice(0, 200);
  const typical_use = String(row.typical_use ?? row.use ?? "").trim().slice(0, 200);
  const rawRef = row.reference_percent ?? row.percent ?? row.reference;
  let reference_percent = 55;
  if (typeof rawRef === "number" && Number.isFinite(rawRef)) {
    reference_percent = Math.min(100, Math.max(0, Math.round(rawRef)));
  } else if (rawRef != null && String(rawRef).trim()) {
    const n = parseFloat(String(rawRef).trim());
    if (Number.isFinite(n)) reference_percent = Math.min(100, Math.max(0, Math.round(n)));
  }
  return {
    id: id || `stat_${idx}`,
    name,
    abbreviation,
    intro,
    description,
    scale,
    typical_use,
    reference_percent,
    radar_icon: String(row.radar_icon ?? row.icon_glyph ?? row.radarGlyph ?? "").trim().slice(0, 64),
  };
}

function normalizeTierAverageFromExtract(row, idx) {
  if (!row || typeof row !== "object") return null;
  const tier_name = String(row.tier_name ?? row.name ?? row.tier ?? "").trim().slice(0, 200);
  if (!tier_name) return null;
  const raw = row.averages ?? row.values ?? row.means ?? {};
  const averages = {};
  if (raw && typeof raw === "object") {
    for (const [k, v] of Object.entries(raw)) {
      const key = String(k).trim().slice(0, 80);
      if (!key) continue;
      const n = typeof v === "number" ? v : parseFloat(String(v).trim());
      if (!Number.isFinite(n)) continue;
      averages[key] = Math.min(100, Math.max(0, Math.round(n)));
    }
  }
  return { tier_name, averages };
}

/** 将解析结果合并进 state.world.attribute_system；有变更则返回 true。 */
function mergeAttributeSystemFromAssistantReply(reply) {
  if (!state.world || !reply) return false;
  const extracted = parseAttributeSystemFromAssistantReply(reply);
  if (!extracted || typeof extracted !== "object") return false;
  const cur = state.world.attribute_system || {
    summary: "",
    design_notes: "",
    stats: [],
    tier_average_profiles: [],
  };
  const summary =
    typeof extracted.summary === "string" ? extracted.summary.trim() : (cur.summary ?? "").trim();
  const design_notes =
    typeof extracted.design_notes === "string"
      ? extracted.design_notes.trim()
      : (cur.design_notes ?? "").trim();
  let stats = Array.isArray(cur.stats) ? [...cur.stats] : [];
  if (Array.isArray(extracted.stats) && extracted.stats.length > 0) {
    stats = extracted.stats.map((row, i) => normalizeAttrStatFromExtract(row, i)).filter(Boolean);
  }
  let tier_average_profiles = Array.isArray(cur.tier_average_profiles)
    ? [...cur.tier_average_profiles]
    : [];
  if (Array.isArray(extracted.tier_average_profiles) && extracted.tier_average_profiles.length > 0) {
    tier_average_profiles = extracted.tier_average_profiles
      .map((row, i) => normalizeTierAverageFromExtract(row, i))
      .filter(Boolean);
  }
  const meaningful =
    (summary && summary.length > 0) ||
    (design_notes && design_notes.length > 0) ||
    (stats && stats.length > 0) ||
    (tier_average_profiles && tier_average_profiles.length > 0);
  if (!meaningful) return false;
  const prev = JSON.stringify(cur);
  const next = { summary, design_notes, stats, tier_average_profiles };
  if (JSON.stringify(next) === prev) return false;
  state.world.attribute_system = next;
  return true;
}

/** 雷达轴端 Material Symbols ligature；stats 可设 radar_icon，否则按 id/name 启发式 */
function pickAttrStatGlyph(stat) {
  const raw = ((stat.radar_icon || stat.icon_glyph || "") + "").trim();
  if (raw && /^[a-z0-9_]+$/i.test(raw)) return raw.slice(0, 64);
  const t = [stat.id, stat.name, stat.abbreviation || ""].join(" ").toLowerCase();
  const rules = [
    [/str|力量|体能|体格|筋骨|体质/, "fitness_center"],
    [/dex|敏捷|灵巧|反射|速度|身手/, "directions_run"],
    [/con|耐力|坚韧|生存|抗性|hp/, "shield_moon"],
    [/int|智力|学识|推理|奥术|知识/, "psychology"],
    [/wis|感知|洞察|察觉|直感|灵觉/, "visibility"],
    [/cha|魅力|社交|威压|亲和|仪态/, "groups_3"],
    [/理智|san|精神崩溃/, "neurology"],
    [/意志|决心|专注|自律/, "center_focus_strong"],
    [/幸运|luck|命运/, "casino"],
    [/感知|察觉|侦查/, "search"],
    [/魅力|说服|欺瞒/, "theater_comedy"],
    [/敏捷|隐匿|潜行/, "nights_stay"],
    [/力量|运动|运动技能/, "exercise"],
  ];
  for (const [re, g] of rules) {
    if (re.test(t)) return g;
  }
  return "bubble_chart";
}

function bindAttrRadarAxisTooltips(svgEl, tipEl, stats, drawableProfiles) {
  if (!svgEl || !tipEl) return;
  const hide = () => {
    tipEl.hidden = true;
    tipEl.innerHTML = "";
  };
  svgEl.querySelectorAll(".radar-axis-hit").forEach((line) => {
    line.addEventListener("pointerenter", (ev) => {
      const i = parseInt(line.getAttribute("data-axis-idx") || "-1", 10);
      if (i < 0 || !stats[i]) return;
      const s = stats[i];
      const rows = [
        `<div class="attr-radar-tip-title">${escapeHtml((s.name || s.id || "").toString())}</div>`,
        `<div class="attr-radar-tip-row"><span class="attr-radar-tip-k">参照轮廓</span><span class="attr-radar-tip-v">${clampRefPercent(
          s.reference_percent
        )} / 100</span></div>`,
      ];
      drawableProfiles.forEach((prof) => {
        const av = prof.averages && typeof prof.averages === "object" ? prof.averages : {};
        const raw = av[s.id];
        const lab = String(prof.tier_name || "").trim() || "境界";
        const v =
          typeof raw === "number" && Number.isFinite(raw) ? `${clampRefPercent(raw)} / 100` : "—";
        rows.push(
          `<div class="attr-radar-tip-row"><span class="attr-radar-tip-k">${escapeHtml(lab)} 平均</span><span class="attr-radar-tip-v">${escapeHtml(
            v
          )}</span></div>`
        );
      });
      tipEl.innerHTML = rows.join("");
      tipEl.hidden = false;
      tipEl.style.left = `${ev.clientX + 12}px`;
      tipEl.style.top = `${ev.clientY + 12}px`;
    });
    line.addEventListener("pointermove", (ev) => {
      if (tipEl.hidden) return;
      tipEl.style.left = `${ev.clientX + 12}px`;
      tipEl.style.top = `${ev.clientY + 12}px`;
    });
    line.addEventListener("pointerleave", hide);
    line.addEventListener("pointercancel", hide);
  });
}

function migrateGlobalLandmarksResourcesIntoRegions(w) {
  const g = w.geography;
  if (!g || !Array.isArray(g.regions) || !g.regions.length) return;
  const gloLm = Array.isArray(g.landmarks) ? g.landmarks.map((x) => String(x).trim()).filter(Boolean) : [];
  const gloRes = Array.isArray(g.resources) ? g.resources.map((x) => String(x).trim()).filter(Boolean) : [];
  const anyRegionHas = g.regions.some(
    (r) =>
      (Array.isArray(r.landmarks) && r.landmarks.length > 0) ||
      (Array.isArray(r.resources) && r.resources.length > 0)
  );
  if (!anyRegionHas && (gloLm.length || gloRes.length)) {
    const r0 = g.regions[0];
    if (!Array.isArray(r0.landmarks)) r0.landmarks = [];
    if (!Array.isArray(r0.resources)) r0.resources = [];
    r0.landmarks.push(...gloLm);
    r0.resources.push(...gloRes);
    g.landmarks = [];
    g.resources = [];
  }
}

function renderAttributePanel(w) {
  const host = $("vizAttributeRadarHost");
  const chips = $("attrStatChips");
  const introsEl = $("attrStatIntros");
  if (!host) return;
  if (!w) {
    host.innerHTML = "";
    if (chips) chips.innerHTML = "";
    if (introsEl) introsEl.innerHTML = "";
    return;
  }
  const stats = (w.attribute_system && w.attribute_system.stats) || [];
  if (!stats.length) {
    host.innerHTML = `<div class="viz-empty">在下方 JSON 中添加 stats（每项含 id、name、abbreviation、intro、reference_percent 等）</div>`;
    if (chips) chips.innerHTML = "";
    if (introsEl) introsEl.innerHTML = "";
    return;
  }
  const profiles = ((w.attribute_system && w.attribute_system.tier_average_profiles) || []).filter((p) =>
    Boolean(p && String(p.tier_name || "").trim())
  );
  const drawableProfiles = profiles.filter((prof) => {
    const av = prof.averages && typeof prof.averages === "object" ? prof.averages : {};
    return stats.some((s) => {
      const raw = av[s.id];
      return typeof raw === "number" && Number.isFinite(raw);
    });
  });
  const n = stats.length;
  const R = 92;
  const angles = stats.map((_, i) => (-Math.PI / 2) + (2 * Math.PI * i) / n);
  let rings = "";
  for (let g = 1; g <= 4; g++) {
    const rr = (R * g) / 4;
    rings += `<circle cx="0" cy="0" r="${rr.toFixed(2)}" class="radar-ring" />`;
  }
  const tierHueCycle = [168, 318, 32, 268, 200, 130];
  let tierPolygons = "";
  drawableProfiles.forEach((prof, ti) => {
    const av = prof.averages && typeof prof.averages === "object" ? prof.averages : {};
    const tierPts = angles
      .map((ang, i) => {
        const sid = stats[i].id;
        const raw = av[sid];
        const v =
          typeof raw === "number" && Number.isFinite(raw) ? clampRefPercent(raw) : 0;
        const pct = v / 100;
        const r = R * pct;
        return `${(r * Math.cos(ang)).toFixed(2)},${(r * Math.sin(ang)).toFixed(2)}`;
      })
      .join(" ");
    const hue = tierHueCycle[ti % tierHueCycle.length];
    tierPolygons += `<polygon class="radar-poly radar-poly--tier" points="${tierPts}" fill="hsla(${hue},62%,52%,0.12)" stroke="hsl(${hue},48%,36%)" stroke-width="1.32" stroke-linejoin="round" />`;
  });
  const refPts = angles
    .map((ang, i) => {
      const pct = clampRefPercent(stats[i].reference_percent) / 100;
      const r = R * pct;
      return `${(r * Math.cos(ang)).toFixed(2)},${(r * Math.sin(ang)).toFixed(2)}`;
    })
    .join(" ");
  let axisVisible = "";
  let axisHits = "";
  let axisIcons = "";
  let axisLabels = "";
  const R_icon = R + 12;
  const R_text = R + 30;
  for (let i = 0; i < n; i++) {
    const ang = angles[i];
    const xe = (R * Math.cos(ang)).toFixed(2);
    const ye = (R * Math.sin(ang)).toFixed(2);
    axisVisible += `<line x1="0" y1="0" x2="${xe}" y2="${ye}" class="radar-axis-visible" />`;
    axisHits += `<line x1="0" y1="0" x2="${xe}" y2="${ye}" class="radar-axis-hit" data-axis-idx="${i}" stroke-linecap="round" />`;
    const glyph = pickAttrStatGlyph(stats[i]);
    const iix = (R_icon * Math.cos(ang)).toFixed(2);
    const iiy = (R_icon * Math.sin(ang)).toFixed(2);
    axisIcons += `<text x="${iix}" y="${iiy}" class="radar-stat-ic" dominant-baseline="central" text-anchor="middle">${glyph}</text>`;
    const lx = R_text * Math.cos(ang);
    const ly = R_text * Math.sin(ang);
    const short = escapeHtml(
      ((stats[i].abbreviation || stats[i].name || "?") + "").toString().slice(0, 6)
    );
    axisLabels += `<text x="${lx.toFixed(2)}" y="${ly.toFixed(2)}" class="radar-label" dominant-baseline="middle" text-anchor="middle">${short}</text>`;
  }
  const gid = "radarFillGrad_" + Math.random().toString(36).slice(2, 11);
  const svgInner = `<svg viewBox="-130 -130 260 260" class="attr-radar-svg" role="img" aria-label="属性维度雷达"><defs><linearGradient id="${gid}" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#6366f1" stop-opacity="0.36"/><stop offset="100%" stop-color="#0ea5e9" stop-opacity="0.2"/></linearGradient></defs><g class="radar-rings">${rings}</g>${tierPolygons}<polygon class="radar-poly radar-poly--ref" points="${refPts}" fill="url(#${gid})" stroke="#4338ca" stroke-width="1.65" stroke-linejoin="round"/><g class="radar-axes-visible">${axisVisible}</g><g class="radar-axes-hit">${axisHits}</g><g class="radar-axes-icons">${axisIcons}</g><g class="radar-axes-labels">${axisLabels}</g></svg>`;

  const legParts = [
    `<span class="radar-legend-i radar-legend-i--ref"><span class="radar-legend-dot" aria-hidden="true"></span>参照轮廓</span>`,
  ];
  drawableProfiles.forEach((prof, ti) => {
    const tname = String(prof.tier_name || "").trim();
    const hue = tierHueCycle[ti % tierHueCycle.length];
    legParts.push(
      `<span class="radar-legend-i" style="--legend-tier-h:${hue}"><span class="radar-legend-dot radar-legend-dot--tier" aria-hidden="true"></span>${escapeHtml(
        tname
      )} 平均</span>`
    );
  });
  const legend = `<div class="attr-radar-legend muted tiny">${legParts.join("")}</div>`;
  host.innerHTML = `<div class="attr-radar-stack"><div class="attr-radar-svg-wrap">${svgInner}<div class="attr-radar-tip" hidden aria-live="polite"></div></div>${legend}</div>`;
  const svgEl = host.querySelector(".attr-radar-svg");
  const tipEl = host.querySelector(".attr-radar-tip");
  bindAttrRadarAxisTooltips(svgEl, tipEl, stats, drawableProfiles);

  if (chips) {
    chips.innerHTML = stats
      .map((s) => {
        const intro = ((s.intro || "") + "").trim();
        const desc = ((s.description || "") + "").trim();
        const tip = escapeHtml((intro || desc || "").slice(0, 260));
        const nm = escapeHtml((s.name || s.id || "").toString());
        return `<span class="attr-chip" title="${tip}"><strong>${nm}</strong><span class="attr-chip-pct">${clampRefPercent(
          s.reference_percent
        )}</span></span>`;
      })
      .join("");
  }
  if (introsEl) {
    introsEl.innerHTML = stats
      .map((s) => {
        const nm = escapeHtml((s.name || s.id || "").toString());
        const intro = ((s.intro || "") + "").trim();
        const desc = ((s.description || "") + "").trim();
        const bodyTxt = intro || desc.slice(0, 200) || "（未填 intro，可在 JSON 中补充）";
        const body = escapeHtml(bodyTxt);
        return `<div class="attr-intro-row"><span class="attr-intro-name">${nm}</span><span class="attr-intro-body">${body}</span></div>`;
      })
      .join("");
  }
}

/** 境界 · 体系子页：各境名称、描述、能力/限制/范例（可编辑，与 tiers JSON 同步） */
function renderPowerTierSystemModules(w) {
  const root = $("vizPowerSystemModules");
  if (!root) return;
  root.replaceChildren();
  const tiers = w.power_system?.tiers || [];
  if (!tiers.length) {
    root.innerHTML = `<div class="viz-empty">暂无境界（可在「技能树」子页下方 tiers JSON 中添加）</div>`;
    return;
  }
  const n = tiers.length;
  tiers.forEach((tier, idx) => {
    const block = document.createElement("div");
    block.className = "viz-module viz-module--power power-tier-viz power-tier-viz--editable";
    block.dataset.powerTierIndex = String(idx);
    const hue = Math.round(198 + (idx / Math.max(n - 1, 1)) * 78);
    block.style.setProperty("--tier-accent-h", String(hue));
    const caps = (Array.isArray(tier.typical_capabilities) ? tier.typical_capabilities : [])
      .map((x) => String(x).trim())
      .filter(Boolean);
    const lims = (Array.isArray(tier.limitations) ? tier.limitations : [])
      .map((x) => String(x).trim())
      .filter(Boolean);
    const exs = (Array.isArray(tier.examples) ? tier.examples : [])
      .map((x) => String(x).trim())
      .filter(Boolean);
    const nameId = `power-tier-name-${idx}`;
    block.innerHTML = `
      <div class="power-tier-viz-accent" aria-hidden="true"></div>
      <div class="viz-module-head power-tier-viz-head">
        <span class="viz-module-idx viz-module-idx--power" aria-hidden="true">${idx + 1}</span>
        <div class="viz-module-head-main">
          <label class="item-grade-name-lbl muted tiny" for="${nameId}">境界名</label>
          <input id="${nameId}" class="item-grade-name-input" type="text" data-power-field="name" value="${escapeAttr(
            tier.name || ""
          )}" placeholder="例如：筑基、第三环…" autocomplete="off" />
          <span class="viz-module-meta muted tiny">下列可直接编辑；列表类一行一条</span>
        </div>
      </div>
      <div class="power-tier-viz-body" role="region" aria-label="境界 ${idx + 1} 体系">
        ${htmlPowerTierEditableField(
          "description",
          "定位与描述",
          tier.description,
          "本境在世界力量阶梯中的位置、读者/玩家如何理解…",
          "mean",
          5
        )}
        <div class="power-tier-viz-grid">
          ${htmlPowerTierEditableField(
            "typical_capabilities",
            "发动能力（典型）",
            caps.join("\n"),
            "每行一条典型能力或表现",
            "caps",
            4
          )}
          ${htmlPowerTierEditableField(
            "limitations",
            "发动限制",
            lims.join("\n"),
            "每行一条限制或代价",
            "lims",
            4
          )}
          ${htmlPowerTierEditableField(
            "examples",
            "例子",
            exs.join("\n"),
            "每行一条叙事或规则范例",
            "ex",
            4
          )}
        </div>
      </div>`;
    root.appendChild(block);
  });
}

/** 境界 · 技能树子页：左栏可视化预览 + 右栏 JSON；防抖保存后仅刷新预览不打断输入 */
function renderPowerTierSkillTreeModules(w) {
  const root = $("vizPowerSkillTreeModules");
  if (!root) return;
  root.replaceChildren();
  const tiers = w.power_system?.tiers || [];
  if (!tiers.length) {
    root.innerHTML = `<div class="viz-empty">暂无境界（可在下方 tiers JSON 中添加）</div>`;
    return;
  }
  const n = tiers.length;
  tiers.forEach((tier, idx) => {
    const block = document.createElement("div");
    block.className = "viz-module viz-module--power power-tier-viz power-tier-viz--trees";
    block.dataset.powerTierIndex = String(idx);
    const hue = Math.round(198 + (idx / Math.max(n - 1, 1)) * 78);
    block.style.setProperty("--tier-accent-h", String(hue));
    const skJson = JSON.stringify(tier.skill_tree ?? [], null, 2);
    const scJson = JSON.stringify(tier.subclass_paths ?? [], null, 2);
    const genPreviewInner = htmlSkillTreePreviewInner(tier.skill_tree ?? []);
    const tierProfs = (w.power_system?.profession_system?.by_tier?.[idx]?.professions) || [];
    const subPreviewInner = htmlSubclassPathsPreviewInner(tier.subclass_paths ?? [], tierProfs, w);
    const genPreview = `<div class="skill-tree-preview-surface">${genPreviewInner}</div>`;
    const subPreview = `<div class="skill-tree-preview-surface skill-tree-preview-surface--sub">${subPreviewInner}</div>`;
    block.innerHTML = `
      <div class="power-tier-viz-accent" aria-hidden="true"></div>
      <div class="viz-module-head power-tier-viz-head">
        <span class="viz-module-idx viz-module-idx--power" aria-hidden="true">${idx + 1}</span>
        <div class="viz-module-head-main">
          <span class="viz-module-title">${escapeHtml(tier.name || `境 ${idx + 1}`)}</span>
          <span class="viz-module-meta muted tiny">左侧为节点预览，右侧编辑 JSON；保存前预览会随输入防抖更新</span>
        </div>
      </div>
      <div class="power-tier-viz-body power-tier-skill-tree-body" role="region" aria-label="境界 ${idx + 1} 技能树">
        <section class="power-tier-skill-band" aria-label="通用技能树">
          <div class="power-tier-skill-split">
            <div class="power-tier-skill-col power-tier-skill-col--viz">
              <div class="power-tier-skill-band-head">
                <span class="ms skill-band-ic" aria-hidden="true">account_tree</span>
                <span class="power-tier-skill-band-title">通用技能树</span>
                <span class="power-tier-skill-band-hint muted tiny">节点 · 前置 · 分支</span>
              </div>
              <div class="power-tier-skill-preview-wrap" data-skill-preview="general">${genPreview}</div>
            </div>
            <div class="power-tier-skill-col power-tier-skill-col--json">
              <div class="power-tier-json-edit-head">
                <span class="ms skill-band-ic" aria-hidden="true">data_object</span>
                <span>skill_tree</span>
                <span class="muted tiny power-tier-json-lang">JSON</span>
              </div>
              <textarea id="power-sk-${idx}" class="power-tier-json-ta" rows="11" spellcheck="false" data-power-tree-part="skill_tree" aria-label="通用技能树 JSON">${escapeHtml(
                skJson
              )}</textarea>
            </div>
          </div>
        </section>
        <section class="power-tier-skill-band power-tier-skill-band--sub" aria-label="子类流派">
          <div class="power-tier-skill-split">
            <div class="power-tier-skill-col power-tier-skill-col--viz">
              <div class="power-tier-skill-band-head">
                <span class="ms skill-band-ic" aria-hidden="true">diversity_3</span>
                <span class="power-tier-skill-band-title">子类流派</span>
                <span class="power-tier-skill-band-hint muted tiny">各流派独立 skill_tree</span>
              </div>
              <div class="power-tier-skill-preview-wrap" data-skill-preview="subclasses">${subPreview}</div>
            </div>
            <div class="power-tier-skill-col power-tier-skill-col--json">
              <div class="power-tier-json-edit-head">
                <span class="ms skill-band-ic" aria-hidden="true">hub</span>
                <span>subclass_paths</span>
                <span class="muted tiny power-tier-json-lang">JSON</span>
              </div>
              <textarea id="power-sc-${idx}" class="power-tier-json-ta" rows="11" spellcheck="false" data-power-tree-part="subclass_paths" aria-label="子类流派 JSON">${escapeHtml(
                scJson
              )}</textarea>
            </div>
          </div>
        </section>
      </div>`;
    root.appendChild(block);
  });
}

function collectProfessionByTierFromDom(tiers) {
  const psRoot = $("vizPowerProfessionModules");
  const list = Array.isArray(tiers) ? tiers : state.world?.power_system?.tiers || [];
  if (!list.length) return [];
  return list.map((t, idx) => {
    let professions = [];
    const card = psRoot?.querySelector(`.power-tier-viz--professions[data-power-tier-index="${idx}"]`);
    const ta = card?.querySelector('[data-profession-part="professions_json"]');
    if (ta) {
      try {
        const p = JSON.parse((ta.value || "").trim() || "[]");
        if (Array.isArray(p)) professions = p;
      } catch (_) {
        const prev = state.world?.power_system?.profession_system?.by_tier?.[idx]?.professions;
        if (Array.isArray(prev)) professions = structuredClone(prev);
      }
    } else {
      const prev = state.world?.power_system?.profession_system?.by_tier?.[idx]?.professions;
      if (Array.isArray(prev)) professions = structuredClone(prev);
    }
    const name = (t.name || "").trim() || `境 ${idx + 1}`;
    return { tier_name: name, professions };
  });
}

let _powerProfessionSyncTimer;
function scheduleSyncProfessionFromVizToState() {
  clearTimeout(_powerProfessionSyncTimer);
  _powerProfessionSyncTimer = setTimeout(() => {
    if (!state.world) return;
    state.world.power_system = state.world.power_system || {};
    state.world.power_system.profession_system = state.world.power_system.profession_system || {};
    state.world.power_system.profession_system.summary = ($("powerProfessionSummary")?.value ?? "").trim();
    state.world.power_system.profession_system.design_notes = ($("powerProfessionDesign")?.value ?? "").trim();
    state.world.power_system.profession_system.by_tier = collectProfessionByTierFromDom(
      state.world.power_system.tiers
    );
    setDirty(true);
    const tiers = state.world.power_system.tiers || [];
    document.querySelectorAll("#vizPowerProfessionModules .power-tier-viz--professions").forEach((el) => {
      const idx = Number.parseInt(el.getAttribute("data-power-tier-index") || "0", 10);
      const tn = tiers[idx]?.name;
      const titleEl = el.querySelector(".viz-module-title");
      if (titleEl && tn != null) titleEl.textContent = tn || `境 ${idx + 1}`;
    });
    updatePowerProfessionPreviews(tiers, state.world.power_system.profession_system);
    updatePowerTierSkillTreePreviews(tiers);
    refreshProfessionPromotionViz();
  }, 220);
}

function renderPowerProfessionModules(w) {
  const root = $("vizPowerProfessionModules");
  if (!root) return;
  root.replaceChildren();
  const tiers = w.power_system?.tiers || [];
  const ps = w.power_system?.profession_system || {};
  const byTier = Array.isArray(ps.by_tier) ? ps.by_tier : [];
  if (!tiers.length) {
    root.innerHTML = `<div class="viz-empty">暂无境界（请先在「体系」或 tiers JSON 中添加境界表）</div>`;
    refreshProfessionPromotionViz();
    return;
  }
  const n = tiers.length;
  tiers.forEach((tier, idx) => {
    const profs = (byTier[idx] && byTier[idx].professions) || [];
    const j = JSON.stringify(profs, null, 2);
    const prevInner = htmlProfessionsPreviewInner(profs, w);
    const block = document.createElement("div");
    block.className = "viz-module viz-module--power power-tier-viz power-tier-viz--professions";
    block.dataset.powerTierIndex = String(idx);
    const hue = Math.round(198 + (idx / Math.max(n - 1, 1)) * 78);
    block.style.setProperty("--tier-accent-h", String(hue));
    block.innerHTML = `
      <div class="power-tier-viz-accent" aria-hidden="true"></div>
      <div class="viz-module-head power-tier-viz-head">
        <span class="viz-module-idx viz-module-idx--power" aria-hidden="true">${idx + 1}</span>
        <div class="viz-module-head-main">
          <span class="viz-module-title">${escapeHtml(tier.name || `境 ${idx + 1}`)}</span>
          <span class="viz-module-meta muted tiny">左侧预览；右栏为本境 professions 数组 JSON</span>
        </div>
      </div>
      <div class="power-tier-viz-body power-tier-skill-tree-body" role="region" aria-label="境界 ${idx + 1} 职业">
        <div class="power-tier-skill-split">
          <div class="power-tier-skill-col power-tier-skill-col--viz">
            <div class="power-tier-skill-band-head">
              <span class="ms skill-band-ic" aria-hidden="true">badge</span>
              <span class="power-tier-skill-band-title">本境职业</span>
              <span class="power-tier-skill-band-hint muted tiny">派系专属填 exclusive_faction_id</span>
            </div>
            <div class="power-tier-skill-preview-wrap" data-profession-preview="list"><div class="profession-preview-surface">${prevInner}</div></div>
          </div>
          <div class="power-tier-skill-col power-tier-skill-col--json">
            <div class="power-tier-json-edit-head">
              <span class="ms skill-band-ic" aria-hidden="true">data_object</span>
              <span>professions</span>
              <span class="muted tiny power-tier-json-lang">JSON</span>
            </div>
            <textarea id="power-pr-${idx}" class="power-tier-json-ta" rows="11" spellcheck="false" data-profession-part="professions_json" aria-label="本境职业 JSON 数组">${escapeHtml(
              j
            )}</textarea>
          </div>
        </div>
      </div>`;
    root.appendChild(block);
  });
  refreshProfessionPromotionViz();
}

function renderPowerTierDashboardModules(w) {
  renderPowerTierSystemModules(w);
  renderPowerTierSkillTreeModules(w);
  renderPowerProfessionModules(w);
}

function setPowerSubView(which) {
  if (which !== "system" && which !== "trees" && which !== "professions") return;
  state.powerSubView = which;
  const sys = $("powerSubSystem");
  const tr = $("powerSubTrees");
  const pr = $("powerSubProfessions");
  if (sys) sys.classList.toggle("is-hidden", which !== "system");
  if (tr) tr.classList.toggle("is-hidden", which !== "trees");
  if (pr) pr.classList.toggle("is-hidden", which !== "professions");
  document.querySelectorAll("[data-power-sub]").forEach((b) => {
    const on = b.dataset.powerSub === which;
    b.classList.toggle("is-active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  if (which === "professions") requestAnimationFrame(() => refreshProfessionPromotionViz());
}

/** 物品：每档位卡片式展示（无 Mermaid 逻辑图）；各栏可在卡片内直接编辑 */
function renderItemGradeDashboardModules(w) {
  const root = $("vizItemGradesRoot");
  if (!root) return;
  root.replaceChildren();
  const grades = w.item_quality_system?.grades || [];
  if (!grades.length) {
    root.innerHTML = `<div class="viz-empty">暂无档位（可在下方 JSON 中添加 grades 数组）</div>`;
    return;
  }
  const nG = grades.length;
  grades.forEach((grade, idx) => {
    const block = document.createElement("div");
    block.className = "viz-module viz-module--item item-grade-viz item-grade-viz--editable";
    block.dataset.itemGradeIndex = String(idx);
    const hue = Math.round(268 + (idx / Math.max(nG - 1, 1)) * 52);
    block.style.setProperty("--tier-accent-h", String(hue));
    const nameId = `item-grade-name-${idx}`;
    const exLines = (Array.isArray(grade.examples) ? grade.examples : []).map((x) => String(x).trim()).filter(Boolean);
    block.innerHTML = `
      <div class="item-grade-viz-accent" aria-hidden="true"></div>
      <div class="viz-module-head item-grade-viz-head">
        <span class="viz-module-idx viz-module-idx--item" aria-hidden="true">${idx + 1}</span>
        <div class="viz-module-head-main">
          <label class="item-grade-name-lbl muted tiny" for="${nameId}">档位名</label>
          <input id="${nameId}" class="item-grade-name-input" type="text" data-item-field="name" value="${escapeAttr(
            grade.name || ""
          )}" placeholder="例如：凡品、稀有…" autocomplete="off" />
          <span class="viz-module-meta muted tiny">下列可直接编辑；「例子」一行一条</span>
        </div>
      </div>
      <div class="item-grade-viz-body" role="region" aria-label="档位 ${idx + 1} 详情">
        ${htmlItemGradeEditableField(
          "rarity_narrative",
          "含义（稀有叙事）",
          grade.rarity_narrative,
          "稀有度在故事里的呈现、获取氛围…",
          "mean"
        )}
        ${htmlItemGradeEditableField(
          "typical_effects",
          "典型效果",
          grade.typical_effects,
          "该档常见机制或叙事效果…",
          "fx"
        )}
        ${htmlItemGradeEditableField(
          "examples",
          "例子",
          exLines.join("\n"),
          "每行一条示例名称或短描述",
          "ex"
        )}
        ${htmlItemGradeEditableField(
          "binding_rules",
          "绑定 / 规则",
          grade.binding_rules,
          "灵魂绑定、使用限制、职业限制等…",
          "bind"
        )}
      </div>`;
    root.appendChild(block);
  });
}

function buildHistoryMermaid(events) {
  const init = mermaidFactionInit();
  const list = Array.isArray(events) ? events : [];
  if (!list.length) return init + 'flowchart TB\n  h0["（无事件）"]';
  const lines = [
    "flowchart TB",
    "  classDef hOld fill:#f1f5f9,color:#475569,stroke:#94a3b8",
    "  classDef hMid fill:#dbeafe,color:#1e40af,stroke:#3b82f6",
    "  classDef hNew fill:#ccfbf1,color:#115e59,stroke:#0d9488",
  ];
  const maxShow = 18;
  const truncated = list.length > maxShow;
  const slice = truncated ? list.slice(0, maxShow) : list;
  const nVis = slice.length;
  const clsFor = (i) => {
    if (nVis <= 1) return "hMid";
    const r = i / (nVis - 1);
    if (r < 0.35) return "hOld";
    if (r < 0.75) return "hMid";
    return "hNew";
  };
  slice.forEach((e, i) => {
    const when = (e.when || "").trim();
    const title = (e.title || "事件").trim();
    const head = mermaidEscape(`${when} ${title}`.trim().slice(0, 44));
    lines.push(`  H${i}["${head}"]`);
    lines.push(`  class H${i} ${clsFor(i)}`);
  });
  for (let i = 0; i < slice.length - 1; i++) {
    const cons = (slice[i].consequences || [])[0];
    const edge = cons ? mermaidEscape(String(cons).trim().slice(0, 22)) : "";
    if (edge) lines.push(`  H${i} -->|"${edge}"| H${i + 1}`);
    else lines.push(`  H${i} --> H${i + 1}`);
  }
  if (truncated) {
    const extra = list.length - maxShow;
    lines.push(`  Hmore["… 另有 ${extra} 条（见 JSON）"]`);
    lines.push("  class Hmore hOld");
    lines.push(`  H${slice.length - 1} --> Hmore`);
  }
  return init + lines.join("\n");
}

function uid(prefix) {
  return prefix + Math.random().toString(36).slice(2, 10);
}

function buildSingleFactionMermaid(entity, allEntities) {
  const self = mermaidEscape((entity.name || entity.id || "派系").slice(0, 28));
  const lines = [
    "flowchart TB",
    "  classDef fvRoot fill:#3d5a80,color:#fff,stroke:#2c4a6e,stroke-width:2px",
    "  classDef fvPeer fill:#f0f4f8,color:#1e293b,stroke:#94a3b8",
    "  classDef fvExt fill:#fffbeb,color:#92400e,stroke:#f59e0b,stroke-dasharray:4 3",
    "  classDef fvHint fill:#f8fafc,color:#94a3b8,stroke:#e2e8f0",
    `  root["${self}"]`,
  ];
  let n = 0;
  (entity.relations || []).forEach((rel) => {
    const tid = rel?.target_id;
    if (!tid || tid === entity.id) return;
    const target = (allEntities || []).find((x) => x.id === tid);
    const isKnown = !!target;
    const rawLabel = isKnown
      ? target.name || target.id || tid
      : `${tid}（未建档）`;
    const label = mermaidEscape(String(rawLabel).slice(0, 30));
    const edgeRaw = `${rel.type || "关联"}${rel.notes ? " · " + rel.notes : ""}`.trim();
    const edge = mermaidEscape(edgeRaw.slice(0, 40));
    lines.push(`  T${n}["${label}"]`);
    lines.push(
      isKnown ? `  root -->|"${edge}"| T${n}` : `  root -.->|"${edge}"| T${n}`
    );
    lines.push(`  class T${n} ${isKnown ? "fvPeer" : "fvExt"}`);
    n += 1;
  });
  lines.push("  class root fvRoot");
  if (n === 0) {
    lines.push('  hint["暂无对外关系"]');
    lines.push("  class hint fvHint");
    lines.push("  root --- hint");
  }
  return mermaidFactionInit() + lines.join("\n");
}

function gidGeo(i) {
  return `g${i}`;
}

/** 区域列表 + 可选 relations（target_id 指向其他区域 id）→ Mermaid 网络图 */
function buildGeographyMermaid(regions, worldLabel) {
  const regs = Array.isArray(regions) ? regions : [];
  const init = mermaidFactionInit();
  if (!regs.length) {
    return init + 'flowchart TB\n  geoEmpty["（暂无区域）"]';
  }
  const hub = mermaidEscape(String(worldLabel || "地理总览").slice(0, 22));
  const lines = [
    "flowchart TB",
    "  classDef mGeoHub fill:#0d9488,color:#fff,stroke:#0f766e,stroke-width:2px",
    "  classDef mGeoReg fill:#ecfdf5,color:#064e3b,stroke:#5eead4",
    "  classDef mGeoExt fill:#fffbeb,color:#92400e,stroke:#f59e0b,stroke-dasharray:4 3",
    `  GHUB["${hub}"]`,
  ];
  regs.forEach((r, i) => {
    const label = mermaidEscape(String(r.name || r.id || `区域${i + 1}`).slice(0, 24));
    lines.push(`  ${gidGeo(i)}["${label}"]`);
    lines.push(`  class ${gidGeo(i)} mGeoReg`);
  });
  lines.push("  class GHUB mGeoHub");
  regs.forEach((r, i) => {
    const edge = mermaidEscape(
      String(r.terrain || r.climate || "子区域").slice(0, 18)
    );
    lines.push(`  GHUB -->|"${edge}"| ${gidGeo(i)}`);
  });
  const idToIdx = new Map();
  regs.forEach((r, i) => {
    const rid = String(r.id || "").trim();
    if (rid) idToIdx.set(rid, i);
  });
  const pairSeen = new Set();
  let unk = 0;
  regs.forEach((r, i) => {
    (r.relations || []).forEach((rel) => {
      const tid = String(rel?.target_id || "").trim();
      if (!tid || tid === String(r.id || "").trim()) return;
      const lab = mermaidEscape(
        `${rel.type || "关联"}${rel.notes ? "·" + rel.notes : ""}`.slice(0, 28)
      );
      const j = idToIdx.get(tid);
      if (j != null && j !== i) {
        const a = Math.min(i, j);
        const b = Math.max(i, j);
        const key = `${a}-${b}`;
        if (pairSeen.has(key)) return;
        pairSeen.add(key);
        lines.push(`  ${gidGeo(a)} -->|"${lab}"| ${gidGeo(b)}`);
      } else {
        const nk = `gU${unk}`;
        unk += 1;
        const tlab = mermaidEscape(`${tid.slice(0, 16)}（未建档）`);
        lines.push(`  ${nk}["${tlab}"]`);
        lines.push(`  class ${nk} mGeoExt`);
        lines.push(`  ${gidGeo(i)} -.->|"${lab}"| ${nk}`);
      }
    });
  });
  return init + lines.join("\n");
}

function getRegionsForGeoViz() {
  const root = $("regionCards");
  if (root) {
    if (root.querySelector(".region-card")) return collectRegionsFromDom();
    return [];
  }
  return state.world?.geography?.regions || [];
}

/** 大陆 / 区域卡片左侧图示（Material Symbols 名称） */
function pickRegionGlyph(name, terrain, summary, idx) {
  const t = [name, terrain, summary].map((x) => (x || "").toString().trim()).join(" ");
  const lower = t.toLowerCase();
  const rules = [
    [/海|洋|岛|港|湾|潮|渔|舰|波|舟|渊|滨海|海岸/, "waves"],
    [/湖|河|川|沼|湿地|溪|流|池|淀|江|漕|渡口/, "water"],
    [/雪|冰|寒|极地|冻|霜|雹|凛冬|冰川/, "severe_cold"],
    [/沙|漠|荒|戈壁|旱|风尘|流沙/, "wb_sunny"],
    [/山|峰|高原|岭|崖|峡|巅|岩|峦|雪域.*山/, "landscape"],
    [/森|林|木|竹|苔|乔|灌|绿荫|雨林/, "forest"],
    [/城|市|镇|坊|都|邑|宫|堡|郭|京畿|城邦/, "location_city"],
    [/草|原|牧|田|农|耕|坪|甸|沃野|麦/, "park"],
    [/谷|盆地|洼地/, "terrain"],
    [/火|熔|岩|浆|火山|硫磺|地热/, "local_fire_department"],
    [/云|天|空|雷|岚|霄|罡|浮空|天穹/, "air"],
    [/洞|穴|地下|隧|矿坑|地底|幽窟/, "layers"],
    [/平|川|陆|广|中原|沃壤/, "map"],
  ];
  for (const [re, g] of rules) {
    if (re.test(t) || re.test(lower)) return g;
  }
  const fallbacks = [
    "travel_explore",
    "public",
    "map",
    "explore",
    "add_location_alt",
    "place",
    "terrain",
  ];
  return fallbacks[idx % fallbacks.length];
}

function syncRegionCardIcon(card) {
  if (!card) return;
  const ic = card.querySelector(".region-viz-ic");
  if (!ic) return;
  const root = card.parentElement;
  const idx = root ? [...root.querySelectorAll(".region-card")].indexOf(card) : 0;
  const name = card.querySelector(".region-name")?.value || "";
  const terrain = card.querySelector(".region-terrain")?.value || "";
  const summary = card.querySelector(".region-summary")?.value || "";
  ic.textContent = pickRegionGlyph(name, terrain, summary, Math.max(0, idx));
}

let _geoVizTimer;
function scheduleGeoVizRefresh() {
  clearTimeout(_geoVizTimer);
  _geoVizTimer = setTimeout(() => refreshGeoNetworkViz(), 240);
}

function refreshGeoNetworkViz() {
  const regs = getRegionsForGeoViz();
  const label = state.world?.meta?.name || "地理总览";
  const def = buildGeographyMermaid(regs, label);
  void drawMermaidHost($("geoNetworkHost"), def);
}

function renderRegionCards(regions) {
  const root = $("regionCards");
  if (!root) return;
  root.replaceChildren();
  const list = Array.isArray(regions) && regions.length ? regions : [];
  list.forEach((r, idx) => {
    const card = document.createElement("div");
    card.className = "region-card";
    const hue = (idx * 53) % 360;
    const relJson = JSON.stringify(r.relations || [], null, 2);
    const lmLines = (Array.isArray(r.landmarks) ? r.landmarks : []).map((x) => String(x).trim()).filter(Boolean);
    const resLines = (Array.isArray(r.resources) ? r.resources : []).map((x) => String(x).trim()).filter(Boolean);
    const glyph = pickRegionGlyph(r.name, r.terrain, r.summary || r.desc, idx);
    card.style.setProperty("--rv-hue", String(hue));
    card.innerHTML = `
      <div class="region-card-head">
        <div class="region-viz" role="img" aria-label="区域类型图示">
          <span class="ms region-viz-ic" aria-hidden="true">${glyph}</span>
        </div>
        <div class="region-fields">
          <div class="region-name-row">
            <input type="hidden" class="region-id" />
            <input type="text" class="region-name" placeholder="大陆 / 区域名称" />
            <button type="button" class="ghost btn-icon remove-region" title="移除此区域">
              <span class="ms" aria-hidden="true">close</span>
            </button>
          </div>
          <div class="region-field region-field-span-2">
            <label class="region-field-label">区域概述</label>
            <textarea class="region-summary" rows="3" placeholder="地貌、政权、文化带、与其他区的关系…"></textarea>
          </div>
          <div class="region-field">
            <label class="region-field-label">地形 / 地貌</label>
            <input type="text" class="region-terrain" placeholder="丘陵、河网、冰原…" />
          </div>
          <div class="region-field">
            <label class="region-field-label">局地气候</label>
            <input type="text" class="region-climate" placeholder="冬雨型、干热谷风…（可选）" />
          </div>
          <div class="region-field region-field-span-2">
            <label class="region-field-label">旅行 / 叙事备注</label>
            <textarea class="region-notes" rows="2" placeholder="风险点、关卡、调查钩子…（可选）"></textarea>
          </div>
          <div class="region-field">
            <label class="region-field-label">地标 <span class="region-field-hint">每行一条</span></label>
            <textarea class="region-landmarks" rows="3" placeholder="辉石城、古渡…"></textarea>
          </div>
          <div class="region-field">
            <label class="region-field-label">资源 <span class="region-field-hint">每行一条</span></label>
            <textarea class="region-resources" rows="3" placeholder="木材、精铁矿…"></textarea>
          </div>
          <div class="region-field region-field-span-2 region-field--relations">
            <label class="region-field-label">与其它区域的关联 <code class="region-code-tag">relations</code></label>
            <textarea class="region-relations-json" rows="3" spellcheck="false" placeholder='[{"target_id":"other-region-id","type":"邻接","notes":""}]'></textarea>
          </div>
        </div>
      </div>`;
    card.querySelector(".region-id").value = r.id || uid("r");
    card.querySelector(".region-name").value = r.name || "";
    card.querySelector(".region-summary").value = r.summary || r.desc || "";
    card.querySelector(".region-terrain").value = r.terrain || "";
    card.querySelector(".region-climate").value = r.climate || "";
    card.querySelector(".region-notes").value = r.notes || "";
    card.querySelector(".region-landmarks").value = lmLines.join("\n");
    card.querySelector(".region-resources").value = resLines.join("\n");
    card.querySelector(".region-relations-json").value = relJson;
    root.appendChild(card);
  });
  scheduleGeoVizRefresh();
  applyAllWorldviewEditModes();
}

function collectRegionsFromDom() {
  const root = $("regionCards");
  if (!root) return [];
  return [...root.querySelectorAll(".region-card")]
    .map((card) => {
      let relations = [];
      try {
        relations = JSON.parse(card.querySelector(".region-relations-json")?.value || "[]");
        if (!Array.isArray(relations)) relations = [];
      } catch {
        relations = [];
      }
      const splitField = (sel) =>
        (card.querySelector(sel)?.value ?? "")
          .split("\n")
          .map((s) => s.trim())
          .filter(Boolean);
      return {
        id: card.querySelector(".region-id")?.value?.trim() || uid("r"),
        name: card.querySelector(".region-name")?.value?.trim() || "",
        summary: card.querySelector(".region-summary")?.value?.trim() || "",
        terrain: card.querySelector(".region-terrain")?.value?.trim() || "",
        climate: card.querySelector(".region-climate")?.value?.trim() || "",
        notes: card.querySelector(".region-notes")?.value?.trim() || "",
        landmarks: splitField(".region-landmarks"),
        resources: splitField(".region-resources"),
        relations,
      };
    })
    .filter(
      (r) =>
        r.name ||
        r.summary ||
        r.terrain ||
        r.climate ||
        r.notes ||
        (Array.isArray(r.landmarks) && r.landmarks.length) ||
        (Array.isArray(r.resources) && r.resources.length) ||
        (Array.isArray(r.relations) && r.relations.length > 0)
    );
}

function syncFactionCardBrief(card, entity) {
  if (!card || !entity) return;
  const g = card.querySelector(".faction-intro-goals");
  const tr = card.querySelector(".faction-intro-territory");
  const nm = card.querySelector(".faction-intro-name");
  if (g) g.textContent = (entity.goals || "").trim() || "（未填写）";
  if (tr) tr.textContent = (entity.territory || "").trim() || "（未填写）";
  if (nm) nm.textContent = (entity.name || "").trim() || "（未命名）";
}

function renderFactionCards(entities) {
  const root = $("factionCards");
  if (!root) return;
  root.replaceChildren();
  const list = Array.isArray(entities) && entities.length ? entities.map((e) => ({ ...e })) : [];
  list.forEach((e, idx) => {
    const card = document.createElement("div");
    card.className = "faction-card";
    const hue = (idx * 47 + 200) % 360;
    const relJson = JSON.stringify(e.relations || [], null, 2);
    const kf = (e.key_figures || []).join("\n");
    const relCount = (e.relations || []).filter((r) => r?.target_id && r.target_id !== e.id).length;
    card.innerHTML = `
      <div class="faction-card-stack">
        <div class="faction-card-toolbar">
          <p class="faction-viz-legend muted tiny">
            关系图可缩放（滚轮或按钮）。实线 → 已建档派系；虚线 → 仅 id。
          </p>
          <button type="button" class="ghost btn-icon remove-faction" title="移除此派系">×</button>
        </div>
        <div class="faction-intro-viz" style="--fv-hue:${hue}">
          <div class="faction-intro-viz-head">
            <span class="ms faction-intro-ic" aria-hidden="true">shield</span>
            <span class="faction-intro-name"></span>
          </div>
          <div class="faction-brief-line">
            <span class="faction-brief-k">目标</span>
            <p class="faction-intro-goals faction-brief-body"></p>
          </div>
          <div class="faction-brief-line">
            <span class="faction-brief-k">地盘</span>
            <p class="faction-intro-territory faction-brief-body"></p>
          </div>
        </div>
        <div class="faction-viz-wrap" style="--fv-hue:${hue}">
          <div class="faction-viz-caption">
            <span>关系网络</span>
            <span class="faction-viz-badge">${relCount} 条</span>
          </div>
          <div class="mermaid-zoom-wrap faction-card-zoom" data-mermaid-zoom>
            <div class="mermaid-zoom-toolbar" role="toolbar" aria-label="关系图缩放">
              <button type="button" class="ghost btn-sm mzoom-out" title="缩小">−</button>
              <span class="mzoom-pct muted tiny">100%</span>
              <button type="button" class="ghost btn-sm mzoom-in" title="放大">+</button>
              <button type="button" class="ghost btn-sm mzoom-reset" title="重置缩放与平移">重置</button>
            </div>
            <div class="mermaid-zoom-viewport faction-card-zoom-viewport">
              <div class="mermaid-zoom-surface">
                <div class="faction-viz-host mermaid-host" role="img" aria-label="派系关系示意"></div>
              </div>
            </div>
          </div>
        </div>
        <div class="faction-fields">
          <div class="row-tight">
            <input type="text" class="faction-id mono" placeholder="id（英文）" />
            <input type="text" class="faction-name" placeholder="派系名称" />
          </div>
          <label class="muted tiny">目标 / 宗旨</label>
          <textarea class="faction-goals" rows="2" placeholder="派系简介：宗旨、立场…"></textarea>
          <label class="muted tiny">地盘 / 势力范围</label>
          <textarea class="faction-territory" rows="2" placeholder="控制区、据点、影响范围…"></textarea>
          <label class="muted tiny">关键人物（每行一人）</label>
          <textarea class="faction-figures" rows="2"></textarea>
          <label class="muted tiny">relations（JSON）</label>
          <textarea class="faction-relations-json json-editor-tiny" rows="2" spellcheck="false"></textarea>
        </div>
      </div>`;
    card.querySelector(".faction-id").value = e.id || uid("f");
    card.querySelector(".faction-name").value = e.name || "";
    card.querySelector(".faction-goals").value = e.goals || "";
    card.querySelector(".faction-territory").value = e.territory || "";
    card.querySelector(".faction-figures").value = kf;
    card.querySelector(".faction-relations-json").value = relJson;
    syncFactionCardBrief(card, e);
    root.appendChild(card);
    const host = card.querySelector(".faction-viz-host");
    void drawMermaidHost(host, buildSingleFactionMermaid(list[idx], list));
  });
  const fj = $("factionsJson");
  if (fj) fj.value = JSON.stringify(list, null, 2);
  refreshFactionChatViz();
}

function collectFactionsFromDom() {
  const root = $("factionCards");
  if (!root) return [];
  return [...root.querySelectorAll(".faction-card")].map((card) => {
    const id = card.querySelector(".faction-id")?.value?.trim() || uid("f");
    const name = card.querySelector(".faction-name")?.value?.trim() || "";
    const goals = card.querySelector(".faction-goals")?.value?.trim() || "";
    const territory = card.querySelector(".faction-territory")?.value?.trim() || "";
    const figTxt = card.querySelector(".faction-figures")?.value || "";
    const key_figures = figTxt
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    let relations = [];
    try {
      relations = JSON.parse(card.querySelector(".faction-relations-json")?.value || "[]");
      if (!Array.isArray(relations)) relations = [];
    } catch {
      relations = [];
    }
    return { id, name, goals, territory, key_figures, relations };
  });
}

/** 对话区派系要人快照：优先读派系页 DOM（未保存的编辑），否则读 state.world */
function factionsSnapshotForChatViz() {
  if (!state.world) return [];
  const root = $("factionCards");
  if (root?.querySelector(".faction-card")) return collectFactionsFromDom();
  return state.world.factions?.entities || [];
}

function refreshFactionChatViz() {
  const host = $("factionChatViz");
  if (!host) return;
  const list = factionsSnapshotForChatViz();
  if (!list.length) {
    host.className = "faction-chat-viz faction-chat-viz--empty";
    host.textContent = state.world
      ? "当前无派系实体。可用下方「写派系」「派系要人」发起对话；保存或开启「对话后同步」后将写入 factions。"
      : "选择或创建世界后，此处显示各派系要人快照（与派系页卡片一致）。";
    return;
  }
  host.className = "faction-chat-viz";
  host.innerHTML = list
    .map((e) => {
      const figs = Array.isArray(e.key_figures) ? e.key_figures.filter(Boolean) : [];
      const n = figs.length;
      const show = figs.slice(0, 4);
      const more = n > 4 ? `<li class="muted tiny">… 共 ${n} 人</li>` : "";
      const lis = show
        .map((f) => {
          const s = String(f);
          const t = s.length > 48 ? `${s.slice(0, 48)}…` : s;
          return `<li>${escapeHtml(t)}</li>`;
        })
        .join("");
      const title = escapeHtml((e.name || e.id || "未命名").slice(0, 22));
      return `<div class="faction-chat-viz-card">
        <div class="faction-chat-viz-card__name"><span class="ms" aria-hidden="true">groups</span><span>${title}</span><span class="faction-chat-viz-badge">${n} 要人</span></div>
        ${
          n
            ? `<ul class="faction-chat-viz-figures">${lis}${more}</ul>`
            : `<p class="muted tiny" style="margin:0">暂无 key_figures，可点「派系要人」请助手扩写。</p>`
        }
      </div>`;
    })
    .join("");
}

let _factionVizTimer;
function refreshAllFactionViz() {
  const root = $("factionCards");
  if (!root) return;
  const all = collectFactionsFromDom();
  const fj = $("factionsJson");
  if (fj) fj.value = JSON.stringify(all, null, 2);
  [...root.querySelectorAll(".faction-card")].forEach((card, idx) => {
    const e = all[idx];
    if (e) syncFactionCardBrief(card, e);
    const badge = card.querySelector(".faction-viz-badge");
    if (badge && e) {
      const n = (e.relations || []).filter((r) => r?.target_id && r.target_id !== e.id).length;
      badge.textContent = `${n} 条`;
    }
    const host = card.querySelector(".faction-viz-host");
    if (host && e) void drawMermaidHost(host, buildSingleFactionMermaid(e, all));
  });
  refreshFactionChatViz();
  applyAllWorldviewEditModes();
}

function scheduleFactionVizRefresh() {
  clearTimeout(_factionVizTimer);
  _factionVizTimer = setTimeout(() => refreshAllFactionViz(), 220);
}

function renderCultureCards(entities) {
  const root = $("cultureCards");
  if (!root) return;
  root.replaceChildren();
  const list = Array.isArray(entities) && entities.length ? entities.map((e) => ({ ...e })) : [];
  list.forEach((e) => {
    const card = document.createElement("div");
    card.className = "faction-card culture-card";
    const relJson = JSON.stringify(e.relations || [], null, 2);
    const sites = (e.sacred_sites || []).join("\n");
    const kf = (e.key_figures || []).join("\n");
    const kind = ["culture", "religion", "syncretic"].includes(e.kind) ? e.kind : "culture";
    card.innerHTML = `
      <div class="faction-card-stack">
        <div class="faction-card-toolbar">
          <p class="faction-viz-legend muted tiny">relations 的 target_id 指向另一文化实体 id</p>
          <button type="button" class="ghost btn-icon remove-culture" title="移除此条目">×</button>
        </div>
        <div class="faction-fields">
          <div class="row-tight">
            <input type="text" class="culture-id mono" placeholder="id" />
            <input type="text" class="culture-name" placeholder="名称" />
            <select class="culture-kind">
              <option value="culture">文化</option>
              <option value="religion">宗教</option>
              <option value="syncretic">融合</option>
            </select>
          </div>
          <label class="muted tiny">概述</label>
          <textarea class="culture-summary" rows="2" placeholder="人群、分布、叙事角色…"></textarea>
          <label class="muted tiny">观念 / 教义</label>
          <textarea class="culture-tenets" rows="2"></textarea>
          <label class="muted tiny">仪式 / 节日 / 禁忌</label>
          <textarea class="culture-practices" rows="2"></textarea>
          <label class="muted tiny">圣地或中心（每行一处）</label>
          <textarea class="culture-sites" rows="2"></textarea>
          <label class="muted tiny">关键人物（每行一人）</label>
          <textarea class="culture-figures" rows="2"></textarea>
          <label class="muted tiny">relations（JSON）</label>
          <textarea class="culture-relations-json json-editor-tiny" rows="2" spellcheck="false"></textarea>
        </div>
      </div>`;
    card.querySelector(".culture-id").value = e.id || uid("c");
    card.querySelector(".culture-name").value = e.name || "";
    card.querySelector(".culture-kind").value = kind;
    card.querySelector(".culture-summary").value = e.summary || "";
    card.querySelector(".culture-tenets").value = e.tenets || "";
    card.querySelector(".culture-practices").value = e.practices || "";
    card.querySelector(".culture-sites").value = sites;
    card.querySelector(".culture-figures").value = kf;
    card.querySelector(".culture-relations-json").value = relJson;
    root.appendChild(card);
  });
  const cj = $("culturesJson");
  if (cj) cj.value = JSON.stringify(list, null, 2);
  scheduleCultureVizRefresh();
  applyAllWorldviewEditModes();
}

function collectCulturesFromDom() {
  const root = $("cultureCards");
  if (!root) return [];
  return [...root.querySelectorAll(".culture-card")].map((card) => {
    const id = card.querySelector(".culture-id")?.value?.trim() || uid("c");
    const name = card.querySelector(".culture-name")?.value?.trim() || "";
    const kind = card.querySelector(".culture-kind")?.value || "culture";
    const summary = card.querySelector(".culture-summary")?.value?.trim() || "";
    const tenets = card.querySelector(".culture-tenets")?.value?.trim() || "";
    const practices = card.querySelector(".culture-practices")?.value?.trim() || "";
    const sitesTxt = card.querySelector(".culture-sites")?.value || "";
    const sacred_sites = sitesTxt
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    const figTxt = card.querySelector(".culture-figures")?.value || "";
    const key_figures = figTxt
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    let relations = [];
    try {
      relations = JSON.parse(card.querySelector(".culture-relations-json")?.value || "[]");
      if (!Array.isArray(relations)) relations = [];
    } catch {
      relations = [];
    }
    return {
      id,
      name,
      kind,
      summary,
      tenets,
      practices,
      sacred_sites,
      key_figures,
      relations,
    };
  });
}

let _cultureVizTimer;
function scheduleCultureVizRefresh() {
  clearTimeout(_cultureVizTimer);
  _cultureVizTimer = setTimeout(() => refreshCultureGlobalViz(), 200);
}

function refreshCultureGlobalViz() {
  const host = $("vizCulturesHost");
  if (!host) return;
  const entities = collectCulturesFromDom();
  const cj = $("culturesJson");
  if (cj) cj.value = JSON.stringify(entities, null, 2);
  void drawMermaidHost(host, buildCultureMermaid(entities));
}

function renderStatStrip(w) {
  const el = $("statStrip");
  if (!el) return;
  if (!w) {
    el.innerHTML = "";
    return;
  }
  const g = w.geography || {};
  const lm = (g.landmarks || []).length;
  const rs = (g.resources || []).length;
  const pt = (w.power_system?.tiers || []).length;
  const ig = (w.item_quality_system?.grades || []).length;
  const at = (w.attribute_system?.stats || []).length;
  const fc = (w.factions?.entities || []).length;
  const cu = (w.cultures?.entities || []).length;
  const ev = (w.history?.events || []).length;
  const wlabel = escapeHtml((w.meta?.name || w.meta?.id || "世界").toString().slice(0, 24));
  const pill = (icon, t) =>
    `<span class="pill"><span class="ms pill-ic" aria-hidden="true">${icon}</span>${t}</span>`;
  el.innerHTML = [
    pill("auto_stories", wlabel),
    pill("place", `地标 ${lm}`),
    pill("forest", `资源 ${rs}`),
    pill("bolt", `境界 ${pt}`),
    pill("bubble_chart", `属性 ${at}`),
    pill("diamond", `品质 ${ig}`),
    pill("groups", `派系 ${fc}`),
    pill("diversity_3", `文化 ${cu}`),
    pill("event", `事件 ${ev}`),
    pill("search", "搜索"),
    pill("folder_open", "导出与快照"),
    pill("tag", `v${w.meta?.version ?? 0}`),
  ].join("");
}

function setThinking(phase) {
  const el = $("chatThinking");
  if (!el) return;
  const lab = el.querySelector(".thinking-label");
  if (!phase) {
    el.hidden = true;
    el.classList.remove("thinking-strip--visible");
    return;
  }
  el.hidden = false;
  el.classList.add("thinking-strip--visible");
  if (lab) {
    lab.textContent =
      phase === "sync" ? "正在将对话整理为结构化设定…" : "模型正在思考回复…";
  }
}

function renderHistoryMajorTimeline(events) {
  const el = $("historyMajorTimeline");
  if (!el) return;
  const list = Array.isArray(events) ? events : [];
  if (!list.length) {
    el.innerHTML = `<div class="viz-empty">暂无事件，可在下方 JSON 中添加，或在时间轴卡片中编辑（有事件后）</div>`;
    return;
  }
  el.innerHTML = list
    .map((e, i) => {
      const cons = (Array.isArray(e.consequences) ? e.consequences : [])
        .map((x) => String(x).trim())
        .filter(Boolean);
      const links = (Array.isArray(e.linked_faction_ids) ? e.linked_faction_ids : [])
        .map((x) => String(x).trim())
        .filter(Boolean);
      const whenId = `hist-when-${i}`;
      const titleId = `hist-title-${i}`;
      return `<div class="hist-tl-row hist-tl-row--editable" data-history-event-index="${i}">
        <div class="hist-tl-axis"><span class="hist-tl-dot"></span>${
          i < list.length - 1 ? '<span class="hist-tl-line"></span>' : ""
        }</div>
        <div class="hist-tl-card hist-tl-card--editable">
          <label class="hist-field-lbl muted tiny" for="${whenId}">时间 / 年代</label>
          <input id="${whenId}" type="text" class="hist-field-input" data-hist-field="when" value="${escapeAttr(
            (e.when ?? "").toString()
          )}" placeholder="如：第三纪 末叶" autocomplete="off" />
          <label class="hist-field-lbl muted tiny" for="${titleId}">标题</label>
          <input id="${titleId}" type="text" class="hist-field-input" data-hist-field="title" value="${escapeAttr(
            (e.title ?? "").toString()
          )}" placeholder="事件名" autocomplete="off" />
          <label class="muted tiny hist-field-lbl">摘要</label>
          <textarea class="hist-field-ta" rows="3" data-hist-field="summary" spellcheck="true" placeholder="叙事摘要…">${escapeHtml(
            (e.summary ?? "").toString()
          )}</textarea>
          <label class="muted tiny hist-field-lbl">后果（一行一条）</label>
          <textarea class="hist-field-ta" rows="2" data-hist-field="consequences" spellcheck="true" placeholder="每行一条后果">${escapeHtml(
            cons.join("\n")
          )}</textarea>
          <label class="muted tiny hist-field-lbl">关联派系 id（一行一个）</label>
          <textarea class="hist-field-ta" rows="2" data-hist-field="linked_faction_ids" spellcheck="false" placeholder="与 factions.entities[].id 对应">${escapeHtml(
            links.join("\n")
          )}</textarea>
        </div>
      </div>`;
    })
    .join("");
}

let _factionBriefTimer;
function scheduleFactionGlobalBriefPreview() {
  clearTimeout(_factionBriefTimer);
  _factionBriefTimer = setTimeout(updateFactionGlobalBriefPreview, 140);
}

function updateFactionGlobalBriefPreview() {
  const el = $("factionGlobalBrief");
  const ta = $("factionSummary");
  if (!el || !ta) return;
  const t = ta.value.trim();
  if (!t) {
    el.innerHTML = `<span class="muted tiny">（在下方「派系总览」中填写后，此处显示可读预览）</span>`;
    return;
  }
  el.innerHTML = `<div class="faction-brief-prose">${escapeHtml(t).replace(/\n/g, "<br/>")}</div>`;
}

let _histJsonTimer;
function scheduleHistoryVizFromForm() {
  clearTimeout(_histJsonTimer);
  _histJsonTimer = setTimeout(() => {
    let events = [];
    try {
      events = JSON.parse($("historyJson")?.value || "[]");
    } catch {
      return;
    }
    if (!Array.isArray(events)) return;
    if (state.world) {
      state.world.history = state.world.history || {};
      state.world.history.events = events;
    }
    renderHistoryMajorTimeline(events);
    void drawMermaidHost($("vizHistoryHost"), buildHistoryMermaid(events));
    applyAllWorldviewEditModes();
  }, 280);
}

/** 派系关系图容器：缩放（按钮 + 滚轮）+ 左键拖拽平移 */
function initMermaidZoom(wrap, opts = {}) {
  if (!wrap) return;
  const surface = wrap.querySelector(".mermaid-zoom-surface");
  const viewport = wrap.querySelector(".mermaid-zoom-viewport");
  const pctEl = wrap.querySelector(".mzoom-pct");
  if (!surface || !viewport) return;

  if (opts.resetPan) {
    wrap.dataset.mzoomTx = "0";
    wrap.dataset.mzoomTy = "0";
  }

  const clamp = (s) => Math.min(2.6, Math.max(0.35, s));
  const apply = () => {
    let scale = parseFloat(wrap.dataset.mzoomScale || "1");
    if (Number.isNaN(scale)) scale = 1;
    scale = clamp(scale);
    wrap.dataset.mzoomScale = String(scale);
    let tx = parseFloat(wrap.dataset.mzoomTx || "0");
    let ty = parseFloat(wrap.dataset.mzoomTy || "0");
    if (Number.isNaN(tx)) tx = 0;
    if (Number.isNaN(ty)) ty = 0;
    wrap.dataset.mzoomTx = String(tx);
    wrap.dataset.mzoomTy = String(ty);
    surface.style.transformOrigin = "0 0";
    surface.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
    if (pctEl) pctEl.textContent = `${Math.round(scale * 100)}%`;
  };

  if (wrap.dataset.mzoomHandlers !== "1") wrap.dataset.mzoomScale = "1";
  apply();

  if (wrap.dataset.mzoomHandlers === "1") return;
  wrap.dataset.mzoomHandlers = "1";

  wrap.addEventListener("click", (e) => {
    const t = e.target;
    if (!t.closest) return;
    let s = parseFloat(wrap.dataset.mzoomScale || "1");
    if (Number.isNaN(s)) s = 1;
    if (t.closest(".mzoom-in")) wrap.dataset.mzoomScale = String(clamp(s * 1.14));
    else if (t.closest(".mzoom-out")) wrap.dataset.mzoomScale = String(clamp(s / 1.14));
    else if (t.closest(".mzoom-reset")) {
      wrap.dataset.mzoomScale = "1";
      wrap.dataset.mzoomTx = "0";
      wrap.dataset.mzoomTy = "0";
      viewport.scrollTo(0, 0);
    } else return;
    apply();
  });

  viewport.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      let s = parseFloat(wrap.dataset.mzoomScale || "1");
      if (Number.isNaN(s)) s = 1;
      wrap.dataset.mzoomScale = String(clamp(s * (e.deltaY < 0 ? 1.06 : 0.94)));
      apply();
    },
    { passive: false }
  );

  const onDocMove = (ev) => {
    const session = wrap.__mzoomPanSession;
    if (!session) return;
    const dx = ev.clientX - session.sx;
    const dy = ev.clientY - session.sy;
    wrap.dataset.mzoomTx = String(session.tx0 + dx);
    wrap.dataset.mzoomTy = String(session.ty0 + dy);
    apply();
  };

  const onDocUp = () => {
    wrap.__mzoomPanSession = null;
    viewport.classList.remove("is-dragging");
    document.removeEventListener("mousemove", onDocMove);
    document.removeEventListener("mouseup", onDocUp);
  };

  viewport.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    if (e.target.closest(".mermaid-zoom-toolbar")) return;
    const tx0 = parseFloat(wrap.dataset.mzoomTx || "0");
    const ty0 = parseFloat(wrap.dataset.mzoomTy || "0");
    wrap.__mzoomPanSession = {
      sx: e.clientX,
      sy: e.clientY,
      tx0: Number.isNaN(tx0) ? 0 : tx0,
      ty0: Number.isNaN(ty0) ? 0 : ty0,
    };
    viewport.classList.add("is-dragging");
    e.preventDefault();
    document.addEventListener("mousemove", onDocMove);
    document.addEventListener("mouseup", onDocUp);
  });
}

async function drawMermaidHost(host, def) {
  if (!host) return;
  host.innerHTML = "";
  if (!def || !window.mermaid) return;
  const id = "mmd" + Math.random().toString(36).slice(2, 11);
  const zoomWrap = host.closest("[data-mermaid-zoom]");
  try {
    if (typeof mermaid.render === "function") {
      const { svg } = await mermaid.render(id, def);
      host.innerHTML = svg;
      initMermaidZoom(zoomWrap, { resetPan: true });
      return;
    }
  } catch (_) {
    /* fall through */
  }
  try {
    host.innerHTML = `<pre class="mermaid">${def.replace(/</g, "&lt;")}</pre>`;
    const node = host.querySelector("pre");
    if (node && typeof mermaid.run === "function") await mermaid.run({ nodes: [node] });
    initMermaidZoom(zoomWrap, { resetPan: true });
  } catch (_) {
    host.innerHTML = "";
  }
}

function refreshContextPanel() {
  const rawEl = $("contextRawJson");
  const powSys = $("vizPowerSystemModules");
  const powTrees = $("vizPowerSkillTreeModules");
  const powProf = $("vizPowerProfessionModules");
  const itemMods = $("vizItemGradesRoot");
  const fac = $("vizFactionHost");
  const his = $("vizHistoryHost");
  const cult = $("vizCulturesHost");

  const geoPanel = $("geoNetworkHost");

  if (!state.world) {
    renderStatStrip(null);
    if (powSys) powSys.innerHTML = "";
    if (powTrees) powTrees.innerHTML = "";
    if (powProf) powProf.innerHTML = "";
    const profPromo = $("vizProfessionPromoHost");
    if (profPromo) profPromo.innerHTML = "";
    if (itemMods) itemMods.innerHTML = "";
    if (geoPanel) geoPanel.innerHTML = "";
    if (fac) fac.innerHTML = "";
    if (cult) cult.innerHTML = "";
    if (his) his.innerHTML = "";
    renderHistoryMajorTimeline([]);
    const fgb = $("factionGlobalBrief");
    if (fgb) fgb.innerHTML = "";
    if (rawEl) rawEl.textContent = "";
    const rlo = $("referenceLintOut");
    if (rlo) rlo.innerHTML = "";
    renderAttributePanel(null);
    void refreshSnapshotPanel();
    applyAllWorldviewEditModes();
    return;
  }

  const w = state.world;
  renderStatStrip(w);
  renderPowerTierDashboardModules(w);
  renderItemGradeDashboardModules(w);
  renderAttributePanel(w);

  refreshGeoNetworkViz();
  void drawMermaidHost(fac, buildFactionMermaid(w.factions?.entities));
  const cultHost = $("vizCulturesHost");
  if (cultHost) void drawMermaidHost(cultHost, buildCultureMermaid(w.cultures?.entities || []));
  const ev = w.history?.events || [];
  renderHistoryMajorTimeline(ev);
  void drawMermaidHost(his, buildHistoryMermaid(ev));

  if (rawEl) rawEl.textContent = JSON.stringify(w, null, 2);
  void refreshSnapshotPanel();
  applyAllWorldviewEditModes();
}

async function refreshSnapshotPanel() {
  const leftSel = $("snapshotDiffLeft");
  const rightSel = $("snapshotDiffRight");
  const rbSel = $("snapshotRollbackSel");
  const wrap = $("snapshotDiffWrap");
  const pre = $("snapshotDiffPre");
  const meta = $("snapshotDiffMeta");
  const btnDiff = $("btnSnapshotDiff");
  const btnRb = $("btnSnapshotRollback");
  if (!leftSel || !rightSel || !rbSel) return;

  if (!state.world?.meta?.id) {
    leftSel.innerHTML = "";
    rightSel.innerHTML = "";
    rbSel.innerHTML = "";
    if (wrap) wrap.hidden = true;
    if (pre) pre.textContent = "";
    if (meta) meta.textContent = "";
    if (btnDiff) btnDiff.disabled = true;
    if (btnRb) btnRb.disabled = true;
    return;
  }

  const id = state.world.meta.id;
  const cv = state.world.meta?.version ?? "?";
  try {
    const data = await api(`/api/worlds/${id}/snapshots`);
    const snaps = Array.isArray(data.snapshots) ? data.snapshots : [];

    leftSel.innerHTML = "";
    rightSel.innerHTML = "";
    rbSel.innerHTML = "";

    const optCurrent = document.createElement("option");
    optCurrent.value = "current";
    optCurrent.textContent = `当前 v${cv}`;
    rightSel.appendChild(optCurrent);

    for (const s of snaps) {
      const v = s.version;
      const ts = (s.updated_at || "").toString().slice(0, 19);
      const label = `v${v}${ts ? " · " + ts : ""}`;

      const ol = document.createElement("option");
      ol.value = String(v);
      ol.textContent = label;
      leftSel.appendChild(ol);

      const or = document.createElement("option");
      or.value = String(v);
      or.textContent = label;
      rightSel.appendChild(or);

      const obr = document.createElement("option");
      obr.value = String(v);
      obr.textContent = `v${v}`;
      rbSel.appendChild(obr);
    }

    if (leftSel.options.length) {
      leftSel.selectedIndex = 0;
    }
    rightSel.selectedIndex = 0;

    const has = snaps.length > 0;
    if (btnDiff) btnDiff.disabled = !has;
    if (btnRb) btnRb.disabled = !has;
    if (!has && wrap) {
      wrap.hidden = true;
      if (meta) meta.textContent = "";
      if (pre) pre.innerHTML = "";
    }
  } catch {
    leftSel.innerHTML = "";
    rightSel.innerHTML = "";
    rbSel.innerHTML = "";
    if (btnDiff) btnDiff.disabled = true;
    if (btnRb) btnRb.disabled = true;
  }
}

function renderSnapshotDiffFromApi(body) {
  const wrap = $("snapshotDiffWrap");
  const pre = $("snapshotDiffPre");
  const meta = $("snapshotDiffMeta");
  if (!wrap || !pre) return;
  wrap.hidden = false;
  const left = body.left ?? "";
  const right = body.right ?? "";
  const trunc = body.truncated ? "（已截断）" : "";
  if (meta) meta.textContent = `左：${left} → 右：${right} ${trunc}`.trim();
  const lines = body.lines || [];
  pre.innerHTML = lines
    .map((ln) => {
      const k = ln.kind === "add" ? "add" : ln.kind === "rem" ? "rem" : "ctx";
      return `<span class="diff-line diff-line--${k}">${escapeHtml(String(ln.text ?? ""))}</span>`;
    })
    .join("");
}

async function runSnapshotDiff() {
  if (!state.world) return toast("请先选择世界");
  const id = state.world.meta.id;
  const left = $("snapshotDiffLeft")?.value;
  const right = $("snapshotDiffRight")?.value;
  if (!left || !right) return toast("请选择对比两端");
  try {
    const params = new URLSearchParams({ left, right });
    const res = await api(`/api/worlds/${id}/snapshots/diff?${params.toString()}`);
    renderSnapshotDiffFromApi(res);
  } catch (e) {
    toast("diff 失败：" + (e?.message || e));
  }
}

async function runSnapshotRollback() {
  if (!state.world) return toast("请先选择世界");
  const id = state.world.meta.id;
  const v = parseInt($("snapshotRollbackSel")?.value || "", 10);
  if (!Number.isFinite(v) || v < 1) return toast("请选择有效快照版本");
  if (
    !confirm(
      `确定回滚到 v${v} 的快照？当前表单未保存的修改将丢失，落盘后版本号 +1。`
    )
  )
    return;
  try {
    await api(`/api/worlds/${id}/snapshots/rollback`, {
      method: "POST",
      body: JSON.stringify({ snapshot_version: v }),
    });
    await loadWorld(id);
    toast("已回滚并落盘");
    void refreshSnapshotPanel();
  } catch (e) {
    toast("回滚失败：" + (e?.message || e));
  }
}

function switchView(name) {
  state.activeView = name;
  document.querySelectorAll(".nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === name);
  });
  document.querySelectorAll(".panel").forEach((p) => {
    p.classList.toggle("active", p.id === `view-${name}`);
  });
  if (name === "files") refreshFilesView();
  if (name === "search") refreshSearchView();
  if (name === "outlines") refreshOutlineHeader();
  if (name === "cultures") scheduleCultureVizRefresh();
  updateCultureHint();
  if (name === "chat") refreshFactionChatViz();
  if (name === "powers") setPowerSubView(state.powerSubView || "system");
  refreshContextPanel();
}

/** 将 profession_system.by_tier 按当前 tiers 顺序与 tier_name 对齐，避免模型输出顺序与境界表不一致导致卡片错位 */
function alignProfessionSystemToTiers(tiers, ps) {
  const src = ps && typeof ps === "object" ? ps : {};
  const raw = Array.isArray(src.by_tier) ? src.by_tier : [];
  if (!Array.isArray(tiers) || !tiers.length) {
    return {
      summary: String(src.summary ?? "").trim(),
      design_notes: String(src.design_notes ?? "").trim(),
      by_tier: raw,
    };
  }
  const nameMap = new Map();
  const display = new Map();
  for (const b of raw) {
    if (!b || typeof b !== "object") continue;
    const tn = String(b.tier_name ?? "").trim();
    const key = tn ? tn.toLowerCase() : "__anon__";
    if (!display.has(key)) display.set(key, tn || key);
    const list = Array.isArray(b.professions) ? b.professions : [];
    const prev = nameMap.get(key) || [];
    nameMap.set(key, prev.concat(list));
  }
  const aligned = [];
  for (const t of tiers) {
    const name = String(t?.name ?? "").trim();
    const k = name.toLowerCase();
    let profs = [];
    if (name && nameMap.has(k)) {
      profs = nameMap.get(k) || [];
      nameMap.delete(k);
    }
    aligned.push({ tier_name: name, professions: structuredClone(profs) });
  }
  for (const [k, profs] of nameMap) {
    if (k === "__anon__" && (!profs || !profs.length)) continue;
    aligned.push({ tier_name: display.get(k) || k, professions: structuredClone(profs || []) });
  }
  return {
    summary: String(src.summary ?? "").trim(),
    design_notes: String(src.design_notes ?? "").trim(),
    by_tier: aligned,
  };
}

function worldToForm(w) {
  if (!w) {
    $("geoSummary").value = "";
    $("geoClimate").value = "";
    $("geoMap").value = "";
    $("powerSummary").value = "";
    if ($("powerRealmDesign")) $("powerRealmDesign").value = "";
    if ($("powerSkillTreeDesign")) $("powerSkillTreeDesign").value = "";
    $("powerTiersJson").value = "[]";
    if ($("powerProfessionSummary")) $("powerProfessionSummary").value = "";
    if ($("powerProfessionDesign")) $("powerProfessionDesign").value = "";
    $("itemSummary").value = "";
    $("itemGradesJson").value = "[]";
    $("factionSummary").value = "";
    $("factionsJson").value = "[]";
    $("cultureSummary").value = "";
    $("culturesJson").value = "[]";
    $("historySummary").value = "";
    $("historyJson").value = "[]";
    if ($("attrSummary")) $("attrSummary").value = "";
    if ($("attrDesignNotes")) $("attrDesignNotes").value = "";
    if ($("attrStatsJson")) $("attrStatsJson").value = "[]";
    if ($("attrTierProfilesJson")) $("attrTierProfilesJson").value = "[]";
    const gm = $("genreMode");
    if (gm) gm.value = "";
    renderRegionCards([]);
    renderFactionCards([]);
    renderCultureCards([]);
    updateGenreModeHint();
    updateCultureHint();
    updateFactionGlobalBriefPreview();
    refreshFactionChatViz();
    refreshContextPanel();
    refreshFilesView();
    refreshSearchView();
    refreshOutlineHeader();
    return;
  }
  $("geoSummary").value = w.geography?.summary ?? "";
  $("geoClimate").value = w.geography?.climate_notes ?? "";
  $("geoMap").value = w.geography?.map_notes ?? "";

  migrateGlobalLandmarksResourcesIntoRegions(w);
  $("powerSummary").value = w.power_system?.summary ?? "";
  if ($("powerRealmDesign"))
    $("powerRealmDesign").value = w.power_system?.realm_design_notes ?? "";
  if ($("powerSkillTreeDesign"))
    $("powerSkillTreeDesign").value = w.power_system?.skill_tree_design_notes ?? "";
  if (w.power_system && Array.isArray(w.power_system.tiers)) {
    w.power_system.profession_system = alignProfessionSystemToTiers(
      w.power_system.tiers,
      w.power_system.profession_system || {}
    );
  }
  $("powerTiersJson").value = JSON.stringify(w.power_system?.tiers ?? [], null, 2);
  if ($("powerProfessionSummary"))
    $("powerProfessionSummary").value = w.power_system?.profession_system?.summary ?? "";
  if ($("powerProfessionDesign"))
    $("powerProfessionDesign").value = w.power_system?.profession_system?.design_notes ?? "";

  $("itemSummary").value = w.item_quality_system?.summary ?? "";
  $("itemGradesJson").value = JSON.stringify(w.item_quality_system?.grades ?? [], null, 2);

  $("factionSummary").value = w.factions?.summary ?? "";
  $("factionsJson").value = JSON.stringify(w.factions?.entities ?? [], null, 2);

  $("cultureSummary").value = w.cultures?.summary ?? "";
  $("culturesJson").value = JSON.stringify(w.cultures?.entities ?? [], null, 2);

  $("historySummary").value = w.history?.summary ?? "";
  $("historyJson").value = JSON.stringify(w.history?.events ?? [], null, 2);

  if ($("attrSummary")) $("attrSummary").value = w.attribute_system?.summary ?? "";
  if ($("attrDesignNotes")) $("attrDesignNotes").value = w.attribute_system?.design_notes ?? "";
  if ($("attrStatsJson"))
    $("attrStatsJson").value = JSON.stringify(w.attribute_system?.stats ?? [], null, 2);
  if ($("attrTierProfilesJson"))
    $("attrTierProfilesJson").value = JSON.stringify(
      w.attribute_system?.tier_average_profiles ?? [],
      null,
      2
    );

  renderRegionCards(w.geography?.regions);
  renderFactionCards(w.factions?.entities);
  renderCultureCards(w.cultures?.entities);

  const gm = $("genreMode");
  if (gm) gm.value = w.meta?.creative_mode || "";
  updateGenreModeHint();
  updateCultureHint();
  updateFactionGlobalBriefPreview();
  refreshFactionChatViz();
}

function formToWorld() {
  if (!state.world) return null;
  const w = structuredClone(state.world);
  const gm = $("genreMode");
  if (gm) w.meta.creative_mode = gm.value?.trim() || null;
  w.geography.summary = $("geoSummary").value.trim();
  w.geography.climate_notes = $("geoClimate").value.trim();
  w.geography.map_notes = $("geoMap").value.trim();
  w.geography.regions = collectRegionsFromDom();
  const flatLm = [];
  const flatRes = [];
  for (const r of w.geography.regions || []) {
    if (Array.isArray(r.landmarks)) flatLm.push(...r.landmarks.map((x) => String(x).trim()).filter(Boolean));
    if (Array.isArray(r.resources)) flatRes.push(...r.resources.map((x) => String(x).trim()).filter(Boolean));
  }
  w.geography.landmarks = [...new Set(flatLm)];
  w.geography.resources = [...new Set(flatRes)];

  w.power_system.summary = $("powerSummary").value.trim();
  w.power_system.realm_design_notes = ($("powerRealmDesign")?.value ?? "").trim();
  w.power_system.skill_tree_design_notes = ($("powerSkillTreeDesign")?.value ?? "").trim();
  w.item_quality_system.summary = $("itemSummary").value.trim();
  w.factions.summary = $("factionSummary").value.trim();
  w.cultures.summary = $("cultureSummary").value.trim();
  w.history.summary = $("historySummary").value.trim();

  const parseJson = (txt, label) => {
    try {
      return JSON.parse(txt || "[]");
    } catch (e) {
      throw new Error(`${label} JSON 无效：${e.message}`);
    }
  };

  const tiersFromViz = collectPowerTiersFromViz();
  const tiersResolved =
    tiersFromViz != null ? tiersFromViz : parseJson($("powerTiersJson").value, "境界 tiers");
  w.power_system.tiers = tiersResolved;
  w.power_system.profession_system = w.power_system.profession_system || {};
  w.power_system.profession_system.summary = ($("powerProfessionSummary")?.value ?? "").trim();
  w.power_system.profession_system.design_notes = ($("powerProfessionDesign")?.value ?? "").trim();
  w.power_system.profession_system.by_tier = collectProfessionByTierFromDom(tiersResolved);
  const gradesFromViz = collectItemGradesFromViz();
  w.item_quality_system.grades =
    gradesFromViz != null
      ? gradesFromViz
      : parseJson($("itemGradesJson").value, "物品档位");
  const fc = document.querySelectorAll("#factionCards .faction-card");
  w.factions.entities =
    fc.length > 0
      ? collectFactionsFromDom()
      : parseJson($("factionsJson")?.value || "[]", "派系");
  const cc = document.querySelectorAll("#cultureCards .culture-card");
  w.cultures.entities =
    cc.length > 0
      ? collectCulturesFromDom()
      : parseJson($("culturesJson")?.value || "[]", "文化/宗教");
  const eventsFromViz = collectHistoryEventsFromViz();
  w.history.events =
    eventsFromViz != null ? eventsFromViz : parseJson($("historyJson").value, "历史事件");

  if (!w.attribute_system)
    w.attribute_system = { summary: "", design_notes: "", stats: [], tier_average_profiles: [] };
  w.attribute_system.summary = ($("attrSummary")?.value ?? "").trim();
  w.attribute_system.design_notes = ($("attrDesignNotes")?.value ?? "").trim();
  w.attribute_system.stats = parseJson($("attrStatsJson")?.value || "[]", "人物属性 stats");
  w.attribute_system.tier_average_profiles = parseJson(
    $("attrTierProfilesJson")?.value || "[]",
    "境界平均属性 tier_average_profiles"
  );

  return w;
}

function refreshWorldTabTitle() {
  const suffix = "Magic Creater World — 世界观工作台";
  if (!state.world?.meta?.id) {
    document.title = suffix;
    return;
  }
  const n = (state.world.meta.name || "").trim() || state.world.meta.id;
  document.title = `${n} — ${suffix}`;
}

function refreshOutlineHeader() {
  const line = $("outlineVersionLine");
  if (!state.world) {
    line.textContent = "请先选择或新建世界。";
    return;
  }
  const m = state.world.meta;
  line.textContent = `当前依据：world.json · ${m.name} · v${m.version} · ${m.id}`;
}

function refreshFilesView() {
  const dir = $("filesDirHint");
  if (dir)
    dir.textContent = state.world ? `worlds/${state.world.meta.id}/` : "—";
  const dump = $("filesDump");
  if (dump) dump.textContent = state.world ? JSON.stringify(state.world, null, 2) : "（无）";
}

function refreshSearchView() {
  const wid = state.world?.meta?.id ?? null;
  if (wid !== _searchPanelWorldId) {
    _searchPanelWorldId = wid;
    const inp = $("worldSearchQ");
    if (inp) inp.value = "";
    const sr = $("worldSearchResults");
    if (sr) {
      sr.innerHTML = "";
      sr.classList.add("muted");
    }
  }
  const hint = $("searchPathHint");
  if (hint) {
    hint.textContent = state.world
      ? `检索范围：worlds/${state.world.meta.id}/world.json 与 world.md（磁盘已保存内容；未保存的编辑请先保存世界）`
      : "请先选择或新建世界。";
  }
}

async function runReferenceLintFlow(opts = {}) {
  const quietToast = Boolean(opts.quietToast);
  const out = $("referenceLintOut");
  if (!state.world?.meta?.id) {
    if (out) out.innerHTML = "";
    return;
  }
  if (out) {
    out.classList.add("muted");
    out.innerHTML = "<p>校验中…</p>";
  }
  try {
    const data = await api(`/api/worlds/${state.world.meta.id}/lint-references`);
    const warns = data.warnings || [];
    if (out) {
      if (!warns.length) {
        out.innerHTML = "<p>未发现引用问题。</p>";
        out.classList.add("muted");
      } else {
        out.classList.remove("muted");
        out.innerHTML =
          `<ul>${warns.map((w) => `<li>${escapeHtml(String(w))}</li>`).join("")}</ul>` +
          (data.truncated ? '<p class="muted tiny" style="margin:8px 0 0">（已达单条报告上限）</p>' : "");
      }
    }
    if (!quietToast) {
      toast(warns.length ? `引用校验：${warns.length} 条提示` : "引用校验：未发现引用问题");
    } else if (warns.length) {
      toast(`保存完成；引用校验有 ${warns.length} 条提示（见看板「引用一致性」）`);
    }
  } catch (e) {
    const msg = e?.message || String(e);
    if (out) {
      out.classList.add("muted");
      out.innerHTML = `<p>${escapeHtml(msg)}</p>`;
    }
    if (!quietToast) toast("引用校验失败：" + msg);
  }
}

function renderWorldSearchResults(data) {
  const box = $("worldSearchResults");
  if (!box) return;
  const j = data.json_hits || [];
  const m = data.markdown_hits || [];
  const tj = data.total_json ?? j.length;
  const tm = data.total_md ?? m.length;
  const parts = [];
  parts.push(
    `<p class="muted tiny" style="margin:0 0 8px">JSON 命中 <strong>${tj}</strong> · world.md 行 <strong>${tm}</strong></p>`
  );
  if (j.length) {
    parts.push('<div class="search-hit-group"><strong class="search-hit-group-title">world.json 路径</strong><ul class="search-hit-list">');
    for (const h of j) {
      const sn = escapeHtml(h.snippet || "").replace(/\n/g, "<br/>");
      parts.push(
        `<li class="search-hit-li"><code class="search-path">${escapeHtml(h.path || "")}</code><div class="search-snippet">${sn}</div></li>`
      );
    }
    parts.push("</ul></div>");
  }
  if (m.length) {
    parts.push('<div class="search-hit-group"><strong class="search-hit-group-title">world.md</strong><ul class="search-hit-list">');
    for (const h of m) {
      parts.push(
        `<li class="search-hit-li"><span class="search-line-no">L${h.line}</span><div class="search-snippet">${escapeHtml(h.text || "")}</div></li>`
      );
    }
    parts.push("</ul></div>");
  }
  if (!j.length && !m.length) {
    parts.push('<p class="muted" style="margin:0">无命中（可换关键词或先保存并导出 world.md）。</p>');
  }
  box.classList.remove("muted");
  box.innerHTML = parts.join("");
}

async function runWorldSearchFlow() {
  if (!state.world) return toast("请先选择世界");
  const inp = $("worldSearchQ");
  const q = (inp?.value || "").trim();
  if (!q) return toast("请输入关键词");
  const box = $("worldSearchResults");
  if (box) {
    box.classList.add("muted");
    box.innerHTML = "<p>搜索中…</p>";
  }
  try {
    const u = new URLSearchParams({ q });
    const data = await api(`/api/worlds/${state.world.meta.id}/search?${u.toString()}`);
    renderWorldSearchResults(data);
    toast(`命中 JSON ${data.total_json ?? 0} · MD ${data.total_md ?? 0}`);
  } catch (e) {
    const msg = e?.message || String(e);
    if (box) {
      box.classList.add("muted");
      box.innerHTML = `<p>${escapeHtml(msg)}</p>`;
    }
    toast("搜索失败：" + msg);
  }
}

async function refreshWorldSelect(selectedId) {
  const data = await api("/api/worlds");
  const sel = $("worldSelect");
  sel.innerHTML = "";
  const raw = data.worlds || [];
  const rows = raw.map((x) =>
    typeof x === "string"
      ? { id: x, name: x }
      : { id: x?.id ?? "", name: ((x?.name ?? "") + "").trim() || x?.id || "" }
  );
  if (!rows.length) {
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = "— 请先创建世界 —";
    sel.appendChild(ph);
    sel.value = "";
    updateEmptyState();
    return;
  }
  for (const { id, name } of rows) {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = name && name !== id ? `${name} · ${id}` : id;
    opt.title = id;
    sel.appendChild(opt);
  }
  if (selectedId && rows.some((r) => r.id === selectedId)) sel.value = selectedId;
  else if (rows[0]) sel.value = rows[0].id;
  sel.disabled = false;
  updateEmptyState();
}

async function loadWorld(id) {
  if (!id) return;
  const data = await api(`/api/worlds/${id}`);
  const w = data.world != null ? data.world : data;
  state.world = w;
  const inc = $("includeMd");
  if (inc && typeof data.has_nonempty_world_md === "boolean") {
    inc.checked = data.has_nonempty_world_md;
  }
  worldToForm(w);
  setDirty(false);
  refreshContextPanel();
  refreshOutlineHeader();
  refreshFilesView();
  refreshSearchView();
  refreshWorldTabTitle();
}

async function refreshFactionRelationsFromPanel() {
  if (!state.world) return toast("请先选择世界");
  const btn = $("btnRefreshFactionRelations");
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    const gm = ($("genreMode")?.value || "").trim() || null;
    const res = await api(`/api/worlds/${state.world.meta.id}/refresh/faction-relations`, {
      method: "POST",
      body: JSON.stringify({ persist: true, creative_mode: gm }),
    });
    if (res.ok === false) {
      toast("派系关系修订失败：" + (res.error || "模型输出无法解析"));
      return;
    }
    state.world = res.world;
    worldToForm(res.world);
    setDirty(false);
    refreshContextPanel();
    let msg = "派系关系网络已更新并保存";
    if (res.persisted === false) {
      msg =
        (res.warnings || []).some((w) => String(w).includes("无派系实体"))
          ? "当前无派系实体，未调用模型"
          : "派系 relations 已合并（未写盘）";
    }
    if (Array.isArray(res.warnings) && res.warnings.length) {
      msg += " — " + res.warnings.slice(0, 5).join("；");
    }
    toast(msg);
  } catch (e) {
    toast("派系关系修订失败：" + (e?.message || e));
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
  }
}

async function refreshCultureRelationsFromPanel() {
  if (!state.world) return toast("请先选择世界");
  const btn = $("btnRefreshCultureRelations");
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    const gm = ($("genreMode")?.value || "").trim() || null;
    const res = await api(`/api/worlds/${state.world.meta.id}/refresh/culture-relations`, {
      method: "POST",
      body: JSON.stringify({ persist: true, creative_mode: gm }),
    });
    if (res.ok === false) {
      toast("文化关系修订失败：" + (res.error || "模型输出无法解析"));
      return;
    }
    state.world = res.world;
    worldToForm(res.world);
    setDirty(false);
    refreshContextPanel();
    let msg = "文化/宗教关系网络已更新并保存";
    if (res.persisted === false) {
      msg =
        (res.warnings || []).some((w) => String(w).includes("无文化"))
          ? "当前无文化/宗教实体，未调用模型"
          : "文化 relations 已合并（未写盘）";
    }
    if (Array.isArray(res.warnings) && res.warnings.length) {
      msg += " — " + res.warnings.slice(0, 5).join("；");
    }
    toast(msg);
  } catch (e) {
    toast("文化关系修订失败：" + (e?.message || e));
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
  }
}

async function init() {
  if (window.mermaid) {
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
      theme: "neutral",
      fontFamily: "system-ui, 'Noto Sans SC', sans-serif",
    });
  }
  if (typeof marked !== "undefined" && typeof marked.use === "function") {
    try {
      marked.use({ gfm: true, breaks: true });
    } catch (_) {
      /* 旧版 marked 无 use 时忽略 */
    }
  }

  ensureWorldviewEditModeToolbars();

  try {
    const cfg = await api("/api/config");
    $("apiHint").textContent = cfg.has_api_key
      ? `对话：${cfg.default_model} · 同步：${cfg.structure_sync_model ?? cfg.default_model}`
      : "未配置 PARATERA_API_KEY（对话/大纲/板块同步将不可用）";
  } catch {
    $("apiHint").textContent = "无法连接 API";
  }

  await refreshWorldSelect();
  updateEmptyState();
  if (hasWorldsInSelect()) await loadWorld($("worldSelect").value);
  else {
    state.world = null;
    refreshContextPanel();
    refreshOutlineHeader();
    refreshWorldTabTitle();
  }

  const sh = $("syncHint");
  if (sh) {
    sh.textContent =
      "默认关闭「仅当前页模块」：助手一次可同步多个板块。若开启，仅在当前导航对应模块写入（地理/境界/物品/文化·宗教/派系/历史等），其它模块输出会被丢弃。";
  }
  updateGenreModeHint();
  updateCultureHint();

  $("btnAddRegion")?.addEventListener("click", () => {
    const cur = collectRegionsFromDom();
    cur.push({ id: uid("r"), name: "", summary: "", terrain: "", relations: [] });
    renderRegionCards(cur);
    setDirty(true);
    scheduleGeoVizRefresh();
  });
  $("btnAddFaction")?.addEventListener("click", () => {
    let cur = collectFactionsFromDom();
    if (!cur.length && state.world?.factions?.entities?.length) {
      cur = JSON.parse(JSON.stringify(state.world.factions.entities));
    }
    cur.push({
      id: uid("f"),
      name: "新派系",
      goals: "",
      territory: "",
      key_figures: [],
      relations: [],
    });
    renderFactionCards(cur);
    setDirty(true);
  });
  $("btnAddCulture")?.addEventListener("click", () => {
    let cur = collectCulturesFromDom();
    if (!cur.length && state.world?.cultures?.entities?.length) {
      cur = JSON.parse(JSON.stringify(state.world.cultures.entities));
    }
    cur.push({
      id: uid("c"),
      name: "新条目",
      kind: "culture",
      summary: "",
      tenets: "",
      practices: "",
      sacred_sites: [],
      key_figures: [],
      relations: [],
    });
    renderCultureCards(cur);
    setDirty(true);
  });
  $("btnRefreshFactionRelations")?.addEventListener("click", () =>
    void refreshFactionRelationsFromPanel()
  );
  $("btnRefreshCultureRelations")?.addEventListener("click", () =>
    void refreshCultureRelationsFromPanel()
  );
  $("regionCards")?.addEventListener("click", (ev) => {
    if (!ev.target.closest(".remove-region")) return;
    ev.target.closest(".region-card")?.remove();
    setDirty(true);
    scheduleGeoVizRefresh();
  });
  $("factionCards")?.addEventListener("click", (ev) => {
    if (!ev.target.closest(".remove-faction")) return;
    ev.target.closest(".faction-card")?.remove();
    setDirty(true);
    scheduleFactionVizRefresh();
  });
  $("cultureCards")?.addEventListener("click", (ev) => {
    if (!ev.target.closest(".remove-culture")) return;
    ev.target.closest(".culture-card")?.remove();
    setDirty(true);
    scheduleCultureVizRefresh();
  });

  document.querySelectorAll(".nav button").forEach((btn) => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });

  $("worldSelect").addEventListener("change", async (e) => {
    if (!e.target.value) return;
    if (state.dirty && !confirm("有未保存更改，确定切换世界？")) {
      e.target.value = state.world?.meta?.id ?? "";
      return;
    }
    await loadWorld(e.target.value);
  });

  document.querySelectorAll("[data-power-sub]").forEach((btn) => {
    btn.addEventListener("click", () => setPowerSubView(btn.dataset.powerSub));
  });
  setPowerSubView(state.powerSubView || "system");

  $("btnSnapshotDiff")?.addEventListener("click", () => void runSnapshotDiff());
  $("btnSnapshotRollback")?.addEventListener("click", () => void runSnapshotRollback());
  $("btnReferenceLint")?.addEventListener("click", () => void runReferenceLintFlow({ quietToast: false }));

  $("btnNewWorld").addEventListener("click", () => createWorldFlow().catch((e) => toast(e.message)));
  $("btnRenameWorld")?.addEventListener("click", () =>
    renameCurrentWorldFlow().catch((e) => toast(e.message))
  );
  $("btnDeleteWorld")?.addEventListener("click", () =>
    deleteCurrentWorldFlow().catch((e) => toast(e.message))
  );
  $("btnEmptyCreate").addEventListener("click", () => createWorldFlow().catch((e) => toast(e.message)));

  const markDirty = () => setDirty(true);
  [
    "geoSummary",
    "geoClimate",
    "geoMap",
    "powerSummary",
    "powerRealmDesign",
    "powerSkillTreeDesign",
    "powerTiersJson",
    "itemSummary",
    "itemGradesJson",
    "factionSummary",
    "factionsJson",
    "cultureSummary",
    "culturesJson",
    "historySummary",
    "historyJson",
    "attrSummary",
    "attrDesignNotes",
    "attrStatsJson",
    "attrTierProfilesJson",
  ].forEach((id) => $(id).addEventListener("input", markDirty));
  $("powerProfessionSummary")?.addEventListener("input", () => {
    markDirty();
    scheduleSyncProfessionFromVizToState();
  });
  $("powerProfessionDesign")?.addEventListener("input", () => {
    markDirty();
    scheduleSyncProfessionFromVizToState();
  });
  $("historyJson")?.addEventListener("input", scheduleHistoryVizFromForm);
  function scheduleAttrVizFromForm() {
    try {
      const stats = JSON.parse($("attrStatsJson")?.value || "[]");
      const tierp = JSON.parse($("attrTierProfilesJson")?.value || "[]");
      if (!state.world || !Array.isArray(stats)) return;
      const w = structuredClone(state.world);
      w.attribute_system = w.attribute_system || {};
      w.attribute_system.stats = stats;
      w.attribute_system.tier_average_profiles = Array.isArray(tierp) ? tierp : [];
      renderAttributePanel(w);
    } catch (_) {
      /* JSON 未完成输入时不刷新 */
    }
  }
  $("attrStatsJson")?.addEventListener("input", scheduleAttrVizFromForm);
  $("attrTierProfilesJson")?.addEventListener("input", scheduleAttrVizFromForm);
  $("powerTiersJson")?.addEventListener("input", () => {
    try {
      const tiers = JSON.parse($("powerTiersJson").value || "[]");
      if (!state.world || !Array.isArray(tiers)) return;
      state.world.power_system = state.world.power_system || {};
      state.world.power_system.tiers = tiers;
      renderPowerTierDashboardModules(state.world);
      applyAllWorldviewEditModes();
    } catch (_) {}
  });
  $("itemGradesJson")?.addEventListener("input", scheduleItemGradesVizFromForm);
  $("view-items")?.addEventListener("input", (ev) => {
    if (!ev.target.closest?.("#vizItemGradesRoot [data-item-field]")) return;
    scheduleSyncItemGradesFromVizToStateAndJson();
  });
  $("view-powers")?.addEventListener("input", (ev) => {
    if (ev.target.closest?.("#vizPowerProfessionModules [data-profession-part]")) {
      scheduleSyncProfessionFromVizToState();
      return;
    }
    if (
      !ev.target.closest?.(
        "#vizPowerSystemModules [data-power-field], #vizPowerSkillTreeModules [data-power-tree-part]"
      )
    )
      return;
    scheduleSyncPowerTiersFromVizToStateAndJson();
  });
  $("view-history")?.addEventListener("input", (ev) => {
    if (!ev.target.closest?.(".hist-tl-row--editable [data-hist-field]")) return;
    scheduleSyncHistoryEventsFromVizToStateAndJson();
  });
  $("factionSummary")?.addEventListener("input", scheduleFactionGlobalBriefPreview);

  $("genreMode")?.addEventListener("change", () => {
    markDirty();
    updateGenreModeHint();
    updateCultureHint();
  });

  $("regionCards")?.addEventListener("input", (ev) => {
    markDirty();
    const card = ev.target.closest(".region-card");
    if (card) syncRegionCardIcon(card);
    scheduleGeoVizRefresh();
  });
  $("factionCards")?.addEventListener("input", () => {
    markDirty();
    scheduleFactionVizRefresh();
  });
  $("cultureCards")?.addEventListener("input", () => {
    markDirty();
    scheduleCultureVizRefresh();
  });
  $("culturesJson")?.addEventListener("input", () => {
    markDirty();
    scheduleCultureVizRefresh();
  });

  async function persistWorldFromForm() {
    if (!state.world) {
      toast("请先选择世界");
      return;
    }
    let body;
    try {
      body = formToWorld();
    } catch (e) {
      toast(e.message);
      return;
    }
    const saved = await api(`/api/worlds/${body.meta.id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    state.world = saved;
    worldToForm(saved);
    setDirty(false);
    refreshContextPanel();
    refreshOutlineHeader();
    toast("已保存");
    void runReferenceLintFlow({ quietToast: true });
  }

  $("btnSaveWorld").addEventListener("click", () =>
    persistWorldFromForm().catch((e) => toast("保存失败：" + e.message))
  );

  document.addEventListener("keydown", (e) => {
    const mac =
      /Mac|iPhone|iPod|iPad/i.test(navigator.platform || "") ||
      (navigator.userAgent && navigator.userAgent.includes("Mac"));
    const mod = mac ? e.metaKey : e.ctrlKey;
    if (!mod || (e.key !== "s" && e.key !== "S")) return;
    e.preventDefault();
    void persistWorldFromForm().catch((err) => toast("保存失败：" + err.message));
  });

  $("btnCopyWorldId")?.addEventListener("click", async () => {
    if (!state.world?.meta?.id) return toast("无世界");
    try {
      await navigator.clipboard.writeText(state.world.meta.id);
      toast("已复制世界 ID");
    } catch {
      toast("复制失败（浏览器可能未授权剪贴板）");
    }
  });

  $("btnExportMd").addEventListener("click", async () => {
    if (!state.world) return toast("无世界");
    await api(`/api/worlds/${state.world.meta.id}/export-md`, { method: "POST" });
    toast("已导出 world.md");
  });

  $("btnWorldSearch")?.addEventListener("click", () => void runWorldSearchFlow());
  $("worldSearchQ")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      void runWorldSearchFlow();
    }
  });

  async function submitChatFromUI() {
    if (!state.world) return toast("请先选择世界");
    const text = $("chatInput").value.trim();
    if (!text) return;
    const mode = $("genreMode").value || null;
    const includeMd = $("includeMd").checked;
    const chat_guides = [];
    if ($("guideSkillTrees")?.checked) chat_guides.push("skill_trees");
    if ($("guideProfessions")?.checked) chat_guides.push("profession_system");
    if ($("guideAttributes")?.checked) chat_guides.push("attribute_system");
    const userMsg = text;
    state.messages.push({ role: "user", content: text });
    $("chatInput").value = "";
    renderMessages();
    setThinking("chat");
    let res;
    try {
      res = await api(`/api/worlds/${state.world.meta.id}/chat`, {
        method: "POST",
        body: JSON.stringify({
          messages: state.messages,
          mode,
          include_markdown_context: includeMd,
          chat_guides,
        }),
      });
    } catch (e) {
      state.messages.pop();
      renderMessages();
      toast("对话失败：" + e.message);
      setThinking(false);
      return;
    }
    state.messages.push({ role: "assistant", content: res.reply });
    renderMessages();
    setThinking(false);

    let shouldPersist = false;
    const applyAttrFromReply = () => {
      if (mergeAttributeSystemFromAssistantReply(res.reply)) {
        worldToForm(state.world);
        setDirty(true);
        refreshContextPanel();
        refreshOutlineHeader();
        toast("通用人物属性：已从助手回复中的 JSON 合并，雷达与表单已更新");
        shouldPersist = true;
        return true;
      }
      return false;
    };

    if (!$("autoSyncPanels")?.checked) {
      applyAttrFromReply();
      if (shouldPersist) {
        try {
          await persistWorldFromForm();
        } catch (e) {
          toast("落盘失败：" + (e?.message || e));
        }
      }
      return;
    }

    setThinking("sync");
    try {
      const syncRes = await api(
        `/api/worlds/${state.world.meta.id}/sync-panels-from-chat`,
        {
          method: "POST",
          body: JSON.stringify({
            user_message: userMsg,
            assistant_reply: res.reply,
            persist: false,
            scope: syncScopeForRequest(),
            creative_mode: $("genreMode")?.value || null,
          }),
        }
      );
      if (syncRes.ok) {
        state.world = syncRes.world;
        worldToForm(syncRes.world);
        setDirty(true);
        refreshContextPanel();
        refreshOutlineHeader();
        if (Array.isArray(syncRes.updated_sections) && syncRes.updated_sections.length > 0) {
          shouldPersist = true;
        }
        if (syncRes.merge_warnings?.length) {
          toast("校验提示：" + syncRes.merge_warnings.join("；"));
        }
        const nn = syncRes.normalize_notes;
        if (nn && typeof nn === "object") {
          const nnLines = Object.entries(nn)
            .filter(([, arr]) => Array.isArray(arr) && arr.length)
            .map(([k, arr]) => k + "：" + arr.join("；"));
          if (nnLines.length) {
            toast("结构归一化：" + nnLines.join(" | "));
          }
        }
        if (
          syncRes.scope_applied &&
          syncRes.scope_applied !== "all" &&
          Array.isArray(syncRes.structure_output_keys)
        ) {
          const dropped = syncRes.structure_output_keys.filter(
            (k) => k !== syncRes.scope_applied
          );
          if (dropped.length) {
            toast("已按「仅当前模块」忽略：" + dropped.join("、"));
          }
        }
        if (syncRes.updated_sections?.length) {
          toast("已更新：" + syncRes.updated_sections.join("、"));
        } else if (!syncRes.merge_warnings?.length) {
          toast("同步：本轮无结构化变更（可检查助手是否像闲聊或未写可落盘设定）");
        }
      } else {
        toast("同步解析失败：" + (syncRes.error || ""));
      }
    } catch (se) {
      toast("同步未执行：" + se.message);
    } finally {
      setThinking(false);
    }

    applyAttrFromReply();
    if (shouldPersist) {
      try {
        await persistWorldFromForm();
      } catch (e) {
        toast("落盘失败：" + (e?.message || e));
      }
    }
  }

  $("btnSend").addEventListener("click", () => void submitChatFromUI());

  $("chatInput")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !e.ctrlKey) return;
    e.preventDefault();
    void submitChatFromUI();
  });

  $("btnOutline").addEventListener("click", async () => {
    if (!state.world) return toast("请先选择世界");
    const prompt = $("outlinePrompt").value.trim();
    if (!prompt) return toast("请输入需求");
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/outline`, {
        method: "POST",
        body: JSON.stringify({
          kind: $("outlineKind").value,
          prompt,
          include_markdown_context: $("outlineIncludeMd").checked,
          creative_mode: $("genreMode")?.value || null,
        }),
      });
      $("outlinePreview").textContent = res.reply;
      toast("已写入 " + res.saved);
      await loadWorld(state.world.meta.id);
    } catch (e) {
      toast("大纲失败：" + e.message);
    }
  });

  const GEO_CHAT_PROMPT =
    "请为当前世界补充或修订 **地理**（对应 world.json 的 **geography**，便于「对话后同步」落盘）。请用自然语言 + 清晰小节组织，并尽量与下列键名对齐（不必输出整段 JSON，除非我要求）：\n\n" +
    "1）**总览 geography.summary**：多大陆/海洋/文明带尺度；不要在这里罗列具体地标或逐条物产表。\n" +
    "2）**全图气候 geography.climate_notes**：气候带、季风、异常气象、季节对旅行的影响。\n" +
    "3）**地图与交通 geography.map_notes**：方位约定、比例、制图说明；主干商路、航道或关隘总览。\n" +
    "4）**分区 geography.regions[]**：每个大陆、王国、海域等可区分单元单独一小节；每区尽量给出稳定 **id**（短 slug，如 `north_realm`），与现有区域 id 一致则沿用。每区包含：\n" +
    "   - **name**、**summary**（地貌/政权/文化带等较长叙述）；\n" +
    "   - **terrain**（地貌关键词）、**climate**（局地气候一句，可选）；\n" +
    "   - **notes**（旅行风险、关卡、调查或叙事钩子，可选）；\n" +
    "   - **landmarks[]**、**resources[]**：各用短名单行或分号列举（一项一名；长说明放进 summary/notes，勿把长段落塞进列表项）；\n" +
    "   - **relations[]**：与其它区的联系，每条写清对方 **target_id**（等于对方区域的 **id**）、**type**（如 邻接/贸易/航道/调查轴）、可选 **notes**。\n" +
    "5）若有尚无法归属到任何区的散点地标或物产，可单独列出并说明稍后将归入哪一区；**优先**写进所属区域的 **landmarks** / **resources**，顶层 **geography.landmarks** / **resources** 仅作补充。\n\n" +
    "若当前 JSON 中已有 regions，请对照修订并说明新增或重命名了哪些 **id**（以便我更新 relations）。";

  const POWER_SYSTEM_CHAT_PROMPT =
    "请为当前世界设计或修订 **境界体系**（对应 world.json 的 **power_system**，勿与 **attribute_system** 混淆；便于「对话后同步」落盘）。请用自然语言 + 清晰小节，尽量与下列键名对齐（不必默认输出整段 JSON，除非我要求）：\n\n" +
    "1）**总览 power_system.summary**：力量阶梯在世界中的位置、读者/玩家如何理解「境」。\n" +
    "2）**境界设计说明 realm_design_notes**：命名规则、递进与破境代价、与 **attribute_system**（人物卡/雷达）的叙事分界。\n" +
    "3）**技能树跨境说明 skill_tree_design_notes**：节点 **id** 命名、**prereq_ids**（前序须为**同一棵树**内已有节点 id）、本境通用 **skill_tree** 与 **subclass_paths** 专属树如何并存。\n" +
    "4）**各境 power_system.tiers[]**：每境 **name**、**description**；**typical_capabilities[]**、**limitations[]**、**examples[]**（**limitations** 写硬边界、代价、禁忌或反作弊叙事）。\n" +
    "5）每境可选 **skill_tree[]**：节点 **id**（该境该树内唯一）、**name**、**summary**、**prereq_ids**、**branch**（可选）。\n" +
    "6）每境可选 **subclass_paths[]**：**id**、**name**、**tagline**、**flavor**；**profession_id**（须与同境 **profession_system.by_tier** 中某 **professions[].id** 一致）；可含该流派 **skill_tree**（节点 id 建议加前缀以免与境界通用树冲突）。\n" +
    "7）可选 **profession_system**：**summary**、**design_notes**、**by_tier[]**（与 tiers 顺序或 **tier_name** 对齐）；每块 **professions[]** 含 **id**、**name**、**tagline**、**flavor**、**exclusive_faction_id**（须为已有 **factions.entities[].id**）、**notes**。\n\n" +
    "若 JSON 中已有 **tiers**，请对照修订并说明是否新增/重命名了境界或技能节点 **id**（以便我检查 **prereq_ids** 与 **profession_id**）。";

  const SKILL_TREE_CHAT_PROMPT =
    "在已完成 **境界总览（summary）**、**realm_design_notes**、**tiers[]** 各境 name/description/limitations 的前提下，请为当前世界细化 **境界技能树**（仍属 world.json 的 **power_system**）：\n\n" +
    "0）在 **skill_tree_design_notes** 中写清：节点 id 前缀、**prereq_ids** 只引用同树已有 id、通用 **skill_tree** 与各境 **subclass_paths** 专属树如何并存；与 **profession_system** 职业 **id** 如何对照。\n" +
    "1）**power_system.tiers[]** 每一境可有通用 **skill_tree**：节点 **id**、**name**、**summary**、**prereq_ids**、**branch**（可选）。\n" +
    "2）每一境可有 **subclass_paths**：**id**、**name**、**tagline**、**flavor**、可选 **profession_id**（须与同境 **profession_system.by_tier[].professions[].id** 一致）、以及该子类 **skill_tree**（节点 id 建议加前缀）。\n" +
    "3）与已有 **typical_capabilities**、**limitations** 自洽；说明通用节点与子类分叉关系。\n\n" +
    "若尚无境界表，请先补 **tiers** 再补树。输出需便于我开启「对话后同步」写入 power_system。";

  const ITEM_QUALITY_CHAT_PROMPT =
    "请为当前世界设计或修订 **物品品质体系**（world.json 的 **item_quality_system**；便于「对话后同步」落盘）。**顶层键必须为 `item_quality_system`**，勿使用 **`items`**、**`item_grades`** 等别名。请用自然语言 + 清晰小节对齐下列键（不必默认输出整段 JSON，除非我要求）：\n\n" +
    "1）**总览 item_quality_system.summary**：道具/宝物在世界中的定位、各档位的读者或玩家预期、与 **power_system** 境界叙事如何挂钩（不在此写人物六维）。\n" +
    "2）**档位 item_quality_system.grades[]**：每档单独说明；每档必填 **name**（档位名，短字符串）；**rarity_narrative**（稀有度与叙事张力）；**typical_effects**（该档典型效果、词条或玩法方向）；**binding_rules**（绑定、交易、掉落、使用限制、反刷等可裁定规则；DnD 式可类比 attunement 叙事）；**examples**（可选：字符串数组，每项为短例句或样例装备名）。\n" +
    "3）档位之间边界清晰（谁能持有、何时损毁/失控、与剧情冲突点）；与 **geography.regions[].resources** 若有分工，请在叙述中说明（资源短名在地理，档位规则在本节）。\n\n" +
    "若 JSON 中已有 **grades**，请对照修订并说明是否重命名了某档 **name** 或收紧了 **binding_rules**。";

  const PROFESSION_CHAT_PROMPT =
    "请为当前世界设计或修订 **境界职业体系**（world.json 的 **power_system.profession_system**，与 attribute_system 独立）：\n\n" +
    "1）**summary**：职业/流派在世界中的定位（宗门、军团、公会、秘传等）。\n" +
    "2）**design_notes**：各境职业如何递进；**exclusive_faction_id** 何时填写（须为已有 **factions.entities[].id**）；与 **subclass_paths.profession_id** 的命名对齐规则。\n" +
    "3）**by_tier[]**：与 **power_system.tiers** 顺序或 **tier_name** 对齐；每项 **professions[]** 含 **id**（单境内唯一）、**name**、**tagline**、**flavor**、**exclusive_faction_id**（可选）、**notes**。\n" +
    "4）若已写技能树，请说明各 **subclass_paths** 的 **profession_id** 应绑定到哪条职业 **id**。\n\n" +
    "输出需便于我开启「对话后同步」写入 **power_system**（内含 profession_system 与既有 tiers 字段合并）。";

  const ATTR_CHAT_PROMPT =
    "请为当前世界建立或修订「通用人物属性」体系（对应 world.json 的 attribute_system，与境界体系 power_system 独立）：\n\n" +
    "1）**总览**：这套属性服务于什么（叙事节奏 / 跑团检定 / 游戏数值的叙事映射等）。\n" +
    "2）**设计说明**：如何读雷达图、建卡建议、与当前创作载体尺度对齐。\n" +
    "3）**stats 维度列表**：建议 4～8 项；每项给出 id（短 id）、name、abbreviation、**intro**（该维度单独一句话简介，用于看板展示）、description（可较长）、scale、typical_use、reference_percent（0–100，雷达上世界参照强度）。\n" +
    "4）**tier_average_profiles**（可选）：与 **power_system.tiers** 各境 **name** 对齐，每项含 **tier_name** 与 **averages**（对象：键须为 stat 的 **id**，值为 0–100）。雷达上**缺键的维度按 0**；若 averages 与当前 stats 的 id **无一能对齐**则**不绘制该境**。\n\n" +
    "若已有 attribute_system，请对照修订并说明改动理由。输出需便于我开启「对话后同步」写入 attribute_system。\n\n" +
    "请尽量在回复末尾用 **json 代码块**（```json … ```）给出完整 `attribute_system` 对象（含 summary、design_notes、stats、可选 tier_average_profiles），前端会在发送后自动合并到「属性」页并更新雷达。";

  function fillChatPromptTemplate(
    text,
    {
      mode = "replace",
      enableAttrGuide = false,
      enableSkillTreeGuide = false,
      enableProfessionGuide = false,
    } = {}
  ) {
    if (!state.world) {
      toast("请先选择世界");
      return;
    }
    if (enableAttrGuide) {
      const g = $("guideAttributes");
      if (g) g.checked = true;
    }
    if (enableSkillTreeGuide) {
      const s = $("guideSkillTrees");
      if (s) s.checked = true;
    }
    if (enableProfessionGuide) {
      const p = $("guideProfessions");
      if (p) p.checked = true;
    }
    const inp = $("chatInput");
    if (!inp) return;
    const cur = (inp.value || "").trim();
    if (mode === "append" && cur) inp.value = `${cur}\n\n${text}`;
    else inp.value = text;
    inp.focus();
    if (enableSkillTreeGuide) toast("已开启「境界技能树」引导，提示已填入输入框");
    else if (enableProfessionGuide) toast("已开启「境界职业体系」引导，提示已填入输入框");
    else if (enableAttrGuide) toast("已开启「人物属性」引导，提示已填入输入框");
  }

  const chips = [
    ["lightbulb", "规划", "请先列出当前世界还缺哪些模块，并给出下一步建议。"],
    ["map", "写地理", GEO_CHAT_PROMPT],
    ["bolt", "写境界体系", POWER_SYSTEM_CHAT_PROMPT],
    [
      "badge",
      "职业体系",
      PROFESSION_CHAT_PROMPT,
      { professionGuide: true, append: true },
    ],
    ["account_tree", "境界技能树", SKILL_TREE_CHAT_PROMPT, { skillTreeGuide: true, append: true }],
    ["bubble_chart", "人物属性", ATTR_CHAT_PROMPT, { attrGuide: true, append: true }],
    ["diamond", "写物品品质", ITEM_QUALITY_CHAT_PROMPT],
    [
      "diversity_3",
      "文化·宗教",
      "请根据当前世界设定，补充或修订「文化 / 宗教」（对应 world.json 的 cultures 节）。请用自然语言说明：总览氛围；若有多条传统或教团，请分别给出名称、是民俗共同体还是宗教组织（或二者融合）、核心观念或教义、主要仪式/节日/禁忌、圣地或中心、关键人物；若彼此有影响、冲突或融合，请说明关系。若有与现有派系、地理的挂钩，请点名对应势力或地区。输出需便于我随后用「对话后同步」写入 cultures。",
    ],
    ["groups", "写派系", "请增加或修订至少两个派系：每个给出 id、name、goals、territory、relations（target_id + ally/enemy/neutral/complex）；并为每个派系列出若干 key_figures（字符串数组，每项可为「姓名」或「姓名 · 职务」），便于写入 world.json 的 factions。"],
    [
      "person",
      "派系要人",
      "请针对当前世界已有 factions.entities（请按 id 逐个点名），为每个派系扩写重要人物 key_figures：每派系 3～7 人，每项一行，建议「姓名 · 职务/立场」或带一句秘密；不要改各派系 id；relations 可保持不变。用分派系小节输出，便于我开启「对话后同步」写入 factions。",
    ],
    ["history_edu", "写历史", "请写一条重大历史事件及后果，并挂钩现有派系。"],
  ];
  const chipBox = $("promptChips");
  chips.forEach((row) => {
    const [glyph, label, text] = row;
    const meta = row.length > 3 && row[3] ? row[3] : {};
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip-btn";
    b.innerHTML = `<span class="ms chip-glyph" aria-hidden="true">${glyph}</span>${label}`;
    b.addEventListener("click", () => {
      fillChatPromptTemplate(text, {
        mode: meta.append ? "append" : "replace",
        enableAttrGuide: !!meta.attrGuide,
        enableSkillTreeGuide: !!meta.skillTreeGuide,
        enableProfessionGuide: !!meta.professionGuide,
      });
    });
    chipBox.appendChild(b);
  });
}

/** 助手回复：Markdown → HTML（GFM），经 DOMPurify 消毒 */
function renderAssistantMarkdownHtml(text) {
  const raw = (text ?? "").toString();
  if (typeof marked === "undefined" || typeof marked.parse !== "function") {
    return escapeHtml(raw).replaceAll("\n", "<br/>");
  }
  try {
    const unsafe = marked.parse(raw);
    if (typeof DOMPurify !== "undefined" && typeof DOMPurify.sanitize === "function") {
      return DOMPurify.sanitize(unsafe, { USE_PROFILES: { html: true } });
    }
    return escapeHtml(raw).replaceAll("\n", "<br/>");
  } catch (_) {
    return escapeHtml(raw).replaceAll("\n", "<br/>");
  }
}

function renderMessages() {
  const box = $("messages");
  box.innerHTML = "";
  for (const m of state.messages) {
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    const roleIc = m.role === "user" ? "person" : "smart_toy";
    const body =
      m.role === "assistant"
        ? renderAssistantMarkdownHtml(m.content)
        : escapeHtml(m.content).replaceAll("\n", "<br/>");
    const bodyClass =
      m.role === "assistant" ? "msg-body msg-body--assistant msg-body--md" : "msg-body msg-body--user";
    div.innerHTML = `<div class="role"><span class="ms role-ic" aria-hidden="true">${roleIc}</span>${m.role}</div><div class="${bodyClass}">${body}</div>`;
    box.appendChild(div);
  }
  box.scrollTop = box.scrollHeight;
}

function escapeHtml(s) {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

init().catch((e) => toast("初始化失败：" + e.message));
