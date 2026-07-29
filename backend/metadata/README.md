# Metadata 导航

这个目录保存 Ella Agent backend 的能力说明文档和流程图。

## 总览入口

优先从下面两个入口开始：

- `ella-agent-capabilities.md`
  - 完整汇总版能力文档
  - 适合一次性了解全貌
- `workflow-overview-v2.svg`
  - 更清晰的 workflow 总览图
  - 适合先看整体执行路径

## 能力文档

### 汇总文档

- `ella-agent-capabilities.md`
  - 当前主汇总文档
  - 已保留，不因拆分而删除
- `ella-agent-capabilities-default.md`
  - 旧版完整副本
- `ella-agent-capabilities copy.md`
  - 另一份完整副本

### 拆分文档

- `ella-agent-capabilities-chat.md`
  - 普通 chat 路径
  - 包括 memory / tool / LLM 在 chat 中的执行顺序
- `ella-agent-capabilities-memory.md`
  - memory 分层
  - 包括 `conversation_messages`、`memories`、`remember(...)`、`store_extracted_memories(...)`
- `ella-agent-capabilities-workflow-foundation.md`
  - workflow 基础边界
  - 包括 registry、workflow API、planner 分流
- `ella-agent-capabilities-tools-and-runtime.md`
  - tools 与 deterministic workflow runtime
  - 包括 meeting / bug workflow 主链路
- `ella-agent-capabilities-cache-and-testing.md`
  - artifact cache 与测试
  - 包括 cache hit / miss、side effect replay、测试覆盖
- `ella-agent-capabilities-status-and-gaps.md`
  - 当前落地状态与剩余缺口
  - 包括 1-8 落地情况、当前限制、建议顺序

## 流程图

- `workflow-overview.svg`
  - 早期总览图
- `workflow-overview-v2.svg`
  - 当前更清晰的总览图
- `workflow-sequence.svg`
  - 时序视角流程图

## 推荐阅读顺序

### 如果你想快速理解系统

1. `workflow-overview-v2.svg`
2. `ella-agent-capabilities.md`
3. `ella-agent-capabilities-status-and-gaps.md`

### 如果你想理解普通 chat

1. `ella-agent-capabilities-chat.md`
2. `ella-agent-capabilities-memory.md`
3. `ella-agent-capabilities-tools-and-runtime.md`

### 如果你想理解 workflow

1. `ella-agent-capabilities-workflow-foundation.md`
2. `ella-agent-capabilities-tools-and-runtime.md`
3. `ella-agent-capabilities-cache-and-testing.md`
4. `workflow-sequence.svg`

## 数据与语义边界

当前最容易混淆的三层数据分别是：

- `conversation_messages`
  - 对话历史
- `memories`
  - 结构化长期记忆
- workflow artifact cache
  - workflow 内容结果缓存

这部分的详细说明在：

- `ella-agent-capabilities-memory.md`
- `ella-agent-capabilities-cache-and-testing.md`
