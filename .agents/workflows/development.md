# 开发工作流

用于维护插件的 Skill、MCP 数据工具、交接格式及测试。

1. 确认当前分支和工作区状态，先阅读 [项目说明](../../README.md) 以及相关 Skill、数据接口、调用方和测试。
2. 确认问题属于 SEO 判断、数据读取还是宿主职责。修复问题时先复现并定位原因，不把宿主的代码修改和发布职责塞进插件。
3. 修改 Skill 时同步检查其引用的 `references/`；修改 MCP 工具或返回格式时检查 `mcp-server/src/`、相关测试和 `schemas/`。
4. 只运行受影响的测试或评测。例如页面检查变更可在 `mcp-server/` 下执行 `uv run --locked pytest -q tests/test_page_inspection.py`；涉及诊断规则时可运行 `uv run --locked python ../evals/run_local.py`。
5. 检查 `git diff --check`，说明真实数据源、宿主交互或授权未验证的部分。不要为文档修改重建环境或运行无关测试。

保留现有只读和私网访问保护；不要提交 API Key、OAuth 凭据或真实站点的私人数据。提交、推送和发布遵循任务中明确的授权。
