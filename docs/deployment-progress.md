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

- 远端私有仓库已推送并核实`master`=`235d6ffeb80d1b349efe91b47bede8a2f2fe9682`；前端生产构建与TypeScript检查通过。前端静态产物未包含提供的密钥。
- Zeabur独立项目`6aa182f76c3d9581b7157c09`，环境`6aa182f7da9bc245fbb121e9`，服务`6aa184156c3d9581b7157c5b`，名称均为`sabc-rating-workbench`，使用账号已有Tokyo服务器。
- GitHub OAuth提示已绑定另一个Zeabur账号，改为本仓库专用只读SSH Deploy Key接入；私钥仅存本地忽略目录及Zeabur认证表单。没有改变账号绑定。
- 实际调用`gpt-5.6-luna`分析模型成功，返回补充信息问题，未生成评分；这只是连通测试，非第五阶段质量验收。

- 已通过UI确认域名`sabc-rating-workbench.zeabur.app`绑定HTTP8080，环境变量11项已保存为私有，硬盘`sabc-data`挂载`/data`。Dockerfile已保存，首次部署已提交，线上成功尚待验证。

- 首次部署`6aa1850681898898b92bf780`运行成功。HTTPS健康200，匿名bootstrap401，网页登录成功，创建`部署验收-宿迁电商-20260910`（`cb0ac87077b7495691a47c3082cc865c`）。实际网页请求完成规划→取数→模型回答；东京取宿迁HTTP493，模型明确报告无数据且未填预算/试点结果。失败保存在artifacts/phase3；不计采集成功，也不计第五阶段验收。
- 已配置SOURCE_GIT_COMMIT_SHA固定235d6ff、GitHub官方meta接口返回的ED25519主机公钥与strict check，正在重新部署核验构建器是否实际采用这些变量。

- 第二次部署`6aa1868281898898b92bf791`已启动成功；旧Pod已移除，新容器`service-6aa184156c3d9581b7157c5b-67b8787ffb-vjfnw`。实际容器中的app.py/auth.py/planner.py/start_cloud.py SHA256均与235d6ff对应本地文件一致，截图`artifacts/phase3/deployed-code-hashes.png`。
- 重新部署前后项目JSON完全相同（2条对话），网页登录旧会话失效，重新登录后项目记录仍可见。
- 注意：已保存strict SSH与固定SHA环境变量，但尚未取得构建器日志证明采用；不把仅保存环境变量当校验已执行。Git通用部署详情的Commit显示空，使用实际容器文件哈希补充核验。
- 第三阶段基础上线验证完成；第四阶段采集服务和第五阶段质量验收仍未完成。

## 第四阶段：上海采集服务（进行中）

