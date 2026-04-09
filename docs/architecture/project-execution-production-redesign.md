# LinX 任务执行域生产级改造方案

## 1. 背景

当前 LinX 的 `project_execution` 已具备任务创建、规划、调度、外部运行时分发、运行工作区和基础详情页，但从生产化角度看，任务域和运行域还没有真正解耦，导致几个问题同时出现：

1. 用户看到的是 `任务`、`运行`、`步骤`、`运行时` 四套对象交错出现，但系统没有明确规定谁是主对象、谁是派生对象。
2. 依赖、交付物、验收标准、评审意见、运行日志很多都落在 `input_payload`、`output_payload`、`runtime_context`、`audit_event` 里，前端只能二次拼装，展示自然会乱。
3. 多任务并发、串行依赖、返工、验收、补证据、重试冷却等关键生产规则没有建成一等模型，只能靠状态名和 payload 约定维持。
4. 前端详情页在 `任务视角` 和 `运行视角` 之间频繁跳转，但后端没有对应的稳定读模型，所以信息层级不清楚。

这份方案参考 `examples-of-reference/agent-company` 的任务状态机、handoff、patchset、依赖和交付验收链路，同时结合 LinX 现有的 FastAPI + SQLAlchemy + React 架构，给出一版适合继续演进为生产系统的改造路径。

## 2. 当前问题诊断

### 2.1 域模型边界不清

当前后端核心实体只有 `ProjectTask`、`ProjectRun`、`ProjectRunStep` 三层，且很多关键业务语义都没有独立建模：

- `ProjectRun.runtime_context` 承担了规划摘要、运行路由、工作区等多种职责。
- `ProjectTask.input_payload/output_payload` 承担了执行模式、验收、依赖、技能、调度原因等多种职责。
- `ProjectRunStep.input_payload` 里再塞了 `acceptance`、`parallel_group`、`dependency_step_ids`。

直接证据：

