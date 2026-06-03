# Intent Routing Specification

## Overview

The Intent Routing service (`app/domain/intent/`) classifies user input into one of several intent categories using a three-layer pipeline (keyword → similarity → LLM) and routes the request to the appropriate processing pipeline. It supports multi-intent detection with query reconstruction for subject omission resolution.

## Intent Categories — [TBD: filled by F16]

| Intent | Description | Target Pipeline |
|--------|-------------|----------------|
| `qa` | Knowledge Q&A requiring retrieval | Knowledge domain (RAG pipeline) |
| `task` | Multi-step task requiring tools | Agent/Workflow pipeline |
| `chat` | Free conversation, no retrieval | Chat domain |
| `retrieve_only` | Pure retrieval, no generation | Knowledge domain (retrieval only) |

Default intent types are extensible by business via prompt configuration. The template provides these 4; business projects can add more through `candidates` parameter and prompt updates.

## Architecture — [TBD: filled by F16]

```
User Input
    ↓
Intent Service (domain/intent/)
    ↓
L1: Keyword Matching (fastest, zero LLM cost)
    ↓ not matched or low confidence
L2: Similarity Matching (embedding-based, low cost)
    ↓ not matched or low confidence
L3: LLM Classification (most accurate, highest cost)
    ↓
Intent Result (primary intent + sub_intents)
    ↓
Router → Target Domain
```

The intent service is intentionally simple — it classifies and returns the result. The actual routing decision is made by the caller (API layer or workflow).

## Three-Layer Pipeline — [TBD: filled by F16]

### L1: Keyword Matching

Fastest layer with zero LLM cost. Matches user input against keyword rules defined in config.

```python
class KeywordMatcher:
    async def match(self, input: str) -> KeywordResult | None:
        """
        1. Load keyword rules from configs/default.yaml intent.layers.keyword.rules
        2. Match input against keywords for each intent
        3. If match found and confidence >= threshold: return result
        4. Otherwise: return None (proceed to L2)
        """
```

### L2: Similarity Matching

Embedding-based matching. Compares query embedding against pre-computed intent representative embeddings.

```python
class SimilarityMatcher:
    async def match(self, input: str) -> SimilarityResult | None:
        """
        1. Embed input via LLM Gateway (embedding model)
        2. Compare against intent representative embeddings
        3. If top score >= threshold: return result
        4. Otherwise: return None (proceed to L3)
        """
```

### L3: LLM Classification

Most accurate layer. Uses LLM to classify intent with structured JSON output.

```python
class LLMClassifier:
    async def classify(self, input: str, candidates: list[str] | None = None) -> IntentResult:
        """
        1. Load intent classification prompt from prompts/intent/classify.md
        2. Call LLM Gateway with task_type="intent"
        3. Parse structured response (JSON output via json_repair service)
        4. Validate intent is in allowed categories (candidates or all)
        5. Return IntentResult
        """
```

### Multi-Intent Detection — [TBD: filled by F16]

When enabled, the LLM classification layer can detect multiple intents in a single query:

> "帮我创建一个知识库，顺便解释下 RAG 是什么"
> → Primary: `task` ("帮我创建一个知识库")
> → Sub: `qa` ("解释下 RAG 是什么")

Each sub-intent has its query reconstructed to resolve subject omission:

| Field | Description |
|-------|-------------|
| `query` | Reconstructed full query (resolves subject omission) |
| `original_query` | Original text fragment from user input |

## Prompt Template — [TBD: filled by F16]

Template loaded from `prompts/intent/classify.md`:

```markdown
Classify the following user input into one or more categories.

Categories: qa, task, chat, retrieve_only

Rules:
- "qa": Knowledge Q&A requiring retrieval from knowledge base
- "task": Multi-step task requiring tools or agent execution
- "chat": Free conversation, greetings, small talk, no retrieval needed
- "retrieve_only": Pure retrieval request, no answer generation needed

{{#if candidates}}
Only consider these categories: {{candidates}}
{{/if}}

User input: {input}

Respond in JSON format:
{{"primary_intent": "<category>", "confidence": <0.0-1.0>, "reasoning": "<brief explanation>", "sub_intents": [{{"intent": "<category>", "query": "<reconstructed full question>", "original_query": "<original fragment>", "confidence": <0.0-1.0>}}]}}
```

