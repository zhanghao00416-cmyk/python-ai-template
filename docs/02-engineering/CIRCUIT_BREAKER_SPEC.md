# 熔断器与信号量管理规范

## 概述

所有外部 AI 推理调用必须经 LLM Gateway，Gateway 内部集成熔断器和信号量管理。本规范定义 `app/infra/circuit_breaker.py` 和 `app/infra/semaphore_manager.py` 的行为。

---

## 熔断器（Circuit Breaker）

### 三态模型

| 状态 | 行为 |
|------|------|
| **closed** | 正常放行请求，统计失败率 |
| **open** | 拒绝所有请求，直接返回 `AI_1102` 或 `AI_1104`，等待恢复时间 |
| **half_open** | 放行探针请求（1 个），成功 → closed，失败 → open |

### 配置参数

```yaml
# configs/default.yaml
circuit_breaker:
  failure_threshold: 5      # 连续失败次数达到此值后进入 open
  recovery_timeout: 30       # open 状态等待秒数后进入 half_open
  half_open_max_calls: 1     # half_open 状态放行的探针请求数
```

### 熔断器实例

每个通道独立熔断器：

| 实例名 | 保护通道 | 降级行为 |
|--------|----------|----------|
| `llm_text` | Qwen Cloud 文本 | open → `AI_1104 云API调用失败` |
| `llm_vllm` | vLLM 文本 | open → `AI_1102 模型服务不可用` |
| `multimodal` | 多模态 | open → `AI_1104` 或 `AI_1102` |
| `embedding` | Embedding | open → `AI_1102` |

### 降级策略

| 任务 | 默认通道 | 降级通道 |
|------|----------|----------|
| 文本任务 | qwen_cloud | vllm |
| 多模态 | 配置指定 | **无**（不可用则异常） |
| Embedding | qwen_cloud | vllm |

文本通道降级由 Gateway 自动处理：`qwen_cloud` 熔断时切换到 `vllm`（如果 `vllm` 也熔断则返回错误）。

---

## 信号量管理（Semaphore Manager）

### 目的

AI 推理任务是重型的。无限制并发会导致：
- 下游服务过载
- 内存溢出
- 响应超时

### 配置参数

```yaml
# configs/default.yaml
concurrency:
  llm_semaphore_size: 20       # 文本 LLM 最大并发
  multimodal_semaphore_size: 10    # 多模态推理最大并发
  embedding_semaphore_size: 20 # Embedding 最大并发
  semaphore_acquire_timeout: 120  # 获取信号量最长等待秒数
```

### 使用模式

```python
sem_mgr = get_semaphore_manager()

async with sem_mgr.acquire("llm"):
    result = await gateway.text_chat(messages, stream=False)

# 超时未获取信号量 → BusinessException(AI_0004, "并发超限，请稍后重试")
```

### 信号量命名

| 名称 | 对应配置 | 保护对象 |
|------|----------|----------|
| `llm` | `llm_semaphore_size` | 文本 LLM 调用 |
| `multimodal` | `multimodal_semaphore_size` | 多模态调用 |
| `embedding` | `embedding_semaphore_size` | Embedding 批量生成 |

---

## 日志要求

每次外部调用必须记录：

| 字段 | 说明 |
|------|------|
| `provider` | qwen_cloud / vllm |
| `model` | 模型 id |
| `elapsed_ms` | 延迟毫秒 |
| `success` | true / false |
| `task` | 任务类型（intent/rag_rewrite/rag_merge/final/chat/multimodal/embedding） |
| `trace_id` | 请求追踪 id |
| `token_usage` | input_tokens / output_tokens（如可用） |

---

## 工单映射

- 熔断器由 **F04 LLM Gateway** 实现
- 信号量管理器由 **F01 项目骨架** 创建框架，**F04** 集成
- 配置参数由 **F01 YAML 配置** 加载