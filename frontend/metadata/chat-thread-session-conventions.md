# Chat Thread Session Conventions

## 推荐约定

1. 一个 chat thread 对应一个 session_id。
2. 同一个 thread 的每次发言都带同一个 session_id。
3. 用户点“新建对话”时，前端生成或切换到新的 session_id。
4. 页面刷新后，如果还是同一个 thread，就继续复用原来的 session_id。
5. 如果支持多个 thread，每个 thread 各自保存自己的 session_id。
6. 不建议把整个浏览器全局只用一个 session_id，否则所有话题都会混在一起。

## 设计意图

- session_id 是后端识别同一轮会话上下文、memory 和记忆链路的边界。
- thread 是前端的会话容器，session_id 应作为 thread 的持久标识之一，而不是页面级全局单例。
- 当用户切换到不同 thread 时，前端应切换到对应的 session_id，避免不同话题污染同一后端会话上下文。

## 前端落地建议

- 在前端状态中，以 thread 为单位保存 sessionId、messages、title 等信息。
- 将 thread 列表和当前 activeThreadId 持久化到浏览器存储中，以支持刷新后恢复。
- 创建新 thread 时，初始化新的 sessionId。
- 发送消息时，始终携带当前 active thread 的 sessionId。
- 如果后端返回新的 X-Session-Id，前端应只更新当前 thread 对应的 sessionId。
