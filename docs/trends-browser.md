# Google Trends 关键词历史曲线

2026-09-09，浏览器直接访问官方Explore页面，无需登录。验收词为artificial intelligence，地区United States，时间Past 12 months，All categories，Web Search，类型Search term。此词仅用于接入测试，不是用户真实项目需求定义。

## 实际结果

从Interest over time图表的可访问数据表读取53条周记录，周标签从Sep 7, 2025至Sep 6, 2026。保存的相对热度范围为0至100；100代表当前查询范围内峰值，不是绝对搜索量、用户数、市场规模或收入。末周可能未完整，采样误差未提供；当前证据不适合据此精确估算需求规模。

- 页面：https://trends.google.com/trends/explore?date=today%2012-m&geo=US&q=artificial%20intelligence&hl=en
- 原始采集文件：data/trends-history-capture.json
- 数据库：data/source-verification.db
- 证据编号：bfbef4412ab6436f8615a1c5bbe1780e
- 评级引用快照：d175924c95e940649360b1eae8c01088；NR/E0（该验收项目仍缺资料）。

只读取页面提供的图表数据表，没有访问隐藏应用状态、会话或Cookie。关联词未纳入该证据。

## 重复采集

1. 用浏览器打开官方Explore，输入项目所需关键词，选择地区、时间范围、分类和搜索类型。
2. 核对页面当前关键词是搜索词还是主题，以及全部筛选条件；加载失败时按初次加最多3次重试规则暂缓。
3. 读取Interest over time的页面数据表，将日期标签和值保留到JSON；不要把不同查询单独归一化后的值直接比较。
4. 按data/trends-history-capture.json格式记录source_id=trends、query、title、source_locator、data_period、scope、content。
5. 导入目标项目：

```powershell
.\.venv\Scripts\python.exe scripts/import_browser_evidence.py data/trends-history-capture.json --database data/sabc.db --project 实际项目ID
```

导入强制设置market、unverified、E0，并记录browser-observation方式。用户核验后最多作为E1外部背景依据。不要将验收文件当成新一次实时采集。

## 能力边界

当前热门RSS可自动调用；关键词历史曲线是浏览器辅助流程。本次公开页面首次访问成功，未要求注册。尚未验证所有地区、词条、长期批量采集、官方API资格及后台无人值守执行。
