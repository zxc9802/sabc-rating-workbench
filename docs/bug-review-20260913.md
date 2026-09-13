# SABC 项目评级工作台 Bug 审查

审查日期：2026-09-13。范围覆盖当前工作区（含未提交改动）的后端、前端与路由口径。本次审查**未改代码**。

## 基线

- Python：385 项测试通过。
- TypeScript：`tsc --noEmit` 无错误。
- 前端 node 测试：6 项通过。
- 未提交改动（`context.py`、`llm.py` 报告校验、`standard.py` 锚点与 `validate_rubric_reasons`、`report_qa.py` 上下文裁剪、`model_router.py` 的 `http_status`）逻辑自洽，对应新测试已覆盖。
- `jobs.py` 取消/删除锁序、`Store` 审计链、SSO 会话刷新未见竞态。

## 建议修复顺序

1. 访谈历史重复拼接（#1），并补生产形状测试。
2. 人工评审表被定时刷新清空（#2）。
3. 仅配置 DeepSeek 时前后端口径不一致（#3）。
4. 其余低优先级项。

---

## 1. 访谈历史被重复拼接（高）

**位置：** `sabc/checkpoints.py`（约 104–109 行）、`sabc/app.py`（约 314 行）

**现象：** `chat_turn` 传给 `analyze()` 的 `messages` 已是完整历史 + 本轮。`normalize()` 又把 `project['messages']` 拼到前面，得到：

```
dialogue = 历史 + 历史 + 新消息
```

拼接点上，第一条用户消息（通常是项目描述）紧跟历史最后一条助手提问。`investment_limit`、`max_loss`、`validation_history` 的 `linked` 判定看 `dialogue[i-1]` 是否为相关提问，会误命中。

**已复现：** 描述写「预算大概 5 万」→ 助手问「总投入上限是多少？」→ 用户答「这个我们还没定」→ 模型把 `investment_limit` 标成 `known`、`quote="5万"` → 被放行为 `verified=true`，随后跳去问战略维度。去掉重复拼接后，同一输入被正确拒绝。

**测试缺口：** 现有 `normalize` 测试按「`messages` 只含新一轮」调用，未覆盖生产形状。`ground_low_scores`（`sabc/standard.py` 约 63 行）有同样双拼，但只做 `in` 判断，当前无害。

**修法：** `normalize` / `ground_low_scores` 只用传入的 `messages`（或在 `_analyze` 调用前去重），并补一条按生产形状调用的测试。

---

## 2. 人工评审表每 60 秒被清空（中）

**位置：** `app/report-panel.tsx`（约 55–64 行）、`app/page.tsx`（约 53 行）

**现象：** 评审表用 `useEffect` 同步 `proposal`，依赖包含 `dimensions`。页面每 60 秒 `reload()` → `setData(fresh)` 产生新数组引用 → effect 触发 → 表单回到已保存值、确认框取消。任何 `refreshProject()` 也会触发。

**影响：** 用户在评审表里填写的八维分数、假设和确认状态会被静默丢弃。

**修法：** 改用稳定依赖（如 `detail.project.id` / `detail.project.updated_at`），或仅在编辑态关闭时从服务端同步。

---

## 3. 仅配置 DeepSeek 时口径不一致（中）

**位置：** `sabc/report_qa.py`（约 14–15 行）、`sabc/model_router.py`（约 65–66 行）

**现象：**

- `public_settings()['configured']` 为 True，访谈可用（`chat_turn` 条件包含 `deepseek()`）。
- `report_qa.answer` 在缺少应用内 `base_url`/密钥且无 mixtoken 时直接拒绝：「报告助手尚未配置模型连接」。
- `routed()` 只在存在 mixtoken 时过滤空 `base_url` 路由；否则每轮先跑一次空地址 primary，再回落 DeepSeek。

**已复现：** `routes tried: [('', ''), ('deepseek-flash', ...)]`，`model_runs` 多一条无意义 failed 记录。

**影响：** 访谈能走 DeepSeek，报告问答不能；审计日志被空路由失败污染。

---

## 4. `/api/health` 定义两次（低）

**位置：** `sabc/app.py`（约 93–95 行、673–675 行）

**现象：** FastAPI 按注册顺序匹配，第一个只返回 `{'status':'ok'}`。带 `rule_version`、`audit_ok` 的第二个是死代码。

**注意：** 直接删除第一个会在 SSO 模式下打坏健康检查——该路径公开、`account_id` 为 None，`store.check_audit()` 经 `AccountStore.scoped()` 会抛 `PermissionError`。若要对外暴露审计校验，须改走 `store.legacy`。

---

## 5. `project_type` 无枚举校验（低）

**位置：** `sabc/llm.py`（约 224 行）、`sabc/app.py`（约 138、196 行）

**现象：** `_analyze` 只过滤 `project_patch` 的键，不校验值；`create_project` / `update_project` 也不校验枚举。模型若把中文类型名写入 `project_patch.project_type`，生成报告时经 `update_project` 落库。

**影响：** `assess` 判 NR 并提示「有效的项目类型」；前端下拉显示空白，用户难以定位原因。

---

## 6. 时区不一致（低）

**位置：**

- `sabc/lifecycle.py`：`today()` 使用 Asia/Shanghai
- `sabc/rating.py`：`date.today()`
- `sabc/report_readiness.py`：`date.today()`
- `sabc/checkpoints.py`：新加的 `dated_sample` 使用 `date.today()`

**影响：** UTC 服务器上，上海时间「今天」完成的测试，在早晨数小时内会被判为未来日期而拒收。

---

## 7. 慢任务 ID 缓存未在中断后清除（低）

**位置：** `lib/types.ts`（约 40–51 行）

**现象：** 慢路径以 `path + body` 哈希作为 job id，存在 `localStorage`。轮询中断时 key 未清除。

**影响：** 下一条**完全相同**的消息会拿回旧任务结果，该条消息静默丢失；再下一次可自愈。

---

## 8. 日期解析错误以 Python 原文返回（低）

**位置：** `sabc/lifecycle.py`（约 168、173 行）

**现象：** `date.fromisoformat('')` 等 `ValueError` 经全局处理器以 422 原样返回。

**影响：** 用户看到 `Invalid isoformat string: ''` 一类提示，而不是可操作的中文说明。

---

## 9. 死代码（清理）

| 项 | 位置 | 说明 |
|---|---|---|
| `initial_job_id` | `sabc/app.py` 约 175、183 行 | 只读不写 |
| `LifecyclePanel` | `app/lifecycle-panel.tsx` | 无引用 |
| `interviewStage` | `lib/interview-history.ts` | 无引用 |

无功能影响，增加维护噪音。

---

## 未见问题

- 本次未提交的报告生成/评分理由校验与答疑上下文裁剪。
- 任务取消与项目删除的锁序。
- 存储审计链、SSO 会话刷新。
