# 评估与实际证据

执行命令：`python scripts/verify.py`；`python scripts/evaluate.py --mode mock`。完整测试结果见 [test-results](../examples/test-results.json)，案例断言见 scripts/evaluate.py 的 check 函数。时间、模型、状态均由实际运行产生，不手填成功日志。

最终本地结果：19 项测试通过；11 组离线案例断言通过。真实接口案例尚未通过；即便某条因接口错误返回 failed，也不会被错误计为“保存失败场景通过”，评估会检查实际是否触发了保存工具的故障注入。新增诊断测试确认只输出白名单错误码，不泄露原始响应正文。

## 六项验收映射

- 正常排期：输入 [normal](../examples/inputs/normal.json)，[离线结果与 Trace](../examples/mock/normal.json)，预期 completed、草稿保存成功、18:00。
- 信息缺失：[输入](../examples/inputs/missing_metadata.json)，[离线结果](../examples/mock/missing_metadata.json)，预期补查后 needs_info，不保存。
- 规则风险：[输入](../examples/inputs/rule_risk.json)，[离线结果](../examples/mock/rule_risk.json)，预期 blocked，不保存。
- 时段冲突：[输入](../examples/inputs/slot_conflict.json)，[离线结果](../examples/mock/slot_conflict.json)，预期建议 19:00、needs_confirmation、提案保存但不占位。
- 重复提交：[输入](../examples/inputs/duplicate.json)，[离线结果](../examples/mock/duplicate.json)，预期首次与第二次 draft_id 相同、总草稿数 1；首次执行在 first_execution。
- 保存失败：[输入](../examples/inputs/save_failure.json)，[离线结果](../examples/mock/save_failure.json)，预期 failed、saved=false，无虚报保存。

更多实际离线案例：changed_occupancy（18/19 已占用，建议 20 点）；supplement_recovery（补查成功）；confirmed_alternative（明确确认后可占位）；read_failure（首次读取失败，恢复）；all_slots_occupied（有限候选窗口无空位时未完成）。汇总见 [mock evaluation](../examples/mock/evaluation.json)。

自动化额外检查：伪造确认参数、模型虚报成功、未审核保存、保存前新增占用、跨请求本地占用、幂等键输入冲突、调用上限、无时区及非规范时间、模型结构异常、接口失败不回退 Mock、数据库触发器中止后事务回滚、规则改动生效。测试只证明代码约束，不证明真实模型决策质量。

## 当前真实模型状态

最新 normal 请求返回 HTTP 429，见 [normal](../examples/live/normal.json) 和 [本次 live evaluation](../examples/live/evaluation.json)。随后独立最小请求实际诊断返回 error.type=insufficient_quota、error.code=credit_balance_exhausted，说明额度耗尽，未继续批量请求。该诊断通过隐藏终端输入使用进程内密钥，未写入仓库。

[slot_conflict](../examples/live/slot_conflict.json)、[save_failure](../examples/live/save_failure.json) 仍是此前 HTTP 401 的历史失败证据，本轮未重跑；最新 evaluation 仅包含本轮 normal。不能宣称真实模型 ReAct 验收通过。

获得有效接口后运行 README 的 live 命令。至少核对 normal 与 slot_conflict 两条模型路径：相同素材由于占用结果不同，后续保存参数和确认状态不同；再核对保存失败没有被包装成功。评估程序自动断言业务输出，但人工仍需检查 reason 是否与观察一致、是否实际有模型调整动作。

## 失败、改进与限制

首次测试在系统临时目录遇到访问限制；同时发现 SQLite 连接上下文并不自动关闭连接，已加显式关闭并在可写权限环境复跑。另修复重复案例在首次运行失败时生成自引用 JSON 的问题。时间规范化问题通过严格 ISO 格式校验解决，避免相同时间不同字符串被误认为变更。

有限模拟测试不是对真实素材审核准确率的评估；不提供通过率或业务收益外推。真实接口认证、真实模型决策及 GitHub 提交状态未完成时必须在交付中明确说明。
