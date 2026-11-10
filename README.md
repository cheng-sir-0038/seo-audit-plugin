# SEO Audit Plugin

一个面向 Agent Host 的只读 SEO 插件。它提供 SEO 工作流、数据工具和诊断交接格式；模型推理、交互控制和后续代码修改由宿主负责。

当前覆盖四类问题：

- **技术 SEO 检查**：页面、robots.txt、sitemap、收录、性能和结构化数据。
- **排名下降排查**：区分搜索表现变化、排名页面变化和数据不足。
- **关键词机会研究**：结合关键词、竞品和搜索结果判断值得研究的方向。
- **自然搜索流量分析**：使用 GA4 分析落地页、访客参与和关键事件。

[SEO Diagnosis Agent](https://github.com/cheng-sir-0038/seo-diagnosis-agent) 是独立应用，两个项目当前没有直接接入关系。

## 目录

```text
plugin.json / .codex-plugin/   插件声明与 Codex 入口
.agents/workflows/            开发 Agent 的协作与诊断流程索引
skills/                       不同 SEO 问题的处理步骤
references/                   运行时需要的判断规则
mcp.json / .mcp.json          MCP 服务启动配置
mcp-server/                   Python 数据服务及测试
mcp-server/src/codex_seo_mcp/workflows/  可执行的只读 SEO 检查流程
schemas/                      版本化诊断交接格式
evals/                        本地确定性评测
```

`skills/` 和 `references/` 是插件运行所需的内容。插件只读取和分析网站数据，不直接修改目标网站或发布内容。

## 基础 SEO 体检

插件加载到支持 MCP 的宿主后，可要求对一个 URL 做基础 SEO 体检。`technical-seo-audit` Skill 可调用 `inspect_site_basics`，依次读取页面、`robots.txt` 和最多一个同站 sitemap，并分别返回每一步的证据或失败原因。它不调用收费 SEO 数据接口，也不修改网站。

此流程只检查一个页面和一个 sitemap；如果存在多个或跨站 sitemap，会明确提示未覆盖的部分。资源请求会沿用现有的安全重定向检查；若跳转到其他站点，结果会标记为部分完成。它不能证明整站的抓取情况或 Google 收录状态。更完整的诊断仍需结合 Skill、其他工具和实际可用的数据来源。

## 本地安装到 Codex

需要 uv 0.12.9；插件使用 Python 3.11.16 和锁定的依赖。首次运行时 uv 可能需要下载 Python 和依赖。

```bash
codex plugin marketplace add /absolute/path/to/seo-audit-plugin
codex plugin add seo-audit-plugin@seo-audit-plugin
codex plugin list --json
```

也可以通过支持对应插件和 MCP 能力的其他 Agent Host 接入。不同宿主的加载方式与交互能力需要分别确认。

## 数据来源和配置

页面 HTML、robots.txt 和 sitemap 检查不要求 SEO 数据供应商账号。DataForSEO、Semrush、Serper、PageSpeed 和 CrUX 等能力需要按实际服务配置凭据或 API Key；可参考 [`.env.example`](.env.example)，本地凭据不要提交到仓库。

Google Search Console 和 GA4 使用 Google Desktop OAuth Client。连接状态为 `not_configured` 时：

1. 在 Google Cloud 创建类型为 **Desktop app** 的 OAuth Client。
2. 将下载的 JSON 放到连接状态返回的 `client_file` 路径，或通过 `GOOGLE_OAUTH_CLIENT_FILE` 指定。
3. 使用对应连接操作完成浏览器授权。GSC 和 GA4 的授权状态分别保存。

如果一个域名匹配多个 GSC 站点或 GA4 媒体资源，宿主需要支持 MCP 表单式用户输入，以便用户选择真实资源；插件不会替用户猜测。

## 验证与限制

```bash
cd mcp-server
uv sync --locked --group dev
uv run --locked pytest -q
uv run --locked python ../evals/run_local.py
```

- 数据来源各有边界：GA4 不证明关键词排名，第三方预估不等同于 GSC 数据。
- 页面检查拒绝解析到本机、私网或特殊地址的目标；使用 Fake-IP 代理时，公网域名也可能被拦截。
- 某些外部接口需要额外授权或产生费用；数据不足时应明确说明。

## 许可证

项目原创内容采用 [MIT 许可证](LICENSE)。随附的第三方组件及依赖保留各自许可，详见 [第三方许可说明](THIRD_PARTY_NOTICES.md)。
