"""本地向量索引：章节手稿、world.md、人物卡的分块、embedding 与语义检索。

依赖 chromadb，embedding 优先使用本地 sentence-transformers 模型，
若不可用则回退到 OpenAI-compatible embedding API（复用 Paratera API）。
索引存储在 story/rag_index/ 下。
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_NAME = os.environ.get("MCW_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
_CHUNK_MAX_CHARS = 600
_CHUNK_OVERLAP_CHARS = 80
_SCENE_TARGET_CHARS = 1600
_SCENE_MAX_CHARS = 2200
_SCENE_MIN_CHARS = 260
_SCENE_BOUNDARY_RE = re.compile(
    r"^\s*(?:"
    r"#{1,4}\s+.+|"
    r"第[一二三四五六七八九十百千万\d]+[场幕节]\b.*|"
    r"[【\[]\s*(?:场景|镜头|Scene|SCENE)\s*[\]】].*|"
    r"(?:-{3,}|\*{3,}|={3,})\s*$"
    r")"
)

_model = None
_use_api_fallback = False
_embedding_dim = 512  # bge-small-zh 默认维度；API 模式运行时动态调整


def _embedding_backend_mode() -> str:
    """local | api | auto（默认 auto：无缓存则不走 HuggingFace）。"""
    return os.environ.get("MCW_EMBEDDING_BACKEND", "auto").strip().lower()


def _apply_hf_env() -> None:
    """可选镜像，例如 MCW_HF_ENDPOINT=https://hf-mirror.com"""
    endpoint = os.environ.get("MCW_HF_ENDPOINT", "").strip()
    if endpoint:
        os.environ["HF_ENDPOINT"] = endpoint.rstrip("/")


def _model_cached(model_name: str) -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache

        for filename in ("config.json", "modules.json", "tokenizer_config.json"):
            if try_to_load_from_cache(model_name, filename) is not None:
                return True
        return False
    except Exception:
        return False


def _should_skip_local_download() -> bool:
    mode = _embedding_backend_mode()
    if mode == "api":
        return True
    if mode == "local":
        return False
    # auto：未下载过则不要连 huggingface.co（避免 WinError 10060 长时间重试）
    return not _model_cached(_MODEL_NAME)


def _get_local_model() -> "SentenceTransformer":
    """尝试加载本地 sentence-transformers 模型。失败抛出异常。"""
    global _model, _embedding_dim
    if _model is None:
        if _should_skip_local_download():
            raise RuntimeError(
                f"跳过 HuggingFace 下载（模型 {_MODEL_NAME} 未在本地缓存）。"
                "可设置 MCW_EMBEDDING_BACKEND=api 使用在线 embedding，"
                "MCW_HF_ENDPOINT=https://hf-mirror.com 使用镜像，"
                "或 MCW_EMBEDDING_BACKEND=local 强制从 Hub 下载。"
            )
        _apply_hf_env()
        user_local_only = os.environ.get("MCW_EMBEDDING_LOCAL_FILES_ONLY", "").lower() in (
            "1", "true", "yes",
        )
        mode = _embedding_backend_mode()
        force_local_only = user_local_only or (mode == "auto" and _model_cached(_MODEL_NAME))
        # 必须在 import sentence_transformers 之前设置 HF_HUB_OFFLINE，
        # 否则 huggingface_hub 在 import 时就会初始化在线客户端。
        prev_offline = os.environ.get("HF_HUB_OFFLINE")
        try:
            if force_local_only:
                os.environ["HF_HUB_OFFLINE"] = "1"
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(_MODEL_NAME, local_files_only=force_local_only)
        finally:
            if prev_offline is None:
                os.environ.pop("HF_HUB_OFFLINE", None)
            else:
                os.environ["HF_HUB_OFFLINE"] = prev_offline
        _embedding_dim = _model.get_embedding_dimension()
    return _model


def _embed_via_api(texts: list[str]) -> list[list[float]]:
    """通过 OpenAI-compatible embedding API 获取向量。"""
    from worldforger.config import get_settings

    settings = get_settings()
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.paratera_api_key,
        base_url=settings.openai_api_base,
    )
    resp = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    global _embedding_dim
    embeds = [d.embedding for d in resp.data]
    if embeds:
        _embedding_dim = len(embeds[0])
    return embeds


