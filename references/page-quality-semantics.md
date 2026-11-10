# 页面性能与体验语义

当 `PageQuality` 数据被用于用户可见结果时，使用本 Reference。内部字段名可以保持稳定英文 key，但最终展示必须以中文业务含义为主，英文缩写只放在括号中辅助识别。

## 展示原则

不要只展示：

```text
LCP: 3200ms
INP: 180ms
CLS: 0.18
```

优先展示：

```text
主要内容加载速度（LCP）：3.2 秒｜需改进
→ 用户看到页面主要内容偏慢

交互响应速度（INP）：180 毫秒｜良好
→ 点击、输入等操作能够较快得到页面反馈

页面视觉稳定性（CLS）：0.18｜需改进
→ 页面加载过程中存在较明显的内容跳动风险
```

只有用户明确要求技术字段/原始指标时，才以缩写作为主要列名。

## 核心网页体验指标

### 主要内容加载速度（LCP）

内部指标：`lcp` / Largest Contentful Paint。

业务含义：用户打开页面后，**页面中最主要、最大的可见内容多久真正显示出来**。常见对象是主图、大标题或主要内容块。这个指标最接近“用户什么时候觉得主要页面已经出来了”。

用户解释：

> 主要内容出现得快不快。

Google 当前建议阈值：

- 良好：`≤ 2.5 秒`
- 需改进：`> 2.5 秒 且 ≤ 4 秒`
- 较差：`> 4 秒`

### 交互响应速度（INP）

内部指标：`inp` / Interaction to Next Paint。

业务含义：用户点击按钮、输入内容、打开菜单等操作后，**页面多久给出下一次可见反馈**。它反映页面整体交互是否“跟手”。

用户解释：

> 点了以后，页面反应快不快。

Google 当前建议阈值：

- 良好：`≤ 200 毫秒`
- 需改进：`> 200 毫秒 且 ≤ 500 毫秒`
- 较差：`> 500 毫秒`

### 页面视觉稳定性（CLS）

内部指标：`cls` / Cumulative Layout Shift。

业务含义：页面加载或使用过程中，**文字、图片、按钮等内容会不会突然跳动、挪位置**。例如用户准备点击按钮时按钮突然下移，就是典型的视觉稳定性问题。

用户解释：

> 页面加载时会不会乱跳。

Google 当前建议阈值：

- 良好：`≤ 0.1`
- 需改进：`> 0.1 且 ≤ 0.25`
- 较差：`> 0.25`

CLS 是无单位分数，不要显示成秒或毫秒。

## 辅助加载诊断指标

FCP 和 TTFB 对定位加载慢的原因很重要，但它们**不是当前三项 Core Web Vitals**。最终结果不要把五项指标都写成“核心网页指标”。

### 首次内容出现速度（FCP）

内部指标：`fcp` / First Contentful Paint。

业务含义：从用户打开页面开始，到**第一次看到任何实际内容**（文字、图片、SVG 等）所需的时间。它回答“页面多久不再是一片空白”。

用户解释：

> 页面多久开始出现第一块可见内容。

Google 当前建议阈值：

- 良好：`≤ 1.8 秒`
- 需改进：`> 1.8 秒 且 ≤ 3 秒`
- 较差：`> 3 秒`

FCP 不能替代 LCP：页面可能很早出现一小块内容，但主要内容仍然很晚才出现。

### 服务器首字节响应（TTFB）

内部指标：`ttfb` / Time to First Byte。

业务含义：从开始访问页面，到浏览器**收到服务器响应的第一个字节**所需的时间。它主要帮助判断服务器、网络连接、重定向、缓存或后端处理是否拖慢后续页面加载。

用户解释：

> 服务器多久开始把页面数据返回给用户。

Google 当前给出的粗略参考：

- 良好：`≤ 0.8 秒`
- 需改进：`> 0.8 秒 且 ≤ 1.8 秒`
- 较差：`> 1.8 秒`

TTFB 不是 Core Web Vitals，阈值应描述为“参考”，不能把 TTFB 单独当成 SEO 排名结论。

## 取数与设备边界

页面性能事实必须通过 `PageQuality` 获取。其 Lighthouse Lab 数据来自 PageSpeed Insights `runPagespeed` API 的结构化 JSON；不要为了拿性能指标或 audits 打开 `pagespeed.web.dev` 网页。Host Browser 只在 rendered DOM、真实交互或视觉行为本身需要浏览器证据时使用。

设备处理：

- 用户明确要求移动端：只取 `strategy=mobile`；
- 用户明确要求桌面端：只取 `strategy=desktop`；
- 用户只给 URL、没有限定设备：分别取 `mobile` 与 `desktop` 两份 `PageQuality`，再比较；
- 一侧 Provider 失败时保留另一侧真实结果并披露缺口，不用 Browser 补造 PageSpeed 数据；
- 不把 mobile Lab 与 desktop Field 拼成一个“综合设备”结果。

