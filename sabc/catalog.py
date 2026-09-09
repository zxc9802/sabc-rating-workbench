SOURCES = [
    ('stats','国家统计局','宏观与行业环境','https://data.stats.gov.cn/','官方文章正文；交互查询待接'),
    ('miit','工信部','产业收入与增长','https://www.miit.gov.cn/gxsj/index.html','官方移动站文章正文'),
    ('local','地方公共数据','区域经营环境','https://data.sd.gov.cn/portal/index','已实现地区接口可自动取数；预览非全量，详细地区与限制见采集入口'),
    ('cninfo','巨潮资讯','竞品财报与风险','https://www.cninfo.com.cn/','已知公告PDF网址；检索待接'),
    ('gsxt','企业信用公示','工商与经营异常','https://www.gsxt.gov.cn/','当前访问受阻，待复测'),
    ('law','国家法律法规库','法规与经营边界','https://flk.npc.gov.cn/','公开检索'),
    ('patent','国家知识产权局','专利与技术壁垒','https://ipdps.cnipa.gov.cn/','需已有账号或实名注册'),
    ('baidu','百度指数','搜索需求趋势','https://index.baidu.com/','浏览器采集后导入；非自动接口'),
    ('douyin','抖音指数','内容与话题趋势','https://creator.douyin.com/','浏览器采集后导入；非自动接口'),
    ('trends','Google Trends','海外需求趋势','https://trends.google.com/','热门RSS；历史曲线需浏览器'),
    ('worldbank','World Bank','人口与宏观指标','https://api.worldbank.org/v2/','公开API'),
    ('github','GitHub','开源生态与活跃度','https://api.github.com/','公开API'),
    ('sec','SEC EDGAR','美国公司披露','https://data.sec.gov/','公开API'),
    ('apple','Apple Search','App竞品基础信息','https://itunes.apple.com/search','公开API'),
]


def catalog():
    return [dict(id=i,name=n,purpose=p,url=u,access=a,status='pending') for i,n,p,u,a in SOURCES]
