# Qdrant 集合配置

## 概述

本文档定义了知识库系统的 Qdrant 向量存储配置。系统支持多集合，具有可配置的类型、类别以及混合检索（稠密 + 稀疏向量）。

## 多集合架构 — [filled by F05]

### 集合管理

- 集合在 `configs/default.yaml` 的 `qdrant.collections` 下定义
- 启动时，系统自动创建配置中声明但尚不存在的集合
- 可通过 API 动态创建/删除集合
- 每个集合独立，拥有自己的向量配置

### 默认集合 — [filled by F05]

```yaml
qdrant:
  url: http://localhost:6333
  collections:
    - name: "general"
      description: "通用知识库"
      vector_dim: 1024
      distance: "Cosine"
      sparse_vectors: true
      payload_indexes:
        - field: "doc_type"
          type: "keyword"
        - field: "source"
          type: "keyword"
        - field: "tag"
          type: "keyword"
        - field: "uploader"
          type: "keyword"
        - field: "doc_id"
          type: "keyword"

    - name: "safety"
      description: "安全隐患文档库"
      vector_dim: 1024
      distance: "Cosine"
      sparse_vectors: true
      payload_indexes:
        - field: "doc_type"
          type: "keyword"
        - field: "source"
          type: "keyword"
        - field: "tag"
          type: "keyword"
        - field: "uploader"
          type: "keyword"
        - field: "doc_id"
          type: "keyword"
```

## 向量配置 — [filled by F05]

### 稠密向量

| 参数 | 默认值 | 说明 |
|-----------|---------|------|
| vector_dim | 1024 | 稠密嵌入维度 |

支持的嵌入模型（通过 LLM Gateway 配置）：

| 模型 | 维度 | 任务类型 |
|-------|-----------|----------|
| text-embedding-v3 | 1024 | 文本嵌入（qwen_cloud，默认） |
| bge-large-zh-v1.5 | 1024 | 本地嵌入（vLLM 降级） |

### 稀疏向量 — [filled by F05]

稀疏向量使用 BM25 风格的词项向量实现关键词级别匹配：

- 每个集合通过 `sparse_vectors: true` 启用
- 稀疏向量字段名：`"bm25"`（与 `configs/default.yaml` 的 `sparse_vector_name` 一致）
- 使用分词 + 词频生成
- 在混合检索中使用倒数排名融合（RRF）

### 混合检索 — [filled by F05]

```
Query
  ↓
┌─────────────┐
│ Dense Search │  → Top-K 稠密结果（语义相似度）
└─────────────┘
  ↓
┌─────────────┐
│ Sparse Search│  → Top-K 稀疏结果（关键词匹配）
└─────────────┘
  ↓
┌─────────────┐
│ RRF Fusion  │  → 合并排序
└─────────────┘
  ↓
Final Results
```

倒数排名融合公式：

```
score(d) = Σ (1 / (k + rank_i(d)))
where k = 60 (default RRF constant)
```

## 负载模式 — [filled by F05]

每个 Qdrant 点具有以下负载：

```python
class PointPayload:
    doc_id: str              # 来源文档标识符
    collection: str          # 集合名称
    doc_type: str            # 文档类型 (类型)
    source: str              # 文档来源 (来源)
    tag: str                 # 文档标签 (标签)
    uploader: str            # 上传者标识符
    heading: str             # 章节标题
    heading_level: int        # H1=1, H2=2, 等
    source_file: str          # 原始 Markdown 文件名
    chunk_index: int          # 文档中的分块位置
    text: str                 # 分块文本内容
    is_parent: bool           # True = 父分块, False = 子分块
    parent_id: str | None     # 子分块：指向父分块 ID；父分块：None
```

### 可配置维度 — [TBD: filled by F15a]

`doc_type`、`source` 和 `tag` 是可配置维度，不在代码中硬编码：

```yaml
qdrant:
  type_dimensions:
    - name: "doc_type"
      values: ["技术文档", "手册", "FAQ"]
    - name: "source"
      values: ["内部", "外部", "爬取"]
    - name: "tag"
      values: ["重要", "已审核", "草稿"]
```

这些维度用于：
- Qdrant 中的负载索引（用于过滤）
- RAG 查询过滤器（将 `doc_type`、`source`、`tag` 作为过滤条件传入）

## 负载索引 — [filled by F05]

为所有可过滤字段创建负载索引：

| 字段 | 索引类型 | 用途 |
|-------|-----------|------|
| `doc_type` | keyword | 按文档类型过滤 (类型) |
| `source` | keyword | 按文档来源过滤 (来源) |
| `tag` | keyword | 按文档标签过滤 (标签) |
| `uploader` | keyword | 按上传者过滤 |
| `doc_id` | keyword | 按来源文档过滤 |
| `is_parent` | keyword | 按父/子分块类型过滤 |
| `parent_id` | keyword | 从子分块查找父分块 |

可在 `configs/default.yaml` 中为每个集合配置额外的索引。

## 集合生命周期 — [filled by F05]

### 启动时自动创建

