# 意图路由规格

## 概述

意图路由服务（`app/domain/intent/`）通过三层流水线（关键词 → 相似度 → LLM）将用户输入分类到若干意图类别之一，并将请求路由到相应的处理流水线。支持多意图检测及主语省略补全的查询重构。

## 意图类别 — [TBD: filled by F16]

| 意图 | 描述 | 目标流水线 |
|--------|-------------|----------------|
| `qa` | 需要检索的知识问答 | 知识域（RAG 流水线） |
| `task` | 需要工具的多步骤任务 | Agent/Workflow 流水线 |
| `chat` | 自由对话，无需检索 | Chat 域 |
| `retrieve_only` | 纯检索，无需生成 | 知识域（仅检索） |

默认意图类型可通过 prompt 配置由业务方扩展。模板提供上述 4 种；业务项目可通过 `candidates` 参数及 prompt 更新添加更多类型。

## 架构 — [TBD: filled by F16]

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

意图服务设计为简单分类并返回结果。实际路由决策由调用方（API 层或 workflow）做出。

## 三层流水线 — [TBD: filled by F16]

### L1：关键词匹配

最快的层，LLM 成本为零。将用户输入与配置中定义的关键词规则进行匹配。

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

### L2：相似度匹配

基于嵌入的匹配。将查询嵌入与预计算的意图代表嵌入进行比较。

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

### L3：LLM 分类

最准确的层。使用 LLM 通过结构化 JSON 输出对意图进行分类。

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

### 多意图检测 — [TBD: filled by F16]

启用后，LLM 分类层可在单次查询中检测多个意图：

> "帮我创建一个知识库，顺便解释下 RAG 是什么"
> → 主意图：`task`（"帮我创建一个知识库"）
> → 子意图：`qa`（"解释下 RAG 是什么"）

每个子意图都会重构查询，以解决主语省略问题：

| 字段 | 描述 |
|-------|-------------|
| `query` | 重构后的完整查询（解决主语省略） |
| `original_query` | 来自用户输入的原始文本片段 |

## Prompt 模板 — [TBD: filled by F16]

模板从 `prompts/intent/classify.md` 加载：

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

## 意图结果 — [TBD: filled by F16]

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

## 降级策略 — [TBD: filled by F16]

| 场景 | 降级意图 |
|----------|----------------|
| 三层均失败 | `chat`（最安全的默认值） |
| 置信度 < 阈值（可配置，默认 0.5） | `chat` |
| 未知意图类别 | `chat` |
| 输入过短（< 3 个字符） | `chat` |

## 配置 — [TBD: filled by F16]

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

## 与 Workflow 的集成 — [TBD: filled by F16]

意图路由可作为 workflow 节点使用：

```python
# In a StateGraph workflow
graph.add_node("classify_intent", intent_classify_node)
graph.add_conditional_edges("classify_intent", route_by_intent)
# route_by_intent returns: "qa_node", "task_node", "chat_node", "retrieve_node", etc.
```

## API 端点 — [TBD: filled by F16]

| 方法 | 路径 | 描述 |
|--------|------|-------------|
| POST | /api/v1/intent | 分类用户意图（三层 + 多意图） |

### 请求

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

### 响应

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

## 错误码 — [TBD: filled by F16]

| 错误码 | 名称 | 描述 |
|------|------|-------------|
| 2001 | INTENT_CLASSIFY_FAILED | LLM 分类调用失败 |
| 2002 | INTENT_UNKNOWN | 无法确定意图 |
| 2003 | INTENT_TIMEOUT | 分类超时 |
| 2004 | INTENT_INVALID_INPUT | 输入过短或格式异常 |

[TBD: filled by work order F16]