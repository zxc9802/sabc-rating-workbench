# Goal v2 部署记录

## 第二阶段：已完成只读核实

2026-09-09，通过computer-use操作既有Ego Lite和腾讯云OrcaTerm。

- 实例：`lhins-rrt80w5q`，上海四区，公网`118.25.107.69`，内网`10.0.0.16`。
- 系统：Ubuntu Server 24.04 LTS x86_64，4核4GB，60GB系统盘，5Mbps带宽。
- 实测根盘59GB，可用47GB；内存3723MB，可用约3003MB，swap1987MB未使用。
- `sudo -n ss -lntp`显示22/SSH及127.0.0.53、127.0.0.54上的53/DNS；未发现Web TCP监听。
- Git和Node存在；未发现docker/nginx/caddy可执行文件。
- 登录方式：既有TAT免密登录，ubuntu可使用sudo -n。本轮未重置密码或创建SSH密钥。
- 默认python3位于`/home/ubuntu/.hermes/hermes-agent/venv/bin/python3`，版本3.11.15。第四阶段必须使用系统Python新建独立采集虚拟环境，不安装进Hermes环境。
- 活跃服务为系统服务、SSH和腾讯云TAT等，未停止或修改任何服务。
- 证据截图：`artifacts/phase2-server-services.png`。
- 防火墙开通和实际采集服务部署仍属第四阶段，尚未执行。

## 第三阶段：进行中

待通过computer-use建立GitHub私有仓库、接入Zeabur并完成环境与持久化配置。尚无线上项目完成证据。

### 2026-09-10 私有仓库与上线配置

- 已通过 computer use 创建并确认 Private：`https://github.com/zxc9802/sabc-rating-workbench`，仓库初始为空。
- 新增单用户登录、HttpOnly/Secure会话、登录频率限制、跨站写入拒绝、会话退出/过期/密码轮换失效。云启动缺少密码或HTTPS域名时拒绝启动。
- 新增Docker独立构建，Next前端对外8080，Python后端仅127.0.0.1:18765，数据库`/data/sabc.db`，必须挂载持久化硬盘。
- 已通过150项Python测试；前端构建与线上验收待完成。
- Zeabur中存在旧sabc服务，本次新仓库应独立部署，避免覆盖。
