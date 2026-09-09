# 全国地方公共数据接入进度

目标仍为尽量覆盖全部省市，无需登录注册。以下为进度记录，不是全国接入完成声明。

当前已支持20个地区入口自动取数：山东省平台及12个地市，四川4个地市，深圳、安徽宿州，以及福建省平台。预览记录不代表全量，部分为区县统计，需核对地区、期间和口径。

## 逐省进度

| 地区 | 当前状态 | 候选入口 |
| --- | --- | --- |
| 北京 | 旧入口受阻或跳转，待核验新入口 | http://data.beijing.gov.cn/ |
| 天津 | 旧域名现为天津市数据局官网，需继续查找开放数据入口 | https://data.tj.gov.cn/ |
| 河北 | 待补查当前官方入口 | 尚未确定 |
| 山西 | 旧入口受阻或跳转，待核验新入口 | http://www.shanxi.gov.cn/sj/ |
| 内蒙古 | 旧入口受阻或跳转，待核验新入口 | http://www.nmg.gov.cn/col/col1586/ |
| 辽宁 | 旧入口受阻或跳转，待核验新入口 | http://www.ln.gov.cn/zfsj/sjfb/ |
| 吉林 | 旧入口受阻或跳转，待核验新入口 | http://www.jl.gov.cn/sj/ |
| 黑龙江 | 待补查当前官方入口 | 尚未确定 |
| 上海 | 访问412，尚未接通 | https://data.sh.gov.cn/ |
| 江苏 | 旧入口受阻或跳转，待核验新入口 | http://www.jiangsu.gov.cn/col/col33688/index.html |
| 浙江 | 杭州仅历史快照；省平台跳转及其他地市待核验 | http://data.zjzwfw.gov.cn/jdop_front/index.do |
| 安徽 | 省级官方入口要求统一登录，跳过；宿州已接入，继续查其他地市 | https://www.ahzwfw.gov.cn/?index=nav |
| 福建 | 省平台普遍开放目录已支持关键词搜索与公开预览；最多30行，按来源核对省市范围 | https://data.fujian.gov.cn/ |
| 江西 | 旧站公告迁移至新域名；匿名目录搜索可用，所试预览返回暂无数据，未接入 | https://kfpt.jiangxi.cn/ |
| 山东 | 省平台及12个地市已支持自动取数 | https://data.sd.gov.cn/portal/index |
| 河南 | 旧入口受阻或跳转，待核验新入口 | http://data.hnzwfw.gov.cn/odweb/ |
| 湖北 | 旧入口受阻或跳转，待核验新入口 | https://www.hubei.gov.cn/data/ |
| 湖南 | 匿名目录搜索可用；本次人口法规目录标为不予开放，已跳过，其他目录待查 | https://data.hunan.gov.cn/etongframework-web/main.do |
| 广东 | 深圳按目录取数；广州仅历史快照，其他地区待完成 | https://gddata.gd.gov.cn/ |
| 广西 | 已在保留证书校验下兼容旧TLS并访问新站；匿名实际取数待验证 | https://gxsjkf.dsjfzj.gxzf.gov.cn:8183/opendata/home |
| 海南 | 首页目录API可匿名访问；已查看税收目录，下载要求登录申请，样例尚未取得 | https://data.hainan.gov.cn/ |
| 重庆 | 待补查当前官方入口 | 尚未确定 |
| 四川 | 已接达州、攀枝花、雅安、宜宾；省平台及其他地市待完成 | https://www.scdata.net.cn/ |
| 贵州 | 当前官网及公开查询脚本可访问；首轮目录请求参数解析失败，待适配 | https://data.guizhou.gov.cn/ |
| 云南 | 官网开放门户显示敬请期待，省级开放服务尚未可用；继续查地市入口 | https://data.yn.gov.cn/ |
| 西藏 | 待补查当前官方入口 | 尚未确定 |
| 陕西 | 旧入口受阻或跳转，待核验新入口 | http://www.sndata.gov.cn/ |
| 甘肃 | 旧入口受阻或跳转，待核验新入口 | http://www.gansu.gov.cn/col/col4420/ |
| 青海 | 旧入口受阻或跳转，待核验新入口 | http://data.qinghai.gov.cn/p/#/index |
| 宁夏 | 补充开放平台候选入口，当前请求超时，暂缓 | http://opendata.nx.gov.cn/portal/index |
| 新疆 | 待补查当前官方入口 | 尚未确定 |

## 核验依据与下一步

- 已整理175个历史省级、地市级入口候选，来源为华中师范大学2021年研究报告附录；旧网址和PDF断行可能失真，不能当作当前官方接口。
- 本轮完成24个省级候选和139个地市级候选的首次HTTP检查；另有四川官方互链入口检查。HTTP 200仅代表返回页面，并非取得数据。
- 实际新接入证据：`artifacts/sichuan-extra-live.json`、`artifacts/yibin-live.json`、`artifacts/shandong-city-live.json`。
- 原始入口检查：`artifacts/national-province-probe.json`、`artifacts/national-platform-audit.jsonl`、`artifacts/sichuan-regional-probe.json`。
- 待办：补齐未确定的省级入口，沿官方跳转和省市互链更新旧地址，逐站验证匿名目录搜索、实际数据响应与来源；需要登录注册的入口跳过。
- 采集器已跳过含身份证或姓名关联手机号/出生日期/民族的个人明细，搜索最多尝试3个目录；网络阻塞仍按最多重试3次处理。

入口复查命令（仅检查候选网页，不会把网页当证据）：

```powershell
.venv/Scripts/python.exe scripts/probe_local_platforms.py --level 地市级 --retries 3
```

最新验证：`artifacts/local-open-filter-regression.json` 中19个已接入入口全部重新取得实际记录；98项后端测试通过。搜索已在官方服务端指定无条件开放筛选，再检查返回目录的开放属性。江西新域名来自旧官方网站迁移公告，入口和预览验证见 `artifacts/jiangxi-entry.html`、`artifacts/jiangxi-search-response-2.json`、`artifacts/jiangxi-preview-probe.json`。

入口检查脚本现支持HTML meta-refresh迁移公告识别；已用江西、广西真实旧站验证，不把迁移页视作数据可用。不会自动跟随登录跳转。原始记录：`artifacts/html-migration-audit.json`。本轮补充6省的核验状态，自动取数仍为19个入口，未新增未经验证的数据源。

新增福建：`fujian/search:森林公园` 已匿名取得省林业局30条公开预览；直接目录另验证三明市21条森林公园记录。福建接口查询开放属性1为普遍开放、0为依申请开放，只接受前者。103项后端测试通过。
