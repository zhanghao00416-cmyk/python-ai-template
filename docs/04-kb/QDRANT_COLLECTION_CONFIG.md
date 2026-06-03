# Qdrant Collection Configuration

## Overview

This document defines the Qdrant vector store configuration for the knowledge base system. The system supports multiple collections with configurable types, categories, and hybrid search (dense + sparse vectors).

## Multi-Collection Architecture — [TBD: filled by F05]

### Collection Management

- Collections are defined in `configs/default.yaml` under `qdrant.collections`
- On startup, the system auto-creates any missing collections declared in config
- Collections can be created/deleted dynamically via API
- Each collection is independent with its own vector configuration

### Default Collections — [TBD: filled by F05]

```yaml
qdrant:
  url: http://localhost:6333
  collections:
    - name: "general"
      description: "General knowledge base"
      vector_size: 1536
      distance: "Cosine"
      sparse_vectors: true
      payload_indexes:
        - field: "doc_type"
          type: "keyword"
        - field: "category"
          type: "keyword"
        - field: "doc_id"
          type: "keyword"

    - name: "safety"
      description: "Safety and hazard documents"
      vector_size: 1536
      distance: "Cosine"
      sparse_vectors: true
      payload_indexes:
        - field: "doc_type"
          type: "keyword"
        - field: "category"
          type: "keyword"
        - field: "doc_id"
          type: "keyword"
```

## Vector Configuration — [TBD: filled by F05]

### Dense Vectors

| Parameter | Default | Description |
|-----------|---------|-------------|
| vector_size | 1536 | Dense embedding dimension |
| distance | Cosine | Distance metric (Cosine, Euclid, Dot) |

Supported embedding models (configured via LLM Gateway):

| Model | Dimensions | Task Type |
|-------|-----------|-----------|
| text-embedding-v3 | 1536 | Text embedding |
| bge-large-zh-v1.5 | 1024 | Local embedding (vLLM) |

### Sparse Vectors — [TBD: filled by F05]

Sparse vectors enable keyword-level matching using BM25-style term vectors:

- Enabled per collection via `sparse_vectors: true`
- Sparse vector field name: `"sparse"`
- Generated using tokenization + term frequency
- Used in hybrid retrieval with Reciprocal Rank Fusion (RRF)

### Hybrid Search — [TBD: filled by F05]

```
Query
  ↓
┌─────────────┐
│ Dense Search │  → Top-K dense results (semantic similarity)
└─────────────┘
  ↓
┌─────────────┐
│ Sparse Search│  → Top-K sparse results (keyword match)
└─────────────┘
  ↓
┌─────────────┐
│ RRF Fusion  │  → Merged ranking
└─────────────┘
  ↓
Final Results
```

Reciprocal Rank Fusion formula:

```
score(d) = Σ (1 / (k + rank_i(d)))
where k = 60 (default RRF constant)
```

## Payload Schema — [TBD: filled by F05]

Each Qdrant point has the following payload:

```python
class PointPayload:
    doc_id: str              # Source document identifier
    collection: str          # Collection name
    doc_type: str            # Document type (类型)
    source: str              # Document origin (来源)
    tag: str                 # Document tag (标签)
    uploader: str            # Uploader identifier
    heading: str             # Section heading
    heading_level: int        # H1=1, H2=2, etc.
    source_file: str          # Original markdown filename
    chunk_index: int          # Chunk position in document
    text: str                 # Chunk text content
    is_parent: bool           # True = parent chunk, False = child chunk
    parent_id: str | None     # Child chunk: points to parent chunk ID; Parent chunk: None
```

### Configurable Dimensions — [TBD: filled by F15a]

`doc_type` and `category` are configurable dimensions, not hardcoded:

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

These dimensions are used for:
- Payload indexes in Qdrant (for filtering)
- RAG query filters (pass `doc_type` and `category` as filter criteria)

## Payload Indexes — [TBD: filled by F05]

Payload indexes are created for all filterable fields:

| Field | Index Type | Purpose |
|-------|-----------|---------|
| `doc_type` | keyword | Filter by document type (类型) |
| `source` | keyword | Filter by document origin (来源) |
| `tag` | keyword | Filter by document tag (标签) |
| `uploader` | keyword | Filter by uploader |
| `doc_id` | keyword | Filter by source document |
| `is_parent` | keyword | Filter by parent/child chunk type |
| `parent_id` | keyword | Lookup parent chunk from child chunk |

Additional indexes can be configured per collection in `configs/default.yaml`.

## Collection Lifecycle — [TBD: filled by F05]

### Auto-Creation on Startup

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

### Dynamic Creation via API

