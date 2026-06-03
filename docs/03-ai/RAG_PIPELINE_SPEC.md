# RAG 流水线规范

## 概述

RAG（检索增强生成）流水线负责知识库文档摄入、向量索引和检索增强问答。该流水线跨越 `domain/knowledge/` 和 `infra/vector_store/` 层。

## 流水线架构 — [TBD: filled by F15a/F15b]

```
User Query
    ↓
Intent Classification (→ RAG intent)
    ↓
┌─────────────────────────────────┐
│         RAG Pipeline            │
│                                 │
│  1. Query Preprocessing         │
│  2. Vector Retrieval             │
│  3. Context Assembly             │
│  4. Prompt Construction          │
│  5. LLM Generation               │
│  6. Citation Extraction          │
│                                 │
└─────────────────────────────────┘
    ↓
RAG Response (answer + citations)
```

## 文档摄入 — [TBD: filled by F15a]

### 流水线流程

```
Upload Markdown Document
    ↓
Parse into chunks (heading-aware splitting)
    ↓
Generate embeddings (via LLM Gateway)
    ↓
Store in Qdrant (with metadata: collection, doc_type, source, tag, uploader, doc_id)
    ↓
Return document ID
```

### 分块策略 — [TBD: filled by F15a]

- 仅支持 Markdown 文档
- 4 种可配置分块策略：

| 策略 | 键名 | 参数 |
|------|------|------|
| 固定长度 + 重叠 | `fixed_overlap` | `chunk_size`（默认 500），`overlap`（默认 50） |
| 分隔符 + 最大长度 | `delimiter_max` | `delimiters`（默认 ["\n\n", "\n"]），`max_chunk_size`（默认 1000） |
| 语义分块 | `semantic` | `similarity_threshold`（默认 0.85） |
| 段落分块 | `paragraph` | `min_paragraph_chars`（默认 50） |

### 父子分块模式 — [TBD: filled by F15a]

所有 4 种分块策略均支持通过 `enable_parent_child=true` 启用可选的父子模式：

- **子分块**：细粒度分块，用于精确匹配（使用所选 `chunking_strategy`）
- **父分块**：粗粒度分块，提供完整上下文（始终使用 `fixed_overlap` 配合 `parent_chunk_params`）

每个子分块存储 `parent_id` 指向其父分块。检索时，匹配到子分块会自动返回父分块内容。

### 分块元数据 — [TBD: filled by F15a]

```python
class ChunkMetadata:
    doc_id: str              # Source document ID
    collection: str          # Qdrant collection name
    doc_type: str            # Document type (类型)
    source: str              # Document origin (来源)
    tag: str                 # Document tag (标签)
    uploader: str            # Uploader identifier
    heading: str             # Heading text
    heading_level: int       # H1=1, H2=2, etc.
    source_file: str         # Original filename
    chunk_index: int         # Chunk position in document
    is_parent: bool          # True = parent chunk, False = child chunk
    parent_id: str | None    # Child: points to parent chunk ID; Parent: None
```

## 向量检索 — [TBD: filled by F05, F15b]

### 查询流程

```
User Query Text
    ↓
Embed query (via LLM Gateway — embedding model)
    ↓
Search Qdrant (with filters)
    ↓
Return top-K chunks with scores
```

### 过滤 — [TBD: filled by F15b]

Qdrant 查询支持多维过滤：

```python
class RetrievalFilter:
    collection: str | None         # Filter by collection name
    doc_type: str | None           # Filter by type (类型)
    source: str | None             # Filter by origin (来源)
    tag: str | None                # Filter by tag (标签)
    uploader: str | None           # Filter by uploader
    score_threshold: float = 0.5  # Minimum similarity score
    limit: int = 5                 # Max number of results
```

### 检索策略 — [TBD: filled by F15b]

| 策略 | 键名 | 描述 |
|------|------|------|
| 关键词 | `keyword` | 稀疏向量 / 全文搜索 |
| 相似度 | `similarity` | 稠密向量搜索 |
| 混合 | `hybrid` | 关键词 + 相似度组合（默认） |
| RRF | `rrf` | 倒数排名融合 |

可通过 `enable_rerank` 参数可选启用重排序。

### 混合搜索 — [TBD: filled by F05]

同时支持稠密（语义）和稀疏（关键词）向量检索：

- 稠密：嵌入模型生成稠密向量
- 稀疏：BM25/稀疏向量进行关键词匹配
- 结果通过倒数排名融合（RRF）合并

## 上下文组装 — [TBD: filled by F15b]

检索后，为 LLM 组装上下文：

```python
class RAGContext:
    query: str                    # Original user query
    retrieved_chunks: list[Chunk] # Top-K relevant chunks
    system_prompt: str             # RAG system prompt template
    max_context_tokens: int        # Token budget for context
```

1. 格式化每个分块并附来源引用标记
2. 若总上下文超出 token 预算则截断
3. 注入到包含 `{context}` 和 `{question}` 变量的提示模板中

## 提示构造 — [TBD: filled by F15b]

RAG 提示模板从 `prompts/rag/` 加载：

```markdown
# prompts/rag/system.md
You are a knowledge assistant. Answer the user's question based on the provided context.

Context:
{context}

If the context does not contain sufficient information, say so honestly.
Always cite your sources using [citation:N] format.

# prompts/rag/user.md
{question}
```

模板由 `services/prompt_manager/` 加载并通过变量替换渲染。

## LLM 生成 — [TBD: filled by F15b]

- 使用 LLM Gateway，`task_type="rag_merge"`
- 支持流式和非流式响应
- Token 用量被跟踪和记录
- 并发由 LLM 信号量控制

## 引用提取 — [TBD: filled by F15b]

```python
class Citation:
    chunk_id: str       # Qdrant point ID
    doc_id: str         # Source document ID
    source_file: str    # Original filename
    heading: str        # Heading text
    score: float        # Similarity score
    text_snippet: str   # Relevant text excerpt
```

引用从 LLM 响应中提取并匹配回已检索的分块。

## API 集成 — [TBD: filled by F15a/F15b]

| 端点 | 方法 | 描述 |
|------|------|------|
| /api/v1/kb/collections | POST | 创建集合 |
| /api/v1/kb/collections | GET | 列出集合 |
| /api/v1/kb/collections/{name} | DELETE | 删除集合 |
| /api/v1/kb/collections/{name}/documents | POST | 上传文档（多部分表单，异步） |
| /api/v1/kb/collections/{name}/documents | GET | 列出/搜索文档 |
| /api/v1/kb/collections/{name}/documents | DELETE | 删除文档（批量/清空需 confirm_token） |
| /api/v1/kb/query | POST | RAG 查询，可配置检索策略 |

## 错误码 — [TBD: filled by F15b]

| 错误码 | 名称 | 描述 |
|--------|------|------|
| 3001 | RAG_COLLECTION_NOT_FOUND | 集合不存在 |
| 3002 | RAG_RETRIEVAL_FAILED | 向量检索查询失败 |
| 3003 | RAG_NO_RESULTS | 未找到相关文档 |
| 3004 | RAG_GENERATION_FAILED | LLM 回答生成失败 |
| 3005 | RAG_INDEXING_FAILED | 文档索引失败 |
| 3006 | RAG_DOCUMENT_NOT_FOUND | 文档不存在 |

[TBD: filled by work orders F05, F15a/F15b]