用户可见结果优先按设备并排或分区展示，让“移动端明显慢、桌面端正常”这类差异直接可见。

### Canonical-first 与重复调用

当用户给的是带追踪参数的 URL，先用 `PageInspection` 判断 canonical 与页面职责。若 query 只用于 campaign/tracking，且 canonical 指向同内容的无参数页面，默认对 canonical 做 `PageQuality`；不要自动把 tracking URL 和 canonical 各跑一套 mobile/desktop。只有当当前假设就是“参数导致 CDN/cache/rendering 差异”时才比较两者，并明确这是性能差异实验。

Provider 调用应复用短期缓存：PageSpeed/Lighthouse 默认按 `URL + strategy + categories + locale` 缓存 30 分钟，CrUX 按 URL/Origin + form factor + metrics 缓存 24 小时；同一 Job 的等价 measurement 也不得重复请求。缓存只减少重复调用，不改变 Lab/Field 的证据语义。

## Lab 与真实用户数据

同一个指标可能同时有两种来源：

- **本次模拟检测**：Google PageSpeed Insights / Lighthouse Lab；用于复现和定位问题，单次结果会受测试环境影响。
- **真实用户体验**：Chrome UX Report (CrUX)；反映真实 Chrome 用户的聚合体验，优先使用第 75 百分位（p75）判断整体体验。

用户可见结果应明确区分二者，不要只写 `lab` / `field`。

推荐：

```text
真实用户体验
主要内容加载速度（LCP）：2.9 秒｜需改进
交互响应速度（INP）：170 毫秒｜良好
页面视觉稳定性（CLS）：0.06｜良好

本次模拟检测
首次内容出现速度（FCP）：1.4 秒
主要内容加载速度（LCP）：2.6 秒

数据来源：Chrome UX Report、Google PageSpeed Insights / Lighthouse
```

如果 CrUX 只有 Origin 级数据，必须说“站点整体真实用户样本”，不能说成“这个页面的真实用户数据”。

## “需改进”必须给下一步动作

当指标状态为“需改进”或“较差”时，不要停在状态解释。优先结合本次 Lighthouse `opportunities[] / diagnostics[]` 给出与实际证据对应的改进动作。

推荐结构：

```text
主要内容加载速度（LCP）：3.2 秒｜需改进
影响：用户看到页面主要内容偏慢。

发现的主要问题
- 首屏渲染被 CSS / JavaScript 阻塞
- 首屏主图体积偏大

建议
P0｜减少首屏阻塞资源
- 只保留首屏关键 CSS
- 非关键 JavaScript 使用 defer/async 或延后执行

P1｜降低主图下载成本
- 使用 WebP / AVIF
- 按实际展示尺寸下发图片

目标：优先把 LCP 降到 2.5 秒以内
```

建议必须遵守：

- 优先使用 `PageQualityIssue.business_label` 和 `recommendations[]`，不要直接把 Lighthouse 英文 audit title 当用户建议；
- 有 `estimated_savings_ms / estimated_savings_bytes` 时，可以用它们辅助排序优先级，但不能承诺实际改善一定等于该估算；
- 只对本次检测实际出现的 Audit 给具体修复动作；
- 如果指标较差但 Lighthouse 没有足够原因证据，应该说“建议进一步定位”，而不是编造具体资源或代码问题；
- 不把性能建议直接写成“SEO 排名一定会上升”。

常见实际 Audit 已在 Adapter 中规范化为中文业务问题，例如：未使用 JavaScript、主线程过重、渲染阻塞资源、图片尺寸/格式、LCP 图片懒加载、服务器响应、重定向、缓存、字体、DOM 规模、布局跳动和第三方脚本等。

## 业务结论边界

性能指标用于回答“用户体验哪里慢/不稳定”和“可能从哪里优化”，不能直接转换成：

- Google 排名下降原因已确认；
- 页面一定会掉排名；
- 一个 Lighthouse 分数就是 SEO 分数。

LCP / INP / CLS 是 Google Core Web Vitals 的用户体验指标；具体 SEO 因果仍需要和排名、页面、SERP、索引等证据结合。

## 官方阈值来源

- LCP / INP / CLS Core Web Vitals thresholds: https://web.dev/articles/defining-core-web-vitals-thresholds
- LCP: https://web.dev/articles/lcp
- INP: https://web.dev/articles/inp
- CLS: https://web.dev/articles/cls
- FCP: https://web.dev/articles/fcp
- TTFB: https://web.dev/articles/ttfb