def _embed_texts(texts: list[str]) -> list[list[float]]:
    """获取文本的 embedding 向量。优先本地模型，回退 API。"""
    global _use_api_fallback
    if not texts:
        return []
    if not _use_api_fallback:
        try:
            model = _get_local_model()
            return model.encode(texts, normalize_embeddings=True).tolist()
        except Exception as exc:
            logger.warning(
                "本地 embedding 不可用，回退到 API 模式（%s）",
                exc,
            )
            _use_api_fallback = True
    try:
        return _embed_via_api(texts)
    except Exception:
        logger.exception("API embedding 也失败，无法获取向量")
        raise


def _embed_query_text(query: str) -> list[float]:
    """获取单条查询的 embedding。bge 模型会自动加前缀。"""
    global _use_api_fallback
    if not query.strip():
        return []
    if not _use_api_fallback:
        try:
            model = _get_local_model()
            return model.encode(
                [f"为这个句子生成表示以用于检索相关文章：{query}"],
                normalize_embeddings=True,
            ).tolist()[0]
        except Exception:
            logger.warning("本地 embedding 模型不可用，回退到 API 模式")
            _use_api_fallback = True
    embeds = _embed_via_api([query])
    return embeds[0] if embeds else []


def get_embedding_dim() -> int:
    """返回当前 embedding 维度。"""
    global _embedding_dim
    global _use_api_fallback
    # 尝试获取实际维度
    if _embedding_dim == 512 and _use_api_fallback:
        try:
            test_embed = _embed_texts(["test"])
            if test_embed:
                _embedding_dim = len(test_embed[0])
        except Exception:
            pass
    return _embedding_dim


def _story_dir(world_id: str) -> Path:
    from worldforger.story.story_store import story_dir

    return story_dir(world_id)


def rag_index_dir(world_id: str) -> Path:
    return _story_dir(world_id) / "rag_index"


def _book_summary_path(world_id: str) -> Path:
    return _story_dir(world_id) / "book_summary.json"


