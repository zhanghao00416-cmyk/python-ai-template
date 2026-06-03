# RAG Pipeline Specification

## Overview

The RAG (Retrieval-Augmented Generation) pipeline handles knowledge base document ingestion, vector indexing, and retrieval-augmented question answering. The pipeline spans the `domain/knowledge/` and `infra/vector_store/` layers.

## Pipeline Architecture — [TBD: filled by F15a/F15b]

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

## Document Ingestion — [TBD: filled by F15a]

### Pipeline Flow

```
Upload Markdown Document
    ↓
Parse into chunks (heading-aware splitting)
    ↓
Generate embeddings (via LLM Gateway)
    ↓
Store in Qdrant (with metadata: collection, type, category, doc_id)
    ↓
Return document ID
```

### Chunking Strategy — [TBD: filled by F15a]

- Only Markdown documents are supported
- 4 configurable chunking strategies:

| Strategy | Key | Parameters |
|----------|-----|------------|
| Fixed + overlap | `fixed_overlap` | `chunk_size` (default 500), `overlap` (default 50) |
| Delimiter + max length | `delimiter_max` | `delimiters` (default ["\n\n", "\n"]), `max_chunk_size` (default 1000) |
| Semantic | `semantic` | `similarity_threshold` (default 0.85) |
| Paragraph | `paragraph` | `min_paragraph_chars` (default 50) |

### Parent-Child Chunking Mode — [TBD: filled by F15a]

All 4 chunking strategies support an optional parent-child mode via `enable_parent_child=true`:

- **Child chunks**: Fine-granularity chunks for precise matching (uses selected `chunking_strategy`)
- **Parent chunks**: Large-granularity chunks for full context (always uses `fixed_overlap` with `parent_chunk_params`)

Each child chunk stores `parent_id` linking to its parent chunk. During retrieval, matching a child chunk automatically returns the parent chunk content.

### Chunk Metadata — [TBD: filled by F15a]

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

## Vector Retrieval — [TBD: filled by F05, F15b]

### Query Flow

```
User Query Text
    ↓
Embed query (via LLM Gateway — embedding model)
    ↓
Search Qdrant (with filters)
    ↓
Return top-K chunks with scores
```

### Filtering — [TBD: filled by F15b]

Qdrant queries support multi-dimensional filtering:

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

### Retrieval Strategies — [TBD: filled by F15b]

| Strategy | Key | Description |
|----------|-----|-------------|
| Keyword | `keyword` | Sparse vector / full-text search |
| Similarity | `similarity` | Dense vector search |
| Hybrid | `hybrid` | Combine keyword + similarity (default) |
| RRF | `rrf` | Reciprocal Rank Fusion |

Reranking can be optionally enabled via `enable_rerank` parameter.

### Hybrid Search — [TBD: filled by F05]

Support both dense (semantic) and sparse (keyword) vector retrieval:

- Dense: embedding model generates dense vectors
- Sparse: BM25/sparse vectors for keyword matching
- Results are fused using Reciprocal Rank Fusion (RRF)

## Context Assembly — [TBD: filled by F15b]

After retrieval, context is assembled for the LLM:

```python
class RAGContext:
    query: str                    # Original user query
    retrieved_chunks: list[Chunk] # Top-K relevant chunks
    system_prompt: str             # RAG system prompt template
    max_context_tokens: int        # Token budget for context
```

1. Format each chunk with source citation markers
2. Truncate if total context exceeds token budget
3. Inject into prompt template with `{context}` and `{question}` variables

## Prompt Construction — [TBD: filled by F15b]

RAG prompt templates are loaded from `prompts/rag/`:

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

Templates are loaded by `services/prompt_manager/` and rendered with variable substitution.

## LLM Generation — [TBD: filled by F15b]

- Uses LLM Gateway with `task_type="rag_merge"`
- Supports both streaming and non-streaming responses
- Token usage is tracked and logged
- Concurrency controlled by LLM semaphore

## Citation Extraction — [TBD: filled by F15b]

```python
class Citation:
    chunk_id: str       # Qdrant point ID
    doc_id: str         # Source document ID
    source_file: str    # Original filename
    heading: str        # Heading text
    score: float        # Similarity score
    text_snippet: str   # Relevant text excerpt
```

Citations are extracted from the LLM response and matched back to retrieved chunks.

## API Integration — [TBD: filled by F15a/F15b]

| Endpoint | Method | Description |
|----------|--------|-------------|
| /api/v1/kb/collections | POST | Create collection |
| /api/v1/kb/collections | GET | List collections |
| /api/v1/kb/collections/{name} | DELETE | Delete collection |
| /api/v1/kb/collections/{name}/documents | POST | Upload document (multipart, async) |
| /api/v1/kb/collections/{name}/documents | GET | List/search documents |
| /api/v1/kb/collections/{name}/documents | DELETE | Delete documents (batch/clear with confirm_token) |
| /api/v1/kb/query | POST | RAG query with configurable retrieval |

## Error Codes — [TBD: filled by F15b]

| Code | Name | Description |
|------|------|-------------|
| 3001 | RAG_COLLECTION_NOT_FOUND | Collection does not exist |
| 3002 | RAG_RETRIEVAL_FAILED | Vector retrieval query failed |
| 3003 | RAG_NO_RESULTS | No relevant documents found |
| 3004 | RAG_GENERATION_FAILED | LLM answer generation failed |
| 3005 | RAG_INDEXING_FAILED | Document indexing failed |
| 3006 | RAG_DOCUMENT_NOT_FOUND | Document does not exist |

[TBD: filled by work orders F05, F15a/F15b]