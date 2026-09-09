# SABC 项目评级工作台

Next.js 中文前端 + FastAPI 规则服务 + 本机 SQLite。当前已实现公司基线版本、项目资料与引导问答、模型建议接入、八维确定性评分、证据、报告快照与 JSON 导出。完整目标仍在执行，14类渠道尚未全部接通。

## 启动

需要 Node.js 20.9+ 和 Python 3.11+。在本目录安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd install
```

分别在两个终端运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn sabc.app:app --host 127.0.0.1 --port 18765
```

```powershell
npm.cmd run dev
```

打开 http://127.0.0.1:3000 。默认数据在 `data/sabc.db`，备份时停止后端并复制整个 data 目录。`SABC_DB` 可指定独立验收数据库。

## 使用

1. 填写公司战略、团队、预算和现金安全线，由负责人确认后保存。
2. 新建项目并填写项目描述。未配置模型时按字段引导补齐资料；这不是模型动态访谈。
3. 在模型设置填 OpenAI 兼容服务地址（包含 /v1 等实际前缀）、模型名和密钥。密钥通过 Windows DPAPI 加密存储，不返回浏览器。配置保存不代表模型已实际验证。
4. 上传资料、记录证据或调用官方数据接口，核对来源、期间、适用范围和核验状态。
5. 在报告页核对评分建议及反方意见，确认后由规则程序计算等级。新增事实或证据后重新评估，旧报告保留当时快照。

资料不足为 NR；外部信息不能替代项目直接验证；高业务分仍受证据封顶。已接入并真实调用 OpenLux 的 gpt-5.6-luna，访谈请求已通过。真实公司基线与历史案例尚未提供，实际经营决策准确率尚未验证。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd run typecheck
npm.cmd run build
```

当前78项测试通过。接口说明和真实取数记录见 [数据接入说明](docs/source-integration.md)。多地区取数、浏览器快照与暂缓项见 [地方数据接入](docs/local-data.md)。测试数据库内所有公司与项目评分均为验收素材，不得用作真实经营依据。

历史案例批量回测见 [回测说明](docs/backtest.md)。

真实模型对抗检查可运行 `.\.venv\Scripts\python.exe scripts/verify_model_adversarial.py`。该命令使用本机已配置模型，进行4次真实请求，结果保存到 `data/model-adversarial-result.json`；测试素材为合成案例，失败或缺少评分建议会原样记录，不生成替代结果。
