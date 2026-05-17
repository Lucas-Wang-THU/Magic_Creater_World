const $ = (id) => document.getElementById(id);

const state = {
  world: null,
  messages: [],
  /** 人物生成页独立对话线程（POST …/character-chat） */
  charMessages: [],
  /** 情节构建页独立对话线程（POST …/story-chat） */
  storyMessages: [],
  dirty: false,
  activeView: "chat",
  storySubView: "overview",
  storyOutlineSub: "macro",
  activeStoryNav: "storyOverview",
  storyActiveChapterId: "",
  storyUnitLabel: "章",
  /** 境界页子页：system | trees | professions */
  powerSubView: "system",
  /** 生态页子页：overview | biomes | species */
  ecologySubView: "overview",
  /** 地理页子页：overview（总览/气候/地图）| regions（大陆/区域+关系图） */
  geoSubView: "overview",
  /** 各世界观子页是否允许编辑表单（默认开启） */
  worldviewEditMode: {
    geo: true,
    ecology: true,
    powers: true,
    attributes: true,
    items: true,
    cultures: true,
    factions: true,
    history: true,
    economy: true,
    charProtagonists: true,
    charSupporting: true,
  },
};

const API = "";

/** 切换世界时清空搜索 UI，避免命中仍显示上一世界 */
let _searchPanelWorldId = null;

const VIEW_TO_SCOPE = {
  geo: "geography",
  ecology: "ecology",
  powers: "power_system",
  attributes: "attribute_system",
  items: "item_quality_system",
  cultures: "cultures",
  factions: "factions",
  history: "history",
  economy: "economy",
  charChat: "characters",
  charProtagonists: "characters",
  charSupporting: "characters",
  charRelations: "characters",
  charData: "characters",
  storyChat: "story",
  storyOverview: "story",
  storyOutline: "story",
  storyChapter: "story",
  storyForeshadow: "story",
  storyWrite: "story",
};

/** 左侧「情节」导航 → 情节工作台子页 */
const STORY_NAV_VIEWS = {
  storyOverview: "overview",
  storyOutline: "outline",
  storyChapter: "chapter",
  storyForeshadow: "foreshadow",
  storyWrite: "write",
};

const STORY_NAV_LABELS = {
  storyOverview: "总览",
  storyOutline: "大纲",
  storyChapter: "章节",
  storyForeshadow: "伏笔",
  storyWrite: "写作",
};

const STORY_SUB_TO_NAV = {
  overview: "storyOverview",
  outline: "storyOutline",
  chapter: "storyChapter",
  foreshadow: "storyForeshadow",
  write: "storyWrite",
};

function isStoryPanelView(name) {
  return name === "story" || name in STORY_NAV_VIEWS;
}

function resolveStoryPanelRoute(name) {
  if (name === "outlines") {
    return { panel: "story", storySubView: "outline", storyOutlineSub: "auxiliary", activeStoryNav: "storyOutline" };
  }
  if (name in STORY_NAV_VIEWS) {
    return {
      panel: "story",
      storySubView: STORY_NAV_VIEWS[name],
      activeStoryNav: name,
      storyOutlineSub: name === "storyOutline" ? state.storyOutlineSub || "macro" : state.storyOutlineSub,
    };
  }
  if (name === "story") {
    return {
      panel: "story",
      storySubView: state.storySubView || "overview",
      activeStoryNav: state.activeStoryNav || STORY_SUB_TO_NAV[state.storySubView] || "storyOverview",
    };
  }
  return { panel: name };
}

/** 左侧「角色」分组：各入口为独立 #view-char* 页面 */
function isCharacterPanelView(name) {
  return (
    name === "charProtagonists" ||
    name === "charSupporting" ||
    name === "charRelations" ||
    name === "charData"
  );
}

function syncNavActiveButtons() {
  document.querySelectorAll(".nav button").forEach((b) => {
    const v = b.dataset.view;
    let active = false;
    if (isStoryPanelView(v) && state.activeView === "story") {
      active = v === (state.activeStoryNav || STORY_SUB_TO_NAV[state.storySubView] || "storyOverview");
    } else {
      active = v === state.activeView;
    }
    b.classList.toggle("active", active);
  });
}

/** 主导航中「世界观」各子页（不含世界观构建页 / 大纲 / 数据页） */
const WORLDVIEW_EDIT_PANEL_IDS = [
  "geo",
  "ecology",
  "powers",
  "attributes",
  "items",
  "cultures",
  "factions",
  "history",
  "economy",
  "charProtagonists",
  "charSupporting",
];

