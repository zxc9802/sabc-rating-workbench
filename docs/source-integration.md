# 外部数据接入记录

2026-09-09 实测。原始证据及每次请求记录保存在本机 `data/source-verification.db` 的 evidence、source_runs 表，测试评级在 assessments。此数据库仅用于验收，不是真实公司业务。

| 来源 | 当前实现与真实结果 | 限制 | 复测输入 |
| --- | --- | --- | --- |
| World Bank | 官方 API，人口指标5个年度数值入库 | 宏观数据不证明本项目需求；年度不等于当前实时值 | CHN/SP.POP.TOTL |
| GitHub | 官方仓库 API，FastAPI 元数据入库 | 星标、分叉、更新时间不证明收入 | fastapi/fastapi |
| SEC EDGAR | 官方 submissions 与 companyfacts API；Apple 披露索引及收入、成本、利润、经营现金流入库 | 保留单位与起止期间，不混合季度/累计值；全文业务风险待接 | 320193 或 320193/facts |
| Apple Search | 官方搜索 API，美国商店 Notion 相关前5条入库 | 非全量竞品、无下载量或收入 | us/notion |
| 国家统计局 | 官方统计文章正文已入库 | 国家数据交互查询尚待接；数据期间需核验 | https://www.stats.gov.cn/sj/zxfb/202608/t20260817_1965056.html |
| 工信部 | 官方移动站软件业统计正文已入库 | 桌面站403；移动站有效，正文期间待人工确认 | https://wap.miit.gov.cn/jgsj/yxj/xxfb/art/2026/art_7ecee3ca8eaa489685c7162a18a92fef.html |
| 地方公共数据 | 深圳/山东公开预览自动取数；杭州/广州浏览器实际表格快照已入库 | 预览非全量；上海仍受阻，北京需登录；详见local-data.md | shenzhen/29200_00403632 或 shandong/20200618135541100100 |
| 巨潮资讯 | 官方公告 PDF 已真实入库，保留前100页页码及总页数 | 网址取数已实现；公告检索尚待接；100页之后的章节未提取 | https://static.cninfo.com.cn/finalpage/2025-03-31/1222946119.PDF |
| 国家企业信用公示系统 | HTTP521、浏览器访问拦截，未取得企业数据 | 保持暂缓 | 网络或访问条件变化后复测 |
| 国家法律法规数据库 | 官方检索与 PDF 全文已入库；个人信息保护法实测成功 | 标题模糊检索需人工选中法规编号；保留公布、生效日期及效力状态，项目适用性待核验 | 个人信息保护法；id:ff8081817b6472a3017b656cc2040044 |
| 国家知识产权局 | 浏览器登录、注册及目录可访问，尚无业务数据入库 | 注册需实名资料；等待用户登录 | 已有账号登录或自行实名注册 |
| 百度指数 | 浏览器真实读取“人工智能”近30天全国PC+移动概览并入库 | 浏览器辅助，非无人值守API；“AI客服”未收录需付费创建，已暂缓该词 | 见 baidu-browser.md |
| 抖音指数 | 浏览器真实读取ai搜索/综合指数周期概览并入库 | 浏览器辅助，非无人值守API；中文输入一致性及逐日下载待完成 | 见 douyin-browser.md |
| Google Trends | 官方热门RSS及浏览器关键词历史曲线均已真实入库 | RSS可自动调用；53周曲线需浏览器辅助，非历史API | US；历史曲线见trends-browser.md |

## 使用和审计

项目 → 证据资料 → 从官方接口获取外部证据，填写上表输入并取数。API 为 `POST /api/projects/{项目ID}/sources/{来源ID}`，请求体为 `{"query":"查询输入"}`。

所有自动取数初始为 E0、待核验。保存来源 URL、数据期间、采集时刻、查询范围、结构化事实、限制与原始响应 SHA-256。人工核验后外部资料最多 E1。评级引用证据 ID，历史快照保留原内容。

`GET /api/source-runs` 返回尝试记录。临时连接故障或服务端 5xx 最多初次加3次重试；限流、权限和参数错误立即暂缓。失败不写证据，不伪报接通。首批四个来源均首次成功。第二批国家统计局文章与 SEC 财务指标首次成功；工信部桌面文章 HTTP 403，改用官方移动站同文后成功。发现过程也已记录 source_runs。

验收使用真实 API 数据与明确标为测试的公司/评分事实；最终 B/E0，重复计算一致。仅证明取数和规则链路，不证明经营预测准确性。

## 官方说明

Google Trends 回访采用官方公开 RSS `https://trends.google.com/trending/rss?geo=US`，HTTP200，实际条目已入库，证据编号 6887185f3c7544f185ebf26bf4cc6b3c。保留趋势发布时间与原样流量区间，不转换为项目需求量。该能力仅适合观察短期话题环境，与关键词历史曲线不同；后续已通过浏览器采集53周历史数据，方法与局限见[历史趋势采集](trends-browser.md)。

法律库回访：环境代理与浏览器连接重置，直连成功。官方前端脚本明确了检索请求结构；排序参数从字符串改为对象后查询成功。详情接口只返回目录，进一步调用官方 GET 下载入口读取 PDF 全文成功，保存16,242字符证据。下载临时签名地址不进入证据、代码或重试日志。当前法律库检索和全文已实现，尚未验证模型对法律适用性的判断。

入口首轮曾遇到连接失败、HTTP521/403等。后续法律库、百度、抖音、Google Trends及四个地方平台已取得上表所述有限能力的数据；企业信用和知识产权仍未取得有效业务数据。上海与北京地方平台仍有未解决事项，见 [地方数据](local-data.md) 与 [暂缓来源](blocked-sources.md)，不能用首页HTTP200作为取数成功证据。

证据详情增加“核验并保存新版本”。原始记录不可覆盖，新记录保留 supersedes 链。官方 API 来源核验后仍固定外部类型，强度不超过 E1。

- [World Bank 指标 API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392)
- [GitHub 仓库 API](https://docs.github.com/en/rest/repos/repos)
- [SEC 数据 API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [Apple Search API](https://developer.apple.com/library/archive/documentation/AudioVideo/Conceptual/iTuneSearchAPI/index.html)