- 已实现TLS+Bearer鉴权服务，独立子进程单任务180秒硬超时，最多2并发。源端最多共3次尝试；远程连接不自动重试，也不退回东京静默取数。
- 每条返回证据标记`collector_region=ap-shanghai`与`collector_job_id`，源端尝试日志回传工作台，外部证据保持level0/unverified。
- 155项本地测试通过，包括远程查询一致性、鉴权、忙碌拒绝、超时杀进程、失败不写证据。
- computer-use上传安装包39.5KB，服务器SHA256与本地一致：137df778d344f7709dcadb72e2dbf2f2045f3aac0f8915c9d6ec8539be9a6f5f。系统Python为3.12.3。
- 安装目标`/opt/sabc-collector`；systemd专用用户`sabc-collector`，状态库`/var/lib/sabc-collector/collector.db`，配置`/etc/sabc-collector`，TLS8443。安装正在执行，尚未核实启动或防火墙。
- 首次启动因安装继承umask077、代码目录不可读而重启；已停止服务，修复仅代码和venv读取权限，并修正安装脚本。00:33:16重新启动后持续运行，uvicorn启动完成、TLS8443监听；密钥仍保留640/root专用组权限。
- computer-use新增TCP8443入站规则，其他规则未更改。信任指定证书的外部健康检查：匿名401、Bearer鉴权200且region=ap-shanghai。
- 上海实际采集宿迁商务统计成功（job 336d222730374cbfa262003f7c8bfc6c，0.8秒），阿克苏2025GDP成功（job 7434c0cc57a04303bda93b5c35eb88a0，1.0秒）；原始返回保存在artifacts/phase4。尚未连接Zeabur，不能计作整链路验收。
- Zeabur部署6aa18b7181898898b92bf7b3运行；云端sources.py、remote_collector.py哈希与db9b35b一致，新增三项采集环境变量已通过computer-use保存。
- 整链路43例完成，41例成功且重新读取项目验证证据、E0/unverified、上海任务ID和source_runs关联。攀枝花3次HTTP500暂缓；Google Trends上海连接失败，180秒硬超时，Zeabur保存504失败记录。报告artifacts/phase4/zeabur-audit。
- 网页阿克苏首次因并发429暂缓，重试成功；UI显示四季度GDP、三次产业、亿元单位及累计/地区限制，证据d981650101984feebd8425b8cf32e3f7对应上海job47ac723f124248f788a0bf0de7fe7d36。失败和成功均留截图。
- 发现Google长请求外层连接约32秒中断，后台到180秒仍正确记录失败。正在修复为持久化后台任务、短连接轮询、同请求编号去重和刷新后恢复结果；尚待新版本线上长请求验证。第四阶段未完成，第五阶段尚未开始。
- ba9a582已推送并通过computer-use更新Zeabur发布配置。生产构建、类型检查及159项后端测试通过。
- 新版网页主动采集Google Trends，任务210f1f64-2f70-465a-b91e-f833095b60ab于00:54:33开始；途中刷新恢复同一任务，00:57:35显示504未取得证据。记录持久保存，原阿克苏证据完全一致。旧版32秒连接中断问题通过后台任务与轮询修复，截图和前后记录在artifacts/phase4/ui-long-job-*。
- 第四阶段执行完成：41/43固定样例取数成功；攀枝花、Google Trends暂缓，浏览器/未实现能力单列docs/shanghai-collection-results.md，不宣称全渠道可用。

## 第五阶段：网页质量与Bug验收（进行中）

- 已冻结标准v1、20组60例主集、8例独立留出集；SHA256保存在artifacts/phase5/frozen-sha256.txt。模型回答与人工规则回归分开计分，不以规则样例冒充模型回答质量。
- 正式案例尚未执行，不能宣称达标。后续逐例记录UI输入、回答、评分、失败及修复版本。
- 首例G01-1已完成实际网页创建→访谈→宿迁取数→事实核对→建议确认→NR报告，项目b9eeb2ec85ee446fb052b927208b8162，报告ba735cc575c8409d81d4c9dc91f91082。四维90/95/90/90，12条原子事实核对正确；说明和扣分理由见artifacts/phase5/G01-1/review.json。当前1/60，留出0/8，下一例G01-2。尚未计算总体达标或稳定性。
- G01-2失败，原版本ba9a582：选源理由把零售总额用于估算可触达商家数量；模型还建议以摘要覆盖原名称/描述并遗漏原事实。未确认这份不合格建议，原项目输入尚保留。两个问题与原回答/截图保存在artifacts/phase5/G01-2。
- 修复中：规划与分析提示明确宏观总量不能推算主体/客户数；后端禁止模型patch覆盖name/description，保留结构化字段提取。新增原始输入保全回归。待线上重跑原冻结案例，G01-1也需受影响回归；不能把原先单例通过当最终通过。
- 修复版本5525f39已在Zeabur部署6aa1948081898898b92bf7d4运行，160项后端测试通过。computer-use读取容器llm.py/planner.py SHA256均与本地提交一致，截图artifacts/phase5/deployed-5525f39.jpg；正在进行网页回归。
- G01-2 R1已通过网页回归两项原缺陷：回复明确不能推算商家数，核对保存后名称/完整描述/20000元预算保持不变；检查条件生成NR报告f157967fb295457ca3d16824cc74534a。但下一步维度仅65分：主要追问，缺可执行验证与通过/失败/停止条件，记QA5-003，仍不通过。没有模型proposal，未把网页默认评审表当模型输出。
- 已继续补充模型输出要求：不足以评级也必须给可执行资料收集/验证步骤，沿用已有目标、周期、预算解释通过和停止条件；未知阈值待负责人确认，不编造数字或批准投入。待部署与原案例再次回归。
