# 素材审核与发布排期 Agent

小影校招第 1 题。CLI / Python 标准库 / SQLite / 可配置真实模型。大模型不限定服务商，提供智谱免费模型接入入口。

读取素材 → 审核 → 查询时段 → 模型根据观察调整动作 → 保存草稿或说明阻断原因。**只有草稿，没有发布接口。**

## 当前交付状态

- 核心实现、离线验收案例、自动化测试和文档已提供。
- `examples/mock/` 是实际运行的离线记录，仅证明流程与业务约束。
- 最新真实模型尝试返回 HTTP 429，独立最小请求诊断为 `credit_balance_exhausted` / `insufficient_quota`，需要补充 API 额度。历史其他案例的 HTTP 401 失败记录仍保留于 `examples/live/`。**这些记录不是通过的 ReAct 证据，当前版本尚不满足考核的真实模型决策验收。** 接口额度恢复后运行下方 live 评估，生成真实结果。
- GitHub 目标仓库：https://github.com/CzYang0619/Content-Review-and-Publishing-Schedule-Agent 。最终 commit SHA 使用 `git rev-parse HEAD` 核对。
- 已使用 CzYang0619 完成 GitHub 授权并成功上传 main；可克隆仓库运行。早先的账号写权限问题已解决，真实模型接口额度问题仍待解决。

## 环境与运行

Python 3.11+，开发验证使用 Python 3.12.14；无需安装第三方依赖。所有命令在仓库根目录运行。

```bash
python --version
python -m unittest discover -s tests -v
python scripts/verify.py
python scripts/evaluate.py --mode mock
python -m src.cli --input examples/inputs/normal.json --mode mock --db runtime/demo.db --output runtime/result.json
```

Windows 若 `python` 指向 WindowsApps 占位程序，改用已安装的 Python 可执行文件完整路径。

评估脚本每个案例使用独立临时数据库；`duplicate` 会在同一数据库重复提交并保留首次记录。CLI 则持久使用 `--db` 路径，因此同一输入重复运行会返回历史草稿。

## 免费真实模型入口（智谱）

已核对智谱官方 [免费发布公告](https://www.zhipuai.cn/zh/news/148) 和 [GLM-4.7-Flash 文档](https://docs.bigmodel.cn/cn/guide/models/free/glm-4.7-flash)：该模型可免费调用，支持结构化输出。账户资格、实名要求和限流以平台实际提示为准；尚未取得智谱账户密钥，因此本项目尚无该平台成功运行记录。

1. 登录 [智谱 API Key 管理](https://bigmodel.cn/usercenter/proj-mgmt/apikeys)，创建自己的密钥。无需提供 OpenAI 密钥。
2. 在本机终端运行以下命令，按提示粘贴智谱密钥，输入隐藏、不保存文件：

```bash
python scripts/run_free.py --cases normal
```

单案例成功后运行全部目标案例：

```bash
python scripts/run_free.py
```

也可预先设置本机进程环境变量 `BIGMODEL_API_KEY`。启动器固定使用 `https://open.bigmodel.cn/api/paas/v4` 和 `glm-4.7-flash`，忽略已有的其他服务商模型配置。不要选成不同的付费型号（例如 FlashX）。官方免费政策可能调整，不承诺无限调用。成功验收后才能更新当前“未完成真实模型验收”的状态。

## 通用真实模型入口（含 OpenAI）

`.env.example` 只说明变量；程序读取进程环境，不自动加载 `.env`。不要提交真实密钥。

PowerShell：

```powershell
$env:OPENAI_API_KEY = '在本机设置真实密钥'
$env:AGENT_MODEL = 'gpt-4.1-mini'
$env:AGENT_BASE_URL = 'https://api.openai.com/v1'
python scripts/evaluate.py --mode live --cases normal slot_conflict missing_metadata rule_risk duplicate save_failure changed_occupancy supplement_recovery confirmed_alternative read_failure
```

模型名是可配置的接入默认值，不代表当前账户有访问权。兼容服务需要支持 Chat Completions 与 JSON object 输出。真实模式出错不会切换成 Mock。

```bash
python -m src.cli --input examples/inputs/slot_conflict.json --mode live --db runtime/live.db --output runtime/live-result.json
```

退出码：`0` 表示完成或已保存待确认建议；`2` 表示阻断、待补充、失败或未完成。调用方必须读取 JSON 的 `status`，不能将退出码 0 理解为已确认或已发布。

## 输入和输出

输入包含 `request` 与 `world`，完整示例见 `examples/inputs/`。`world` 是合成业务服务快照，**由可信调用方提供**，不是允许模型自行修改的事实。

`request` 字段：`request_id`、`material_id`、`requested_at`、`channel`、`hard_requirement`；可选 `confirmed_at` 表示用户明确同意的替代时间。时间严格使用 `2026-11-10T18:00:00+08:00` 格式，一小时时段。原要求本身视为用户对该时段的授权。

输出包含 `review_status`、`risks`、`suggested_at`、`pending_items`、`confirmation_status`、`draft.saved`、`draft.draft_id`、`status` 和完整 `trace`。`published` 始终为 false。

- 替代硬性时间可保存为 `pending_hard_requirement_change` 提案，不占用时段。
- 用户确认替代时间后，以**新的 request_id** 携带精确 `confirmed_at` 提交；旧草稿保留。
- 已确认草稿在本地 SQLite 中占用对应时段。多请求查询和保存会检查这些占用。
- 相同 request_id 与相同输入返回同一草稿；同 ID 不同输入返回冲突。历史重放不代表当前规则、素材或排期重新审核通过，会明确提示复核。

## 评审建议顺序

1. 运行测试和 mock 评估，查看 `examples/test-results.json` 与 `examples/mock/evaluation.json`。
2. 检查 `normal.json` 与 `slot_conflict.json` 的工具参数、结果与后续决策；注意其 mode 标签。
3. 配置可用模型后运行 live 评估，核验至少两条成功的真实模型动态路径。
4. 修改输入的 `world.schedule` 再提交新请求，或改变 `data/rules.json` 后重跑评估。
5. 重复提交同一请求；核对 draft_id 不变、draft_count 不增长。
6. 检查保存失败返回 `draft.saved=false`，没有“已发布”成功声明。

## 目录

```text
src/                 模型适配、Agent 循环、业务工具和校验
tests/               自动化验收及越权/幂等/事务测试
data/                合成素材与规则
scripts/evaluate.py  生成输入、实际运行、验证输出并保存 Trace
scripts/verify.py    运行测试并写入机器可读记录
examples/inputs/     可复用输入
examples/mock/       离线实际结果（非真实模型证据）
examples/live/       真实接口调用记录（当前认证失败）
docs/                需求、方案、评估、AI 使用与复盘
```

## 设计与已知限制

原生有界循环，无 Agent 框架。模型以 JSON 选择下一动作；程序验证参数、执行工具并把结果送回模型。JSON 格式并不保证业务正确，保存权限由业务层校验。接口格式参考 [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat)。

审核只检查合成元数据和配置词项，不做真实视听内容理解。单时区、整点、一小时时段，不处理任意区间重叠。SQLite 事务保护本地已确认草稿；外部排期是静态快照，未连接真实排期服务。待确认提案不预留时段。生产身份认证、跨服务锁、真实发布、多素材批处理均不在本次范围。
