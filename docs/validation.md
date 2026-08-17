# 验证记录

验证日期：2026-08-17。

## 自动化检查

- `ruff check`：通过。
- `ruff format --check`：通过。
- `pytest`：12项通过，包括大模型适配器结构化响应校验、密钥不泄露、无密钥显式基线、模拟 LLM 复排闭环及 HTTPS 反代静态资源回归测试。
- 合成 Excel：2个工作表、1,000条匿名人员、12个虚构岗位；公式扫描无命中，两张表均完成渲染抽检。

## 远端 Linux 容器验证

验证环境：Debian 13、Linux x86_64、Docker 29.6.2、Compose 5.3.1。

- 镜像在远端 x86_64 主机从源码构建成功。
- 容器健康状态：`healthy`。
- 10个内置插件完成装载；未配置测试密钥时，大模型提供方明确为 `degraded/baseline`，其余9个插件为 `enabled`。
- 自动导入批次：`ready`，1,000人、12岗。
- 本体映射：`CNC操作/数控机床操作 → skill:cnc_operation`，岗位映射为 `occupation:cnc_operator`，本体版本 `1.0.0`。
- Golden Flow：Top10生成、解释、人工审核、业务反馈、指标和带BOM的CSV导出均通过。
- Docker `test` 阶段中 `ruff check`、`ruff format --check` 与12项 `pytest` 全部通过；Docker 仅在远端 Linux 构建和运行。
- Chromium 桌面与移动视口检查：CSS/JS加载成功、微软雅黑为首选字体、页面无横向溢出；移动端结果表提供独立横向滚动提示。
- 大模型真实网络调用未执行，因为验证环境没有 DeepSeek API Key；模型路径使用 `httpx.MockTransport` 验证，正式接口启用仍需提供密钥后补做真实调用验收。

该结果证明最小验证闭环可运行，不等同于生产安全、模型效果或并发容量验收。Top10业务指标仍需客户金标集复测。
