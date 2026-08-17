# 就业AI智能体：插件化最小MVP

这是一个面向客户评审版 V2.1 的可运行验证工程。它只实现一条 Golden Flow：

> Excel 双 Sheet 导入 → 数据质量门 → 本体语义规范化 → Top10 人岗匹配与解释 → 人工审核 → 反馈/指标 → 受控导出

项目不是完整招聘平台，也不接入真实个人信息、5+2、BOSS、企微、OCR 或政策 RAG。所有仓库内测试数据均为程序化生成的虚构数据。

## 1. 一分钟启动

```bash
cp .env.example .env
# 修改 SESSION_SECRET、OPERATOR_PASSWORD、REVIEWER_PASSWORD
docker compose up --build
```

打开 <http://localhost:8000>。

Compose 默认只绑定 `127.0.0.1`。部署到远端后可用 SSH 隧道访问；正式公网开放前应先配置 HTTPS、强密码、访问控制和备份。

若未设置 `.env`，Compose 仅为本地演示提供以下默认账号：

- 业务操作员：`operator` / `operator-demo`
- 审核人：`reviewer` / `reviewer-demo`

生产或客户环境必须修改默认密码和 `SESSION_SECRET`。
若通过 HTTPS 反向代理对外服务，请设置 `COOKIE_SECURE=true`；纯 HTTP 本地演示保持 `false`。
生产模式若仍使用示例密钥/密码，应用会拒绝启动。

## 2. 配置真实大模型

项目支持 DeepSeek 及其他 OpenAI Chat Completions 兼容接口。密钥只从服务端环境变量读取，前端只能看到供应商、模型和是否配置，永远拿不到明文密钥。

```bash
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-v4-flash
LLM_API_KEY=replace-with-your-deepseek-key
LLM_CANDIDATE_LIMIT=20
LLM_WEIGHT=0.4
LLM_REQUIRED=false
LLM_THINKING=false
```

处理逻辑不是“让模型直接决定录用”，而是：

1. 硬规则检查岗位有效性、就业状态及明确冲突；
2. 规则与本地相似度召回最多 `LLM_CANDIDATE_LIMIT` 名匿名候选人；
3. LLM 结构化输出语义分、迁移性理由、风险和人工核验问题；
4. 规则分与 LLM 分按 `LLM_WEIGHT` 合成 Top-N，硬规则冲突不可被模型删除；
5. 保存 provider、model、响应 ID、token 用量和解释证据，最终由人工审核。

未设置 `LLM_API_KEY` 时，系统会在界面明确显示“规则基线”，不会冒充大模型结果。若希望无密钥时禁止运行匹配，可设置 `LLM_REQUIRED=true`。

接口实现依据 [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion) 和 [JSON Output](https://api-docs.deepseek.com/guides/json_mode/)；插件/模型路由设计参考 [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)，但本项目不直接依赖其开发预览运行时。内部设计决策见 `docs/adr/0002-provider-model-routed-llm.md`。

## 3. MVP交付范围

- 稳定内核：身份/双角色、插件注册与配置、生命周期、事件总线、SQLite 状态、审计日志。
- 数据插件：受控 Excel 双 Sheet 导入、字段校验、重复/枚举/区间检查、错误定位。
- 本体插件：技能、岗位、行业同义词映射为版本化概念 ID，原始值、证据和置信度并存。
- 匹配插件：硬规则召回、可配置 LLM 语义复排、Top10 排序、逐项解释与版本留痕；无密钥时显式降级为本地基线。
- 审核插件：通过、驳回、待复核及理由记录。
- 反馈插件：有效、无效、未联系、拒绝、待跟进和指标统计。
- 导出插件：当前岗位匹配结果 CSV 导出，防止公式注入。
- 插件运维：状态查看、受控启停；依赖中的插件禁止直接停用。

## 4. 模拟数据

仓库包含 `data/synthetic/employment_ai_demo.xlsx`：

- `person_snapshot`：1,000 名虚构求职者，不含姓名、身份证和手机。
- `job_snapshot`：12 个虚构岗位、3 家虚构企业。

字段定义、生成边界和数据声明见 `data/synthetic/README.md` 与 `docs/data-contract.md`。

## 5. 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
uvicorn employment_ai.main:app --reload
```

## 6. Linux部署

要求：Linux x86_64/arm64、Docker Engine 24+、Docker Compose v2。应用只需要一个持久卷 `/app/runtime`；默认使用 SQLite，适合单实例 MVP 验证。

```bash
docker build -t employment-ai-mvp:0.2.0 .
docker run --rm -p 8000:8000 \
  -e SESSION_SECRET='replace-me' \
  -e OPERATOR_PASSWORD='replace-me' \
  -e REVIEWER_PASSWORD='replace-me' \
  -e LLM_API_KEY='replace-with-your-deepseek-key' \
  -v employment_ai_runtime:/app/runtime \
  employment-ai-mvp:0.2.0
```

## 7. 明确边界

- 只支持单租户、单实例、单个 PC 工作台；不采用微服务、Kubernetes、Redis、ES 或消息队列。
- 本体层与存储层解耦：MVP 用 JSON-LD 管理语义词表、SQLite 保存业务状态与映射证据；未来可通过插件替换为 RDF/图数据库，不影响业务契约。
- 不自动触达、不自动录用、不写回外部系统，AI只排序与解释，最终决定由人工完成。
- “回退”指插件版本/配置及系统内状态的受控恢复。跨系统外发或写回若未来加入，必须采用幂等、补偿和审计，不能承诺完全逆转。
- LLM 只接收匿名候选 ID 与岗位相关字段，不发送姓名、联系方式或特殊标签；接入真实个人信息前仍需完成数据出境、委托处理、脱敏及日志留存评审。
- 当前匹配算法与 Prompt 是可解释的验证基线，不代表生产模型或效果承诺。Top10 指标需以客户确认的金标集复测。

架构与插件契约分别见 [ARCHITECTURE.md](ARCHITECTURE.md) 和 [docs/plugin-contract.md](docs/plugin-contract.md)。

安全边界与验证记录见 [SECURITY.md](SECURITY.md) 和 [docs/validation.md](docs/validation.md)。
