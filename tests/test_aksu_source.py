import httpx
import pytest

from sabc.local_sources import fetch_local, parse_query


def fetch(payload):
    def handler(request):
        assert request.url.params['start'] == '2025年1季度'
        assert request.url.params['end'] == '2025年4季度'
        return httpx.Response(200, json=payload)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        return fetch_local(client, 'aksu/gdp:2025')


def sample():
    return dict(titleList=['2025年1季度', '2025年2季度'], sczzList=['372.43', '812.27'],
                dycyList=['15.62', '72.06'], decyList=['145.69', '318.18'], dscyList=['211.12', '422.02'])


def test_preserves_reported_period_unit_and_cumulative_limitation():
    result = fetch(sample())
    assert result['facts']['rows'][1]['地区生产总值'] == '812.27'
    assert result['facts']['unit'] == '亿元'
    assert '不能相加' in result['limitation']
    assert '不代表新疆全区' in result['limitation']
    assert '2025年2季度' in result['period']


@pytest.mark.parametrize('field,value', [
    ('titleList', ['2024年1季度', '2024年2季度']),
    ('titleList', ['2025年1季度', '2025年1季度']),
    ('titleList', []), ('sczzList', ['372.43']),
    ('sczzList', ['', '812.27']), ('sczzList', ['NaN', '812.27']),
    ('sczzList', [True, '812.27']),
])
def test_rejects_mismatched_periods_missing_or_invalid_values(field, value):
    data = sample()
    data[field] = value
    with pytest.raises(ValueError):
        fetch(data)


def test_query_cannot_supply_arbitrary_url():
    with pytest.raises(ValueError):
        parse_query('aksu/https://example.com')