```python
POST /api/v1/kb/collections
{
  "name": "custom_collection",
  "description": "Custom knowledge collection",
  "vector_size": 1536,
  "distance": "Cosine",
  "sparse_vectors": true
}
```

### Deletion

```python
DELETE /api/v1/kb/collections/{collection_name}
→ Deletes collection and all its points (irreversible)
```

## Document Operations — [TBD: filled by F15a/F15b]

### Upload Document

```python
POST /api/v1/kb/collections/{collection_name}/documents
Content-Type: multipart/form-data

file: <markdown file>
doc_type: "技术文档"             # Metadata: 类型
source: "内部"                   # Metadata: 来源
tag: "已审核"                    # Metadata: 标签
uploader: "user1"                # Uploader identifier
chunking_strategy: "fixed_overlap"  # Optional: chunking strategy
# chunking_params: {...}         # Optional: strategy-specific parameters
```

Pipeline:
1. Parse markdown into chunks (using configured chunking strategy)
2. If `enable_parent_child=true`:
   a. Create parent chunks using `fixed_overlap` strategy with `parent_chunk_params`
   b. Create child chunks using selected `chunking_strategy`
   c. Link each child chunk to its parent via `parent_id`
3. Generate dense embeddings via LLM Gateway
4. Generate sparse vectors (tokenization)
5. Upsert points to Qdrant with metadata
6. Returns task_id (async processing)

### Parent-Child Chunking Mode

When `enable_parent_child=true`, documents are chunked at two granularities:

- **Parent chunks**: Large-granularity (default 2000 chars), provide full context
- **Child chunks**: Fine-granularity (per selected strategy), for precise matching

Retrieval behavior: match child chunk → look up `parent_id` → return parent chunk content with child chunk position info.

Deduplication: if filename + uploader + collection already exists, return HTTP 409.

### List/Search Documents

```python
GET /api/v1/kb/collections/{collection_name}/documents?filename=guide&doc_type=技术文档&source=内部&tag=已审核&uploader=user1&limit=20&offset=0
```

### Delete Documents

```python
# Two-step confirmation:
# Step 1: Without confirm_token → returns impact scope + confirm_token
DELETE /api/v1/kb/collections/{collection_name}/documents?clear_all=true
→ { "affected_documents_count": 42, "confirm_token": "uuid" }

# Step 2: With confirm_token → executes deletion
DELETE /api/v1/kb/collections/{collection_name}/documents?clear_all=true&confirm_token=uuid
→ { "deleted_documents_count": 42 }
```

Also supports targeted deletion via query params: `doc_id`, `doc_type`, `source`, `tag`, `uploader`, `filename`.

### Query (RAG)

```python
POST /api/v1/kb/query
{
  "query": "How to handle chemical spills?",
  "collection_names": ["safety"],  # Optional, defaults to all collections
  "doc_type": "regulation",        # Optional filter
  "source": "内部",                # Optional filter
  "tag": "已审核",                 # Optional filter
  "uploader": "user1",            # Optional filter
  "retrieval_strategy": "hybrid", # keyword/similarity/hybrid/rrf
  "top_k": 5,
  "score_threshold": 0.5,
  "enable_rerank": false,
  "stream": true
}
```

## Error Codes — [TBD: filled by F05, F15a/F15b]

| Code | Name | Description |
|------|------|-------------|
| 6001 | KB_COLLECTION_EXISTS | Collection already exists |
| 6002 | KB_COLLECTION_CREATE_FAILED | Failed to create collection |
| 6003 | KB_COLLECTION_DELETE_FAILED | Failed to delete collection |
| 6004 | KB_DOCUMENT_UPLOAD_FAILED | Document parsing or indexing failed |
| 6005 | KB_DOCUMENT_DELETE_FAILED | Document deletion failed |
| 6006 | KB_INVALID_DOCUMENT_TYPE | Only markdown documents are supported |

## Qdrant Client Configuration — [TBD: filled by F05]

```python
# app/infra/vector_store/qdrant_client.py
class QdrantClientWrapper:
    def __init__(self, url: str, timeout: float = 30.0):
        self.client = qdrant_client.QdrantClient(url=url, timeout=timeout)

    async def create_collection(self, config: CollectionConfig) -> None: ...
    async def delete_collection(self, name: str) -> None: ...
    async def upsert_points(self, collection: str, points: list[PointStruct]) -> None: ...
    async def search(self, collection: str, query_vector: list, limit: int, filters: dict = None) -> list[ScoredPoint]: ...
    async def delete_points(self, collection: str, point_ids: list[str]) -> None: ...
```

All Qdrant operations go through this wrapper, never directly via the SDK in domain code.

[TBD: filled by work orders F05, F15a/F15b/F15c]