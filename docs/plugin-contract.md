# 插件契约 V1

每个插件以 `PluginManifest` 声明以下内容：

| 字段 | 含义 | MVP校验 |
|---|---|---|
| `id` / `version` | 稳定标识与语义版本 | 格式、唯一性 |
| `provides` | 插件向系统提供的能力键 | 全局唯一 |
| `requires` | 运行前必须存在的能力键 | 缺失或成环时拒绝启动 |
| `permissions` | 所需数据/系统权限 | 启用前可审查 |
| `config_schema` | 配置结构及默认值 | 记录但不执行任意代码 |
| `events_in/out` | 消费和产生的领域事件 | 用于审计与后续解耦 |
| `cleanup_strategy` | 停用/升级时的清理或补偿策略 | 必填 |

生命周期为 `register → validate → install → start → health → stop/cleanup`。MVP只支持仓库内静态插件的受控启停，不支持远程插件市场或未签名代码加载。

## 能力键

| 插件 | 提供能力 | 依赖能力 |
|---|---|---|
| DataQuality | `data.quality` | — |
| SemanticOntology | `semantic.normalize` | `data.quality` |
| ExcelSource | `data.source.excel` | `data.quality`, `semantic.normalize` |
| RuleFilter | `match.rules` | — |
| Explanation | `match.explain` | `match.rules` |
| LlmProvider | `llm.rerank` | — |
| SemanticRanker | `match.rank` | `match.rules`, `match.explain`, `llm.rerank` |
| ReviewWorkflow | `review.workflow` | `match.rank` |
| FeedbackMetrics | `feedback.metrics` | `review.workflow` |
| MatchExport | `export.matches` | `feedback.metrics` |
