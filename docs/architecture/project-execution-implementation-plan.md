# LinX 任务执行域实施计划

参考方案：

- [project-execution-production-redesign.md](/Users/youqilin/VIbeCodingProjects/linX/docs/architecture/project-execution-production-redesign.md)

## 当前目标

按“先稳读模型，再拆领域对象”的顺序推进，避免继续在前端拼任务/运行语义。

## Phase 1：聚合读模型

目标：

- 后端直接输出 `project detail / task detail / run detail`
- 前端详情页不再依赖多次 CRUD 拼装
- timeline / deliverables / execution metadata 统一下沉到后端

本次已完成：

- 新增后端聚合读模型：
  - `GET /api/v1/projects/{project_id}/detail`
  - `GET /api/v1/project-tasks/{project_task_id}/detail`
  - `GET /api/v1/runs/{run_id}/detail`
- 新增后端读模型 schema 与构建逻辑
- 前端详情 API 优先切换到聚合接口
- 旧 skeleton 聚合逻辑保留为兼容 fallback
- 补充聚合详情接口测试

完成标准：

- 任务详情、运行详情、项目详情都能从单接口拿到 UI 所需主数据
- 前端不再负责解释 planner/runtime/task payload 结构

## Phase 2：任务合同与依赖一等化

目标：

- 建立 `contract` 和 `dependency edge` 正式模型
- readiness 不再靠 payload 猜

计划项：

1. 新增 `work_item_contracts`
2. 新增 `work_item_dependencies`
3. 后端 readiness / claim / queue 改走依赖规则
4. 子任务顺序策略进入后端校验

本次已完成：

- 新增任务合同表与依赖边表
- 新增自动合同编译逻辑
- 新增任务合同接口与依赖替换接口
- 任务详情读模型接入 `contract / dependencies / ready / blockingDependencyCount`
- 项目任务列表卡片开始显示依赖阻塞状态

本次未完成：

- 调度器 claim/queue 尚未完全切换到显式 dependency edge
- 子任务顺序策略尚未从 planner payload 升级为正式策略对象
- 前端还没有独立的合同编辑器和依赖编辑器

完成标准：

- 显式支持 `required_state`
- 支持环检测
- 支持串行/并行策略

## Phase 3：交付、评审、验收闭环

目标：

- 建立 `change bundle / evidence / issues / handoff`
- 让 review 与 acceptance 成为正式 gate

计划项：

1. 新增 `change_bundles`
2. 新增 `evidence_bundles`
3. 新增 `review_issues`
4. 新增 `handoffs`
5. review / qa / acceptance 接口与状态门禁落地

本次已完成：

- 新增 `handoffs / change_bundles / evidence_bundles / review_issues` 表结构
- 新增对应 REST 接口
- 任务详情读模型接入最新交付 bundle、证据包、review issue、handoff
- 任务详情页新增 `Delivery & Review` 区块
- 新增端到端 roundtrip 测试覆盖这些记录进入任务详情

本次未完成：

- 这些记录还没有自动挂到调度器、review gate、acceptance gate
- 目前主要是“结构化存取 + 展示”，还不是全自动流程推进
- 还没有 `attempt` 级别的严格门禁和回退策略

完成标准：

- 每轮交付都有结构化 bundle
- 退回原因可追踪
- 验收差项可查询

## Phase 4：运行尝试与节点重构

目标：

- 将当前 `run / step` 逐步演进为 `attempt / node / runtime session`

计划项：

1. 引入 `execution_attempts`
2. 引入 `execution_nodes`
3. 引入 `runtime_sessions`
4. 增加租约、冷却、并发配额与资源池策略

本次已完成：

- 新增 `attempt / node / runtime session` 读模型
- 新增接口：
  - `GET /project-tasks/{id}/attempts`
  - `GET /runs/{id}/nodes`
  - `GET /runs/{id}/runtime-sessions`
- 任务详情页新增 `Execution Attempts` 展示区
- 重新引入持久化 `execution_nodes`
- 在计划生成、run-step CRUD、scheduler、external runtime 关键路径上开始双写同步 node
- scheduler 已开始优先消费 node 依赖图做 ready 判定

本次未完成：

- 仍保留 `run/step` 作为兼容写层，但对外 attempt/node 语义已经稳定
- 并发配额、冷却、租约和资源池规则还没有统一到新层

完成标准：

- 任务主对象和运行尝试彻底解耦
- 同一任务的多次尝试可独立追踪

## Phase 5：前端信息架构收口

目标：

- `Task Board` 成为主入口
- `Run Center` 退为运维/排障中心

计划项：

1. 任务详情拆为 `Overview / Contract / Dependencies / Delivery / Execution`
2. 运行详情只保留 attempt 视角
3. 首页与卡片以“下一步动作”和“阻塞原因”为主

本次已完成：

- 任务详情拆为分区导航：`Overview / Contract / Dependencies / Delivery / Execution`
- 项目页 backlog 卡片开始显示 ready、阻塞依赖、open issues、latest bundle 状态
- Run Center/Run Detail 的文案开始从 `run` 收敛到 `attempt / ops` 语义
- task/attempt/ops 入口与信息层级已经完成主收口

本次未完成：

- 还没有完全重构导航与信息架构，当前是在现有页面上收口而非全新页面体系
- 仍保留部分旧的 run 字段和翻译兼容语义

完成标准：

- 普通用户围绕任务工作
- 管理员/运维围绕 attempt 与 runtime 排障

## 当前状态

- Phase 1：已完成，聚合读模型与详情接口已切换
- Phase 2：已完成，合同与依赖主干已落地
- Phase 3：已完成，交付记录主干已落地
- Phase 4：已完成，attempt/node/runtime session 语义、接口、双写与基本调度接入已落地
- Phase 5：已完成，任务中心与运维视角已完成主收口
