# 第六、七次实测回归输入

两个 JSON 来自用户提供的 2026-09-14 测试包，保留原始用户描述、访谈、上传证据及有缺陷的旧评分，用于检查修复前后行为。旧助手结论和旧报告不是新的经营事实。

来源为各 ZIP 内以 `20_` 开头的默认报告 JSON：

| 文件 | 原始报告 SHA256 |
| --- | --- |
| `tripadvisor-review.json` | `6867398d7cc7bcdb6de53ff78307a579f46c6e5134cf0477b1ee4de8055b2523` |
| `duolingo-review.json` | `b1db9a84d17aa1d1cf58d3b03b89828554a68e49f17138cb4d5fdb176836aa9d` |

夹具选取快照中的 project/company/evidence/proposal 和原报告 result，省略存储元数据与重复的旧生命周期历史。以上哈希针对原始导出文件，不能用于校验精简后的夹具。

`test_report_evidence_contract.py` 在真实代码边界运行这些输入。`report_evidence_browser.py` 使用明确的 API 夹具检查显示与修订操作，其截图不代表线上模型的新报告。合成正向来源样本位于 `tests/report_fixtures.py`，用于契约校验，不代表真实商业实绩。
