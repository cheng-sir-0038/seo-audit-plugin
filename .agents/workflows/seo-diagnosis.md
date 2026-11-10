# SEO 诊断工作流

本文件用于定位插件已有的业务流程；宿主实际运行时应读取对应的 Skill。

1. 技术 SEO 检查使用 [`technical-seo-audit`](../../skills/technical-seo-audit/SKILL.md)。
2. 排名或自然搜索表现下降使用 [`ranking-drop-diagnosis`](../../skills/ranking-drop-diagnosis/SKILL.md)。
3. 关键词机会研究使用 [`keyword-opportunity-research`](../../skills/keyword-opportunity-research/SKILL.md)。
4. GA4 自然搜索访问和转化分析使用 [`organic-traffic-analysis`](../../skills/organic-traffic-analysis/SKILL.md)。

对应 Skill 按问题选择 [`references/`](../../references/) 中的判断规则，并通过 [`mcp-server/`](../../mcp-server/) 读取所需数据。结论应区分已观察事实、推断和缺失证据；证据不足时不要编造。

插件在诊断、建议和交接处结束。目标项目的修改、测试、构建和发布由宿主在获得相应授权后处理；插件不自行执行这些操作。
