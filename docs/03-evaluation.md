# 评估与实际证据

执行命令：`python scripts/verify.py`；`python scripts/evaluate.py --mode mock`。完整测试结果见 [test-results](../examples/test-results.json)，案例断言见 scripts/evaluate.py 的 check 函数。时间、模型、状态均由实际运行产生，不手填成功日志。

最终结果：22 项自动化测试通过；11 组离线案例通过；10 组真实模型案例通过，覆盖全部六项必须验收。真实模型是智谱官方免费 glm-4-flash-250414。保存失败案例的 failed 是预期业务结果，断言同时检查是否真正调用了保存工具并触发故障注入，接口错误不会被误判为该场景通过。

真实批次原始记录为 [glm4-final evaluation](../examples/glm4-final/evaluation.json)，unrun_cases 为空；examples/live 为该批次便捷副本，后续复跑会覆盖。评估脚本只对本批已运行案例计数。

## 六项验收映射

- 正常排期：[输入](../examples/inputs/normal.json)、[真实输出与 Trace](../examples/glm4-final/normal.json)、[离线结果](../examples/mock/normal.json)。实际 completed，草稿保存成功，建议原要求 18:00。
- 信息缺失：[输入](../examples/inputs/missing_metadata.json)、[真实输出](../examples/glm4-final/missing_metadata.json)、[离线结果](../examples/mock/missing_metadata.json)。实际补查后仍缺 owner，needs_info，不保存。
- 规则风险：[输入](../examples/inputs/rule_risk.json)、[真实输出](../examples/glm4-final/rule_risk.json)、[离线结果](../examples/mock/rule_risk.json)。实际版权状态 unknown，规则阻断，模型 finish blocked，不保存。
- 时段冲突：[输入](../examples/inputs/slot_conflict.json)、[真实输出](../examples/glm4-final/slot_conflict.json)、[离线结果](../examples/mock/slot_conflict.json)。实际原 18:00 占用后，模型改用可用 19:00 保存建议；needs_confirmation，pending_hard_requirement_change，不占位。
- 重复提交：[输入](../examples/inputs/duplicate.json)、[真实输出](../examples/glm4-final/duplicate.json)、[离线结果](../examples/mock/duplicate.json)。实际首次与第二次 draft_id 相同，总草稿数 1；first_execution 保留第一次真实模型轨迹。
- 保存失败：[输入](../examples/inputs/save_failure.json)、[真实输出](../examples/glm4-final/save_failure.json)、[离线结果](../examples/mock/save_failure.json)。实际保存工具返回 INJECTED_SAVE_DRAFT_FAILURE，模型结束，failed、saved=false，无虚报保存。

更多实际离线案例：changed_occupancy（18/19 已占用，建议 20 点）；supplement_recovery（补查成功）；confirmed_alternative（明确确认后可占位）；read_failure（首次读取失败，恢复）；all_slots_occupied（有限候选窗口无空位时未完成）。汇总见 [mock evaluation](../examples/mock/evaluation.json)。

自动化额外检查：伪造确认参数、模型虚报成功、未审核保存、保存前新增占用、跨请求本地占用、幂等键输入冲突、调用上限、无时区及非规范时间、模型结构异常、接口失败不回退 Mock、数据库触发器中止后事务回滚、规则改动生效。测试只证明代码约束，不证明真实模型决策质量。

## 模型动态决策与改进验证

正常与冲突两条路径使用相同素材和规则，但工具时段结果不同，模型实际 save_draft.suggested_at 分别为 18:00 与 19:00；变更占用案例在 18:00 和 19:00 均占用时实际改选 20:00。上述变化由真实接口返回的动作产生，不是 Mock 或固定日志。参见 [changed_occupancy](../examples/glm4-final/changed_occupancy.json)。

信息不足时，模型真实调用 read_material(supplement=true) 后重新审核；无补充记录则 needs_info，有补充记录则继续排期。参见 [supplement_recovery](../examples/glm4-final/supplement_recovery.json)。精确 confirmed_at 的替代时间能形成 confirmed 草稿，见 [confirmed_alternative](../examples/glm4-final/confirmed_alternative.json)。读取失败后模型重试一次并完成，见 [read_failure](../examples/glm4-final/read_failure.json)。

修正前证据保留：[GLM-4.7 首批](../examples/history/glm-first-batch/evaluation.json)、[延长超时后的失败](../examples/history/glm47-retry/evaluation.json)、[GLM-4 格式错误实验](../examples/glm4-experiment/evaluation.json)、[中文说明调整前的首批结果](../examples/history/glm4-initial/evaluation.json)。最后一批曾有规则风险动作缺字段、补查恢复跳过补查等失败。改进后使用单一中文工具契约、明确观察中的工具名、拒绝不合规动作并请求模型修正格式，整批复跑才得到 10/10；没有手工改写失败日志。

复现：`python scripts/run_free.py`，在隐藏提示处输入自己的智谱密钥；输出到 examples/live。网络瞬时限流/格式纠错事件可在 provider_events 核查。服务不可用会停止并列出未运行案例，不承诺每次重跑都通过。

## 失败、改进与限制

首次测试在系统临时目录遇到访问限制；同时发现 SQLite 连接上下文并不自动关闭连接，已加显式关闭并在可写权限环境复跑。另修复重复案例在首次运行失败时生成自引用 JSON 的问题。时间规范化问题通过严格 ISO 格式校验解决，避免相同时间不同字符串被误认为变更。

有限合成案例不代表真实素材审核准确率，不外推业务收益。部分模型 reason 对重试次数的文字描述不准确；read_failure 的实际工具观察仅有一次读取失败和一次成功重试，以结构化观察、保存事实和参数为准。原型仍存在元数据审核覆盖有限、免费服务限流和模型非确定性的限制。