const WORLDVIEW_EDIT_LABELS = {
  geo: "地理",
  ecology: "生态与生境",
  powers: "境界体系",
  attributes: "通用人物属性",
  items: "物品品质",
  cultures: "文化与宗教",
  factions: "派系",
  history: "历史",
  economy: "经济与流通",
  charProtagonists: "主角团",
  charSupporting: "重要配角",
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
  if (panelId === "charProtagonists" || panelId === "charSupporting") refreshCharactersVizFromForm();
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

/** 人物卡司：从表单 JSON 解析；失败返回 null（调用方勿刷 viz） */
function tryParseCharacterEntitiesRelations() {
  const parseJson = (txt, label) => {
    try {
      return JSON.parse(txt || "[]");
    } catch {
      throw new Error(`${label} JSON 无效`);
    }
  };
  try {
    const entities = parseJson($("charEntitiesJson")?.value, "characters.entities");
    const relations = parseJson($("charRelationsJson")?.value, "characters.relations");
    if (!Array.isArray(entities) || !Array.isArray(relations)) return null;
    return { entities, relations };
  } catch {
    return null;
  }
}

const CAST_ROLE_LABELS = {
  protagonist_core: "主角团",
  supporting_major: "重要配角",
  supporting_minor: "配角",
  antagonist: "对立面",
  background: "背景",
};

const CAST_ROLE_HUES = {
  protagonist_core: 200,
  supporting_major: 268,
  supporting_minor: 245,
  antagonist: 350,
  background: 160,
};

/** 卡司卡片内联编辑：与 JSON 锚定 id 一致；勿在卡片内改 id（请用卡司数据 JSON）。 */
const CHAR_ROSTER_EDIT_ROLE_ORDER = [
  "protagonist_core",
  "supporting_major",
  "supporting_minor",
  "antagonist",
  "background",
];

function escapeAttr(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;");
}

function charCastRoleSelectHtml(currentRaw) {
  const cur = String(currentRaw ?? "").trim() || "background";
  return CHAR_ROSTER_EDIT_ROLE_ORDER.map((r) => {
    const sel = r === cur ? " selected" : "";
    const lab = CAST_ROLE_LABELS[r] || r;
    return `<option value="${escapeAttr(r)}"${sel}>${escapeHtml(lab)}</option>`;
  }).join("");
}

function renderCharCastCardEditHtml(ent, variant = "protagonists") {
  const idRaw = String(ent?.id ?? "").trim();
  if (!idRaw) return "";
  const id = escapeHtml(idRaw);
  const roleRaw = String(ent?.cast_role ?? "").trim();
  const hue = CAST_ROLE_HUES[roleRaw] ?? 210;
  const hook = String(ent?.one_line_hook ?? "");
  const notes = String(ent?.notes ?? "");
  const skills = Array.isArray(ent?.notable_skills) ? ent.notable_skills : [];
  const skillsTxt = skills.map((s) => String(s).trim()).filter(Boolean).join("\n");
  const aliases = Array.isArray(ent?.aliases) ? ent.aliases : [];
  const aliasesTxt = aliases.map((a) => String(a).trim()).filter(Boolean).join("，");
  const fac = Array.isArray(ent?.faction_ids) ? ent.faction_ids.map((x) => String(x).trim()).filter(Boolean) : [];
  const home = String(ent?.home_region_id ?? "").trim();
  const avIc = variant === "supporting" ? "person" : "badge";
  return `<article class="char-roster-card char-roster-card--edit" data-char-edit-card="1" data-char-entity-id="${escapeAttr(
    idRaw
  )}" style="--char-card-hue:${hue}">
    <div class="char-roster-card-rim" aria-hidden="true"></div>
    <div class="char-roster-card-inner">
      <header class="char-roster-card-head char-roster-card-head--edit">
        <div class="char-roster-avatar" aria-hidden="true"><span class="ms char-roster-avatar-ic">${avIc}</span></div>
        <div class="char-roster-head-main">
          <label class="char-roster-field"><span class="char-roster-field-lbl">名称</span>
            <input type="text" class="char-roster-field-ctrl" data-char-field="name" value="${escapeAttr(
              String(ent?.name ?? "").trim()
            )}" autocomplete="off" spellcheck="true" /></label>
          <div class="char-roster-idline"><span class="char-roster-k">id</span><code class="char-roster-code">${id}</code></div>
        </div>
        <div class="char-roster-edit-head-actions">
          <label class="char-roster-field char-roster-field--inline"><span class="char-roster-field-lbl">卡司位</span>
            <select class="char-roster-field-ctrl char-roster-select-role" data-char-field="cast_role" title="cast_role">${charCastRoleSelectHtml(
              roleRaw
            )}</select></label>
          <button type="button" class="ghost btn-sm btn-ic char-roster-del" data-char-delete-entity="${escapeAttr(
            idRaw
          )}" title="从卡司删除该实体，并移除 relations 中相关边">
            <span class="ms" aria-hidden="true">delete</span></button>
        </div>
      </header>
      <section class="char-roster-block char-roster-block--edit"><div class="char-roster-block-hd">叙事钩 · one_line_hook</div>
        <textarea class="char-roster-field-ta" data-char-field="one_line_hook" rows="2" spellcheck="true">${escapeHtml(
          hook
        )}</textarea></section>
      <section class="char-roster-block char-roster-block--edit"><div class="char-roster-block-hd">备注 · notes</div>
        <textarea class="char-roster-field-ta" data-char-field="notes" rows="2" spellcheck="true">${escapeHtml(
          notes
        )}</textarea></section>
      <section class="char-roster-block char-roster-block--edit"><div class="char-roster-block-hd">别名 aliases（逗号或顿号分隔）</div>
        <input type="text" class="char-roster-field-ctrl" data-char-field="aliases" value="${escapeAttr(
          aliasesTxt
        )}" autocomplete="off" /></section>
      <section class="char-roster-block char-roster-block--edit char-roster-block--skills"><div class="char-roster-block-hd">特长 notable_skills（每行一条）</div>
        <textarea class="char-roster-field-ta" data-char-field="notable_skills" rows="3" spellcheck="true">${escapeHtml(
          skillsTxt
        )}</textarea></section>
      <section class="char-roster-block char-roster-block--edit char-roster-block--meta"><div class="char-roster-block-hd">边界 · 引用锚点</div>
        <label class="char-roster-field"><span class="char-roster-field-lbl">faction_ids（逗号或空格分隔）</span>
          <input type="text" class="char-roster-field-ctrl" data-char-field="faction_ids" value="${escapeAttr(
            fac.join("，")
          )}" autocomplete="off" /></label>
        <label class="char-roster-field"><span class="char-roster-field-lbl">home_region_id</span>
          <input type="text" class="char-roster-field-ctrl" data-char-field="home_region_id" value="${escapeAttr(
            home
          )}" autocomplete="off" /></label>
      </section>
    </div>
  </article>`;
}

function shouldSkipCharRosterReRender(panelId) {
  const ae = document.activeElement;
  if (!ae?.closest) return false;
  if (!isWorldviewPanelEditEnabled(panelId)) return false;
  const root = document.getElementById(`view-${panelId}`);
  if (!root?.contains(ae)) return false;
  return Boolean(ae.closest("[data-char-edit-card]"));
}

let _charRosterPersistTimer = {};

function readCharEditCardFromDom(article) {
  const id = String(article?.dataset?.charEntityId ?? "").trim();
  if (!id) return null;
  const g = (field) => article.querySelector(`[data-char-field="${field}"]`);
  const name = (g("name")?.value ?? "").trim();
  const cast_role = (g("cast_role")?.value ?? "").trim() || "background";
  const one_line_hook = (g("one_line_hook")?.value ?? "").trim();
  const notes = (g("notes")?.value ?? "").trim();
  const aliasesRaw = (g("aliases")?.value ?? "").trim();
  const aliases = aliasesRaw
    .split(/[,，;；\n]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const skillsRaw = (g("notable_skills")?.value ?? "").trim();
  const notable_skills = skillsRaw
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  const factionRaw = (g("faction_ids")?.value ?? "").trim();
  const faction_ids = factionRaw
    .split(/[,，\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const home_region_id = (g("home_region_id")?.value ?? "").trim();
  return { id, name, cast_role, one_line_hook, notes, aliases, notable_skills, faction_ids, home_region_id };
}

function persistCharRosterCards(panelId) {
  const rootId = panelId === "charProtagonists" ? "vizCharProtagonists" : "vizCharSupporting";
  const root = $(rootId);
  if (!root || !isWorldviewPanelEditEnabled(panelId)) return;
  let entities;
  try {
    entities = JSON.parse($("charEntitiesJson")?.value || "[]");
  } catch {
    return;
  }
  if (!Array.isArray(entities)) return;
  const cards = root.querySelectorAll("[data-char-edit-card]");
  cards.forEach((article) => {
    const patch = readCharEditCardFromDom(article);
    if (!patch) return;
    const idx = entities.findIndex((e) => String(e?.id ?? "").trim() === patch.id);
    if (idx < 0) return;
    const prev = entities[idx] && typeof entities[idx] === "object" ? { ...entities[idx] } : {};
    const next = {
      ...prev,
      id: patch.id,
      name: patch.name,
      cast_role: patch.cast_role,
      aliases: patch.aliases,
      notable_skills: patch.notable_skills,
    };
    if (patch.one_line_hook) next.one_line_hook = patch.one_line_hook;
    else delete next.one_line_hook;
    if (patch.notes) next.notes = patch.notes;
    else delete next.notes;
    if (patch.faction_ids.length) next.faction_ids = patch.faction_ids;
    else delete next.faction_ids;
    if (patch.home_region_id) next.home_region_id = patch.home_region_id;
    else delete next.home_region_id;
    entities[idx] = next;
  });
  $("charEntitiesJson").value = JSON.stringify(entities, null, 2);
  setDirty(true);
  refreshCharactersVizFromForm();
}

function scheduleCharRosterPersist(panelId) {
  clearTimeout(_charRosterPersistTimer[panelId]);
  _charRosterPersistTimer[panelId] = setTimeout(() => persistCharRosterCards(panelId), 320);
}

function deleteCharacterEntityById(entityId) {
  const id = String(entityId ?? "").trim();
  if (!id) return;
  let entities;
  let relations;
  try {
    entities = JSON.parse($("charEntitiesJson")?.value || "[]");
    relations = JSON.parse($("charRelationsJson")?.value || "[]");
  } catch {
    toast("卡司 JSON 无效，无法删除");
    return;
  }
  if (!Array.isArray(entities)) return;
  const nextEnt = entities.filter((e) => String(e?.id ?? "").trim() !== id);
  const nextRel = Array.isArray(relations)
    ? relations.filter((r) => String(r?.source_id ?? "").trim() !== id && String(r?.target_id ?? "").trim() !== id)
    : [];
  $("charEntitiesJson").value = JSON.stringify(nextEnt, null, 2);
  $("charRelationsJson").value = JSON.stringify(nextRel, null, 2);
  setDirty(true);
  refreshCharactersVizFromForm();
  toast("已删除该角色并清理相关关系边");
}

function appendCharacterEntity(defaultRole) {
  let entities;
  try {
    entities = JSON.parse($("charEntitiesJson")?.value || "[]");
  } catch {
    toast("entities JSON 无效");
    return;
  }
  if (!Array.isArray(entities)) entities = [];
  const rid = defaultRole === "protagonist_core" ? uid("prot") : uid("sup");
  entities.push({
    id: rid,
    name: defaultRole === "protagonist_core" ? "新主角" : "新配角",
    cast_role: defaultRole,
    aliases: [],
    notable_skills: [],
  });
  $("charEntitiesJson").value = JSON.stringify(entities, null, 2);
  setDirty(true);
  refreshCharactersVizFromForm();
  toast("已添加角色，可在卡片中填写详情");
}

function renderCharCastCardHtml(ent, opts = {}) {
  const idRaw = String(ent?.id ?? "").trim();
  const id = escapeHtml(idRaw || "（无 id）");
  const name = escapeHtml(String(ent?.name ?? "").trim() || idRaw || "未命名");
  const roleRaw = String(ent?.cast_role ?? "").trim();
  const roleLab = escapeHtml(CAST_ROLE_LABELS[roleRaw] || roleRaw || "未标注");
  const hue = CAST_ROLE_HUES[roleRaw] ?? 210;
  const hookRaw = String(ent?.one_line_hook ?? "").trim();
  const notesRaw = String(ent?.notes ?? "").trim();
  const displayHook = hookRaw || notesRaw;
  const hook = displayHook ? escapeHtml(displayHook) : "";
  const hookLabel = hookRaw ? "叙事钩 · one_line_hook" : notesRaw ? "备注 · notes" : "叙事";
  const skills = Array.isArray(ent?.notable_skills) ? ent.notable_skills : [];
  const skillsLi = skills
    .map((s) => String(s).trim())
    .filter(Boolean)
    .slice(0, 14)
    .map((s) => `<li>${escapeHtml(s)}</li>`)
    .join("");
  const aliases = Array.isArray(ent?.aliases)
    ? ent.aliases.map((a) => String(a).trim()).filter(Boolean).slice(0, 8)
    : [];
  const aliasesStr = aliases.length ? escapeHtml(aliases.join(" · ")) : "";
  const fac = Array.isArray(ent?.faction_ids) ? ent.faction_ids.map((x) => String(x).trim()).filter(Boolean) : [];
  const home = String(ent?.home_region_id ?? "").trim();
  const facRow = fac.length
    ? `<div class="char-roster-meta-row"><span class="char-roster-k">faction_ids</span><code class="char-roster-code">${escapeHtml(
        fac.join(" · ")
      )}</code></div>`
    : "";
  const homeRow = home
    ? `<div class="char-roster-meta-row"><span class="char-roster-k">home_region_id</span><code class="char-roster-code">${escapeHtml(
        home
      )}</code></div>`
    : "";
  const metaBlock =
    facRow || homeRow
      ? `<section class="char-roster-block char-roster-block--meta" aria-label="引用锚点"><div class="char-roster-block-hd">边界 · 引用锚点</div><div class="char-roster-block-bd">${facRow}${homeRow}</div></section>`
      : "";
  const avIc = opts.variant === "supporting" ? "person" : "badge";
  return `<article class="char-roster-card" style="--char-card-hue:${hue}">
    <div class="char-roster-card-rim" aria-hidden="true"></div>
    <div class="char-roster-card-inner">
      <header class="char-roster-card-head">
        <div class="char-roster-avatar" aria-hidden="true"><span class="ms char-roster-avatar-ic">${avIc}</span></div>
        <div class="char-roster-head-main">
          <h3 class="char-roster-name">${name}</h3>
          <div class="char-roster-idline"><span class="char-roster-k">id</span><code class="char-roster-code">${id}</code></div>
        </div>
        <span class="char-roster-role-chip" title="cast_role">${roleLab}</span>
      </header>
      ${
        aliasesStr
          ? `<section class="char-roster-block"><div class="char-roster-block-hd">别名 aliases</div><div class="char-roster-block-bd char-roster-aliases">${aliasesStr}</div></section>`
          : ""
      }
      ${
        displayHook
          ? `<section class="char-roster-block"><div class="char-roster-block-hd">${hookLabel}</div><div class="char-roster-block-bd char-roster-hook">${hook}</div></section>`
          : ""
      }
      ${
        skillsLi
          ? `<section class="char-roster-block char-roster-block--skills"><div class="char-roster-block-hd">特长 notable_skills</div><ul class="char-roster-skill-list">${skillsLi}</ul></section>`
          : ""
      }
      ${metaBlock}
    </div>
  </article>`;
}

function renderCharCastSubgrid(panelId, rootId, emptyId, list, variant = "protagonists") {
  const root = $(rootId);
  const emptyEl = $(emptyId);
  if (!root) return;
  const arr = Array.isArray(list) ? list : [];
  if (emptyEl) emptyEl.hidden = arr.length > 0;
  const editing = isWorldviewPanelEditEnabled(panelId);
  root.innerHTML = arr.length
    ? arr
        .map((e) => (editing ? renderCharCastCardEditHtml(e, variant) : renderCharCastCardHtml(e, { variant })))
        .join("")
    : "";
}

function countCharacterGraphEdges(entities, relations) {
  const list = Array.isArray(entities) ? entities.filter((e) => e && typeof e === "object") : [];
  const rels = Array.isArray(relations) ? relations.filter((r) => r && typeof r === "object") : [];
  const idToIdx = new Map();
  list.forEach((e, i) => {
    const id = String(e.id ?? "").trim();
    if (id && !idToIdx.has(id)) idToIdx.set(id, i);
  });
  let n = 0;
  for (const r of rels) {
    const s = String(r.source_id ?? "").trim();
    const t = String(r.target_id ?? "").trim();
    if (!s || !t || s === t) continue;
    if (idToIdx.get(s) === undefined || idToIdx.get(t) === undefined) continue;
    n += 1;
  }
  return n;
}

function buildCharacterRelationMermaid(entities, relations) {
  const list = Array.isArray(entities) ? entities.filter((e) => e && typeof e === "object") : [];
  const rels = Array.isArray(relations) ? relations.filter((r) => r && typeof r === "object") : [];
  if (!list.length) return mermaidFactionInit() + 'flowchart TB\n  empty["（无人物实体，无法绘图）"]';

  const idToIdx = new Map();
  list.forEach((e, i) => {
    const id = String(e.id ?? "").trim();
    if (id && !idToIdx.has(id)) idToIdx.set(id, i);
  });

  const lines = [
    "flowchart LR",
    "  classDef chP fill:#e0f2fe,color:#0c4a6e,stroke:#0284c7,stroke-width:1.5px",
    "  classDef chS fill:#ede9fe,color:#4c1d95,stroke:#7c3aed,stroke-width:1.2px",
    "  classDef chA fill:#ffe4e6,color:#881337,stroke:#e11d48,stroke-width:1.2px",
    "  classDef chB fill:#f1f5f9,color:#334155,stroke:#94a3b8",
  ];
  list.forEach((e, i) => {
    const lab = mermaidEscape(e.name || e.id || `角色${i + 1}`);
    lines.push(`  C${i}["${lab}"]`);
  });
  for (const r of rels) {
    const s = String(r.source_id ?? "").trim();
    const t = String(r.target_id ?? "").trim();
    if (!s || !t || s === t) continue;
    const si = idToIdx.get(s);
    const ti = idToIdx.get(t);
    if (si === undefined || ti === undefined) continue;
    const rt = String(r.relation_type ?? "关联").trim();
    const notes = String(r.notes ?? "").trim();
    const edgeLab = mermaidEscape(`${rt}${notes ? " · " + notes : ""}`);
    lines.push(`  C${si} -->|"${edgeLab}"| C${ti}`);
  }
  const clsProt = [];
  const clsSup = [];
  const clsAnt = [];
  const clsBg = [];
  list.forEach((e, i) => {
    const cr = String(e?.cast_role ?? "").trim();
    if (cr === "protagonist_core") clsProt.push(`C${i}`);
    else if (cr === "antagonist") clsAnt.push(`C${i}`);
    else if (["supporting_major", "supporting_minor"].includes(cr)) clsSup.push(`C${i}`);
    else clsBg.push(`C${i}`);
  });
  if (clsProt.length) lines.push(`  class ${clsProt.join(",")} chP`);
  if (clsSup.length) lines.push(`  class ${clsSup.join(",")} chS`);
  if (clsAnt.length) lines.push(`  class ${clsAnt.join(",")} chA`);
  if (clsBg.length) lines.push(`  class ${clsBg.join(",")} chB`);
  return mermaidFactionInit() + lines.join("\n");
}

function refreshCharRelationNetworkViz() {
  const host = $("charRelationNetworkHost");
  const stats = $("charRelationStats");
  if (!host) return;
  const parsed = tryParseCharacterEntitiesRelations();
  if (!parsed) {
    if (stats) stats.textContent = "";
    return;
  }
  if (stats) {
    const nEnt = parsed.entities.filter((e) => e && typeof e === "object" && String(e.id ?? "").trim()).length;
    const nEdge = countCharacterGraphEdges(parsed.entities, parsed.relations);
    stats.textContent = `${nEnt} 个实体 · ${nEdge} 条可绘制关系边（端点均存在于 entities）`;
  }
  void drawMermaidHost(host, buildCharacterRelationMermaid(parsed.entities, parsed.relations));
}

/** 从当前表单刷新主角团 / 配角卡片；在「人物关系网络」页时刷新关系图 */
function refreshCharactersVizFromForm() {
  const parsed = tryParseCharacterEntitiesRelations();
  if (!parsed) return;
  const { entities } = parsed;
  const pro = entities.filter((e) => String(e?.cast_role ?? "").trim() === "protagonist_core");
  const sup = entities.filter((e) =>
    ["supporting_major", "supporting_minor", "antagonist"].includes(String(e?.cast_role ?? "").trim())
  );
  if (!shouldSkipCharRosterReRender("charProtagonists"))
    renderCharCastSubgrid("charProtagonists", "vizCharProtagonists", "charProtagonistsEmpty", pro, "protagonists");
  if (!shouldSkipCharRosterReRender("charSupporting"))
    renderCharCastSubgrid("charSupporting", "vizCharSupporting", "charSupportingEmpty", sup, "supporting");
  if (state.activeView === "charRelations") refreshCharRelationNetworkViz();
}

let _charVizTimer;
function scheduleCharactersVizFromForm() {
  clearTimeout(_charVizTimer);
  _charVizTimer = setTimeout(() => refreshCharactersVizFromForm(), 200);
}

function setupCharRosterInlineEditors() {
  const bindPanel = (viewId, panelId) => {
    const v = $(viewId);
    if (!v) return;
    v.addEventListener("input", (ev) => {
      if (!ev.target.closest("[data-char-edit-card]")) return;
      if (!isWorldviewPanelEditEnabled(panelId)) return;
      scheduleCharRosterPersist(panelId);
    });
    v.addEventListener("change", (ev) => {
      if (!ev.target.closest("[data-char-edit-card]")) return;
      if (!isWorldviewPanelEditEnabled(panelId)) return;
      if (ev.target.matches('select[data-char-field="cast_role"]')) scheduleCharRosterPersist(panelId);
    });
    v.addEventListener("click", (ev) => {
      const del = ev.target.closest("[data-char-delete-entity]");
      if (!del) return;
      if (!isWorldviewPanelEditEnabled(panelId)) return;
      ev.preventDefault();
      const eid = del.getAttribute("data-char-delete-entity");
      if (!eid || !confirm("确定从卡司删除该角色？相关关系边将一并删除。")) return;
      deleteCharacterEntityById(eid);
    });
  };
  bindPanel("view-charProtagonists", "charProtagonists");
  bindPanel("view-charSupporting", "charSupporting");
  $("btnCharProtagonistAdd")?.addEventListener("click", () => {
    if (!isWorldviewPanelEditEnabled("charProtagonists")) return;
    appendCharacterEntity("protagonist_core");
  });
  $("btnCharSupportingAdd")?.addEventListener("click", () => {
    if (!isWorldviewPanelEditEnabled("charSupporting")) return;
    appendCharacterEntity("supporting_major");
  });
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
  state.charMessages = [];
  state.storyMessages = [];
  renderMessages();
  renderCharMessages();
  renderStoryMessages();
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

function setGeoSubView(which) {
  if (which !== "regions" && which !== "overview") return;
  state.geoSubView = which;
  const reg = $("geoSubRegions");
  const ov = $("geoSubOverview");
  if (reg) reg.classList.toggle("is-hidden", which !== "regions");
  if (ov) ov.classList.toggle("is-hidden", which !== "overview");
  document.querySelectorAll("[data-geo-sub]").forEach((b) => {
    const on = b.dataset.geoSub === which;
    b.classList.toggle("is-active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  if (which === "regions") requestAnimationFrame(() => refreshGeoNetworkViz());
  if (which === "overview") requestAnimationFrame(() => refreshGeoMarkdownPreviews());
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

function setEcologySubView(which) {
  if (which !== "overview" && which !== "biomes" && which !== "species") return;
  state.ecologySubView = which;
  const ov = $("ecologySubOverview");
  const bio = $("ecologySubBiomes");
  const sp = $("ecologySubSpecies");
  if (ov) ov.classList.toggle("is-hidden", which !== "overview");
  if (bio) bio.classList.toggle("is-hidden", which !== "biomes");
  if (sp) sp.classList.toggle("is-hidden", which !== "species");
  document.querySelectorAll("[data-ecology-sub]").forEach((b) => {
    const on = b.dataset.ecologySub === which;
    b.classList.toggle("is-active", on);
    b.setAttribute("aria-selected", on ? "true" : "false");
  });
  if (which === "overview") requestAnimationFrame(() => refreshEcologyMarkdownPreviews());
  if (which === "biomes" || which === "species") requestAnimationFrame(() => renderEcologyVizFromForm());
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

let _geoMdPreviewTimer = null;
function scheduleGeoMarkdownPreviews() {
  clearTimeout(_geoMdPreviewTimer);
  _geoMdPreviewTimer = setTimeout(() => refreshGeoMarkdownPreviews(), 140);
}

/** 总览 / 气候 / 地图：与助手区相同的 Markdown 解析 + 消毒，用于右侧预览 */
function refreshGeoMarkdownPreviews() {
  const pairs = [
    ["geoSummary", "geoSummaryPreview"],
    ["geoClimate", "geoClimatePreview"],
    ["geoMap", "geoMapPreview"],
  ];
  for (const [srcId, preId] of pairs) {
    const src = $(srcId);
    const pre = $(preId);
    if (!pre) continue;
    const raw = (src?.value ?? "").toString();
    if (!raw.trim()) {
      pre.innerHTML = '<p class="muted tiny" style="margin:0">（空）</p>';
      continue;
    }
    pre.innerHTML = renderAssistantMarkdownHtml(raw);
  }
}

/** 生态页：地理区域 id → 显示名（优先当前「大陆/区域」表单，其次已加载 world） */
function getEcologyRegionLookup() {
  const m = new Map();
  try {
    for (const r of collectRegionsFromDom()) {
      const id = String(r.id || "").trim();
      if (id) m.set(id, String(r.name || "").trim() || id);
    }
  } catch {
    /* ignore */
  }
  const wr = state.world?.geography?.regions || [];
  for (const r of wr) {
    if (!r || typeof r !== "object") continue;
    const id = String(r.id || "").trim();
    if (!id || m.has(id)) continue;
    m.set(id, String(r.name || "").trim() || id);
  }
  return m;
}

function parseEcologyBiomesSpeciesJson() {
  let biomes = [];
  let species = [];
  try {
    const b = JSON.parse($("ecologyBiomesJson")?.value || "[]");
    biomes = Array.isArray(b) ? b : [];
  } catch {
    biomes = [];
  }
  try {
    const s = JSON.parse($("ecologySpeciesJson")?.value || "[]");
    species = Array.isArray(s) ? s : [];
  } catch {
    species = [];
  }
  return { biomes, species };
}

function ecologyPlainText(v) {
  return v == null ? "" : String(v).trim();
}

function ecologyMarkdownOrEmpty(raw) {
  const t = ecologyPlainText(raw);
  if (!t) return '<p class="muted tiny" style="margin:0">（空）</p>';
  return renderAssistantMarkdownHtml(t);
}

let _ecologyMdTimer = null;
function scheduleEcologyMarkdownPreviews() {
  clearTimeout(_ecologyMdTimer);
  _ecologyMdTimer = setTimeout(() => refreshEcologyMarkdownPreviews(), 140);
}

function refreshEcologyMarkdownPreviews() {
  const pairs = [
    ["ecologySummary", "ecologySummaryPreview"],
    ["ecologyDesignNotes", "ecologyDesignNotesPreview"],
  ];
  for (const [srcId, preId] of pairs) {
    const src = $(srcId);
    const pre = $(preId);
    if (!pre) continue;
    const raw = (src?.value ?? "").toString();
    if (!ecologyPlainText(raw)) {
      pre.innerHTML = '<p class="muted tiny" style="margin:0">（空）</p>';
      continue;
    }
    pre.innerHTML = renderAssistantMarkdownHtml(raw);
  }
}

let _ecologyVizTimer = null;
function scheduleEcologyVizFromForm() {
  clearTimeout(_ecologyVizTimer);
  _ecologyVizTimer = setTimeout(() => renderEcologyVizFromForm(), 160);
}

function renderEcologyVizFromForm() {
  const biomeRoot = $("vizEcologyBiomes");
  const speciesRoot = $("vizEcologySpecies");
  const emptyBio = $("ecologyBiomeEmpty");
  const emptySp = $("ecologySpeciesEmpty");
  if (!biomeRoot || !speciesRoot) return;
  const { biomes, species } = parseEcologyBiomesSpeciesJson();
  const regionMap = getEcologyRegionLookup();

  biomeRoot.replaceChildren();
  if (!biomes.length) {
    if (emptyBio) emptyBio.hidden = false;
  } else {
    if (emptyBio) emptyBio.hidden = true;
    biomes.forEach((b, idx) => {
      if (!b || typeof b !== "object") return;
      const card = document.createElement("article");
      card.className = "ecology-biome-card";
      card.style.setProperty("--eco-biome-hue", String((152 + idx * 47) % 360));
      const bid = ecologyPlainText(b.id);
      const bname = ecologyPlainText(b.name) || "未命名生境";
      const linked = Array.isArray(b.linked_region_ids) ? b.linked_region_ids : [];
      const pills = linked
        .map((rid) => {
          const id = ecologyPlainText(rid);
          if (!id) return "";
          const nm = escapeHtml(regionMap.get(id) || id);
          const idEsc = escapeHtml(id);
          return `<span class="ecology-pill ecology-pill--region" title="${idEsc}"><span class="ecology-pill-dot" aria-hidden="true"></span>${nm}</span>`;
        })
        .filter(Boolean)
        .join("");

      const extraBits = [];
      if (ecologyPlainText(b.climate_habitat))
        extraBits.push(
          `<div class="ecology-biome-extra"><span class="ecology-biome-extra-label">生境气候</span><div class="ecology-biome-extra-body msg-body msg-body--md">${ecologyMarkdownOrEmpty(
            b.climate_habitat
          )}</div></div>`
        );
      if (ecologyPlainText(b.hazards))
        extraBits.push(
          `<div class="ecology-biome-extra ecology-biome-extra--hazard"><span class="ecology-biome-extra-label">风险</span><div class="ecology-biome-extra-body msg-body msg-body--md">${ecologyMarkdownOrEmpty(
            b.hazards
          )}</div></div>`
        );
      if (ecologyPlainText(b.notes))
        extraBits.push(
          `<div class="ecology-biome-extra"><span class="ecology-biome-extra-label">备注</span><div class="ecology-biome-extra-body msg-body msg-body--md">${ecologyMarkdownOrEmpty(
            b.notes
          )}</div></div>`
        );

      card.innerHTML = `
        <div class="ecology-biome-card-top">
          <div class="ecology-biome-icon" aria-hidden="true"><span class="ms">park</span></div>
          <div class="ecology-biome-title-block">
            <h4 class="ecology-biome-name">${escapeHtml(bname)}</h4>
            ${bid ? `<code class="ecology-biome-id">${escapeHtml(bid)}</code>` : ""}
          </div>
        </div>
        ${
          pills
            ? `<div class="ecology-biome-regions"><span class="ecology-biome-regions-label muted tiny">关联区域</span><div class="ecology-pill-row">${pills}</div></div>`
            : ""
        }
        <div class="ecology-biome-summary msg-body msg-body--md">${ecologyMarkdownOrEmpty(b.summary)}</div>
        ${extraBits.join("")}`;
      biomeRoot.appendChild(card);
    });
  }

  const biomeNameById = new Map();
  for (const b of biomes) {
    if (b && typeof b === "object") {
      const id = ecologyPlainText(b.id);
      if (id) biomeNameById.set(id, ecologyPlainText(b.name) || id);
    }
  }

  speciesRoot.replaceChildren();
  if (!species.length) {
    if (emptySp) emptySp.hidden = false;
  } else {
    if (emptySp) emptySp.hidden = true;
    species.forEach((s, idx) => {
      if (!s || typeof s !== "object") return;
      const el = document.createElement("article");
      el.className = "ecology-species-card";
      el.style.setProperty("--eco-spec-hue", String((210 + idx * 53) % 360));
      const sid = ecologyPlainText(s.id);
      const sname = ecologyPlainText(s.name) || "未命名物种";
      const biomeId = ecologyPlainText(s.biome_id);
      const biomeLabel = biomeId ? biomeNameById.get(biomeId) || biomeId : "";
      const traits = Array.isArray(s.traits) ? s.traits : [];
      const traitHtml = traits
        .map((t) => ecologyPlainText(t))
        .filter(Boolean)
        .map((t) => `<span class="ecology-chip">${escapeHtml(t)}</span>`)
        .join("");
      const skills = Array.isArray(s.notable_skills) ? s.notable_skills : [];
      const skList = skills
        .map((x) => {
          if (x && typeof x === "object") return ecologyPlainText((x).name ?? (x).summary ?? JSON.stringify(x));
          return ecologyPlainText(x);
        })
        .filter(Boolean)
        .map(
          (x) =>
            `<li><span class="ms ecology-skill-ic" aria-hidden="true">auto_awesome</span><span class="ecology-skill-txt">${escapeHtml(
              x
            )}</span></li>`
        )
        .join("");
      const dial = ecologyPlainText(s.encounter_dialogue);
      const danger = ecologyPlainText(s.danger_notes);

      el.innerHTML = `
        <header class="ecology-species-head">
          <div class="ecology-species-avatar" aria-hidden="true"><span class="ms">pets</span></div>
          <div class="ecology-species-head-text">
            <h4 class="ecology-species-name">${escapeHtml(sname)}</h4>
            <div class="ecology-species-meta">
              ${sid ? `<code class="ecology-species-id">${escapeHtml(sid)}</code>` : ""}
              ${
                biomeId
                  ? `<span class="ecology-species-biome-badge" title="biome_id: ${escapeHtml(biomeId)}"><span class="ms">park</span>${escapeHtml(
                      biomeLabel
                    )}</span>`
                  : ""
              }
            </div>
          </div>
        </header>
        ${
          traitHtml
            ? `<div class="ecology-species-traits"><span class="muted tiny ecology-block-label">特征</span><div class="ecology-chip-row">${traitHtml}</div></div>`
            : ""
        }
        ${
          skList
            ? `<div class="ecology-species-skills"><span class="muted tiny ecology-block-label">行为与「物种技能」</span><ul class="ecology-skill-list">${skList}</ul></div>`
            : ""
        }
        ${
          dial
            ? `<blockquote class="ecology-encounter"><span class="ecology-encounter-label muted tiny">遭遇台词 / 旁白</span><div class="ecology-encounter-body msg-body msg-body--md">${renderAssistantMarkdownHtml(
                dial
              )}</div></blockquote>`
            : ""
        }
        ${
          danger
            ? `<div class="ecology-danger"><span class="ms ecology-danger-ic" aria-hidden="true">warning</span><div class="ecology-danger-body msg-body msg-body--md muted tiny">${renderAssistantMarkdownHtml(
                danger
              )}</div></div>`
            : ""
        }`;
      speciesRoot.appendChild(el);
    });
  }
}

function refreshEcologyGenerateMarkdown(raw) {
  const out = $("ecologyGenerateOut");
  if (!out) return;
  const t = ecologyPlainText(raw);
  if (!t) {
    out.innerHTML = '<p class="muted tiny" style="margin:0">（尚无生成结果）</p>';
    return;
  }
  out.innerHTML = renderAssistantMarkdownHtml(t);
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
  const eb = (w.ecology?.biomes || []).length;
  const es = (w.ecology?.species || []).length;
  const econ =
    (w.economy?.currencies?.length || 0) +
    (w.economy?.markets?.length || 0) +
    (w.economy?.trade_routes?.length || 0) +
    (w.economy?.trade_goods?.length || 0);
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
    pill("forest", `生态 ${eb}/${es}`),
    pill("payments", `经济 ${econ}`),
    pill("recent_actors", `人物 ${(w.characters?.entities || []).length}`),
    pill("tag", `v${w.meta?.version ?? 0}`),
  ].join("");
}

function setThinking(phase, opts = {}) {
  if (!phase) {
    for (const id of ["chatThinking", "charChatThinking", "storyChatThinking"]) {
      const strip = $(id);
      if (!strip) continue;
      strip.hidden = true;
      strip.classList.remove("thinking-strip--visible");
    }
    return;
  }
  let panel = opts.panel;
  if (!panel) {
    if (state.activeView === "charChat") panel = "char";
    else if (state.activeView === "storyChat") panel = "story";
    else panel = "world";
  }
  const el =
    panel === "char" ? $("charChatThinking") : panel === "story" ? $("storyChatThinking") : $("chatThinking");
  for (const id of ["chatThinking", "charChatThinking", "storyChatThinking"]) {
    const strip = $(id);
    if (!strip || strip === el) continue;
    strip.hidden = true;
    strip.classList.remove("thinking-strip--visible");
  }
  if (!el) return;
  const lab = el.querySelector(".thinking-label");
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
  const route = resolveStoryPanelRoute(name);
  name = route.panel;
  if (route.storySubView) state.storySubView = route.storySubView;
  if (route.activeStoryNav) state.activeStoryNav = route.activeStoryNav;
  if (route.storyOutlineSub) state.storyOutlineSub = route.storyOutlineSub;
  state.activeView = name;
  syncNavActiveButtons();
  document.querySelectorAll(".panel").forEach((p) => {
    p.classList.toggle("active", p.id === `view-${name}`);
  });
  if (name === "files") refreshFilesView();
  if (name === "search") refreshSearchView();
  if (name === "story") {
    state.storyUnitLabel = storyUnitLabelForMode(state.world?.meta?.creative_mode || $("genreMode")?.value);
    storyMetaToForm();
    void refreshStoryPanel();
    setStorySubView(state.storySubView || "overview");
  }
  if (name === "cultures") scheduleCultureVizRefresh();
  updateCultureHint();
  if (name === "chat") refreshFactionChatViz();
  if (name === "charChat") renderCharMessages();
  if (name === "storyChat") {
    refreshStoryChatContextLine();
    renderStoryMessages();
  }
  if (isCharacterPanelView(name)) scheduleCharactersVizFromForm();
  if (name === "powers") setPowerSubView(state.powerSubView || "system");
  if (name === "geo") setGeoSubView(state.geoSubView || "overview");
  if (name === "ecology") {
    requestAnimationFrame(() => setEcologySubView(state.ecologySubView || "overview"));
  }
  refreshContextPanel();
}

/** 对话后同步若写入了 economy，切换到「经济」页以便立即看到表单与 JSON（须已 worldToForm） */
function navigateToEconomyAfterSyncIfNeeded(updatedSections) {
  if (!Array.isArray(updatedSections) || !updatedSections.includes("economy")) return;
  requestAnimationFrame(() => {
    switchView("economy");
    $("view-economy")?.querySelector(".card")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

/** 情节构建同步后跳转到对应情节子栏 */
function navigateToStoryAfterSyncIfNeeded(updatedSections) {
  if (!Array.isArray(updatedSections) || !updatedSections.includes("story")) return;
  requestAnimationFrame(() => {
    const fs = state.world?.story?.foreshadowing;
    if (Array.isArray(fs) && fs.length) switchView("storyForeshadow");
    else if (state.world?.story?.chapters?.length) switchView("storyOutline");
    else switchView("storyOverview");
    $("view-story")?.querySelector(".story-workbench")?.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function storyUnitLabelForMode(mode) {
  const m = (mode || "").trim().toLowerCase();
  if (m === "game") return "章节";
  if (m === "coc" || m === "dnd") return "跑团会话";
  return "章";
}

function stripAuthorOnlyMarkdown(md) {
  const t = (md ?? "").toString();
  const m = t.match(/^##\s*作者备注\s*$/m);
  if (!m || m.index == null) return t;
  return t.slice(0, m.index).trim();
}

function updateStoryMarkdownPreview(previewId, text, authorView) {
  const el = $(previewId);
  if (!el) return;
  const raw = authorView ? text : stripAuthorOnlyMarkdown(text);
  el.innerHTML = renderAssistantMarkdownHtml(raw);
}

function sortedStoryChapters() {
  const arr = state.world?.story?.chapters;
  if (!Array.isArray(arr)) return [];
  return [...arr].sort((a, b) => (a.order || 0) - (b.order || 0) || String(a.id).localeCompare(String(b.id)));
}

function storyMetaToForm() {
  const s = state.world?.story || {};
  const unit = state.storyUnitLabel || storyUnitLabelForMode($("genreMode")?.value);
  if ($("storyUnitLine")) $("storyUnitLine").textContent = `情节单元：${unit}`;
  if ($("storySummary")) $("storySummary").value = s.summary ?? "";
  if ($("storyDesignNotes")) $("storyDesignNotes").value = s.design_notes ?? "";
  if ($("storyChaptersJson"))
    $("storyChaptersJson").value = JSON.stringify(s.chapters ?? [], null, 2);
  if ($("storyForeshadowJson"))
    $("storyForeshadowJson").value = JSON.stringify(s.foreshadowing ?? [], null, 2);
  const n = s.narrator || {};
  if ($("storyNarratorPerson")) $("storyNarratorPerson").value = n.person || "third_person_limited";
  if ($("storyNarratorVoice")) $("storyNarratorVoice").value = n.voice_notes ?? "";
  const wd = s.writing_defaults || {};
  if ($("storyAttachPrev")) $("storyAttachPrev").value = String(wd.attach_prev_chapters ?? 3);
  refreshStoryNarratorSelect(n.character_id || "");
  refreshStoryChapterSelects();
  renderStoryChapterNav();
  renderStoryForeshadowTimeline(s.foreshadowing ?? []);
  updateStoryWbStats();
  updateStoryWbTitle();
}

function refreshStoryNarratorSelect(selectedId) {
  const sel = $("storyNarratorCharacter");
  if (!sel) return;
  const ents = state.world?.characters?.entities || [];
  let html = '<option value="">（不绑定 POV 角色）</option>';
  for (const e of ents) {
    if (!e || typeof e !== "object") continue;
    const id = String(e.id ?? "").trim();
    if (!id) continue;
    const name = String(e.name ?? id).trim();
    const selAttr = id === selectedId ? " selected" : "";
    html += `<option value="${escapeAttr(id)}"${selAttr}>${escapeHtml(name)} · ${escapeHtml(id)}</option>`;
  }
  sel.innerHTML = html;
}

function refreshStoryChapterSelects() {
  const chapters = sortedStoryChapters();
  const opts = chapters
    .map(
      (c) =>
        `<option value="${escapeAttr(c.id)}">${escapeHtml(String(c.order))}. ${escapeHtml(c.title || c.id)}</option>`
    )
    .join("");
  const empty = '<option value="">（请先新建章节）</option>';
  for (const id of ["storyBeatChapterSelect", "storyMsChapterSelect", "storyWriteChapterSelect"]) {
    const el = $(id);
    if (!el) continue;
    el.innerHTML = chapters.length ? opts : empty;
  }
  const active = state.storyActiveChapterId || chapters[0]?.id || "";
  if (active) {
    for (const id of ["storyBeatChapterSelect", "storyMsChapterSelect", "storyWriteChapterSelect"]) {
      const el = $(id);
      if (el && [...el.options].some((o) => o.value === active)) el.value = active;
    }
  }
}

function updateStoryWbTitle() {
  const h = $("storyWbTitle");
  if (!h) return;
  const nav = state.activeStoryNav || STORY_SUB_TO_NAV[state.storySubView] || "storyOverview";
  const lab = STORY_NAV_LABELS[nav] || "情节";
  h.innerHTML = `<span class="ms h2-ic" aria-hidden="true">auto_stories</span>情节 · ${escapeHtml(lab)}`;
}

function setStoryOutlineSub(name) {
  state.storyOutlineSub = name;
  document.querySelectorAll("#storyOutlineSubtabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.outlineSub === name);
  });
  for (const [key, pid] of Object.entries({
    macro: "storyPaneMacro",
    beats: "storyPaneBeats",
    auxiliary: "storyPaneAuxiliary",
  })) {
    $(pid)?.classList.toggle("hidden", key !== name);
  }
  if (name === "macro") void loadStoryMacro();
  if (name === "beats") void loadStoryBeat();
  if (name === "auxiliary") refreshOutlineHeader();
}

function setStorySubView(name) {
  state.storySubView = name;
  state.activeStoryNav = STORY_SUB_TO_NAV[name] || state.activeStoryNav || "storyOverview";
  syncNavActiveButtons();
  updateStoryWbTitle();
  const panes = {
    overview: "storyPaneOverview",
    outline: "storyPaneOutline",
    chapter: "storyPaneChapter",
    foreshadow: "storyPaneForeshadow",
    write: "storyPaneWrite",
  };
  for (const [key, pid] of Object.entries(panes)) {
    $(pid)?.classList.toggle("hidden", key !== name);
  }
  if (name === "outline") setStoryOutlineSub(state.storyOutlineSub || "macro");
  if (name === "chapter") void loadStoryManuscript();
  if (name === "foreshadow") {
    const items = parseStoryForeshadowingFromForm();
    if (items) renderStoryForeshadowTimeline(items);
  }
  refreshStoryChatContextLine();
}

async function refreshStoryPanel() {
  if (!state.world?.meta?.id) return;
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/story`);
    if (res.story) state.world.story = res.story;
    state.storyUnitLabel = res.unit_label || storyUnitLabelForMode(state.world.meta.creative_mode);
    if (res.legacy_imported) toast("已从 outlines/plot_outline.md 导入粗纲");
    storyMetaToForm();
  } catch (e) {
    toast("加载情节失败：" + (e?.message || e));
  }
}

async function loadStoryMacro() {
  if (!state.world?.meta?.id) return;
  const res = await api(`/api/worlds/${state.world.meta.id}/story/macro-outline`);
  if ($("storyMacroEdit")) $("storyMacroEdit").value = res.content || "";
  updateStoryMarkdownPreview("storyMacroPreview", res.content || "", true);
}

async function loadStoryBeat() {
  const cid = $("storyBeatChapterSelect")?.value;
  if (!cid || !state.world?.meta?.id) return;
  const res = await api(`/api/worlds/${state.world.meta.id}/story/chapters/${encodeURIComponent(cid)}/beat`);
  if ($("storyBeatEdit")) $("storyBeatEdit").value = res.content || "";
  updateStoryMarkdownPreview("storyBeatPreview", res.content || "", true);
}

async function loadStoryManuscript() {
  const cid = $("storyMsChapterSelect")?.value;
  if (!cid || !state.world?.meta?.id) return;
  const res = await api(
    `/api/worlds/${state.world.meta.id}/story/chapters/${encodeURIComponent(cid)}/manuscript`
  );
  if ($("storyManuscriptEdit")) $("storyManuscriptEdit").value = res.content || "";
  const author = $("storyAuthorView")?.checked ?? true;
  updateStoryMarkdownPreview("storyManuscriptPreview", res.content || "", author);
}

function collectStoryMetaForWorld(w) {
  if (!w.story) w.story = {};
  w.story.summary = ($("storySummary")?.value ?? "").trim();
  w.story.design_notes = ($("storyDesignNotes")?.value ?? "").trim();
  w.story.unit_label = storyUnitLabelForMode(w.meta.creative_mode || $("genreMode")?.value);
  const parseJson = (txt, label) => {
    try {
      return JSON.parse(txt || "[]");
    } catch (e) {
      throw new Error(`${label} JSON 无效：${e.message}`);
    }
  };
  w.story.chapters = parseJson($("storyChaptersJson")?.value, "story.chapters");
  w.story.foreshadowing = document.querySelector("#storyForeshadowList .story-fs-card")
    ? collectStoryForeshadowingFromDom()
    : parseJson($("storyForeshadowJson")?.value, "story.foreshadowing");
  if (!w.story.narrator) w.story.narrator = {};
  w.story.narrator.character_id = ($("storyNarratorCharacter")?.value ?? "").trim();
  w.story.narrator.person = $("storyNarratorPerson")?.value || "third_person_limited";
  w.story.narrator.voice_notes = ($("storyNarratorVoice")?.value ?? "").trim();
  if (!w.story.writing_defaults) w.story.writing_defaults = {};
  const ap = parseInt($("storyAttachPrev")?.value ?? "3", 10);
  w.story.writing_defaults.attach_prev_chapters = Number.isFinite(ap)
    ? Math.max(0, Math.min(5, ap))
    : 3;
}

function bindStoryEditorPreview(textareaId, previewId, authorCheckboxId) {
  const ta = $(textareaId);
  if (!ta) return;
  const run = () => {
    const author = authorCheckboxId ? ($(authorCheckboxId)?.checked ?? true) : true;
    updateStoryMarkdownPreview(previewId, ta.value, author);
  };
  ta.addEventListener("input", run);
  if (authorCheckboxId) $(authorCheckboxId)?.addEventListener("change", run);
}

function initStoryPanelBindings() {
  document.querySelectorAll("#storyOutlineSubtabs button").forEach((b) => {
    b.addEventListener("click", () => setStoryOutlineSub(b.dataset.outlineSub || "macro"));
  });
  bindStoryEditorPreview("storyMacroEdit", "storyMacroPreview");
  bindStoryEditorPreview("storyBeatEdit", "storyBeatPreview");
  bindStoryEditorPreview("storyManuscriptEdit", "storyManuscriptPreview", "storyAuthorView");
  $("storyBeatChapterSelect")?.addEventListener("change", () => {
    const cid = $("storyBeatChapterSelect")?.value;
    if (cid) state.storyActiveChapterId = cid;
    renderStoryChapterNav(cid);
    void loadStoryBeat();
  });
  $("storyMsChapterSelect")?.addEventListener("change", () => {
    const cid = $("storyMsChapterSelect")?.value;
    if (cid) state.storyActiveChapterId = cid;
    renderStoryChapterNav(cid);
    void loadStoryManuscript();
  });

  $("btnStoryAddChapterSide")?.addEventListener("click", () => $("btnStoryAddChapter")?.click());
  $("storyChapterNav")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-story-chapter-id]");
    if (!btn?.dataset.storyChapterId) return;
    selectStoryChapter(btn.dataset.storyChapterId);
  });
  $("storyForeshadowList")?.addEventListener("input", scheduleStoryForeshadowSync);
  $("storyForeshadowList")?.addEventListener("change", scheduleStoryForeshadowSync);
  $("storyForeshadowList")?.addEventListener("click", (e) => {
    const rm = e.target.closest("[data-fs-remove]");
    if (!rm) return;
    const idx = parseInt(rm.dataset.fsRemove ?? "", 10);
    const items = collectStoryForeshadowingFromDom().filter((_, i) => i !== idx);
    syncStoryForeshadowJson(items);
    renderStoryForeshadowTimeline(items);
    updateStoryWbStats();
    setDirty(true);
  });
  $("storyForeshadowJson")?.addEventListener("input", scheduleStoryForeshadowFromJson);
  $("btnStoryAddForeshadow")?.addEventListener("click", () => {
    let list = document.querySelector("#storyForeshadowList .story-fs-card")
      ? collectStoryForeshadowingFromDom()
      : parseStoryForeshadowingFromForm() ?? [];
    const chapters = sortedStoryChapters();
    list.push({
      id: newStoryForeshadowId(),
      label: "",
      planted_chapter_id: chapters[0]?.id || "",
      payoff_chapter_id: "",
      reader_known: false,
      status: "open",
      notes: "",
    });
    syncStoryForeshadowJson(list);
    renderStoryForeshadowTimeline(list);
    updateStoryWbStats();
    setDirty(true);
  });
  $("storyChaptersJson")?.addEventListener("input", () => {
    if (state.world?.story) {
      try {
        state.world.story.chapters = JSON.parse($("storyChaptersJson")?.value || "[]");
      } catch {
        return;
      }
    }
    refreshStoryChapterSelects();
    renderStoryChapterNav();
    updateStoryWbStats();
    const items = parseStoryForeshadowingFromForm();
    if (items) renderStoryForeshadowTimeline(items);
    setDirty(true);
  });

  $("btnStorySaveMacro")?.addEventListener("click", async () => {
    if (!state.world) return toast("请先选择世界");
    try {
      await api(`/api/worlds/${state.world.meta.id}/story/macro-outline`, {
        method: "PUT",
        body: JSON.stringify({ content: $("storyMacroEdit")?.value ?? "" }),
      });
      toast("粗纲已保存");
    } catch (e) {
      toast("保存失败：" + e.message);
    }
  });

  $("btnStorySaveBeat")?.addEventListener("click", async () => {
    const cid = $("storyBeatChapterSelect")?.value;
    if (!cid || !state.world) return;
    try {
      await api(`/api/worlds/${state.world.meta.id}/story/chapters/${encodeURIComponent(cid)}/beat`, {
        method: "PUT",
        body: JSON.stringify({ content: $("storyBeatEdit")?.value ?? "" }),
      });
      toast("细纲已保存");
    } catch (e) {
      toast("保存失败：" + e.message);
    }
  });

  $("btnStorySaveManuscript")?.addEventListener("click", async () => {
    const cid = $("storyMsChapterSelect")?.value;
    if (!cid || !state.world) return;
    try {
      const res = await api(
        `/api/worlds/${state.world.meta.id}/story/chapters/${encodeURIComponent(cid)}/manuscript`,
        {
          method: "PUT",
          body: JSON.stringify({ content: $("storyManuscriptEdit")?.value ?? "" }),
        }
      );
      toast(`文稿已保存（约 ${res.word_count ?? 0} 字）`);
      await refreshStoryPanel();
    } catch (e) {
      toast("保存失败：" + e.message);
    }
  });

  $("btnStoryAddChapter")?.addEventListener("click", async () => {
    if (!state.world) return toast("请先选择世界");
    const title = prompt("新章节标题（可留空）") || "";
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/story/chapters`, {
        method: "POST",
        body: JSON.stringify({ title }),
      });
      state.world = res.world;
      storyMetaToForm();
      setDirty(true);
      toast("已新建章节");
    } catch (e) {
      toast("新建失败：" + e.message);
    }
  });

  $("btnStoryImportLegacy")?.addEventListener("click", async () => {
    if (!state.world) return;
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/story/import-legacy-outline`, {
        method: "POST",
        body: "{}",
      });
      if (res.ok && $("storyMacroEdit")) $("storyMacroEdit").value = res.content || "";
      toast(res.ok ? "已导入旧情节总纲" : "未找到可导入文件");
      if (res.ok) {
        switchView("storyOutline");
        setStoryOutlineSub("macro");
      }
    } catch (e) {
      toast("导入失败：" + e.message);
    }
  });

  $("btnStoryGenMacro")?.addEventListener("click", async () => {
    if (!state.world) return;
    const promptText =
      ($("storyGenMacroHint")?.value ?? "").trim() || "请根据当前世界设定撰写全书粗纲。";
    setThinking("chat", { panel: "story" });
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/story/generate/macro-outline`, {
        method: "POST",
        body: JSON.stringify({
          prompt: promptText,
          include_markdown_context: false,
          creative_mode: $("genreMode")?.value || null,
          persist: true,
        }),
      });
      state.world = res.world;
      if ($("storyMacroEdit")) $("storyMacroEdit").value = res.reply || "";
      updateStoryMarkdownPreview("storyMacroPreview", res.reply || "", true);
      storyMetaToForm();
      setDirty(false);
      toast("粗纲已生成并落盘");
    } catch (e) {
      toast("生成失败：" + e.message);
    } finally {
      setThinking(false);
    }
  });

  $("btnStoryGenBeats")?.addEventListener("click", async () => {
    if (!state.world) return;
    const cid = $("storyBeatChapterSelect")?.value;
    const ids = cid ? [cid] : sortedStoryChapters().map((c) => c.id);
    if (!ids.length) return toast("请先新建章节");
    const promptText = ($("storyGenBeatsHint")?.value ?? "").trim() || "请撰写本章细纲。";
    setThinking("chat", { panel: "story" });
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/story/generate/chapter-beats`, {
        method: "POST",
        body: JSON.stringify({
          chapter_ids: ids,
          prompt: promptText,
          creative_mode: $("genreMode")?.value || null,
          persist: true,
        }),
      });
      state.world = res.world;
      storyMetaToForm();
      if (cid && res.beats?.[cid] && $("storyBeatEdit")) {
        $("storyBeatEdit").value = res.beats[cid];
        updateStoryMarkdownPreview("storyBeatPreview", res.beats[cid], true);
      }
      setDirty(false);
      toast("细纲已生成");
    } catch (e) {
      toast("生成失败：" + e.message);
    } finally {
      setThinking(false);
    }
  });

  $("btnStoryGenManuscript")?.addEventListener("click", async () => {
    if (!state.world) return;
    const cid = $("storyWriteChapterSelect")?.value;
    if (!cid) return toast("请选择章节");
    setThinking("chat", { panel: "story" });
    try {
      const res = await api(`/api/worlds/${state.world.meta.id}/story/generate/manuscript`, {
        method: "POST",
        body: JSON.stringify({
          chapter_id: cid,
          prompt: ($("storyWritePrompt")?.value ?? "").trim() || "请撰写本章正文。",
          person: $("storyNarratorPerson")?.value || null,
          character_id: $("storyNarratorCharacter")?.value || null,
          attach_prev_chapters: parseInt($("storyAttachPrev")?.value ?? "3", 10),
          creative_mode: $("genreMode")?.value || null,
          persist: true,
        }),
      });
      state.world = res.world;
      storyMetaToForm();
      if ($("storyMsChapterSelect")) $("storyMsChapterSelect").value = cid;
      if ($("storyManuscriptEdit")) $("storyManuscriptEdit").value = res.reply || "";
      updateStoryMarkdownPreview(
        "storyManuscriptPreview",
        res.reply || "",
        $("storyAuthorView")?.checked ?? true
      );
      setDirty(false);
      toast("本章文稿已生成");
      switchView("storyChapter");
    } catch (e) {
      toast("生成失败：" + e.message);
    } finally {
      setThinking(false);
    }
  });
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
    if ($("economySummary")) $("economySummary").value = "";
    if ($("economyDesignNotes")) $("economyDesignNotes").value = "";
    if ($("economyLaborNotes")) $("economyLaborNotes").value = "";
    if ($("economyTaxationNotes")) $("economyTaxationNotes").value = "";
    if ($("economyVolatilityNotes")) $("economyVolatilityNotes").value = "";
    if ($("economyCurrenciesJson")) $("economyCurrenciesJson").value = "[]";
    if ($("economyMarketsJson")) $("economyMarketsJson").value = "[]";
    if ($("economyTradeRoutesJson")) $("economyTradeRoutesJson").value = "[]";
    if ($("economyTradeGoodsJson")) $("economyTradeGoodsJson").value = "[]";
    if ($("attrSummary")) $("attrSummary").value = "";
    if ($("attrDesignNotes")) $("attrDesignNotes").value = "";
    if ($("attrStatsJson")) $("attrStatsJson").value = "[]";
    if ($("attrTierProfilesJson")) $("attrTierProfilesJson").value = "[]";
    if ($("ecologySummary")) $("ecologySummary").value = "";
    if ($("ecologyDesignNotes")) $("ecologyDesignNotes").value = "";
    if ($("ecologyBiomesJson")) $("ecologyBiomesJson").value = "[]";
    if ($("ecologySpeciesJson")) $("ecologySpeciesJson").value = "[]";
    if ($("ecologyGenerateHint")) $("ecologyGenerateHint").value = "";
    if ($("ecologyGenerateOut")) $("ecologyGenerateOut").innerHTML = "";
    if ($("charEntitiesJson")) $("charEntitiesJson").value = "[]";
    if ($("charRelationsJson")) $("charRelationsJson").value = "[]";
    if ($("charIncludeMd")) $("charIncludeMd").checked = false;
    if ($("charAutoSyncPanels")) $("charAutoSyncPanels").checked = true;
    if ($("storySummary")) $("storySummary").value = "";
    if ($("storyDesignNotes")) $("storyDesignNotes").value = "";
    if ($("storyChaptersJson")) $("storyChaptersJson").value = "[]";
    if ($("storyForeshadowJson")) $("storyForeshadowJson").value = "[]";
    state.charMessages = [];
    renderCharMessages();
    renderCharCastSubgrid("charProtagonists", "vizCharProtagonists", "charProtagonistsEmpty", [], "protagonists");
    renderCharCastSubgrid("charSupporting", "vizCharSupporting", "charSupportingEmpty", [], "supporting");
    const gm = $("genreMode");
    if (gm) gm.value = "";
    renderRegionCards([]);
    renderFactionCards([]);
    renderCultureCards([]);
    refreshGeoMarkdownPreviews();
    refreshEcologyMarkdownPreviews();
    renderEcologyVizFromForm();
    refreshEcologyGenerateMarkdown("");
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

  const eco = w.economy || {};
  if ($("economySummary")) $("economySummary").value = eco.summary ?? "";
  if ($("economyDesignNotes")) $("economyDesignNotes").value = eco.design_notes ?? "";
  if ($("economyLaborNotes")) $("economyLaborNotes").value = eco.labor_notes ?? "";
  if ($("economyTaxationNotes")) $("economyTaxationNotes").value = eco.taxation_notes ?? "";
  if ($("economyVolatilityNotes")) $("economyVolatilityNotes").value = eco.volatility_notes ?? "";
  if ($("economyCurrenciesJson"))
    $("economyCurrenciesJson").value = JSON.stringify(eco.currencies ?? [], null, 2);
  if ($("economyMarketsJson")) $("economyMarketsJson").value = JSON.stringify(eco.markets ?? [], null, 2);
  if ($("economyTradeRoutesJson"))
    $("economyTradeRoutesJson").value = JSON.stringify(eco.trade_routes ?? [], null, 2);
  if ($("economyTradeGoodsJson"))
    $("economyTradeGoodsJson").value = JSON.stringify(eco.trade_goods ?? [], null, 2);

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

  if ($("ecologySummary")) $("ecologySummary").value = w.ecology?.summary ?? "";
  if ($("ecologyDesignNotes")) $("ecologyDesignNotes").value = w.ecology?.design_notes ?? "";
  if ($("ecologyBiomesJson"))
    $("ecologyBiomesJson").value = JSON.stringify(w.ecology?.biomes ?? [], null, 2);
  if ($("ecologySpeciesJson"))
    $("ecologySpeciesJson").value = JSON.stringify(w.ecology?.species ?? [], null, 2);

  const ch = w.characters || {};
  if ($("charEntitiesJson"))
    $("charEntitiesJson").value = JSON.stringify(ch.entities ?? [], null, 2);
  if ($("charRelationsJson"))
    $("charRelationsJson").value = JSON.stringify(ch.relations ?? [], null, 2);

  renderRegionCards(w.geography?.regions);
  renderFactionCards(w.factions?.entities);
  renderCultureCards(w.cultures?.entities);

  refreshGeoMarkdownPreviews();
  refreshEcologyMarkdownPreviews();
  renderEcologyVizFromForm();

  const gm = $("genreMode");
  if (gm) gm.value = w.meta?.creative_mode || "";
  updateGenreModeHint();
  updateCultureHint();
  updateFactionGlobalBriefPreview();
  refreshFactionChatViz();
  scheduleCharactersVizFromForm();

  const st = w.story || {};
  state.storyUnitLabel = st.unit_label || storyUnitLabelForMode(w.meta?.creative_mode);
  if ($("storySummary")) $("storySummary").value = st.summary ?? "";
  if ($("storyDesignNotes")) $("storyDesignNotes").value = st.design_notes ?? "";
  if ($("storyChaptersJson")) $("storyChaptersJson").value = JSON.stringify(st.chapters ?? [], null, 2);
  if ($("storyForeshadowJson"))
    $("storyForeshadowJson").value = JSON.stringify(st.foreshadowing ?? [], null, 2);
  const sn = st.narrator || {};
  if ($("storyNarratorPerson")) $("storyNarratorPerson").value = sn.person || "third_person_limited";
  if ($("storyNarratorVoice")) $("storyNarratorVoice").value = sn.voice_notes ?? "";
  const swd = st.writing_defaults || {};
  if ($("storyAttachPrev")) $("storyAttachPrev").value = String(swd.attach_prev_chapters ?? 3);
  refreshStoryNarratorSelect(sn.character_id || "");
  refreshStoryChapterSelects();
  renderStoryChapterNav();
  renderStoryForeshadowTimeline(st.foreshadowing ?? []);
  updateStoryWbStats();
  if ($("storyUnitLine")) $("storyUnitLine").textContent = `情节单元：${state.storyUnitLabel}`;
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

  if (!w.ecology) w.ecology = { summary: "", design_notes: "", biomes: [], species: [] };
  w.ecology.summary = ($("ecologySummary")?.value ?? "").trim();
  w.ecology.design_notes = ($("ecologyDesignNotes")?.value ?? "").trim();
  w.ecology.biomes = parseJson($("ecologyBiomesJson")?.value || "[]", "生态 biomes");
  w.ecology.species = parseJson($("ecologySpeciesJson")?.value || "[]", "生态 species");

  if (!w.economy)
    w.economy = {
      summary: "",
      design_notes: "",
      currencies: [],
      markets: [],
      trade_routes: [],
      trade_goods: [],
      labor_notes: "",
      taxation_notes: "",
      volatility_notes: "",
    };
  w.economy.summary = ($("economySummary")?.value ?? "").trim();
  w.economy.design_notes = ($("economyDesignNotes")?.value ?? "").trim();
  w.economy.labor_notes = ($("economyLaborNotes")?.value ?? "").trim();
  w.economy.taxation_notes = ($("economyTaxationNotes")?.value ?? "").trim();
  w.economy.volatility_notes = ($("economyVolatilityNotes")?.value ?? "").trim();
  w.economy.currencies = parseJson($("economyCurrenciesJson")?.value || "[]", "经济 currencies");
  w.economy.markets = parseJson($("economyMarketsJson")?.value || "[]", "经济 markets");
  w.economy.trade_routes = parseJson($("economyTradeRoutesJson")?.value || "[]", "经济 trade_routes");
  w.economy.trade_goods = parseJson($("economyTradeGoodsJson")?.value || "[]", "经济 trade_goods");

  if (!w.characters) w.characters = { summary: "", design_notes: "", entities: [], relations: [] };
  w.characters.entities = parseJson($("charEntitiesJson")?.value || "[]", "人物 entities");
  w.characters.relations = parseJson($("charRelationsJson")?.value || "[]", "人物 relations");

  if (!w.story) {
    w.story = {
      summary: "",
      design_notes: "",
      unit_label: "",
      chapters: [],
      foreshadowing: [],
    };
  }
  collectStoryMetaForWorld(w);

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
  const line = $("storyOutlineVersionLine") || $("outlineVersionLine");
  if (!line) return;
  if (!state.world) {
    line.textContent = "请先选择或新建世界。";
    return;
  }
  const m = state.world.meta;
  line.textContent = `当前依据：world.json · ${m.name} · v${m.version} · ${m.id}`;
}

function updateOutlineMarkdownPreview(text) {
  const el = $("outlinePreview");
  if (!el) return;
  el.innerHTML = renderAssistantMarkdownHtml((text ?? "").toString());
}

function refreshStoryChatContextLine() {
  const line = $("storyChatContextLine");
  if (!line) return;
  const cid = state.storyActiveChapterId || "";
  if (!cid) {
    line.textContent = "当前章节：（未选，将使用第一章或空）";
    return;
  }
  const ch = sortedStoryChapters().find((c) => c.id === cid);
  line.textContent = `当前章节：${ch ? `${ch.order}. ${ch.title || ch.id}` : cid}（id=${cid}）`;
}

function parseStoryMdBlocks(text) {
  const blocks = [];
  const re = /```([^\n`]+)\s*\n([\s\S]*?)```/g;
  let m;
  const raw = (text ?? "").toString();
  while ((m = re.exec(raw))) {
    const tag = (m[1] || "").trim().toLowerCase();
    const content = (m[2] || "").trim();
    if (!content) continue;
    if (tag === "story-macro") blocks.push({ kind: "macro", chapterId: "", content });
    else if (tag.startsWith("story-beat:"))
      blocks.push({ kind: "beat", chapterId: tag.slice("story-beat:".length).trim(), content });
    else if (tag.startsWith("story-manuscript:"))
      blocks.push({
        kind: "manuscript",
        chapterId: tag.slice("story-manuscript:".length).trim(),
        content,
      });
  }
  return blocks;
}

async function applyStoryMdBlock(block) {
  if (!state.world?.meta?.id || !block?.content) return;
  const wid = state.world.meta.id;
  if (block.kind === "macro") {
    await api(`/api/worlds/${wid}/story/macro-outline`, {
      method: "PUT",
      body: JSON.stringify({ content: block.content }),
    });
    if ($("storyMacroEdit")) $("storyMacroEdit").value = block.content;
    updateStoryMarkdownPreview("storyMacroPreview", block.content, true);
    switchView("storyOutline");
    setStoryOutlineSub("macro");
    toast("已写入粗纲");
    return;
  }
  const cid = block.chapterId;
  if (!cid) return toast("代码块缺少章节 id");
  if (block.kind === "beat") {
    await api(`/api/worlds/${wid}/story/chapters/${encodeURIComponent(cid)}/beat`, {
      method: "PUT",
      body: JSON.stringify({ content: block.content }),
    });
    state.storyActiveChapterId = cid;
    if ($("storyBeatChapterSelect")) $("storyBeatChapterSelect").value = cid;
    if ($("storyBeatEdit")) $("storyBeatEdit").value = block.content;
    updateStoryMarkdownPreview("storyBeatPreview", block.content, true);
    switchView("storyOutline");
    setStoryOutlineSub("beats");
    renderStoryChapterNav(cid);
    toast("已写入细纲");
    return;
  }
  if (block.kind === "manuscript") {
    const res = await api(`/api/worlds/${wid}/story/chapters/${encodeURIComponent(cid)}/manuscript`, {
      method: "PUT",
      body: JSON.stringify({ content: block.content }),
    });
    state.storyActiveChapterId = cid;
    if ($("storyMsChapterSelect")) $("storyMsChapterSelect").value = cid;
    if ($("storyManuscriptEdit")) $("storyManuscriptEdit").value = block.content;
    updateStoryMarkdownPreview(
      "storyManuscriptPreview",
      block.content,
      $("storyAuthorView")?.checked ?? true
    );
    await refreshStoryPanel();
    switchView("storyChapter");
    toast(`已写入文稿（约 ${res.word_count ?? 0} 字）`);
  }
}

function fillStoryChatPromptTemplate(text, opts = {}) {
  const inp = $("storyChatInput");
  if (!inp) return;
  const cur = (inp.value || "").trim();
  if (opts.mode === "append" && cur) inp.value = `${cur}\n\n${text}`;
  else inp.value = text;
  inp.focus();
}

function renderStoryMessages() {
  const box = $("storyMessages");
  if (!box) return;
  box.innerHTML = "";
  for (let mi = 0; mi < state.storyMessages.length; mi++) {
    const m = state.storyMessages[mi];
    const div = document.createElement("div");
    div.className = `msg ${m.role}`;
    const roleIc = m.role === "user" ? "person" : "smart_toy";
    let extra = "";
    if (m.role === "assistant") {
      const blocks = parseStoryMdBlocks(m.content);
      if (blocks.length) {
        extra =
          '<div class="story-md-apply-row">' +
          blocks
            .map((b, bi) => {
              const lab =
                b.kind === "macro"
                  ? "写入粗纲"
                  : b.kind === "beat"
                    ? `写入细纲 · ${escapeHtml(b.chapterId)}`
                    : `写入文稿 · ${escapeHtml(b.chapterId)}`;
              return `<button type="button" class="ghost tiny story-md-apply" data-msg-index="${mi}" data-block-index="${bi}">${lab}</button>`;
            })
            .join("") +
          "</div>";
      }
    }
    const body =
      m.role === "assistant"
        ? renderAssistantMarkdownHtml(m.content)
        : escapeHtml(m.content).replaceAll("\n", "<br/>");
    const bodyClass =
      m.role === "assistant" ? "msg-body msg-body--assistant msg-body--md" : "msg-body msg-body--user";
    div.innerHTML = `<div class="role"><span class="ms role-ic" aria-hidden="true">${roleIc}</span>${m.role}</div><div class="${bodyClass}">${body}</div>${extra}`;
    div.innerHTML = div.innerHTML.replace('<div class="role"', '<div class="role"');
    box.appendChild(div);
  }
  box.querySelectorAll(".story-md-apply").forEach((btn) => {
    btn.addEventListener("click", () => {
      const mi = parseInt(btn.dataset.msgIndex ?? "", 10);
      const bi = parseInt(btn.dataset.blockIndex ?? "", 10);
      const msg = state.storyMessages[mi];
      if (!msg) return;
      const blocks = parseStoryMdBlocks(msg.content);
      const block = blocks[bi];
      if (block) void applyStoryMdBlock(block);
    });
  });
  box.scrollTop = box.scrollHeight;
}

function newStoryForeshadowId() {
  return `fs_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

function parseStoryForeshadowingFromForm() {
  try {
    const raw = JSON.parse($("storyForeshadowJson")?.value || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return null;
  }
}

function syncStoryForeshadowJson(items) {
  const list = Array.isArray(items) ? items : [];
  if ($("storyForeshadowJson")) $("storyForeshadowJson").value = JSON.stringify(list, null, 2);
  if (state.world?.story) state.world.story.foreshadowing = list;
}

function chapterIndexMap(chapters) {
  const map = new Map();
  chapters.forEach((c, i) => {
    if (c?.id) map.set(String(c.id), i);
  });
  return map;
}

function storyForeshadowChapterSelectHtml(field, index, selectedId, chapters) {
  let html = `<select data-fs-field="${field}" data-fs-index="${index}"><option value="">（未指定）</option>`;
  for (const c of chapters) {
    const id = String(c.id ?? "").trim();
    if (!id) continue;
    html += `<option value="${escapeAttr(id)}"${id === selectedId ? " selected" : ""}>${escapeHtml(
      String(c.order)
    )}. ${escapeHtml(c.title || id)}</option>`;
  }
  return html + "</select>";
}

function renderStoryForeshadowTimeline(items) {
  const host = $("storyForeshadowTimeline");
  const listEl = $("storyForeshadowList");
  if (!host || !listEl) return;
  const chapters = sortedStoryChapters();
  const list = Array.isArray(items) ? items : [];
  const idxMap = chapterIndexMap(chapters);
  const cols = Math.max(chapters.length, 1);

  if (!chapters.length) {
    host.innerHTML =
      '<div class="story-fs-grid story-fs-grid--empty">请先新建章节，再沿章节轴编排伏笔。</div>';
  } else {
    let grid = `<div class="story-fs-grid" style="grid-template-columns: minmax(72px, 0.9fr) repeat(${cols}, minmax(48px, 1fr))">`;
    grid += '<div class="story-fs-corner">伏笔</div>';
    for (const ch of chapters) {
      const t = String(ch.title || ch.id).trim();
      grid += `<div class="story-fs-ch" title="${escapeAttr(t)}">${escapeHtml(t.slice(0, 8) || ch.id)}</div>`;
    }
    if (!list.length) {
      grid +=
        '<div class="story-fs-grid story-fs-grid--empty" style="grid-column: 1 / -1">暂无伏笔，点击「+ 添加伏笔」。</div>';
    } else {
      for (const fs of list) {
        const label = String(fs.label || fs.id || "未命名").trim();
        const planted = String(fs.planted_chapter_id || "").trim();
        const payoff = String(fs.payoff_chapter_id || "").trim();
        const pi = planted && idxMap.has(planted) ? idxMap.get(planted) : -1;
        const pj = payoff && idxMap.has(payoff) ? idxMap.get(payoff) : -1;
        const status = String(fs.status || "open");
        const barClass =
          pi < 0 && pj < 0
            ? "story-fs-bar--orphan"
            : status === "resolved"
              ? "story-fs-bar--status-resolved"
              : status === "partial"
                ? "story-fs-bar--status-partial"
                : "";
        grid += `<div class="story-fs-row-label" title="${escapeAttr(label)}">${escapeHtml(label)}</div>`;
        for (let c = 0; c < cols; c++) {
          let inner = "";
          if (pi >= 0 || pj >= 0) {
            const lo = pi >= 0 && pj >= 0 ? Math.min(pi, pj) : pi >= 0 ? pi : pj;
            const hi = pi >= 0 && pj >= 0 ? Math.max(pi, pj) : lo;
            if (c >= lo && c <= hi) inner = `<span class="story-fs-bar ${barClass}"></span>`;
          }
          grid += `<div class="story-fs-track">${inner}</div>`;
        }
      }
    }
    grid += "</div>";
    host.innerHTML = grid;
  }

  const statusOpts = [
    ["open", "未回收"],
    ["partial", "部分揭晓"],
    ["resolved", "已回收"],
  ];
  if (!list.length) {
    listEl.innerHTML = '<p class="muted tiny">暂无伏笔条目。</p>';
    return;
  }
  listEl.innerHTML = list
    .map((fs, i) => {
      const id = String(fs.id || newStoryForeshadowId());
      const planted = String(fs.planted_chapter_id || "");
      const payoff = String(fs.payoff_chapter_id || "");
      const status = String(fs.status || "open");
      const opts = statusOpts
        .map(([v, lab]) => `<option value="${v}"${v === status ? " selected" : ""}>${lab}</option>`)
        .join("");
      return `<article class="story-fs-card" data-fs-index="${i}">
        <div class="story-fs-card-head">
          <input type="text" data-fs-field="label" data-fs-index="${i}" value="${escapeAttr(
            (fs.label ?? "").toString()
          )}" placeholder="伏笔名称" autocomplete="off" />
          <label class="muted tiny"><input type="checkbox" data-fs-field="reader_known" data-fs-index="${i}"${
            fs.reader_known ? " checked" : ""
          } /> 读者已知</label>
          <button type="button" class="ghost tiny" data-fs-remove="${i}">删除</button>
        </div>
        <div class="story-fs-card-grid">
          <label>埋设章节 ${storyForeshadowChapterSelectHtml("planted_chapter_id", i, planted, chapters)}</label>
          <label>回收章节 ${storyForeshadowChapterSelectHtml("payoff_chapter_id", i, payoff, chapters)}</label>
          <label>状态 <select data-fs-field="status" data-fs-index="${i}">${opts}</select></label>
        </div>
        <label class="muted tiny">备注</label>
        <textarea rows="2" data-fs-field="notes" data-fs-index="${i}" spellcheck="true">${escapeHtml(
          (fs.notes ?? "").toString()
        )}</textarea>
        <input type="hidden" data-fs-field="id" data-fs-index="${i}" value="${escapeAttr(id)}" />
      </article>`;
    })
    .join("");
}

function collectStoryForeshadowingFromDom() {
  const cards = document.querySelectorAll("#storyForeshadowList .story-fs-card");
  const out = [];
  cards.forEach((card) => {
    const i = card.dataset.fsIndex;
    const get = (field) => {
      const el = card.querySelector(`[data-fs-field="${field}"][data-fs-index="${i}"]`);
      if (!el) return "";
      if (el.type === "checkbox") return el.checked;
      return el.value;
    };
    out.push({
      id: String(get("id") || newStoryForeshadowId()).trim(),
      label: String(get("label") || "").trim(),
      planted_chapter_id: String(get("planted_chapter_id") || "").trim(),
      payoff_chapter_id: String(get("payoff_chapter_id") || "").trim(),
      reader_known: !!get("reader_known"),
      status: get("status") || "open",
      notes: String(get("notes") || "").trim(),
    });
  });
  return out;
}

let _storyFsTimer;
function scheduleStoryForeshadowSync() {
  clearTimeout(_storyFsTimer);
  _storyFsTimer = setTimeout(() => {
    const items = collectStoryForeshadowingFromDom();
    syncStoryForeshadowJson(items);
    renderStoryForeshadowTimeline(items);
    updateStoryWbStats();
    setDirty(true);
  }, 220);
}

function scheduleStoryForeshadowFromJson() {
  clearTimeout(_storyFsTimer);
  _storyFsTimer = setTimeout(() => {
    const items = parseStoryForeshadowingFromForm();
    if (items === null) return;
    renderStoryForeshadowTimeline(items);
    if (state.world?.story) state.world.story.foreshadowing = items;
    updateStoryWbStats();
  }, 280);
}

function updateStoryWbStats() {
  const el = $("storyWbStats");
  if (!el) return;
  const chapters = sortedStoryChapters();
  const fs = parseStoryForeshadowingFromForm() ?? state.world?.story?.foreshadowing ?? [];
  const open = (Array.isArray(fs) ? fs : []).filter((x) => (x.status || "open") !== "resolved").length;
  const unit = state.storyUnitLabel || "章";
  el.textContent = `${chapters.length} 个${unit} · ${Array.isArray(fs) ? fs.length : 0} 条伏笔（${open} 条未回收）`;
}

function renderStoryChapterNav(activeId) {
  const nav = $("storyChapterNav");
  if (!nav) return;
  const chapters = sortedStoryChapters();
  const unit = state.storyUnitLabel || "章";
  if ($("storyAsideUnitLabel")) $("storyAsideUnitLabel").textContent = unit;
  if (!chapters.length) {
    nav.innerHTML = `<p class="muted tiny">尚无${unit}</p>`;
    return;
  }
  const aid = activeId || state.storyActiveChapterId || chapters[0]?.id || "";
  state.storyActiveChapterId = aid;
  nav.innerHTML = chapters
    .map((c) => {
      const id = String(c.id);
      const active = id === aid ? " active" : "";
      return `<button type="button" class="story-ch-nav-btn${active}" data-story-chapter-id="${escapeAttr(
        id
      )}" title="${escapeAttr(c.title || id)}">
        <span class="story-ch-order">${escapeHtml(String(c.order))}</span>${escapeHtml(c.title || id)}
      </button>`;
    })
    .join("");
}

function selectStoryChapter(chapterId, subView) {
  if (!chapterId) return;
  state.storyActiveChapterId = chapterId;
  renderStoryChapterNav(chapterId);
  for (const selId of ["storyBeatChapterSelect", "storyMsChapterSelect", "storyWriteChapterSelect"]) {
    const el = $(selId);
    if (el) el.value = chapterId;
  }
  refreshStoryChatContextLine();
  if (subView === "beats") {
    switchView("storyOutline");
    setStoryOutlineSub("beats");
  } else if (subView === "chapter") {
    switchView("storyChapter");
    void loadStoryManuscript();
  } else if (subView === "write") {
    switchView("storyWrite");
  } else if (subView) setStorySubView(subView);
  else if (state.storySubView === "outline" && state.storyOutlineSub === "beats") void loadStoryBeat();
  else if (state.storySubView === "chapter") void loadStoryManuscript();
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
  const skipClearFixPanel = Boolean(opts.skipClearFixPanel);
  const out = $("referenceLintOut");
  if (!skipClearFixPanel) {
    const fixOut = $("referenceLintFixOut");
    if (fixOut) fixOut.innerHTML = "";
  }
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
      toast(`保存完成；引用校验有 ${warns.length} 条提示（见「数据」→「引用一致性」）`);
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

function formatReferenceLintFollowupHtml(lint) {
  if (!lint || lint.ok) return "";
  const w = lint.warnings || [];
  if (!w.length) return "";
  return (
    '<p class="muted tiny" style="margin:8px 0 4px">自动修复后仍可能存在的提示（需人工）：</p>' +
    `<ul style="margin:0;padding-left:1.1em">${w.map((x) => `<li>${escapeHtml(String(x))}</li>`).join("")}</ul>`
  );
}

async function runReferenceFixPreview() {
  const fixOut = $("referenceLintFixOut");
  if (!state.world?.meta?.id) {
    if (fixOut) fixOut.innerHTML = "";
    return toast("请先选择世界");
  }
  if (fixOut) {
    fixOut.classList.add("muted");
    fixOut.innerHTML = "<p>生成预览…</p>";
  }
  try {
    const res = await api(`/api/worlds/${state.world.meta.id}/fix-references`, {
      method: "POST",
      body: JSON.stringify({ dry_run: true }),
    });
    const lines = res.would_apply || [];
    const cnt = typeof res.apply_count === "number" ? res.apply_count : lines.length;
    if (fixOut) {
      const noSteps = !lines.length;
      fixOut.classList.toggle("muted", noSteps && res.lint_after && res.lint_after.ok);
      const head = noSteps
        ? `<p class="tiny" style="margin:0 0 6px">预览：<strong>0</strong> 步变更（当前规则下无需自动修复）。</p>`
        : `<p class="tiny" style="margin:0 0 6px">预览：<strong>${cnt}</strong> 步（未写盘），应用后将执行：</p><ul style="margin:0;padding-left:1.1em">${lines
            .map((l) => `<li>${escapeHtml(String(l))}</li>`)
            .join("")}</ul>`;
      fixOut.innerHTML = head + formatReferenceLintFollowupHtml(res.lint_after);
    }
    toast(
      lines.length ? `预览：${lines.length} 步自动修复（未写盘）` : "预览：当前无需自动修复项"
    );
  } catch (e) {
    const msg = e?.message || String(e);
    if (fixOut) {
      fixOut.classList.add("muted");
      fixOut.innerHTML = `<p>${escapeHtml(msg)}</p>`;
    }
    toast("预览自动修复失败：" + msg);
  }
}

async function runReferenceFixApply() {
  const fixOut = $("referenceLintFixOut");
  if (!state.world?.meta?.id) {
    if (fixOut) fixOut.innerHTML = "";
    return toast("请先选择世界");
  }
  if (
    !confirm(
      "将按预览相同规则修改磁盘上的 world.json 并升级版本保存；表单中未保存的更改将丢失。是否继续？"
    )
  ) {
    return;
  }
  if (fixOut) {
    fixOut.classList.add("muted");
    fixOut.innerHTML = "<p>正在应用…</p>";
  }
  const id = state.world.meta.id;
  try {
    const res = await api(`/api/worlds/${id}/fix-references`, {
      method: "POST",
      body: JSON.stringify({ dry_run: false }),
    });
    if (!res.saved) {
      if (fixOut) {
        fixOut.classList.add("muted");
        fixOut.innerHTML =
          "<p>未写盘：当前磁盘 world 在本规则下无需修改（或已与修复结果一致）。可先运行校验查看剩余提示。</p>";
      }
      toast("引用自动修复：无需写盘");
      return;
    }
    await loadWorld(id);
    const applied = res.applied || [];
    if (fixOut) {
      fixOut.classList.remove("muted");
      fixOut.innerHTML =
        `<p class="tiny" style="margin:0 0 6px">已应用 <strong>${applied.length}</strong> 步并落盘：</p><ul style="margin:0;padding-left:1.1em">${applied
          .map((l) => `<li>${escapeHtml(String(l))}</li>`)
          .join("")}</ul>` + formatReferenceLintFollowupHtml(res.lint);
    }
    await runReferenceLintFlow({ quietToast: true, skipClearFixPanel: true });
    toast(`引用自动修复已落盘（${applied.length} 步）`);
  } catch (e) {
    const msg = e?.message || String(e);
    if (fixOut) {
      fixOut.classList.add("muted");
      fixOut.innerHTML = `<p>${escapeHtml(msg)}</p>`;
    }
    toast("应用自动修复失败：" + msg);
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
  const charInc = $("charIncludeMd");
  if (charInc && typeof data.has_nonempty_world_md === "boolean") {
    charInc.checked = data.has_nonempty_world_md;
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
  setupCharRosterInlineEditors();

  try {
    const cfg = await api("/api/config");
    $("apiHint").textContent = cfg.has_api_key
      ? `世界观构建：${cfg.default_model} · 同步：${cfg.structure_sync_model ?? cfg.default_model}`
      : "未配置 PARATERA_API_KEY（世界观构建 / 大纲 / 板块同步将不可用）";
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
      "默认关闭「仅当前页模块」：助手一次可同步多个板块。若开启，仅在当前导航对应模块写入（地理/生态/境界/物品/属性/文化·宗教/派系/历史/**经济**/**人物卡司** 等），其它模块输出会被丢弃。在「人物生成」或左侧「主角团 / 重要配角 / 人物关系网络 / 卡司数据」任一页开启时，scope 为 **characters**；在「经济」页开启时，scope 为 **economy**。";
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

  document.querySelectorAll("[data-geo-sub]").forEach((btn) => {
    btn.addEventListener("click", () => setGeoSubView(btn.dataset.geoSub));
  });
  setGeoSubView(state.geoSubView || "overview");

  document.querySelectorAll("[data-ecology-sub]").forEach((btn) => {
    btn.addEventListener("click", () => setEcologySubView(btn.dataset.ecologySub));
  });
  setEcologySubView(state.ecologySubView || "overview");

  $("btnSnapshotDiff")?.addEventListener("click", () => void runSnapshotDiff());
  $("btnSnapshotRollback")?.addEventListener("click", () => void runSnapshotRollback());
  $("btnReferenceLint")?.addEventListener("click", () => void runReferenceLintFlow({ quietToast: false }));
  $("btnReferenceLintFixPreview")?.addEventListener("click", () => void runReferenceFixPreview());
  $("btnReferenceLintFixApply")?.addEventListener("click", () => void runReferenceFixApply());

  $("btnNewWorld").addEventListener("click", () => createWorldFlow().catch((e) => toast(e.message)));
  $("btnRenameWorld")?.addEventListener("click", () =>
    renameCurrentWorldFlow().catch((e) => toast(e.message))
  );
  $("btnDeleteWorld")?.addEventListener("click", () =>
    deleteCurrentWorldFlow().catch((e) => toast(e.message))
  );
  $("btnEmptyCreate").addEventListener("click", () => createWorldFlow().catch((e) => toast(e.message)));

  const markDirty = () => setDirty(true);
  ["geoSummary", "geoClimate", "geoMap"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      markDirty();
      scheduleGeoMarkdownPreviews();
    });
  });
  [
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
    "economySummary",
    "economyDesignNotes",
    "economyLaborNotes",
    "economyTaxationNotes",
    "economyVolatilityNotes",
    "economyCurrenciesJson",
    "economyMarketsJson",
    "economyTradeRoutesJson",
    "economyTradeGoodsJson",
    "attrSummary",
    "attrDesignNotes",
    "attrStatsJson",
    "attrTierProfilesJson",
  ].forEach((id) => $(id).addEventListener("input", markDirty));
  ["charEntitiesJson", "charRelationsJson"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      markDirty();
      scheduleCharactersVizFromForm();
    });
  });
  ["ecologySummary", "ecologyDesignNotes"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      markDirty();
      scheduleEcologyMarkdownPreviews();
    });
  });
  ["ecologyBiomesJson", "ecologySpeciesJson"].forEach((id) => {
    const el = $(id);
    if (!el) return;
    el.addEventListener("input", () => {
      markDirty();
      scheduleEcologyVizFromForm();
    });
  });
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
    if (state.world) {
      state.storyUnitLabel = storyUnitLabelForMode($("genreMode")?.value);
      if ($("storyUnitLine")) $("storyUnitLine").textContent = `情节单元：${state.storyUnitLabel}`;
    }
    markDirty();
    updateGenreModeHint();
    updateCultureHint();
  });

  $("regionCards")?.addEventListener("input", (ev) => {
    markDirty();
    const card = ev.target.closest(".region-card");
    if (card) syncRegionCardIcon(card);
    scheduleGeoVizRefresh();
    scheduleEcologyVizFromForm();
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

  $("btnQuitApp")?.addEventListener("click", async () => {
    const warn = state.dirty
      ? "有未保存更改，确定仍要退出？本地服务将停止，未保存内容将丢失。"
      : "确定退出？将停止本地服务并尝试关闭本页。";
    if (!confirm(warn)) return;
    const btn = $("btnQuitApp");
    if (btn) btn.disabled = true;
    try {
      const r = await fetch(API + "/api/shutdown", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!r.ok) {
        const t = await r.text();
        let detail = r.statusText;
        try {
          const j = JSON.parse(t || "{}");
          if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
          else if (t) detail = t;
        } catch {
          if (t) detail = t;
        }
        throw new Error(detail);
      }
    } catch (e) {
      if (btn) btn.disabled = false;
      toast("退出失败：" + (e?.message || e));
      return;
    }
    document.body.innerHTML = `<main class="shutdown-screen" role="status"><p class="shutdown-title">服务已停止</p><p class="shutdown-hint">可关闭本浏览器标签页；若浏览器未自动关闭窗口，请手动关闭。</p></main>`;
    requestAnimationFrame(() => {
      try {
        window.open("", "_self");
        window.close();
      } catch (_) {
        /* 用户直接打开的标签页可能不允许脚本关闭，保留占位页即可 */
      }
    });
  });

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
    if ($("guideEcology")?.checked) chat_guides.push("ecology");
    if ($("guideEconomy")?.checked) chat_guides.push("economy");
    const userMsg = text;
    state.messages.push({ role: "user", content: text });
    $("chatInput").value = "";
    renderMessages();
    setThinking("chat", { panel: "world" });
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
    let syncUpdatedSections = null;
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

    setThinking("sync", { panel: "world" });
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
        syncUpdatedSections = syncRes.updated_sections;
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
    navigateToEconomyAfterSyncIfNeeded(syncUpdatedSections);
  }

  async function submitCharChatFromUI() {
    if (!state.world) return toast("请先选择世界");
    const text = ($("charChatInput")?.value ?? "").trim();
    if (!text) return;
    const mode = $("genreMode")?.value || null;
    const includeMd = $("charIncludeMd")?.checked ?? false;
    const chat_guides = [];
    if ($("guideCharacterRoster")?.checked) chat_guides.push("character_roster");
    const userMsg = text;
    state.charMessages.push({ role: "user", content: text });
    if ($("charChatInput")) $("charChatInput").value = "";
    renderCharMessages();
    setThinking("chat", { panel: "char" });
    let res;
    try {
      res = await api(`/api/worlds/${state.world.meta.id}/character-chat`, {
        method: "POST",
        body: JSON.stringify({
          messages: state.charMessages,
          mode,
          include_markdown_context: includeMd,
          chat_guides,
        }),
      });
    } catch (e) {
      state.charMessages.pop();
      renderCharMessages();
      toast("人物对话失败：" + e.message);
      setThinking(false);
      return;
    }
    state.charMessages.push({ role: "assistant", content: res.reply });
    renderCharMessages();
    setThinking(false);

    let shouldPersist = false;
    let syncUpdatedSections = null;
    if (!$("charAutoSyncPanels")?.checked) return;

    setThinking("sync", { panel: "char" });
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
        syncUpdatedSections = syncRes.updated_sections;
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

    if (shouldPersist) {
      try {
        await persistWorldFromForm();
      } catch (e) {
        toast("落盘失败：" + (e?.message || e));
      }
    }
    navigateToEconomyAfterSyncIfNeeded(syncUpdatedSections);
  }

  async function submitStoryChatFromUI() {
    if (!state.world) return toast("请先选择世界");
    const text = ($("storyChatInput")?.value ?? "").trim();
    if (!text) return;
    const mode = $("genreMode")?.value || null;
    const includeFiles = $("storyIncludeFiles")?.checked ?? false;
    const cid =
      state.storyActiveChapterId ||
      $("storyBeatChapterSelect")?.value ||
      $("storyMsChapterSelect")?.value ||
      sortedStoryChapters()[0]?.id ||
      "";
    const userMsg = text;
    state.storyMessages.push({ role: "user", content: text });
    if ($("storyChatInput")) $("storyChatInput").value = "";
    renderStoryMessages();
    setThinking("chat", { panel: "story" });
    let res;
    try {
      res = await api(`/api/worlds/${state.world.meta.id}/story-chat`, {
        method: "POST",
        body: JSON.stringify({
          messages: state.storyMessages,
          mode,
          include_markdown_context: false,
          include_story_files: includeFiles,
          active_chapter_id: cid,
        }),
      });
    } catch (e) {
      state.storyMessages.pop();
      renderStoryMessages();
      toast("情节对话失败：" + e.message);
      setThinking(false);
      return;
    }
    state.storyMessages.push({ role: "assistant", content: res.reply });
    renderStoryMessages();
    setThinking(false);

    let shouldPersist = false;
    let syncUpdatedSections = null;
    if (!$("storyAutoSyncPanels")?.checked) return;

    setThinking("sync", { panel: "story" });
    try {
      const syncScope =
        state.activeView === "storyChat" || isStoryPanelView(state.activeView)
          ? "story"
          : syncScopeForRequest();
      const syncRes = await api(`/api/worlds/${state.world.meta.id}/sync-panels-from-chat`, {
        method: "POST",
        body: JSON.stringify({
          user_message: userMsg,
          assistant_reply: res.reply,
          persist: false,
          scope: syncScope,
          creative_mode: $("genreMode")?.value || null,
        }),
      });
      if (syncRes.ok) {
        state.world = syncRes.world;
        worldToForm(syncRes.world);
        setDirty(true);
        refreshContextPanel();
        refreshOutlineHeader();
        syncUpdatedSections = syncRes.updated_sections;
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
          if (nnLines.length) toast("结构归一化：" + nnLines.join(" | "));
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

    if (shouldPersist) {
      try {
        await persistWorldFromForm();
      } catch (e) {
        toast("落盘失败：" + (e?.message || e));
      }
    }
    navigateToStoryAfterSyncIfNeeded(syncUpdatedSections);
  }

  $("btnSend").addEventListener("click", () => void submitChatFromUI());

  $("chatInput")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !e.ctrlKey) return;
    e.preventDefault();
    void submitChatFromUI();
  });

  $("btnCharSend")?.addEventListener("click", () => void submitCharChatFromUI());
  $("charChatInput")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !e.ctrlKey) return;
    e.preventDefault();
    void submitCharChatFromUI();
  });

  $("btnStorySend")?.addEventListener("click", () => void submitStoryChatFromUI());
  $("storyChatInput")?.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" || !e.ctrlKey) return;
    e.preventDefault();
    void submitStoryChatFromUI();
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
      updateOutlineMarkdownPreview(res.reply);
      toast("已写入 " + res.saved);
      await loadWorld(state.world.meta.id);
    } catch (e) {
      toast("大纲失败：" + e.message);
    }
  });

  $("btnEcologyGenerate")?.addEventListener("click", () => {
    void (async () => {
      if (!state.world) return toast("请先选择世界");
      const hint = ($("ecologyGenerateHint")?.value ?? "").trim();
      setThinking("chat");
      try {
        const res = await api(`/api/worlds/${state.world.meta.id}/ecology-generate`, {
          method: "POST",
          body: JSON.stringify({
            hint,
            creative_mode: $("genreMode")?.value || null,
          }),
        });
        const reply = (res.reply ?? "").toString();
        if (out) refreshEcologyGenerateMarkdown(reply);
        const det = $("ecologyGenDetails");
        if (det && reply) det.open = true;
        toast(reply ? "生态生成完成（见上方预览；可复制 JSON 后同步或手填）" : "模型返回为空");
      } catch (e) {
        toast("生态生成失败：" + (e?.message || e));
      } finally {
        setThinking(false);
      }
    })();
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

  const ECOLOGY_CHAT_PROMPT =
    "请为当前世界补充或修订 **生态与生境**（world.json 的 **ecology**；与 **geography**、**attribute_system** 对齐；便于「对话后同步」落盘）。请用自然语言 + 清晰小节，尽量与下列键名对齐（不必默认输出整段 JSON，除非我要求）：\n\n" +
    "1）**总览 ecology.summary**：全图生态位、危险带、文明与荒野/超凡力量的交界叙事。\n" +
    "2）**设计说明 ecology.design_notes**：哪些 **geography.regions[].id**、气候/地貌与 **attribute_system.stats** 的叙事刻度如何对应野外压力或魔化生态。\n" +
    "3）**生境群落 ecology.biomes[]**：每项 **id**、**name**、**summary**；**linked_region_ids[]** 只能使用已有 **geography.regions[].id**（无则不要虚构 id）；可选 **climate_habitat**、**hazards**、**notes**。\n" +
    "4）**代表物种 ecology.species[]**：每项 **id**、**name**、**biome_id**（须为 **biomes[].id**）；**traits[]**；**notable_skills[]**（物种行为或叙事向「类技能」短句，**非**境界 **power_system.skill_tree** 节点）；**encounter_dialogue**（一句遭遇旁白或台词，供跑团/DM 使用）；可选 **danger_notes**。\n\n" +
    "若 JSON 中已有 **biomes/species**，请对照修订并说明是否新增或重命名了 **id**（以便我检查 **biome_id** 与 **linked_region_ids**）。\n\n" +
    "若你准备给出可机读补丁，请在回复**文末**用单个 **```json** 代码块给出根对象 `{ \"ecology\": { ... } }`（字段与上述一致）。";

  const ECONOMY_CHAT_PROMPT =
    "请为当前世界补充或修订 **经济与流通**（world.json 的 **economy**；与 **geography.regions**、**factions.entities**、**item_quality_system** 对齐；便于「对话后同步」落盘）。请用自然语言 + 清晰小节，尽量与下列键名对齐（不必默认输出整段 JSON，除非我要求）：\n\n" +
    "1）**总览 economy.summary**：通货、铸币权、商会与黑市、关税与走私带等宏观叙事。\n" +
    "2）**设计说明 economy.design_notes**：哪些 **regions[].id**、**factions.entities[].id**、物品档位如何牵动现金流与危机。\n" +
    "3）**货币 economy.currencies[]**：每项 **id**、**name**；可选 **symbol**、**issuer_faction_id**（须为已有派系 **id**）、**exchange_notes**。\n" +
    "4）**市场 economy.markets[]**：每项 **id**、**name**；可选 **summary**、**linked_region_ids[]**（仅已有区域 **id**）、**dominant_faction_ids[]**、**notes**。\n" +
    "5）**商路 economy.trade_routes[]**：每项 **id**、**name**、**from_region_id**、**to_region_id**（须为已有区域 **id**）；可选 **summary**、**goods_notes**、**controlling_faction_ids[]**、**notes**。\n" +
    "6）**贸易品 economy.trade_goods[]**：每项 **id**、**name**；可选 **category**（如 strategic|luxury|common|contraband）、**summary**、**notes**。\n" +
    "7）**labor_notes**、**taxation_notes**、**volatility_notes**：劳动力、税收再分配、物价波动与危机等条款式说明。\n\n" +
    "若你准备给出可机读补丁，请在回复**文末**用单个 **```json** 代码块给出根对象 `{ \"economy\": { ... } }`（字段与上述一致）。";

  const FACTIONS_CHAT_PROMPT =
    "请为当前世界新增或修订 **派系**（world.json 的 **factions**；便于「对话后同步」写入）。请用 Markdown，**按派系分块**（每个派系建议用三级标题，正文内显式写出 **id**、**name**、**goals**、**territory** 以便抽取）：\n\n" +
    "1）**factions.summary**（可选）：多派系博弈总览。\n" +
    "2）**factions.entities[]**（核心）：每项必须含 **id**（短英文 slug，全局唯一）、**name**；**goals** 与 **territory** 各为**一整段字符串**（宗旨/立场；控制区、据点、外溢影响），勿把长叙事拆成无键名的散列表。\n" +
    "3）**key_figures**：**字符串数组**，每项一行，如「阿兰 · 外务执事」；**禁止**使用 `{ name, role }` 形式的对象列表（当前 schema 无法落盘）。\n" +
    "4）**relations[]**：派系之间的关系；每项 **target_id** 填**另一派系**的 **id**（不要用中文派系名代替 id）；**type** 只能是英文 **ally** | **enemy** | **neutral** | **complex** 四选一（不要用 rival、联盟、敌对等——若语义如此请映射成 enemy/ally/neutral/complex 后再写），可选 **notes**。\n" +
    "5）若已有 **factions.entities**，请保留既有 **id**，只增补 goals、territory、key_figures、relations；新增派系须用新的唯一 **id**。\n\n" +
    "若你准备给出可机读补丁，请在回复**文末**用单个 **```json** 代码块给出根对象 `{ \"factions\": { \"summary\": \"...\", \"entities\": [ ... ] } }`，结构与上述一致。";

  const FACTION_KEY_PEOPLE_CHAT_PROMPT =
    "请针对当前 **world.json** 中已有 **factions.entities**（请按每个实体的 **id** 逐个点名），为每个派系扩写 **key_figures**：每派系 **3～7** 条，每项**一行字符串**（建议「姓名 · 职务/立场」或「姓名（一句秘密或叙事钩子）」）。\n\n" +
    "**不要**改动各派系 **id** 与 **name**；不要新增不了解的 **relations**，除非同时给出规范的 **target_id** + **type**（**ally|enemy|neutral|complex**）+ 可选 **notes**。\n" +
    "请用 Markdown **按派系 id 分小节**列出便于同步；若提供 JSON，文末单个 **```json** 根对象须为 `{ \"factions\": { \"entities\": [ ... ] } }`，每个实体须含 **id** 与 **key_figures**（字符串数组），其余字段可与已有世界一致并写全以便合并。";

  const CHARACTER_ROSTER_CHAT_PROMPT =
    "请为当前世界补充或修订 **人物卡司**（world.json 的 **characters**；与派系、地理 id 对齐；便于「对话后同步」落盘）。请用自然语言 + 清晰小节，尽量与下列键名对齐（不必默认输出整段 JSON，除非我要求）：\n\n" +
    "1）**characters.summary**：谁在驱动主线/副线，卡司规模与叙事功能。\n" +
    "2）**characters.design_notes**：与 **factions** 要人、**history**、**geography.regions** 籍贯等 **id** 的对齐与防漂移约定。\n" +
    "3）**characters.entities[]**：每项 **id**、**name**；**cast_role** 取 `protagonist_core`（主角团核心）| `supporting_major` | `supporting_minor` | `antagonist` | `background`；**faction_ids[]** 须对齐已有 **factions.entities[].id**；**home_region_id** 须对齐已有 **geography.regions[].id**；可选 **aliases[]**、**one_line_hook**、**notes**、**notable_skills[]**（人物叙事或玩法向特长短句，**非**境界 **power_system.skill_tree** 节点）。\n" +
    "4）**characters.relations[]**：**source_id**、**target_id**（均为 **entities[].id**）；**relation_type**（如 ally/rival/family/debt/secret）；可选 **visibility**、**notes**。\n\n" +
    "若你准备给出可机读补丁，请在回复**文末**用单个 **```json** 代码块给出根对象 `{ \"characters\": { ... } }`。";

  function fillCharChatPromptTemplate(text, { mode = "replace", enableCharacterGuide = false } = {}) {
    if (!state.world) {
      toast("请先选择世界");
      return;
    }
    if (enableCharacterGuide) {
      const g = $("guideCharacterRoster");
      if (g) g.checked = true;
    }
    const inp = $("charChatInput");
    if (!inp) return;
    const cur = (inp.value || "").trim();
    if (mode === "append" && cur) inp.value = `${cur}\n\n${text}`;
    else inp.value = text;
    inp.focus();
    if (enableCharacterGuide) toast("已开启「人物卡司」引导，提示已填入输入框");
  }

  function fillChatPromptTemplate(
    text,
    {
      mode = "replace",
      enableAttrGuide = false,
      enableSkillTreeGuide = false,
      enableProfessionGuide = false,
      enableEcologyGuide = false,
      enableEconomyGuide = false,
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
    if (enableEcologyGuide) {
      const e = $("guideEcology");
      if (e) e.checked = true;
    }
    if (enableEconomyGuide) {
      const y = $("guideEconomy");
      if (y) y.checked = true;
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
    else if (enableEcologyGuide) toast("已开启「生态与生境」引导，提示已填入输入框");
    else if (enableEconomyGuide) toast("已开启「经济系统」引导，提示已填入输入框");
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
    ["forest", "写生态", ECOLOGY_CHAT_PROMPT, { ecologyGuide: true, append: true }],
    ["payments", "写经济", ECONOMY_CHAT_PROMPT, { economyGuide: true, append: true }],
    ["diamond", "写物品品质", ITEM_QUALITY_CHAT_PROMPT],
    [
      "diversity_3",
      "文化·宗教",
      "请根据当前世界设定，补充或修订「文化 / 宗教」（对应 world.json 的 cultures 节）。请用自然语言说明：总览氛围；若有多条传统或教团，请分别给出名称、是民俗共同体还是宗教组织（或二者融合）、核心观念或教义、主要仪式/节日/禁忌、圣地或中心、关键人物；若彼此有影响、冲突或融合，请说明关系。若有与现有派系、地理的挂钩，请点名对应势力或地区。输出需便于我随后用「对话后同步」写入 cultures。",
    ],
    ["groups", "写派系", FACTIONS_CHAT_PROMPT],
    [
      "person",
      "派系要人",
      FACTION_KEY_PEOPLE_CHAT_PROMPT,
    ],
    ["history_edu", "写历史", "请写一条重大历史事件及后果，并挂钩现有派系。"],
  ];
  const chipBox = $("promptChips");
  if (chipBox)
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
          enableEcologyGuide: !!meta.ecologyGuide,
          enableEconomyGuide: !!meta.economyGuide,
        });
      });
      chipBox.appendChild(b);
    });

  const charChipBox = $("charPromptChips");
  const storyChipBox = $("storyPromptChips");
  if (storyChipBox) {
    const storyChips = [
      [
        "list_alt",
        "全书粗纲",
        "请根据当前 world.json 与卡司，输出全书粗纲（Markdown），并用 ```story-macro 代码块包裹正文以便一键写入。",
      ],
      [
        "format_list_numbered",
        "本章细纲",
        "请为当前选中章节撰写细纲（Markdown），用 ```story-beat:<chapter_id> 代码块，id 与 chapters 一致。",
      ],
      [
        "linear_scale",
        "伏笔表",
        "请建议 5～8 条伏笔：每条说明 label、planted_chapter_id、payoff_chapter_id、status；便于同步进 story.foreshadowing。",
      ],
      [
        "draw",
        "本章正文",
        "请撰写当前章正文（Markdown），用 ```story-manuscript:<chapter_id> 代码块；人称与 POV 对齐 story.narrator。",
      ],
    ];
    storyChips.forEach((row) => {
      const [glyph, label, text] = row;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip-btn";
      b.innerHTML = `<span class="ms chip-glyph" aria-hidden="true">${glyph}</span>${label}`;
      b.addEventListener("click", () => fillStoryChatPromptTemplate(text));
      storyChipBox.appendChild(b);
    });
  }

  if (charChipBox) {
    const charChips = [
      ["groups", "对齐派系 id", "请列出当前 world.json 中已有 **factions.entities[].id** 与 **geography.regions[].id**，据此设计 3～6 名主要人物：每人给出建议 **id**、**name**、**cast_role**、**faction_ids[]**、**home_region_id**、**one_line_hook**，并说明与现有派系/区域如何挂钩。"],
      ["family_history", "人物关系边", "在已有或拟新增的 **characters.entities[]** 上，补充 **characters.relations[]**：每条 **source_id**、**target_id**、**relation_type**、**notes**；关系要有戏剧功能（债务、秘密、家族、对立、同盟）。"],
      ["military_tech", "主角团张力", "请设计 **cast_role** 为 **protagonist_core** 的主角团（3～5 人）：写清每人 **notable_skills[]**（叙事向短句）、内在目标冲突，以及他们为何被迫同行。"],
      ["person_alert", "反派与压力", "请增加或修订 **antagonist** 与 **supporting_major**：每人 **one_line_hook**、与主角团的 **relations**（rival/debt/secret 等），并挂钩 **history** 或 **factions**。"],
      ["auto_stories", "卡司总览", CHARACTER_ROSTER_CHAT_PROMPT, { charGuide: true, append: false }],
    ];
    charChips.forEach((row) => {
      const [glyph, label, text] = row;
      const meta = row.length > 3 && row[3] ? row[3] : {};
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip-btn";
      b.innerHTML = `<span class="ms chip-glyph" aria-hidden="true">${glyph}</span>${label}`;
      b.addEventListener("click", () => {
        fillCharChatPromptTemplate(text, {
          mode: meta.append ? "append" : "replace",
          enableCharacterGuide: !!meta.charGuide,
        });
      });
      charChipBox.appendChild(b);
    });
  }

  initStoryPanelBindings();
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

function renderCharMessages() {
  const box = $("charMessages");
  if (!box) return;
  box.innerHTML = "";
  for (const m of state.charMessages) {
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
