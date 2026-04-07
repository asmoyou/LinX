# 贡献指南

感谢你关注 LinX，也感谢你愿意一起把它做得更好。

为了减少来回沟通，建议先快速阅读这些文件：
- [`AGENTS.md`](AGENTS.md)
- [`CLAUDE.md`](CLAUDE.md)
- [`README.md`](README.md)
- [`LICENSE`](LICENSE)

## 贡献与授权说明

- 欢迎提交 Issue、文档修订、测试补充、Bug 修复和功能改进
- 提交贡献即表示你同意维护者可以将你的提交整合进项目并按仓库当前双许可证方式发布
- LinX 当前采用 `MIT OR Apache-2.0` 双许可证；具体条款以 [`LICENSE`](LICENSE)、[`LICENSE-MIT`](LICENSE-MIT) 和 [`LICENSE-APACHE`](LICENSE-APACHE) 为准

## 如何贡献

### 报告问题

如果你发现了 Bug 或有功能建议：

1. 先在 [Issues](https://github.com/asmoyou/LinX/issues) 中搜索是否已有相关问题
2. 如果没有，再创建新的 Issue
3. 尽量写清楚预期行为、实际行为、复现步骤和运行环境
4. 如果是界面问题，建议附上截图或录屏

### 提交代码

1. Fork 仓库
2. 创建分支，例如：`git checkout -b feat/my-change`
3. 完成修改并自测
4. 提交更改
5. 推送分支并发起 Pull Request

建议使用语义化提交信息：
- `feat:` 新功能
- `fix:` 修复问题
- `docs:` 文档更新
- `refactor:` 重构
- `test:` 测试相关
- `chore:` 工具或流程调整

示例：

```text
feat(skill-library): add skill package validation
fix(project-execution): handle missing lease status
docs: refresh public README and license guide
```

## 开发环境

### 后端

请始终使用项目内虚拟环境 `backend/.venv`。

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python scripts/dev_server.py preflight
```

常用命令：

```bash
cd backend
source .venv/bin/activate
make run
make run-debug
make format
make lint
make type-check
make test
make test-cov
make migrate
```

### 前端

```bash
cd frontend
npm install
```

常用命令：

```bash
cd frontend
npm run dev
npm run lint
npm run type-check
npm run format
npm run test
npm run build
```

### 基础设施

如果你需要本地依赖服务：

```bash
docker compose up -d postgres redis minio etcd minio-milvus milvus
```

或者直接拉起整套本地环境：

```bash
docker compose up -d
```

## 代码规范

### Python

- 遵循 PEP 8
- 使用 Black + isort
- 生产代码尽量补全 type hints
- 与现有模块边界保持一致，不要随意跨域塞逻辑

推荐检查方式：

```bash
cd backend
source .venv/bin/activate
make format
make lint
make type-check
```

### TypeScript / React

- 遵循 ESLint 与 Prettier 约束
- 保持类型定义和页面/状态逻辑同步
- 尽量复用已有组件、hooks 和 stores

推荐检查方式：

```bash
cd frontend
npm run lint
npm run type-check
npm run format
```

## 测试

提交 PR 前，请尽量完成与改动范围相匹配的测试。

### 后端测试

```bash
cd backend
source .venv/bin/activate
make test
```

如需更完整覆盖：

```bash
cd backend
source .venv/bin/activate
make test-cov
```

### 前端测试

```bash
cd frontend
npm run test
```

## 文档同步

如果你的改动影响以下任一内容，请同步更新文档：
- 对外功能描述
- 安装与部署步骤
- 配置项
- API 或页面行为
- 授权说明

至少请检查：
- [`README.md`](README.md)
- [`README_EN.md`](README_EN.md)
- `docs/` 下相关文档

## 项目结构

请尽量遵循现有目录边界：

```text
backend/
├── api_gateway/       # API 网关、路由与中间件
├── agent_framework/   # 智能体框架
├── task_manager/      # 任务协调
├── knowledge_base/    # 知识库
├── user_memory/       # 用户记忆
├── skill_library/     # 技能系统
├── llm_providers/     # 模型提供方接入
└── tests/             # 测试

frontend/
├── src/
│   ├── api/           # API 层
│   ├── components/    # 组件
│   ├── pages/         # 页面
│   ├── stores/        # Zustand 状态管理
│   ├── hooks/         # 自定义 hooks
│   └── types/         # 类型定义
└── tests/             # 测试
```

## 行为准则

- 尊重所有贡献者
- 保持专业、友好、可协作
- 关注问题本身，不做人身攻击
- 接受建设性反馈，也尽量给出可执行建议

## 有问题怎么办

你可以：
- 查看 [`docs/`](docs/)
- 在 [Issues](https://github.com/asmoyou/LinX/issues) 中提问
- 对照 [`README.md`](README.md) 与 [`CLAUDE.md`](CLAUDE.md) 先确认当前约定

再次感谢你的投入，哪怕只是一个小修复，也会让这个项目更稳一点。