## Intent Result — [TBD: filled by F16]

```python
class IntentResult:
    intent: str                    # Primary intent: one of qa/task/chat/retrieve_only
    confidence: float              # Primary intent confidence (0.0–1.0)
    query: str                     # Reconstructed full query for primary intent
    layer_used: str                # Which layer resolved: keyword / similarity / llm
    routing: RoutingInfo           # Recommended routing for primary intent
    sub_intents: list[SubIntent]   # Additional intents (not executed)
    model: str                     # LLM model used (None for L1/L2)
    input_tokens: int              # Token consumption (0 for L1/L2)
    latency_ms: float              # Classification latency

class SubIntent:
    intent: str                    # Sub-intent category
    confidence: float              # Sub-intent confidence
    query: str                     # Reconstructed full query (resolves subject omission)
    original_query: str            # Original text fragment

class RoutingInfo:
    workflow_id: str               # Recommended workflow
    model: str                     # Recommended model
```

## Fallback Strategy — [TBD: filled by F16]

| Scenario | Fallback Intent |
|----------|----------------|
| All three layers fail | `chat` (safest default) |
| Confidence < threshold (configurable, default 0.5) | `chat` |
| Unknown intent category | `chat` |
| Input too short (< 3 characters) | `chat` |

## Configuration — [TBD: filled by F16]

```yaml
# configs/default.yaml
intent:
  layers:
    keyword:
      enabled: true
      rules:
        - intent: qa
          keywords: ["什么是", "怎么用", "如何", "解释"]
        - intent: task
          keywords: ["帮我", "执行", "创建", "删除"]
        - intent: chat
          keywords: ["你好", "闲聊", "聊聊"]
        - intent: retrieve_only
          keywords: ["搜索", "查找", "检索"]
      confidence_threshold: 0.9
    similarity:
      enabled: true
      top_k: 3
      score_threshold: 0.85
    llm:
      enabled: true
      model_routing: intent
  multi_intent:
    enabled: true
    max_intents: 3
  fallback_intent: chat
  max_input_length: 1000
  timeout: 5.0
```

## Integration with Workflow — [TBD: filled by F16]

Intent routing can be used as a workflow node:

```python
# In a StateGraph workflow
graph.add_node("classify_intent", intent_classify_node)
graph.add_conditional_edges("classify_intent", route_by_intent)
# route_by_intent returns: "qa_node", "task_node", "chat_node", "retrieve_node", etc.
```

## API Endpoint — [TBD: filled by F16]

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/intent | Classify user intent (three-layer + multi-intent) |

### Request

```json
{
  "user_id": "user123",
  "session_id": "session456",
  "query": "帮我创建一个知识库，顺便解释下 RAG 是什么",
  "candidates": ["qa", "task", "chat", "retrieve_only"],
  "options": {
    "keyword_enabled": true,
    "similarity_enabled": true,
    "multi_intent_enabled": true
  }
}
```

### Response

```json
{
  "code": 0,
  "data": {
    "intent": "task",
    "confidence": 0.95,
    "query": "帮我创建一个知识库",
    "layer_used": "keyword",
    "routing": {
      "workflow_id": "task_workflow",
      "model": "qwen-plus"
    },
    "sub_intents": [
      {
        "intent": "qa",
        "confidence": 0.88,
        "query": "解释下 RAG 是什么",
        "original_query": "顺便解释下 RAG 是什么"
      }
    ]
  }
}
```

## Error Codes — [TBD: filled by F16]

| Code | Name | Description |
|------|------|-------------|
| 2001 | INTENT_CLASSIFY_FAILED | LLM classification call failed |
| 2002 | INTENT_UNKNOWN | Could not determine intent |
| 2003 | INTENT_TIMEOUT | Classification timed out |
| 2004 | INTENT_INVALID_INPUT | Input too short or malformed |

[TBD: filled by work order F16]
