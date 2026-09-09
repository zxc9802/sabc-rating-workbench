# 新加坡服务器数据采集测试

测试包只包含当前地方数据采集器、测试程序及依赖清单。不包含应用数据库、模型密钥或浏览器快照。无需部署 Next.js、启动应用或配置模型。

## Linux 服务器运行（Python 3.10 及以上）

将 `sabc-server-probe.zip` 上传到服务器的空目录，运行：

```bash
unzip sabc-server-probe.zip
cd sabc-server-probe
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m scripts.probe_server_data
```

若提示没有 venv，Ubuntu/Debian 可安装 `sudo apt-get update`、`sudo apt-get install -y python3-venv unzip` 后重试。其他发行版使用对应包管理器。

先测几个地区：

```bash
.venv/bin/python -m scripts.probe_server_data --regions fujian,shandong,shenzhen --retries 0
```

再执行默认命令测试全部30个地区入口。程序按地区顺序请求；暂时性网络或服务端故障在其他地区首轮结束后最多重试3次。403、412、429、证书错误、跳转、开放属性不符和空数据会记录原因并跳过，不重复冲击。请求默认超时15秒，一次目录查询包含多个HTTP请求，总耗时可能数分钟。可用 `--timeout 30` 调整。无需开放服务器入站端口，仅需出站HTTP/HTTPS和DNS。

## 查看结果

每次运行生成独立 `server-probe-results/时间/` 目录：

- `summary.csv`：地区、状态、实际记录数、目录名称、统计期间、耗时和失败原因。
- `report.json`：最终结果、来源链接、请求状态、记录哈希和预览限制。
- `attempts.jsonl`：每次尝试即时落盘；中途停止时可据此定位阻塞。

`success` 表示该次查询取得有效记录，不是仅首页返回200。`network_error` 表示网络/TLS/超时，`http_error` 表示服务器拒绝或错误，`no_usable_data` 表示无匹配、跳转、非公开或无实际记录，`format_changed` 表示返回结构不符合采集器预期。退出码0表示所选查询全部通过，1表示存在失败，2表示参数错误；有失败时报告仍会保存。

程序直连目标网站，不读取HTTP_PROXY等环境代理，不读取已登录浏览器，保留TLS证书验证，不保存原始记录值。确保命令实际在新加坡服务器执行；本机成功不能证明新加坡出口可用。若部署应用使用容器或其他代理网络，应在相同网络环境中再测。

30个入口不等于30个独立平台（福建地市共享省级平台）。测试使用各地区一个已知查询，只证明该查询在当时可用，不能证明所有目录均可调用或持续稳定。每次新请求仍可能取得旧年份或部分预览数据。杭州、广州快照及未接通的上海单独列为 `not_integrated`，不算成功。

将本次 `report.json` 和 `summary.csv` 发回即可进一步判断哪些来源可在云端使用；本工具不需要SSH密码或模型密钥。