```python
async def ensure_collections():
    """
    On startup:
    1. Read collection config from configs/default.yaml
    2. For each declared collection:
       a. Check if collection exists in Qdrant
       b. If not: create with configured vector size, distance, sparse vectors, payload indexes
       c. If exists: verify configuration matches (log warning if mismatch)
    """
```

### 通过 API 动态创建

```python
POST /api/v1/kb/collections
{
  "name": "custom_collection",
  "description": "Custom knowledge collection",
  "vector_dim": 1024,
  "distance": "Cosine",
  "sparse_vectors": true
}
```

### 删除

```python
DELETE /api/v1/kb/collections/{collection_name}
→ Deletes collection and all its points (irreversible)
```

## 文档操作 — [TBD: filled by F15a/F15b]

### 上传文档

```python
POST /api/v1/kb/collections/{collection_name}/documents
Content-Type: multipart/form-data

file: <markdown file>
doc_type: "技术文档"             # 元数据：类型
source: "内部"                   # 元数据：来源
tag: "已审核"                    # 元数据：标签
uploader: "user1"                # 上传者标识符
chunking_strategy: "fixed_overlap"  # 可选：分块策略
# chunking_params: {...}         # 可选：策略特定参数
```

处理流程：
1. 将 Markdown 解析为分块（使用配置的分块策略）
2. 如果 `enable_parent_child=true`：
   a. 使用 `fixed_overlap` 策略和 `parent_chunk_params` 创建父分块
   b. 使用选定的 `chunking_strategy` 创建子分块
   c. 通过 `parent_id` 将每个子分块链接到其父分块
3. 通过 LLM Gateway 生成稠密嵌入
4. 生成稀疏向量（分词）
5. 将带元数据的点插入 Qdrant
6. 返回 task_id（异步处理）

### 父子分块模式

当 `enable_parent_child=true` 时，文档以两种粒度进行分块：

- **父分块**：粗粒度（默认 2000 字符），提供完整上下文
- **子分块**：细粒度（按选定策略），用于精确匹配

检索行为：匹配子分块 → 查找 `parent_id` → 返回父分块内容及子分块位置信息。

去重：如果文件名 + 上传者 + 集合已存在，返回 HTTP 409。

### 列出/搜索文档

```python
GET /api/v1/kb/collections/{collection_name}/documents?filename=guide&doc_type=技术文档&source=内部&tag=已审核&uploader=user1&limit=20&offset=0
```

### 删除文档

```python
# 两步确认：
# 第 1 步：不带 confirm_token → 返回影响范围 + confirm_token
DELETE /api/v1/kb/collections/{collection_name}/documents?clear_all=true
→ { "affected_documents_count": 42, "confirm_token": "uuid" }

# 第 2 步：带 confirm_token → 执行删除
DELETE /api/v1/kb/collections/{collection_name}/documents?clear_all=true&confirm_token=uuid
→ { "deleted_documents_count": 42 }
```

也支持通过查询参数定向删除：`doc_id`、`doc_type`、`source`、`tag`、`uploader`、`filename`。

### 查询 (RAG)

```python
POST /api/v1/kb/query
{
  "query": "How to handle chemical spills?",
  "collection_names": ["safety"],  # 可选，默认为所有集合
  "doc_type": "regulation",        # 可选过滤器
  "source": "内部",                # 可选过滤器
  "tag": "已审核",                 # 可选过滤器
  "uploader": "user1",            # 可选过滤器
  "retrieval_strategy": "hybrid", # keyword/similarity/hybrid/rrf
  "top_k": 5,
  "score_threshold": 0.5,
  "enable_rerank": false,
  "stream": true
}
```

## 错误码 — [filled by F05]

| 代码 | 名称 | 说明 |
|------|------|------|
| 6001 | KB_UPLOAD_FAILED | 文件上传失败 |
| 6002 | KB_FILENAME_EXISTS | 文件名已存在 |
| 6003 | KB_FILE_NOT_FOUND | 文件未找到 |
| 6004 | KB_FORMAT_UNSUPPORTED | 不支持的文件格式（仅支持 markdown） |
| 6005 | KB_VECTOR_WRITE_FAILED | 向量写入失败 |
| 6006 | KB_CHUNK_LIMIT_EXCEEDED | 分块数量超过 max_chunks 限制 |

> 6xxx 错误码以 `docs/01-architecture/ERROR_CODE.md` 为权威来源，本表与其保持一致。

## Qdrant 客户端配置 — [filled by F05]

实现位于 `app/infra/vector_store/qdrant_store.py`，提供 `QdrantVectorStore` 类：

- 异步客户端：`AsyncQdrantClient`
- 多集合管理：`create_collection` / `delete_collection` / `collection_exists` / `list_collections`
- 向量操作：`upsert_points` / `search` / `hybrid_search` / `search_by_strategy` / `delete_points` / `delete_by_filter` / `scroll_points`
- 检索策略：`similarity`（稠密）、`keyword`（稀疏）、`hybrid`（混合 RRF）、`rrf`
- 配置来源：`configs/default.yaml` 的 `knowledge.collections` 和 `qdrant` 段
- 抽象基类：`app/infra/vector_store/base.py` `VectorStoreBase`
- 错误映射：Qdrant 连接失败 → AI_1202；向量写入失败 → AI_6005