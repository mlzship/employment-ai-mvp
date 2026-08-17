# ADR-0002：Provider/Model 路由的大模型复排插件

状态：已采用（内部工程参考，不作为客户功能承诺）

## 背景

V1 的 `semantic-ranker` 使用 RapidFuzz/SequenceMatcher 计算本地文本相似度，只能作为无外部依赖的可解释基线，不能称为大模型语义判断。

## 决策

- 将大模型能力定义为独立 `llm.rerank` seam，由 `llm-provider` 插件拥有。
- 每次请求显式记录 `provider + model`，模型名称不用于隐式选择供应商。
- API 密钥只从 `LLM_API_KEY` 读取，不进入浏览器、数据库、插件状态或审计详情。
- 规则引擎先处理资格与确定性冲突；LLM 仅对匿名候选短名单做语义复排。
- LLM 必须返回结构化 JSON，并对候选 ID 完整性、重复项、分数范围和字段长度进行验证。
- 上游网络、HTTP、JSON 或完整性失败时，本次运行失败且不覆盖已有匹配结果；不进行静默回退。
- 没有密钥且 `LLM_REQUIRED=false` 时才允许显式使用本地基线，结果中标记 `llm_used=false`。

## 对 DeepSeek Harness 的借鉴边界

[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) 使用 Cordis 将模型适配器、工具、会话与循环都实现为可替换插件，并把 provider 与 model 分开路由。本项目借鉴以下原则：

1. 能力由 Service Definition / Provider / Consumer 分离；
2. 一个 provider 在运行上下文中只有一个能力所有者；
3. 配置显式校验，凭据与普通设置分离；
4. 插件卸载可撤销能力注册，但历史证据保持版本化；
5. 模型调用错误显式暴露，不通过隐式适配或顺序规则掩盖。

本项目是 Python/FastAPI 最小 MVP，不引入 DeepSeek Harness 开发预览运行时，也不复制其 Agent Loop、工具系统或会话协议。

## 数据与决策边界

发送给模型的字段限定为岗位要求、候选匿名 ID、教育/专业、技能、本体概念、就业状态、薪资区间、地区偏好、行业偏好、经验和班次。不发送姓名、身份证、电话、村镇位置或特殊标签。硬规则冲突保留在最终解释中，LLM 不拥有录用、触达或写回权限。
