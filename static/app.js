const $ = (id) => document.getElementById(id);

const state = {
  world: null,
  messages: [],
  dirty: false,
  activeView: "chat",
};

const API = "";

const VIEW_TO_SCOPE = {
  geo: "geography",
  powers: "power_system",
  items: "item_quality_system",
  factions: "factions",
  history: "history",
};

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2800);
}

const GENRE_MODE_HINTS = {
  "": "未选择时：对话仍用通用架构师；若世界已保存载体，则对话/同步/大纲会沿用该载体。",
  novel: "小说：叙事弧线、人物动机与伏笔；同步时偏向可写成场景的地理与派系细节。",
  game: "游戏：成长与任务链、系统边界；同步时偏向档位、规则与可策划模块。",
  coc: "CoC：调查链、理智与神话代价；同步时偏向可调查地点、教团与禁忌物品。",
  dnd: "DnD：冒险钩子、遭遇与裁定边界；同步时偏向阵营据点、等级感与绑定规则。",
};

function updateGenreModeHint() {
  const el = $("genreModeHint");
  const sel = $("genreMode");
  if (!el || !sel) return;
  el.textContent = GENRE_MODE_HINTS[sel.value] ?? GENRE_MODE_HINTS[""];
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

/** 力量：每境界卡片式展示（无 Mermaid 逻辑图） */
function renderPowerTierDashboardModules(w) {
  const root = $("vizPowerTiersRoot");
  if (!root) return;
  root.replaceChildren();
  const tiers = w.power_system?.tiers || [];
  if (!tiers.length) {
    root.innerHTML = `<div class="viz-empty">暂无等级</div>`;
    return;
  }
  const n = tiers.length;
  tiers.forEach((tier, idx) => {
    const block = document.createElement("div");
    block.className = "viz-module viz-module--power power-tier-viz";
    const hue = Math.round(198 + (idx / Math.max(n - 1, 1)) * 78);
    block.style.setProperty("--tier-accent-h", String(hue));
    const desc = (tier.description || "").trim();
    const descHtml = desc
      ? `<div class="power-tier-desc-wrap"><p class="power-tier-desc">${escapeHtml(desc).replace(/\n/g, "<br/>")}</p></div>`
      : "";
    block.innerHTML = `
      <div class="power-tier-viz-accent" aria-hidden="true"></div>
      <div class="viz-module-head power-tier-viz-head">
        <span class="viz-module-idx viz-module-idx--power" aria-hidden="true">${idx + 1}</span>
        <div class="viz-module-head-main">
          <span class="viz-module-title">${escapeHtml(tier.name || `境 ${idx + 1}`)}</span>
          <span class="viz-module-meta muted tiny">能力 · 限制 · 范例</span>
        </div>
      </div>
      <div class="power-tier-viz-body" role="region" aria-label="境界 ${idx + 1} 详情">
        ${descHtml}
        <div class="power-tier-viz-grid">
          ${htmlStrListBlock("发动能力（典型）", tier.typical_capabilities, "可在 typical_capabilities 中补充列表项", "caps")}
          ${htmlStrListBlock("发动限制", tier.limitations, "可在 limitations 中补充列表项", "lims")}
          ${htmlStrListBlock("例子", tier.examples, "可在 examples 数组中补充", "ex")}
        </div>
      </div>`;
    root.appendChild(block);
  });
}

/** 物品：每档位卡片式展示（无 Mermaid 逻辑图） */
function renderItemGradeDashboardModules(w) {
  const root = $("vizItemGradesRoot");
  if (!root) return;
  root.replaceChildren();
  const grades = w.item_quality_system?.grades || [];
  if (!grades.length) {
    root.innerHTML = `<div class="viz-empty">暂无档位</div>`;
    return;
  }
  const nG = grades.length;
  grades.forEach((grade, idx) => {
    const block = document.createElement("div");
    block.className = "viz-module viz-module--item item-grade-viz";
    const hue = Math.round(268 + (idx / Math.max(nG - 1, 1)) * 52);
    block.style.setProperty("--tier-accent-h", String(hue));
    const ex = Array.isArray(grade.examples) ? grade.examples.filter(Boolean) : [];
    const examplesHtml = htmlStrListBlock(
      "例子",
      ex,
      "可在 JSON 的 examples 字段中补充字符串数组",
      "ex"
    );
    block.innerHTML = `
      <div class="item-grade-viz-accent" aria-hidden="true"></div>
      <div class="viz-module-head item-grade-viz-head">
        <span class="viz-module-idx viz-module-idx--item" aria-hidden="true">${idx + 1}</span>
        <div class="viz-module-head-main">
          <span class="viz-module-title">${escapeHtml(grade.name || `档 ${idx + 1}`)}</span>
          <span class="viz-module-meta muted tiny">叙事 · 效果 · 范例 · 规则</span>
        </div>
      </div>
      <div class="item-grade-viz-body" role="region" aria-label="档位 ${idx + 1} 详情">
        ${htmlProseBlock("含义（稀有叙事）", grade.rarity_narrative, "填写 rarity_narrative", "mean")}
        ${htmlProseBlock("典型效果", grade.typical_effects, "填写 typical_effects", "fx")}
        ${examplesHtml}
        ${htmlProseBlock("绑定 / 规则", grade.binding_rules, "可选", "bind")}
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
    const glyph = pickRegionGlyph(r.name, r.terrain, r.summary || r.desc, idx);
    card.innerHTML = `
      <div class="region-card-head">
        <div class="region-viz" style="--rv-hue:${hue}" role="img" aria-label="区域类型图示">
          <span class="ms region-viz-ic" aria-hidden="true">${glyph}</span>
        </div>
        <div class="region-fields">
          <input type="hidden" class="region-id" />
          <input type="text" class="region-name" placeholder="大陆 / 区域名称" />
          <textarea class="region-summary" rows="3" placeholder="区域概述（地貌、政权、特色）"></textarea>
          <input type="text" class="region-terrain" placeholder="地形 / 地貌关键词" />
          <label class="muted tiny">与其它区域的关联 relations（JSON，target_id 填另一区域 id）</label>
          <textarea class="region-relations-json" rows="2" placeholder='[{"target_id":"other-region-id","type":"邻接","notes":""}]'></textarea>
        </div>
        <button type="button" class="ghost btn-icon remove-region" title="移除此区域">×</button>
      </div>`;
    card.querySelector(".region-id").value = r.id || uid("r");
    card.querySelector(".region-name").value = r.name || "";
    card.querySelector(".region-summary").value = r.summary || r.desc || "";
    card.querySelector(".region-terrain").value = r.terrain || "";
    card.querySelector(".region-relations-json").value = relJson;
    root.appendChild(card);
  });
  scheduleGeoVizRefresh();
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
      return {
        id: card.querySelector(".region-id")?.value?.trim() || uid("r"),
        name: card.querySelector(".region-name")?.value?.trim() || "",
        summary: card.querySelector(".region-summary")?.value?.trim() || "",
        terrain: card.querySelector(".region-terrain")?.value?.trim() || "",
        relations,
      };
    })
    .filter(
      (r) => r.name || r.summary || r.terrain || (Array.isArray(r.relations) && r.relations.length > 0)
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
}

function scheduleFactionVizRefresh() {
  clearTimeout(_factionVizTimer);
  _factionVizTimer = setTimeout(() => refreshAllFactionViz(), 220);
}

function renderPowerBars(container, tiers) {
  if (!container) return;
  if (!tiers?.length) {
    container.innerHTML = `<div class="viz-empty">—</div>`;
    return;
  }
  const caps = tiers.map((t) => (t.typical_capabilities || []).length);
  const lims = tiers.map((t) => (t.limitations || []).length);
  const maxCap = Math.max(1, ...caps, 1);
  const nT = tiers.length;
  container.innerHTML = tiers
    .map((t, idx) => {
      const n = caps[idx];
      const lc = lims[idx];
      const pct = Math.round((n / maxCap) * 100);
      const hue = Math.round(200 + (idx / Math.max(1, nT - 1)) * 95);
      const tip = `${n} 条典型能力 · ${lc} 条限制`;
      return `<div class="bar-row bar-row--rich" title="${escapeHtml(tip)}">
        <span class="bar-label bar-label--stack">
          <span class="bar-name">${escapeHtml(t.name || `境${idx + 1}`)}</span>
          <span class="bar-meta">${n} 能力 · ${lc} 限制</span>
        </span>
        <div class="bar-track"><div class="bar-fill bar-fill--tier" style="width:${pct}%;--tier-hue:${hue}"></div></div>
      </div>`;
    })
    .join("");
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
  const fc = (w.factions?.entities || []).length;
  const ev = (w.history?.events || []).length;
  const pill = (icon, t) =>
    `<span class="pill"><span class="ms pill-ic" aria-hidden="true">${icon}</span>${t}</span>`;
  el.innerHTML = [
    pill("place", `地标 ${lm}`),
    pill("forest", `资源 ${rs}`),
    pill("bolt", `等级 ${pt}`),
    pill("diamond", `品质 ${ig}`),
    pill("groups", `派系 ${fc}`),
    pill("event", `事件 ${ev}`),
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
    el.innerHTML = `<div class="viz-empty">暂无事件，可在下方 JSON 中添加</div>`;
    return;
  }
  el.innerHTML = list
    .map((e, i) => {
      const when = escapeHtml((e.when || "—").toString().slice(0, 36));
      const title = escapeHtml((e.title || "未命名事件").toString().slice(0, 80));
      const sum = (e.summary || "").toString();
      const sumShort = escapeHtml(sum.slice(0, 160)) + (sum.length > 160 ? "…" : "");
      const nCons = (e.consequences || []).length;
      return `<div class="hist-tl-row">
        <div class="hist-tl-axis"><span class="hist-tl-dot"></span>${i < list.length - 1 ? '<span class="hist-tl-line"></span>' : ""}</div>
        <div class="hist-tl-card">
          <div class="hist-tl-when">${when}</div>
          <div class="hist-tl-title">${title}</div>
          <div class="hist-tl-sum muted tiny">${sumShort || "（无摘要）"}</div>
          ${nCons ? `<div class="hist-tl-meta tiny">后果 ${nCons} 条</div>` : ""}
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
    renderHistoryMajorTimeline(events);
    void drawMermaidHost($("vizHistoryHost"), buildHistoryMermaid(events));
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
  const pow = $("vizPowerBars");
  const powMods = $("vizPowerTiersRoot");
  const itemMods = $("vizItemGradesRoot");
  const fac = $("vizFactionHost");
  const his = $("vizHistoryHost");

  const geoPanel = $("geoNetworkHost");

  if (!state.world) {
    renderStatStrip(null);
    if (pow) pow.innerHTML = "";
    if (powMods) powMods.innerHTML = "";
    if (itemMods) itemMods.innerHTML = "";
    if (geoPanel) geoPanel.innerHTML = "";
    if (fac) fac.innerHTML = "";
    if (his) his.innerHTML = "";
    renderHistoryMajorTimeline([]);
    const fgb = $("factionGlobalBrief");
    if (fgb) fgb.innerHTML = "";
    if (rawEl) rawEl.textContent = "";
    return;
  }

  const w = state.world;
  renderStatStrip(w);
  renderPowerBars(pow, w.power_system?.tiers);
  renderPowerTierDashboardModules(w);
  renderItemGradeDashboardModules(w);

  refreshGeoNetworkViz();
  void drawMermaidHost(fac, buildFactionMermaid(w.factions?.entities));
  const ev = w.history?.events || [];
  renderHistoryMajorTimeline(ev);
  void drawMermaidHost(his, buildHistoryMermaid(ev));

  if (rawEl) rawEl.textContent = JSON.stringify(w, null, 2);
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
  if (name === "outlines") refreshOutlineHeader();
  refreshContextPanel();
}

function worldToForm(w) {
  $("geoSummary").value = w.geography?.summary ?? "";
  $("geoClimate").value = w.geography?.climate_notes ?? "";
  $("geoMap").value = w.geography?.map_notes ?? "";
  $("geoLandmarks").value = (w.geography?.landmarks ?? []).join("\n");
  $("geoResources").value = (w.geography?.resources ?? []).join("\n");

  $("powerSummary").value = w.power_system?.summary ?? "";
  $("powerTiersJson").value = JSON.stringify(w.power_system?.tiers ?? [], null, 2);

  $("itemSummary").value = w.item_quality_system?.summary ?? "";
  $("itemGradesJson").value = JSON.stringify(w.item_quality_system?.grades ?? [], null, 2);

  $("factionSummary").value = w.factions?.summary ?? "";
  $("factionsJson").value = JSON.stringify(w.factions?.entities ?? [], null, 2);

  $("historySummary").value = w.history?.summary ?? "";
  $("historyJson").value = JSON.stringify(w.history?.events ?? [], null, 2);

  renderRegionCards(w.geography?.regions);
  renderFactionCards(w.factions?.entities);

  const gm = $("genreMode");
  if (gm) gm.value = w.meta?.creative_mode || "";
  updateGenreModeHint();
  updateFactionGlobalBriefPreview();
}

function formToWorld() {
  if (!state.world) return null;
  const w = structuredClone(state.world);
  const gm = $("genreMode");
  if (gm) w.meta.creative_mode = gm.value?.trim() || null;
  w.geography.summary = $("geoSummary").value.trim();
  w.geography.climate_notes = $("geoClimate").value.trim();
  w.geography.map_notes = $("geoMap").value.trim();
  w.geography.landmarks = $("geoLandmarks").value
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  w.geography.resources = $("geoResources").value
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  w.geography.regions = collectRegionsFromDom();

  w.power_system.summary = $("powerSummary").value.trim();
  w.item_quality_system.summary = $("itemSummary").value.trim();
  w.factions.summary = $("factionSummary").value.trim();
  w.history.summary = $("historySummary").value.trim();

  const parseJson = (txt, label) => {
    try {
      return JSON.parse(txt || "[]");
    } catch (e) {
      throw new Error(`${label} JSON 无效：${e.message}`);
    }
  };

  w.power_system.tiers = parseJson($("powerTiersJson").value, "超凡等级");
  w.item_quality_system.grades = parseJson($("itemGradesJson").value, "物品档位");
  const fc = document.querySelectorAll("#factionCards .faction-card");
  w.factions.entities =
    fc.length > 0
      ? collectFactionsFromDom()
      : parseJson($("factionsJson")?.value || "[]", "派系");
  w.history.events = parseJson($("historyJson").value, "历史事件");
  return w;
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
  $("filesDirHint").textContent = state.world
    ? `worlds/${state.world.meta.id}/`
    : "—";
  $("filesDump").textContent = state.world
    ? JSON.stringify(state.world, null, 2)
    : "（无）";
}

async function refreshWorldSelect(selectedId) {
  const data = await api("/api/worlds");
  const sel = $("worldSelect");
  sel.innerHTML = "";
  if (!data.worlds?.length) {
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = "— 请先创建世界 —";
    sel.appendChild(ph);
    sel.value = "";
    updateEmptyState();
    return;
  }
  for (const id of data.worlds) {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = id;
    sel.appendChild(opt);
  }
  if (selectedId && data.worlds.includes(selectedId)) sel.value = selectedId;
  else if (data.worlds[0]) sel.value = data.worlds[0];
  sel.disabled = false;
  updateEmptyState();
}

async function loadWorld(id) {
  if (!id) return;
  const w = await api(`/api/worlds/${id}`);
  state.world = w;
  worldToForm(w);
  setDirty(false);
  refreshContextPanel();
  refreshOutlineHeader();
  refreshFilesView();
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
  }

  const sh = $("syncHint");
  if (sh) {
    sh.textContent =
      "默认关闭「仅当前页模块」：助手一次可同步多个板块。若开启，仅在当前导航对应模块写入，其它模块输出会被丢弃。";
  }
  updateGenreModeHint();

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

  $("btnNewWorld").addEventListener("click", () => createWorldFlow().catch((e) => toast(e.message)));
  $("btnEmptyCreate").addEventListener("click", () => createWorldFlow().catch((e) => toast(e.message)));

  const markDirty = () => setDirty(true);
  [
    "geoSummary",
    "geoClimate",
    "geoMap",
    "geoLandmarks",
    "geoResources",
    "powerSummary",
    "powerTiersJson",
    "itemSummary",
    "itemGradesJson",
    "factionSummary",
    "factionsJson",
    "historySummary",
    "historyJson",
  ].forEach((id) => $(id).addEventListener("input", markDirty));
  $("historyJson")?.addEventListener("input", scheduleHistoryVizFromForm);
  $("factionSummary")?.addEventListener("input", scheduleFactionGlobalBriefPreview);

  $("genreMode")?.addEventListener("change", () => {
    markDirty();
    updateGenreModeHint();
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

  $("btnSaveWorld").addEventListener("click", async () => {
    if (!state.world) return toast("请先选择世界");
    let body;
    try {
      body = formToWorld();
    } catch (e) {
      return toast(e.message);
    }
    try {
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
    } catch (e) {
      toast("保存失败：" + e.message);
    }
  });

  $("btnExportMd").addEventListener("click", async () => {
    if (!state.world) return toast("无世界");
    await api(`/api/worlds/${state.world.meta.id}/export-md`, { method: "POST" });
    toast("已导出 world.md");
  });

  async function submitChatFromUI() {
    if (!state.world) return toast("请先选择世界");
    const text = $("chatInput").value.trim();
    if (!text) return;
    const mode = $("genreMode").value || null;
    const includeMd = $("includeMd").checked;
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

    if (!$("autoSyncPanels")?.checked) return;

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
        if (syncRes.merge_warnings?.length) {
          toast("校验提示：" + syncRes.merge_warnings.join("；"));
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

  const chips = [
    ["lightbulb", "规划", "请先列出当前世界还缺哪些模块，并给出下一步建议。"],
    ["map", "写地理", "请补充地理总览：地貌、政权分布、交通要冲与资源。"],
    ["bolt", "写力量体系", "请设计超凡力量等级（名称、能力、限制），与现有设定自洽。"],
    ["diamond", "写物品品质", "请设计物品品质档位与叙事效果边界。"],
    ["groups", "写派系", "请增加或修订两个对立派系及其关系。"],
    ["history_edu", "写历史", "请写一条重大历史事件及后果，并挂钩现有派系。"],
  ];
  const chipBox = $("promptChips");
  chips.forEach(([glyph, label, text]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip-btn";
    b.innerHTML = `<span class="ms chip-glyph" aria-hidden="true">${glyph}</span>${label}`;
    b.addEventListener("click", () => {
      $("chatInput").value = text;
      $("chatInput").focus();
    });
    chipBox.appendChild(b);
  });
}

function renderMessages() {
  const box = $("messages");
  box.innerHTML = "";
  for (const m of state.messages) {
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    const roleIc = m.role === "user" ? "person" : "smart_toy";
    div.innerHTML = `<div class="role"><span class="ms role-ic" aria-hidden="true">${roleIc}</span>${m.role}</div>${escapeHtml(m.content)}`;
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
