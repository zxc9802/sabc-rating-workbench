# 主站账号登录

主站 master 注册独立产品 `sabcxm`，保留旧 `sabc`。入口先到子站 `/api/sso/start` 设置浏览器绑定状态，再由主站签发一次性票据。子站后端兑换、核验账号权限，以 HttpOnly Secure Cookie 建立最长 8 小时会话。主站会话有效期使用毫秒时间戳。权限校验最多缓存 15 秒；主站不可用时拒绝数据请求。

部署变量：
- 主站 `SSO_SABCXM_CLIENT_SECRET`：独立随机密钥，至少 32 字符。
- SABC `SABC_AUTH_MODE=sso`
- SABC `SABC_SSO_MAIN_ORIGIN=https://www.qycm.top`
- SABC `SABC_SSO_CLIENT_SECRET`：与主站专用密钥一致。
- SABC `SABC_UI_ORIGIN=https://sabcxm.qycm.top`

数据库位于原数据库目录下 `accounts/<账号ID的SHA256>/sabc.db`，附件位于各自账号目录。保留原数据库但不会分配给任何账号。必须挂载整个 `/data`。后台任务保存账号上下文；模型服务配置由服务端统一管理，账号不能修改共享模型密钥的目标接口。

服务重启会清除本地登录会话，再次通过主站进入即可；项目数据持久保存。无需新增主站数据库表。先部署主站产品注册及配置，再部署子站与 SSO 配置。线上启用 SSO 后旧密码接口不可用。保留非 SSO 模式用于本地开发。

验证：`pytest tests/test_sso.py` 覆盖状态绑定、票据兑换协议、会话撤销、主站故障、账号数据隔离、后台任务上下文与跨账号取消隔离。另需真实浏览器验证主站入口及域名回跳。