- 当前运行、任务、步骤模型都把核心业务信息压在 JSON 字段里，而不是一等表结构，见 [backend/database/project_execution_models.py](/Users/youqilin/VIbeCodingProjects/linX/backend/database/project_execution_models.py#L134)。
- 任务启动时，会创建 `task -> plan -> run -> steps`，但所有 step 仍然挂回同一个 task，依赖关系也只写进 `step.input_payload.dependency_step_ids`，见 [backend/project_execution/service.py](/Users/youqilin/VIbeCodingProjects/linX/backend/project_execution/service.py#L577)。

这意味着当前系统并没有真正的：

- 任务依赖表
- 子任务表/任务树
- 交付合同表
- handoff 表
- 评审结果表
- patchset / change bundle 表
- 验收证据表
- 运行尝试表

生产上，这会直接造成两个后果：

1. 状态变化很难做强约束，只能依赖代码约定。
2. 任一页面想展示“为什么卡住”“谁负责下一步”“本轮交付了什么”“验收差什么证据”，都要靠拼装和猜测。

### 2.2 前端在拼领域语义，而不是消费稳定读模型

当前 `ProjectTaskDetail` 和 `RunDetail` 不是直接读取后端定义好的详情视图，而是前端通过多个 skeleton API 聚合，再从 payload 提取字段：

- `buildRunDetailFromSkeleton()` 在前端拼出 timeline、deliverables、executorAssignment、runWorkspaceRoot，见 [frontend/src/api/projectExecution.ts](/Users/youqilin/VIbeCodingProjects/linX/frontend/src/api/projectExecution.ts#L2334)。
- `buildTaskDetailFromSkeleton()` 在前端拼出 metadata、acceptanceCriteria、events、assignedSkillNames，见 [frontend/src/api/projectExecution.ts](/Users/youqilin/VIbeCodingProjects/linX/frontend/src/api/projectExecution.ts#L2407)。
- `getProjectDetailFromSkeleton()`、`getProjectTaskDetailFromSkeleton()`、`getRunDetailFromSkeleton()` 都是前端并发请求基础 CRUD 接口后再做领域聚合，见 [frontend/src/api/projectExecution.ts](/Users/youqilin/VIbeCodingProjects/linX/frontend/src/api/projectExecution.ts#L2593)。

这不是“前端灵活”，而是“后端领域不完整”。结果就是：

- 任何一个字段改名或 payload 结构变化，前端多个地方都要同步猜。
- Timeline 并不是权威事件流，而是前端按规则拼出来的“像时间线的东西”。
- Deliverables 不是真实交付物，而是从多个 payload 里兜底扫描的文件集合。
- 当前还有 fallback seed 逻辑，说明平台本身对这块读模型稳定性没有足够信心。

### 2.3 任务域和运行域混用，导致 UI 信息层级混乱

当前任务页承担了“业务任务 + 执行控制面板”两种职责：

- 任务详情页顶部主按钮是 `Generate Plan + Start Run`，见 [frontend/src/pages/ProjectTaskDetail.tsx](/Users/youqilin/VIbeCodingProjects/linX/frontend/src/pages/ProjectTaskDetail.tsx#L176)。
- 任务详情主体展示的是执行上下文、步骤数、当前步骤、调度元数据，而不是“任务合同、依赖、交付、验收、责任人”。
- 运行详情页又反过来有 `Source task` 卡片和 `Open Task` 操作，见 [frontend/src/pages/RunDetail.tsx](/Users/youqilin/VIbeCodingProjects/linX/frontend/src/pages/RunDetail.tsx#L325)。

因此用户容易产生三个混淆：

1. 我到底是在看“任务”，还是在看“某次运行尝试”？
2. 任务的完成情况是以任务状态为准，还是以 run/step 为准？
3. 交付、验收、日志、运行时到底应该在哪一层看？

### 2.4 依赖和并发只做到步骤级，不足以支持生产级任务编排

当前真正存在的依赖只有 step 级依赖：

- `PlannerStep.depends_on` 和 `parallel_group` 在 planner 层定义，见 [backend/project_execution/model_planner.py](/Users/youqilin/VIbeCodingProjects/linX/backend/project_execution/model_planner.py#L29)。
- 调度器通过 `dependency_step_ids` 判断 step readiness，见 [backend/project_execution/scheduler.py](/Users/youqilin/VIbeCodingProjects/linX/backend/project_execution/scheduler.py#L275)。
- 数据库里没有 task dependency 实体，搜索结果也只剩 step payload 依赖。

这套机制适合“单次 run 内部的步骤流水线”，但不适合生产中的以下场景：

- A 任务依赖 B 任务达到 `approved` 后才能开始
- 父任务拆解出来的子任务默认串行，只有少数子任务可并发
- 某个任务只依赖另一个任务产出的特定 artifact，而不是整个任务完成
- 高优先级任务插队，但不能突破依赖约束
- 同一资源池的并发配额、租约、冷却、重试预算

而 `agent-company` 的参考实现已经把这些规则落到了可校验行为上：

- 任务依赖支持 `required_state`，并阻止未满足依赖的任务被认领，见 [examples-of-reference/agent-company/tests/test_task_priority_dependencies.py](/Users/youqilin/VIbeCodingProjects/linX/examples-of-reference/agent-company/tests/test_task_priority_dependencies.py#L65)。
- 子任务默认按 `subtask_order` 串行推进，前序未通过时后序不能执行，见 [examples-of-reference/agent-company/README.md](/Users/youqilin/VIbeCodingProjects/linX/examples-of-reference/agent-company/README.md#L99)。

### 2.5 质量验收和交付流程没有一等化

当前系统有 acceptance 文本，但没有完整的“交付合同 -> 证据 -> 评审 -> 验收 -> 归档”闭环。

现状问题：

- acceptance 只是 planner 或 payload 里的一段文本，不是结构化清单。
- deliverables 不是受控清单，而是从 payload/artifacts 里做聚合推断。
- reviewer、qa、manager、user acceptance 没有稳定的 stage gate。
- 缺少“这轮为什么退回”的 issue/evidence/attempt 历史。

参考项目已经把这块做成了完整链路：

- 任务描述会被编译成合同，提取 `goal / deliverables / acceptance`，见 [examples-of-reference/agent-company/tests/test_autonomous_delivery_upgrade.py](/Users/youqilin/VIbeCodingProjects/linX/examples-of-reference/agent-company/tests/test_autonomous_delivery_upgrade.py#L43)。
- review 退回会持久化 issue、evidence、attempt，并维护 open issue 数量与 retry strategy，见 [examples-of-reference/agent-company/tests/test_autonomous_delivery_upgrade.py](/Users/youqilin/VIbeCodingProjects/linX/examples-of-reference/agent-company/tests/test_autonomous_delivery_upgrade.py#L59)。
- patchset 是结构化对象，而不是只存一个 commit hash，见 [examples-of-reference/agent-company/tests/test_autonomous_delivery_upgrade.py](/Users/youqilin/VIbeCodingProjects/linX/examples-of-reference/agent-company/tests/test_autonomous_delivery_upgrade.py#L119)。
- 状态流转要求关键阶段必须带 handoff，且事务性落库，见 [examples-of-reference/agent-company/README.md](/Users/youqilin/VIbeCodingProjects/linX/examples-of-reference/agent-company/README.md#L121) 和 [examples-of-reference/agent-company/tests/test_transition_atomicity.py](/Users/youqilin/VIbeCodingProjects/linX/examples-of-reference/agent-company/tests/test_transition_atomicity.py#L35)。

### 2.6 代码结构已有双轨，后续继续叠加只会更乱

当前仓库里 `backend/task_manager` 和 `backend/project_execution` 是两套相近能力并存：

- `task_manager` 还保留了分解、依赖、结果收集、进度跟踪等旧逻辑，见 [backend/task_manager/task_decomposer.py](/Users/youqilin/VIbeCodingProjects/linX/backend/task_manager/task_decomposer.py#L1)。
- `project_execution` 已经复制了一份 `capability_mapper`，并明确说明是从 legacy task_manager 复制过来的，见 [backend/project_execution/capability_mapper.py](/Users/youqilin/VIbeCodingProjects/linX/backend/project_execution/capability_mapper.py#L1)。

这说明现在的任务执行域还处在“从旧任务域迁移到新执行域”的中间态。继续在这两套之上叠加新功能，会让业务语义更分裂。

## 3. 参考项目里值得吸收的设计原则

参考 `agent-company`，我建议吸收下面 6 个原则，而不是照搬它的 SQLite/MVP 形态：

1. 任务状态机和运行状态机必须分开。
2. 关键流转必须有结构化 handoff，而不是靠日志文本。
3. 交付物应该以 patchset/change bundle 为主对象，而不是“最后一次提交”。
4. 依赖必须是一等实体，并支持 required state。
5. 验收标准必须可编译成结构化 contract，并绑定 evidence。
6. 用户动作和系统流转必须分 API、分权限、分审计。

这 6 条在 LinX 里比参考项目更重要，因为你现在的系统已经不仅是本地多 Agent MVP，而是正在向平台态演进。

## 4. 目标设计：任务是主对象，运行是尝试对象

### 4.1 核心原则

生产版建议把领域拆成四层：

1. `WorkItem`：业务任务，用户真正关心的对象。
2. `ExecutionAttempt`：该任务的某一次执行尝试。
3. `ExecutionNode`：该次尝试中的步骤/阶段节点。
4. `Delivery`：交付、评审、证据、验收相关对象。

用一句话定义：

- 任务负责“要做什么、为什么做、做到什么算完成”
- 运行负责“这次怎么执行、执行到了哪一步、卡在哪”
- 交付负责“本轮改了什么、凭什么过、谁接下一棒”

### 4.2 目标对象模型

建议新增或重构为以下实体：

| 实体 | 作用 | 说明 |
|---|---|---|
| `work_items` | 业务任务主表 | 替代当前“task+部分run语义混用” |
| `work_item_dependencies` | 任务依赖边 | 支持 `required_state`、强/弱依赖 |
| `work_item_contracts` | 任务合同版本 | `goal/scope/constraints/deliverables/acceptance/evidence_required` |
| `execution_attempts` | 任务执行尝试 | 每次“启动运行”就是一次 attempt |
| `execution_nodes` | 尝试内节点 | planning/implementation/review/qa/merge/acceptance |
| `handoffs` | 结构化交接 | from/to/stage/status/payload |
| `change_bundles` | 交付变更集 | patchset/base/head/changed_files/artifact_manifest |
| `evidence_bundles` | 证据包 | acceptance checks、测试结果、链接、摘要 |
| `review_issues` | 评审问题 | severity/category/status/acceptance_ref |
| `artifacts` | 交付物表 | 受控的产物目录、类型、归属、验收状态 |
| `domain_events` | 统一事件流 | 替代“前端拼 timeline” |
| `runtime_sessions` | 运行时会话 | external dispatch / sandbox / workspace / ack |

### 4.3 与现有表的关系

为了降低切换风险，不建议一次性删除现有 `ProjectTask/ProjectRun/ProjectRunStep`。

建议采用三阶段兼容：

1. 第一阶段新增新表，旧表继续写。
2. 第二阶段由应用层双写，新 UI 只读新读模型。
3. 第三阶段完成回填后，把旧表退化为兼容层或只读历史层。

## 5. 目标状态机

### 5.1 任务状态机

任务状态只表达“业务交付状态”，不表达运行细节：

```text
draft -> triage -> ready -> in_progress -> in_review -> approved -> pending_acceptance -> completed -> archived
                           |              |
                           |              -> needs_changes
                           -> blocked
                           -> cancelled
```

说明：

- `triage`：补全需求、编译合同、判断是否拆分。
- `ready`：依赖满足，可以进入执行队列。
- `in_progress`：至少有一个活跃 attempt。
- `in_review`：已有交付提交，等待 reviewer/qa/manager。
- `approved`：技术评审通过。
- `pending_acceptance`：等待业务/用户验收。
- `needs_changes`：有问题，但任务不关闭，等待返工。
- `blocked`：被依赖、资源、环境、权限、人工决策阻塞。

### 5.2 执行尝试状态机

尝试状态只表达“本轮运行状态”：

```text
created -> planned -> queued -> running -> waiting_review -> waiting_acceptance -> finished
                                 |             |                   |
                                 |             -> failed_review    -> rejected
                                 -> failed
                                 -> blocked
                                 -> cancelled
```

### 5.3 节点状态机

节点状态用于细粒度调度：

```text
pending -> ready -> leased -> running -> produced -> verified -> done
                               |          |           |
                               |          |           -> failed
                               |          -> blocked
                               -> cancelled
```

### 5.4 动作分层

必须把动作来源分清：

- 用户动作：`accept`, `reject`, `cancel`, `retry`, `archive`
- 系统动作：`claim`, `lease`, `handoff`, `approve`, `merge`, `promote`, `block`
- 运行时动作：`ack`, `progress`, `complete`, `fail`

这点参考 `agent-company` 是正确的：用户动作和系统流转必须分接口分权限。

## 6. 依赖、顺序与并发规则

### 6.1 任务依赖

建议任务依赖建成显式边：

```text
work_item_id -> depends_on_work_item_id
required_state = ready_to_start | approved | completed | accepted
dependency_type = hard | soft | artifact | review
artifact_selector = optional
```

规则：

1. `hard` 依赖未满足时，任务不能进入可认领队列。
2. `approved` 依赖适用于“前序任务技术通过即可继续”。
3. `artifact` 依赖适用于“只需要上游产出某个文件/接口/schema”。
4. 所有依赖变更必须做环检测。

### 6.2 子任务顺序

建议保留参考项目里的 `subtask_order` 思路，但升级为更明确的 `execution_policy`：

- `serial_strict`
- `serial_on_approval`
- `parallel`
- `barrier_after_group`

默认值：

- 父任务拆出来的子任务默认 `serial_on_approval`
- 即前序任务达到 `approved/pending_acceptance/completed` 后，后续子任务才可进入 `ready`

### 6.3 并发与资源池

生产版还需要引入：

- 项目级并发配额
- agent type 并发配额
- runtime host 并发配额
- workspace 锁
- 冷却时间与重试预算

规则建议：

1. 同一 `WorkItem` 默认只能有一个 active attempt。
2. 同一 `ExecutionNode` 只能有一个 lease owner。
3. 同一 workspace 在 merge/acceptance 阶段启用排他锁。
4. 发生连续同 fingerprint 失败时，自动进入 cooldown，等待人工干预。

## 7. 交付、评审与验收流程

### 7.1 任务合同

任务创建或 triage 完成后，必须生成 `contract`：

- `goal`
- `scope`
- `constraints`
- `deliverables[]`
- `acceptance_criteria[]`
- `assumptions[]`
- `evidence_required[]`
- `allowed_surface`

这块可以直接借鉴 `agent-company/task_intelligence.py` 的思路，但需要把结果持久化为正式表，而不是只做运行时推断。

### 7.2 交付物

交付应分三层：

1. `artifact`：实际文件
2. `change_bundle`：一次交付对应的变更集合
3. `delivery_snapshot`：提交给 reviewer/manager/user 的交付快照

最低要求：

- 开发节点完成时必须生成 `change_bundle`
- `change_bundle` 必须含 `base/head`
- 必须记录 `changed_files`
- 必须记录 artifact manifest
- 如有测试/截图/报告，进入 evidence bundle

### 7.3 Review Gate

Review 不是一个状态名，而是一道门：

- 输入：contract + change_bundle + evidence_bundle
- 输出：`approved` 或 `needs_changes`
- 副产物：review issues、risk summary、next actor

建议 reviewer 的输出结构：

```json
{
  "decision": "approve|request_changes",
  "summary": "string",
  "issues": [
    {
      "issue_id": "string",
      "severity": "critical|high|medium|low",
      "category": "correctness|coverage|security|scope|evidence|docs|performance|ux|other",
      "acceptance_ref": "A3",
      "summary": "string",
      "suggestion": "string"
    }
  ],
  "evidence_checks": [],
  "risk_level": "low|medium|high"
}
```

### 7.4 QA Gate

不是所有任务都要独立 QA，但生产版应支持按任务类型或风险等级插入 QA 节点：

- 高频改动路径
- 发布/迁移/权限/支付/数据类任务
- 用户显式开启质量门禁

### 7.5 User Acceptance Gate

用户验收必须结构化：

- 接受：哪些 acceptance 项已满足
- 拒绝：缺哪几项、补充要求是什么
- 结论：通过/退回/部分通过

建议不要只保留一段 `feedback` 文本，而是记录：

- `acceptance_results[]`
- `business_comment`
- `decision`
- `decided_by`
- `decided_at`

## 8. 日志、时间线与可观测性

### 8.1 不要再把 timeline 当成拼装结果

时间线应该由后端基于 typed event 生产，前端只消费。

事件类型建议：

- `work_item.created`
- `contract.compiled`
- `dependency.blocked`
- `attempt.started`
- `node.leased`
- `runtime.acked`
- `artifact.published`
- `handoff.created`
- `review.request_changes`
- `review.approved`
- `acceptance.accepted`
- `acceptance.rejected`

### 8.2 日志要分四类

建议把现在“日志/事件/运行时输出/告警”分开：

1. `Activity Feed`
   业务事件流，给产品/项目负责人看。
2. `Execution Log`
   节点执行日志，给 agent/operator 看。
3. `Runtime Console`
   原始 stdout/stderr，给运维/排障看。
4. `Audit Log`
   权限动作、人工操作、状态变更，给审计看。

### 8.3 统一关联 ID

每条日志/事件都带：

- `project_id`
- `work_item_id`
- `attempt_id`
- `node_id`
- `runtime_session_id`
- `trace_id`

### 8.4 核心指标

建议新增以下指标面板：

- 任务从 `ready -> in_progress` 的排队耗时
- `in_progress -> in_review` 的交付耗时
- `in_review -> approved` 的评审耗时
- `approved -> pending_acceptance` 的交付晋级耗时
- `pending_acceptance -> completed` 的业务验收耗时
- 依赖阻塞总时长
- stale change bundle 数量
- 重试 fingerprint streak
- 未解决 review issue 数

## 9. 前端信息架构改造

### 9.1 主入口改成“任务中心”，运行中心退为“运维中心”

当前最大问题不是样式，而是入口层级。

建议：

- `Projects` 下主要展示 `Task Board`
- `Runs` 页面改名为 `Attempts` 或 `Ops Center`
- 普通用户默认围绕任务工作
- 运行页只服务排障、调度、Host dispatch、重试、工作区查看

### 9.2 任务详情页改为 5 个 Tab

`Task Detail` 推荐改成：

1. `Overview`
   标题、状态、责任人、优先级、下一动作、阻塞原因
2. `Contract`
   目标、范围、交付物、验收标准、假设、证据要求
3. `Dependencies`
   上游依赖、下游影响、当前 readiness、串并行规则
4. `Delivery`
   change bundles、artifacts、review issues、evidence
5. `Execution`
   attempt 列表、最新 attempt、节点状态、运行入口

当前 `ProjectTaskDetail` 里展示的 `Execution context` 和 `Metadata` 不应该成为主内容，而应该下沉到 `Execution` 或 `Ops` 视图。

### 9.3 运行详情页只关注“这次尝试”

`RunDetail` 只保留：

- 尝试状态
- 节点 DAG
- 运行时/dispatch
- workspace
- console
- 本次交付产物

不再重复承载：

- 任务合同
- 业务验收标准
- 项目摘要
- 长期依赖关系

这些都应该返回到任务页。

### 9.4 卡片首页只给“下一步”

任务卡片上建议展示：

- 当前状态
- 当前 owner
- 当前 blocker
- readiness
- 上游未满足依赖数
- 未解决 issue 数
- 最新交付 bundle 状态

而不是只显示 `dependencies: 2` 这种弱信息。

## 10. 后端代码结构改造建议

建议把 `backend/project_execution` 重新整理为下面结构，并逐步吸收 `task_manager` 的旧能力：

```text
backend/project_execution/
├── domain/
│   ├── work_items.py
│   ├── dependencies.py
│   ├── contracts.py
│   ├── attempts.py
│   ├── nodes.py
│   ├── handoffs.py
│   ├── deliveries.py
│   ├── evidence.py
│   ├── issues.py
│   └── state_machine.py
├── application/
│   ├── triage_service.py
│   ├── planning_service.py
│   ├── scheduling_service.py
│   ├── delivery_service.py
│   ├── review_service.py
│   ├── acceptance_service.py
│   └── read_model_service.py
├── infrastructure/
│   ├── repositories/
│   ├── runtimes/
│   ├── workspace/
│   ├── git/
│   ├── events/
│   └── metrics/
├── api/
│   ├── work_items.py
│   ├── attempts.py
│   ├── deliveries.py
│   ├── reviews.py
│   └── ops.py
└── migrations/
```

同时建议：

- `backend/task_manager` 停止继续承载新功能
- 只保留迁移期兼容调用
- 新能力全部进入 `project_execution/domain + application`

## 11. API 设计建议

### 11.1 读接口

不要让前端继续拼细节，直接提供聚合读模型：

- `GET /api/v1/projects/{project_id}/work-items`
- `GET /api/v1/work-items/{work_item_id}`
- `GET /api/v1/work-items/{work_item_id}/graph`
- `GET /api/v1/work-items/{work_item_id}/deliveries`
- `GET /api/v1/work-items/{work_item_id}/attempts`
- `GET /api/v1/attempts/{attempt_id}`
- `GET /api/v1/attempts/{attempt_id}/timeline`
- `GET /api/v1/attempts/{attempt_id}/runtime-console`

### 11.2 写接口

分三类：

1. 用户动作
   - `/work-items/{id}/actions/accept`
   - `/work-items/{id}/actions/reject`
   - `/work-items/{id}/actions/cancel`
2. 系统流转
   - `/work-items/{id}/transitions`
   - `/attempts/{id}/nodes/{node_id}/handoff`
3. 运行时回调
   - `/runtime-sessions/{id}/ack`
   - `/runtime-sessions/{id}/progress`
   - `/runtime-sessions/{id}/complete`
   - `/runtime-sessions/{id}/fail`

### 11.3 事件推送

WebSocket 推送建议改成 typed channels：

- `work_item.updated`
- `dependency.updated`
- `attempt.updated`
- `node.updated`
- `delivery.updated`
- `issue.updated`
- `runtime_console.chunk`

## 12. 迁移路线图

### Phase 0：语义收敛

目标：先把“任务”和“运行”分清，不动太多底层。

1. 前端文案统一：
   - `Task` = 业务任务
   - `Run` = 运行尝试
2. `RunDetail` 页面标注“这是运行尝试，不是任务”
3. `TaskDetail` 页面加“最新尝试”卡片，不再把执行上下文当主内容
4. 关闭生产环境 fallback seed

### Phase 1：读模型先行

目标：先停止前端拼装。

1. 后端增加 `task detail`、`run detail` 聚合接口
2. Timeline 改由后端生成
3. Deliverables 改由后端从 artifact/change bundle 构建
4. 前端改用新详情接口

### Phase 2：依赖与合同一等化

目标：把最关键的生产规则落表。

1. 新增 `work_item_dependencies`
2. 新增 `work_item_contracts`
3. 子任务顺序和 required_state 进入后端校验
4. claim/readiness 统一走 dependency policy

### Phase 3：交付与评审闭环

目标：建立可追溯交付链。

1. 新增 `handoffs`
2. 新增 `change_bundles`
3. 新增 `evidence_bundles`
4. 新增 `review_issues`
5. review gate / acceptance gate 正式上线

### Phase 4：运行时与调度重构

目标：让 attempt/node/runtime 真正解耦。

1. 引入 `execution_attempts`
2. 引入 `execution_nodes`
3. `ProjectRunStep` 迁移为节点兼容层
4. 引入租约、冷却、并发配额、资源池

### Phase 5：体验收口

目标：用户层面真正变清晰。

1. Task Board 成为主入口
2. Run Center 改为 Ops Center
3. Task Detail 五个 tab 完整上线
4. Dependency Graph / Delivery / Review / Acceptance 全部独立成区块

## 13. 每阶段验收标准

### Phase 0 验收

- 用户能明确区分任务和运行尝试
- 任务页不再把运行细节作为主视角

### Phase 1 验收

- 前端不再从多个 CRUD 接口拼 task/run detail
- fallback seed 在生产关闭
- timeline/deliverables 由后端聚合输出

### Phase 2 验收

- 存在显式依赖表
- 后端能阻止不满足依赖的任务进入 ready/claim
- 子任务顺序规则可测

### Phase 3 验收

- 每轮交付都有 change bundle
- review request_changes 会落 issue/evidence/attempt
- acceptance 结果可结构化查询

### Phase 4 验收

- 尝试、节点、运行时会话三层对象可独立查询
- 并发、租约、冷却有统一策略
- 运行日志与业务事件流分离

### Phase 5 验收

- 普通用户围绕任务完成工作，不需要理解运行时内部结构
- 运维/管理员可以在 Ops Center 排障
- 所有关键视图都能回答四个问题：
  - 现在卡在哪
  - 谁负责下一步
  - 差哪些验收项
  - 这轮交付了什么

## 14. 我对当前 LinX 的具体建议

如果你想尽快把“看着乱”变成“能上线给真实团队用”，优先级我建议这样排：

1. 先做后端聚合读模型，停掉前端拼详情。
2. 立刻把任务合同、依赖边、交付 bundle 三个对象落表。
3. 把任务状态机和运行状态机拆开。
4. 让 `Run` 退回为尝试对象，`Task` 成为唯一主对象。
5. 把 review / qa / acceptance 做成真正的 gate，而不是几个散落字段。

如果只做一件事，我建议先做第 1 和第 2 条。因为只要任务合同、依赖和交付 bundle 成为一等对象，前端展示会立刻清楚一大半，后续状态机和调度也有了可靠地基。

## 15. 附：为什么不建议继续在现有结构上“修修页面”

因为这不是单纯 UI 问题，而是领域模型问题。

如果只改页面，不改模型，最终会继续出现：

- 任务页里越来越多“运行态信息”
- 运行页里越来越多“业务态信息”
- 依赖关系继续靠 payload 猜
- 交付物继续靠工作区扫描
- 验收继续靠自由文本
- 日志继续混在一起

这种情况下 UI 再怎么重排，最多只是“短期没那么乱”，不会变成生产级。

真正的解法是：

先把任务域、运行域、交付域分清，再去做展示层。