class ChapterIndexer:
    """管理单个世界的向量索引（章节手稿 + world.md + 人物卡）。"""

    _global_clients: dict[str, "chromadb.PersistentClient"] = {}

    def __init__(self, world_id: str):
        self.world_id = world_id
        self._index_dir = rag_index_dir(world_id)

    # ── client / collection (lazy, cached) ──

    def _get_client(self) -> "chromadb.PersistentClient":
        import chromadb
        if self.world_id not in self._global_clients:
            self._index_dir.mkdir(parents=True, exist_ok=True)
            self._global_clients[self.world_id] = chromadb.PersistentClient(path=str(self._index_dir))
        return self._global_clients[self.world_id]

    @classmethod
    def close_world(cls, world_id: str) -> None:
        """Close and release the ChromaDB client for a world (frees file locks)."""
        client = cls._global_clients.pop(world_id, None)
        if client is not None:
            try:
                client._system.stop()  # chromadb >= 0.4
            except Exception:
                try:
                    client._admin_client._server.stop()  # older chromadb
                except Exception:
                    pass
        import gc
        gc.collect()

    @property
    def _collection(self):
        return self._get_client().get_or_create_collection(
            name="narrative_chunks",
            metadata={"hnsw:space": "cosine"},
        )

    # ── chunking ──

    @staticmethod
    def _chunk_text(text: str, max_chars: int = _CHUNK_MAX_CHARS) -> list[str]:
        """按段落边界分块，保持叙事完整性。"""
        if not text or not text.strip():
            return []
        paragraphs = text.split("\n\n")
        chunks: list[str] = []
        current = ""
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            if len(current) + len(para) > max_chars and current:
                chunks.append(current.strip())
                # overlap: 保留最后一段作为上下文衔接
                overlap = current[-_CHUNK_OVERLAP_CHARS:] if len(current) > _CHUNK_OVERLAP_CHARS else ""
                current = overlap + para if overlap else para
            else:
                current += "\n\n" + para if current else para
        if current.strip():
            chunks.append(current.strip())
        return chunks

    @staticmethod
    def _split_explicit_scenes(text: str) -> list[tuple[str, str]]:
        """Split by visible scene headings/separators while keeping headings."""
        scenes: list[tuple[str, str]] = []
        current: list[str] = []
        boundary = "implicit"
        for raw_line in text.splitlines():
            line = raw_line.rstrip()
            is_boundary = bool(_SCENE_BOUNDARY_RE.match(line))
            if is_boundary and current and "\n".join(current).strip():
                scenes.append(("\n".join(current).strip(), boundary))
                current = []
                boundary = "explicit"
            current.append(line)
            if is_boundary:
                boundary = "explicit"
        if current and "\n".join(current).strip():
            scenes.append(("\n".join(current).strip(), boundary))
        return scenes

    @classmethod
    def _split_long_scene(cls, scene: str, *, max_chars: int = _SCENE_MAX_CHARS) -> list[str]:
        """Split an oversized scene on paragraph boundaries without tiny shards."""
        if len(scene) <= max_chars:
            return [scene.strip()] if scene.strip() else []
        chunks: list[str] = []
        current = ""
        for para in re.split(r"\n\s*\n", scene):
            para = para.strip()
            if not para:
                continue
            if len(para) > max_chars:
                if current.strip():
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(cls._chunk_text(para, max_chars=max_chars))
                continue
            if current and len(current) + len(para) + 2 > max_chars:
                chunks.append(current.strip())
                current = para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current.strip():
            chunks.append(current.strip())
        return chunks

    @classmethod
    def _scene_chunks(
        cls,
        text: str,
        *,
        target_chars: int = _SCENE_TARGET_CHARS,
        max_chars: int = _SCENE_MAX_CHARS,
    ) -> list[dict]:
        """Build LongRAG scene-level chunks from a chapter manuscript.

        Prefer explicit Markdown/Chinese scene boundaries.  If a manuscript has
        no visible scene marks, merge paragraphs into longer complete units
        instead of fixed 500-600 char shards.
        """
        if not text or not text.strip():
            return []
        explicit = cls._split_explicit_scenes(text)
        has_explicit = any(boundary == "explicit" for _, boundary in explicit)
        scene_texts: list[tuple[str, str]] = []

        if has_explicit:
            scene_texts = explicit
        else:
            current = ""
            for para in re.split(r"\n\s*\n", text):
                para = para.strip()
                if not para:
                    continue
                if current and len(current) + len(para) + 2 > target_chars:
                    scene_texts.append((current.strip(), "paragraph_group"))
                    current = para
                else:
                    current = f"{current}\n\n{para}" if current else para
            if current.strip():
                scene_texts.append((current.strip(), "paragraph_group"))

        chunks: list[dict] = []
        for scene_index, (scene, boundary) in enumerate(scene_texts):
            for part_index, part in enumerate(cls._split_long_scene(scene, max_chars=max_chars)):
                chunks.append({
                    "text": part,
                    "unit_type": "scene",
                    "scene_index": scene_index,
                    "scene_part": part_index,
                    "boundary": boundary,
                    "chars": len(part),
                })
        return chunks

    @classmethod
    def debug_chunk_plan(cls, text: str) -> dict:
        """Return chunking diagnostics without touching the vector store."""
        scenes = cls._scene_chunks(text)
        return {
            "strategy": "scene_longrag",
            "scene_chunks": len(scenes),
            "total_chars": len(text or ""),
            "chunks": scenes,
        }

    # ── embedding ──

    def _embed(self, texts: list[str]) -> list[list[float]]:
        return _embed_texts(texts)

    def _embed_query(self, query: str) -> list[float]:
        return _embed_query_text(query)

    # ── index ──

    def index_chapter(self, chapter_id: str, manuscript_text: str, metadata: dict | None = None) -> int:
        """将章节手稿按场景级长块写入向量索引。返回新增 chunk 数。"""
        if not manuscript_text.strip():
            return 0
        meta = dict(metadata or {})
        meta.setdefault("source_type", "manuscript")
        meta["chapter_id"] = chapter_id
        scene_chunks = self._scene_chunks(manuscript_text)
        if not scene_chunks:
            return 0
        chunks = [c["text"] for c in scene_chunks]
        embeddings = self._embed(chunks)
        ids = [f"scene_{chapter_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            dict(
                meta,
                chunk_index=i,
                unit_type="scene",
                scene_index=scene_chunks[i]["scene_index"],
                scene_part=scene_chunks[i]["scene_part"],
                scene_boundary=scene_chunks[i]["boundary"],
                chars=scene_chunks[i]["chars"],
            )
            for i in range(len(chunks))
        ]
        self._collection.add(embeddings=embeddings, documents=chunks, ids=ids, metadatas=metadatas)
        logger.info("indexed %d scene chunks for chapter %s", len(chunks), chapter_id)
        return len(chunks)

    def index_world_md(self, world_md_text: str) -> int:
        """将 world.md 按 ## 章节分块索引。返回新增 chunk 数。"""
        if not world_md_text.strip():
            return 0
        sections = re.split(r"\n(?=## )", world_md_text)
        total = 0
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            # 从 section 标题提取名称
            title_match = re.match(r"^##\s+(.+)", sec)
            section_name = title_match.group(1).strip() if title_match else "world_overview"
            chunks = self._chunk_text(sec)
            if not chunks:
                continue
            embeddings = self._embed(chunks)
            ids = [f"wb_{_slug(section_name)}_{i}" for i in range(len(chunks))]
            metadatas = [
                {"source_type": "world_md", "section": section_name, "chunk_index": i}
                for i in range(len(chunks))
            ]
            self._collection.add(embeddings=embeddings, documents=chunks, ids=ids, metadatas=metadatas)
            total += len(chunks)
        logger.info("indexed %d world.md chunks", total)
        return total

    def index_characters(self, characters_section: list[dict]) -> int:
        """将人物卡分别序列化并索引。返回新增 chunk 数。"""
        import json

        total = 0
        for ent in characters_section:
            if not isinstance(ent, dict):
                continue
            char_id = str(ent.get("id", ""))
            if not char_id:
                continue
            # 构建人物摘要文本
            parts = [
                f"角色：{ent.get('name', '')}",
                f"别名：{ent.get('aliases', '')}" if ent.get("aliases") else "",
                f"身份：{ent.get('cast_role', '')}",
            ]
            rs = ent.get("runtime_state")
            if isinstance(rs, dict):
                parts.append(
                    f"位置：{rs.get('current_location', '')}，"
                    f"目标：{rs.get('current_goal', '')}，"
                    f"情绪：{rs.get('emotional_state', '')}"
                )
            notes = ent.get("notes", "")
            if notes:
                parts.append(f"备注：{notes[:1500]}")
            text = "\n".join(p for p in parts if p)
            if not text.strip():
                continue
            # 单个人物通常在一 chunk 内
            chunks = self._chunk_text(text, max_chars=1200)
            embeddings = self._embed(chunks)
            ids = [f"char_{char_id}_{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "source_type": "character",
                    "character_id": char_id,
                    "character_name": ent.get("name", ""),
                    "chunk_index": i,
                }
                for i in range(len(chunks))
            ]
            self._collection.add(embeddings=embeddings, documents=chunks, ids=ids, metadatas=metadatas)
            total += len(chunks)
        logger.info("indexed %d character chunks", total)
        return total

    def index_all(self, world) -> int:
        """全量索引：所有章节手稿 + world.md + 人物卡。返回总 chunk 数。"""
        from worldforger.story.story_store import manuscript_path, read_text
        from worldforger.world_store import load_world_markdown_optional, world_root

        total = 0
        # 章节手稿
        for ch in world.story.chapters:
            text = read_text(manuscript_path(world.meta.id, ch.id))
            if text.strip():
                total += self.index_chapter(ch.id, text, {
                    "chapter_order": ch.order,
                    "chapter_title": ch.title,
                })
        # world.md
        md = load_world_markdown_optional(world.meta.id)
        if md:
            total += self.index_world_md(md)
        # 人物卡
        chars = world.characters.entities if hasattr(world.characters, 'entities') else world.characters.get('entities', [])
        if chars:
            total += self.index_characters(chars)
        logger.info("index_all: %d total chunks for world %s", total, world.meta.id)
        return total

    # ── remove ──

    def remove_chapter(self, chapter_id: str) -> int:
        """删除指定章节的所有 chunk。返回删除数量。"""
        results = self._collection.get(
            where={"chapter_id": chapter_id},
            include=[],
        )
        ids_to_delete = results.get("ids", [])
        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
        logger.info("removed %d chunks for chapter %s", len(ids_to_delete), chapter_id)
        return len(ids_to_delete)

    def clear_all(self) -> int:
        """清空此世界所有索引。返回删除数量。"""
        results = self._collection.get(include=[])
        ids = results.get("ids", [])
        if ids:
            self._collection.delete(ids=ids)
        logger.info("cleared %d chunks for world %s", len(ids), self.world_id)
        return len(ids)

    # ── retrieve ──

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        *,
        exclude_chapter_id: str | None = None,
        source_types: list[str] | None = None,
    ) -> list[dict]:
        """语义检索最相关的 chunk。

        Args:
            query: 检索 query 文本
            top_k: 返回数量
            exclude_chapter_id: 排除指定章节（避免检索到本章自身）
            source_types: 限定来源类型，如 ["manuscript", "character", "world_md"]

        Returns:
            [{chunk_id, document, metadata, distance}, ...]
        """
        if not query.strip():
            return []
        where = {}
        conditions: list[dict] = []
        if exclude_chapter_id:
            conditions.append({"chapter_id": {"$ne": exclude_chapter_id}})
        if source_types:
            conditions.append({"source_type": {"$in": source_types}})
        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}

        q_embedding = self._embed_query(query)
        if not q_embedding:
            return []

        try:
            results = self._collection.query(
                query_embeddings=[q_embedding],
                n_results=min(top_k * 2, 20),
                where=where if where else None,
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            logger.exception("ChromaDB query failed")
            return []

        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        out = []
        for i in range(len(ids)):
            meta = metas[i] if i < len(metas) else {}
            doc = docs[i] if i < len(docs) else ""
            dist = dists[i] if i < len(dists) else 1.0
            out.append({
                "chunk_id": ids[i],
                "document": doc,
                "metadata": meta,
                "distance": dist,
            })

        out.sort(key=lambda x: x["distance"])
        return out[:top_k]

    def retrieve_for_chapter(
        self,
        chapter_id: str,
        *,
        beat_text: str = "",
        character_ids: list[str] | None = None,
        foreshadowing_ids: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """为指定章节构建检索 query 并检索相关前文。

        组合查询来源：节拍大纲关键词 + 出场人物名 + 待推进伏笔 ID。
        """
        from worldforger.world_store import load_world

        queries: list[str] = []

        # 从 beat 中提取关键场景描述（取前 800 字作为 query）
        if beat_text.strip():
            queries.append(beat_text.strip()[:800])

        # 人物名精确匹配
        if character_ids:
            try:
                world = load_world(self.world_id)
                names = []
                for ent in world.characters.entities:
                    if isinstance(ent, dict) and ent.get("id") in character_ids:
                        names.append(ent.get("name", ""))
                if names:
                    queries.append(" ".join(names))
            except Exception:
                pass

        # 伏笔关键词
        if foreshadowing_ids:
            queries.append(" ".join(foreshadowing_ids))

        combined_query = " ".join(queries)

        if not combined_query.strip():
            return []

        return self.retrieve(
            combined_query,
            top_k=top_k,
            exclude_chapter_id=chapter_id,
            source_types=["manuscript", "character", "world_md"],
        )

    def retrieve_for_chapter_debug(
        self,
        chapter_id: str,
        *,
        beat_text: str = "",
        character_ids: list[str] | None = None,
        foreshadowing_ids: list[str] | None = None,
        top_k: int = 5,
    ) -> dict:
        """Retrieve with diagnostics for LongRAG panels/tests."""
        results = self.retrieve_for_chapter(
            chapter_id,
            beat_text=beat_text,
            character_ids=character_ids,
            foreshadowing_ids=foreshadowing_ids,
            top_k=top_k,
        )
        return {
            "chapter_id": chapter_id,
            "strategy": "scene_longrag",
            "beat_query_chars": len((beat_text or "").strip()[:800]),
            "character_ids": list(character_ids or []),
            "foreshadowing_ids": list(foreshadowing_ids or []),
            "top_k": top_k,
            "result_count": len(results),
            "results": [
                {
                    "chunk_id": r.get("chunk_id", ""),
                    "unit_type": (r.get("metadata") or {}).get("unit_type", ""),
                    "source_type": (r.get("metadata") or {}).get("source_type", ""),
                    "chars": len(r.get("document", "") or ""),
                    "distance": r.get("distance", 1.0),
                }
                for r in results
            ],
        }

    # ── stats ──

    def get_stats(self) -> dict:
        """返回索引统计信息。"""
        try:
            results = self._collection.get(include=["metadatas"])
            metas = results.get("metadatas", [])
            total = len(metas)
            chapter_ids = set()
            source_counts: dict[str, int] = {}
            unit_counts: dict[str, int] = {}
            for m in metas:
                if isinstance(m, dict):
                    cid = m.get("chapter_id", "")
                    if cid:
                        chapter_ids.add(cid)
                    st = m.get("source_type", "unknown")
                    source_counts[st] = source_counts.get(st, 0) + 1
                    unit = m.get("unit_type") or ("chunk" if st == "manuscript" else st)
                    unit_counts[unit] = unit_counts.get(unit, 0) + 1
            return {
                "total_chunks": total,
                "indexed_chapters": len(chapter_ids),
                "chapter_ids": sorted(chapter_ids),
                "source_counts": source_counts,
                "unit_counts": unit_counts,
            }
        except Exception:
            return {"total_chunks": 0, "indexed_chapters": 0, "chapter_ids": [], "source_counts": {}, "unit_counts": {}}


def _slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", s).strip("_")[:40]
