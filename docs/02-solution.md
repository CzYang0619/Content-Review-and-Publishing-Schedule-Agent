# 方案与技术取舍

原生 Python 循环：模型读取当前请求与完整工具观察 → 返回 action/args/reason → 执行工具 → 观察反馈 → 再由模型决策，最多 10 次模型调用、8 次工具调用；单次 HTTP 超时 45 秒。上限可配置但不超过 30；没有无界自动重试。

真实模型使用 Chat Completions JSON object 输出，经客户端验证后执行。业务工具为本地真实函数，模型不可直接修改数据库。模型推理服务是唯一外部调用。无第三方 Agent 框架，避免在有限时间内引入框架状态转换成本。

四个工具：read_material 可选补充查询；check_rules 读取已获取资料并计算风险；query_slots 查询连续三个一小时时段；save_draft 校验审核、已查询时间及当前占用后事务保存。补充信息来自独立 supplements，不能由模型编造。

模型的动态选择包括：补查缺失信息、选择替代时段、工具失败后重试或停止、最终请求确认/阻断。MockModel 是固定规则模拟器，明确不构成模型决策证据。不能将它的日志称为真实 ReAct。

可信边界：模型提出动作，业务层裁决合法性。save_draft 不能接受 confirmed/saved/review_status 等伪造参数；最终成功状态从工具保存结果推导。模型 finish 声称成功但无保存记录时返回 incomplete。自由文本仅在 trace 中作为模型输出记录，不作为可信状态显示。

SQLite 使用 request_id UNIQUE 与输入 SHA-256 指纹实现幂等，confirmed_slot 部分唯一索引防止本地已确认草稿重复占时段。BEGIN IMMEDIATE 包裹保存前冲突复查和 INSERT。事务成功后才返回 saved=true，连接显式关闭。待确认提案不占位；确认通过新请求形成保留历史的新草稿。

Trace 每步保存动作、工具参数、观察结果和简要依据，不请求或记录模型内部思维过程。未保存时无 draft_id；已保存但模型后续异常仍保留真实持久化结果，任务状态可为 failed/incomplete，不能反向抹除成功的保存事实。

历史幂等重放返回原草稿，并标注 availability_revalidated=false；不能把旧审核当成对最新素材和排期的认证。需重新规划时使用新请求 ID。

限制：输入 world 为静态可信快照，外部排期并发变更未实现分布式锁；请求上下文随步骤增长但受上限控制；JSON mode 不能保证所有模型都按 schema 输出，结构错误将明确失败。
