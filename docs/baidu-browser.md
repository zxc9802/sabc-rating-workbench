# 百度指数浏览器取数

2026-09-09 已通过真实浏览器读取免费已收录关键词“人工智能”的概览表，并导入独立测试证据库。当前是浏览器辅助取数，不是免登录 API，也尚未实现无人值守定时抓取。

1. 打开 https://index.baidu.com/，搜索项目实际相关关键词。
2. 若出现登录框，使用用户授权的账户方式完成登录。密码、短信验证码、cookie 不进入项目代码或采集文件。
3. 若关键词未收录且提示购买创建词条，停止该词查询并记录付费依赖，不购买。本次“AI客服”遇到此提示；“人工智能”仅用于验证免费行业背景取数，不替代AI客服具体需求。
4. 在趋势研究页面核对关键词、日期范围、地区和设备口径。读取“搜索指数概览”整行，保留原始列名，不把指数当搜索人数。
5. 保存 capture JSON：source_id=baidu、title、source_locator、data_period、scope、content、query、retrieved_at。content 记录完整表头与对应数值、限制；不包含账号昵称或登录信息。
6. 将快照导入所选项目：

```powershell
.\.venv\Scripts\python.exe scripts\import_browser_evidence.py data\baidu-capture.json --database data\sabc.db --project 实际项目ID
```

导入后为待核验E0，可在证据详情核验并保存新版本；外部证据最多E1。报告必须引用新证据编号。页面变化、登录失效或权限变化时重新检查，不能套用上次数值。
