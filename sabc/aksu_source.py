"""Aksu's public GDP chart; preserve reported periods and cumulative values."""
import math
import re


def fetch_gdp(client, year):
    from sabc.local_sources import public_request

    response = public_request(client, 'get', 'https://www.aks.gov.cn/xjcms/api/data/sczz.jsp',
                              params={'start': year + '年1季度', 'end': year + '年4季度'})
    raw = response.json()
    periods = raw.get('titleList')
    series = {'sczzList': '地区生产总值', 'dycyList': '第一产业',
              'decyList': '第二产业', 'dscyList': '第三产业'}
    if not isinstance(periods, list) or not periods or len(periods) > 4:
        raise ValueError('阿克苏接口未返回有效季度记录')
    if len(set(periods)) != len(periods) or any(
            not isinstance(p, str) or not re.fullmatch(year + r'年[1-4]季度', p) for p in periods):
        raise ValueError('阿克苏返回期间与查询年份不一致，未保存证据')
    rows = [{'期间': period} for period in periods]
    for key, label in series.items():
        values = raw.get(key)
        if not isinstance(values, list) or len(values) != len(periods):
            raise ValueError('阿克苏指标与季度记录数量不一致')
        for row, value in zip(rows, values):
            try:
                valid = not isinstance(value, bool) and math.isfinite(float(value))
            except (TypeError, ValueError):
                valid = False
            if not valid:
                raise ValueError('阿克苏指标缺失或格式无效，不能当作零')
            row[label] = value
    limitation = ('阿克苏地区数据，不代表新疆全区。单位亿元，依官网图表说明；'
                  '季度可能为年内累计值，不能相加或当作单季值。仅含返回期间，不能推断项目需求或收益。')
    return dict(title='阿克苏地区生产总值及三次产业', period='；'.join(periods),
                facts={'region': 'aksu', 'rows': rows, 'unit': '亿元', 'retrieved_rows': len(rows),
                       'metadata': {'source_page': 'https://www.aks.gov.cn/sjkf/index.html'},
                       'coverage': '官方图表返回的季度记录'},
                limitation=limitation, locator=str(response.url), response=response)
