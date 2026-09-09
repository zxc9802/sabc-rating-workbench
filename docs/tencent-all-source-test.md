# 腾讯云上海：全部自动采集来源验收

本包复用项目生产采集器，包含10类已实现来源、43个示例查询（32个地方入口，以及其他来源11个查询；SEC和法律库各测两种能力）。成功要求采集器解析并保存有效证据，HTTP200或网页截图不算成功。测试输入来自项目已记录的官方查询，并非全部目录覆盖。

企业信用、专利、百度指数、抖音指数尚无自动采集器，报告中单列未实现，不会通过浏览器快照冒充接通。Google Trends只测热门RSS，不含关键词历史曲线。依申请、登录注册来源不在本次范围。

## 运行

需要Linux、Python3.10+、venv；不用Node.js、Next.js、模型密钥或业务数据库。
将压缩包上传到服务器（以下假定为 `/tmp/sabc-all-sources-test.zip`）：

```sh
python3 -m zipfile -e /tmp/sabc-all-sources-test.zip /tmp/sabc-all-test
cd /tmp/sabc-all-test/sabc-all-sources-test
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
nohup .venv/bin/python -u -m scripts.probe_all_sources > probe.log 2>&1 < /dev/null &
```

每一步无报错再运行下一步。后台运行避免网页终端断开影响进度；记录启动时打印的PID。Ubuntu/Debian缺venv时安装与Python版本匹配的系统venv包，其他发行版先核对环境。

```sh
tail -n 15 /tmp/sabc-all-test/sabc-all-sources-test/probe.log
```

出现 `FINISHED PASS 成功数/43` 为整轮结束。日志包含进度与耗时，`all-source-results/时间/` 下保存 `summary.csv`、`report.json`、即时结果 `results.jsonl` 和独立测试数据库 `verification.db`。只需分享 summary.csv 和 report.json。数据库仅保存该次公共取数证据，与真实项目隔离。

两个并发查询，单次HTTP操作超时25秒；生产采集器暂时性连接/服务器错误最多初次加3次重试，403/429等直接暂缓。失败只说明此示例在当时环境不成功，不代表整个来源永久不可用。统计年份和预览限制以证据为准。

可单独复测某些来源：`--sources github,worldbank,sec`。默认使用生产采集器网络设置，部分来源会读取系统代理变量；对比两台服务器时须确认实际网络出口一致于计划部署环境，不应把代理成功误报为直连成功。

## 测试之后

目标是新加坡运行界面和评级逻辑，腾讯云上海统一运行已实现的接口/爬虫采集器。该测试包尚不是对外采集服务，不需要放开任何新增入站端口。通过实测后仍需实现带鉴权的采集服务、新加坡调用适配、总超时、并发控制和部署验收。所有自动来源纳入上海测试，海外来源能否从上海访问也以结果为准。
