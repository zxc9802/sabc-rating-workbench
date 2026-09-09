# 上海采集整链路验收（2026-09-10）

范围：现有代码的43条固定样例，不代表全部省市或全量数据。41条成功返回、保存，2条未成功。第五阶段回答质量验收尚未开始。

| 来源/地区 | 查询 | 结果 | 耗时秒 |
|---|---|---|---|
| 人口指标 | `CHN/SP.POP.TOTL` | 成功 | 1.8 |
| 公开仓库 | `fastapi/fastapi` | 成功 | 2.06 |
| 公司披露索引 | `320193` | 成功 | 1.24 |
| 公司财务指标 | `320193/facts` | 成功 | 2.41 |
| 应用搜索 | `us/notion` | 成功 | 1.13 |
| 官方统计文章 | `https://www.stats.gov.cn/sj/zxfb/202608/t20260817_1965056.html` | 成功 | 2.21 |
| 软件业统计文章 | `https://wap.miit.gov.cn/jgsj/yxj/xxfb/art/2026/art_7ecee3ca8eaa489685c7162a18a92fef.html` | 成功 | 2.96 |
| 公告PDF | `https://static.cninfo.com.cn/finalpage/2025-03-31/1222946119.PDF` | 成功 | 8.86 |
| 法规检索 | `个人信息保护法` | 成功 | 1.48 |
| 法规PDF全文 | `id:ff8081817b6472a3017b656cc2040044` | 成功 | 3.14 |
| 热门搜索RSS | `US` | RemoteProtocolError: Server disconnected without sending a response. | 32.11 |
| 宿迁（江苏） | `suqian/search:商务统计` | 成功 | 2.29 |
| 阿克苏（新疆） | `aksu/gdp:2025` | 成功 | 1.81 |
| 深圳 | `shenzhen/29200_00403632` | 成功 | 2.09 |
| 山东 | `shandong/search:社会消费品零售总额` | 成功 | 4.66 |
| 达州 | `dazhou/search:人口` | 成功 | 2.15 |
| 攀枝花 | `panzhihua/search:常住人口` | local 取数暂缓（本轮 3 次）：HTTP 500 | 2.3 |
| 雅安 | `yaan/search:人口` | 成功 | 2.06 |
| 宜宾 | `yibin/search:人口` | 成功 | 1.72 |
| 宿州（安徽） | `suzhou_ah/search:人口` | 成功 | 2.24 |
| 福建 | `fujian/search:森林公园` | 成功 | 17.14 |
| 枣庄 | `zaozhuang/search:人口` | 成功 | 3.9 |
| 淄博 | `zibo/search:人口` | 成功 | 2.73 |
| 东营 | `dongying/search:生产总值` | 成功 | 2.42 |
| 烟台 | `yantai/search:人口` | 成功 | 4.59 |
| 潍坊 | `weifang/search:人口` | 成功 | 3.91 |
| 泰安 | `taian/search:人口` | 成功 | 4.07 |
| 日照 | `rizhao/search:人口` | 成功 | 2.9 |
| 临沂 | `linyi/search:人口` | 成功 | 6.47 |
| 德州 | `dezhou/search:人口` | 成功 | 3.02 |
| 聊城 | `liaocheng/search:人口` | 成功 | 3.54 |
| 滨州 | `binzhou/search:人口` | 成功 | 3.2 |
| 菏泽 | `heze/search:人口` | 成功 | 3.71 |
| 福州 | `fuzhou_fj/search:生产总值` | 成功 | 11.68 |
| 厦门 | `xiamen/search:生产总值` | 成功 | 13.39 |
| 漳州 | `zhangzhou/search:生产总值` | 成功 | 12.98 |
| 泉州 | `quanzhou/search:生产总值` | 成功 | 8.29 |
| 三明 | `sanming/search:生产总值` | 成功 | 10.21 |
| 莆田 | `putian/search:生产总值` | 成功 | 12.16 |
| 南平 | `nanping/search:生产总值` | 成功 | 11.25 |
| 龙岩 | `longyan/search:旅行社` | 成功 | 11.98 |
| 宁德 | `ningde/search:生产总值` | 成功 | 11.72 |
| 平潭综合实验区 | `pingtan/search:生产总值` | 成功 | 4.02 |

成功证据均复读确认：collector_region=ap-shanghai、collector_job_id与源端运行日志对应、E0且unverified。原始记录：artifacts/phase4/zeabur-audit。

## 暂缓及手工渠道

- 攀枝花：3次HTTP500，本轮暂缓。
- Google Trends：上海ConnectError、180秒硬超时；没有写入证据。外层连接提前中断已通过持久化任务与轮询修复；真实网页在处理中刷新后恢复原任务，最终收到失败信息，旧证据保持一致。
- 企业信用公示：当前访问受阻，待复测。
- 国家知识产权局：需已有账号或实名注册。
- 百度指数：浏览器采集后导入；非自动接口。
- 抖音指数：浏览器采集后导入；非自动接口。
- 地方入口杭州：浏览器预览；已取富阳市场8行；完整下载需确认许可协议。
- 地方入口上海：暂缓；程序返回412，浏览器空白；尚未取得数据。
- 地方入口广州：浏览器预览；通过开放广东；已取养老机构预览10行，非全量。

## 网页验证

阿克苏网页取数曾因繁忙429失败；解除并发后重试成功，回答引用真实四季度数值、单位，说明累计及地区限制，并追问缺失经营信息。失败和成功截图均保留。尚未据此宣称模型质量达标。
