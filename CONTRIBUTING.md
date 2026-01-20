# 贡献指南

感谢你对 LinX 项目的关注！我们欢迎所有形式的贡献。

## 如何贡献

### 报告问题

如果你发现了 bug 或有功能建议：

1. 在 [Issues](https://github.com/asmoyou/LinX/issues) 中搜索是否已有相关问题
2. 如果没有，创建一个新的 Issue
3. 清楚地描述问题或建议
4. 如果是 bug，请提供复现步骤

### 提交代码

1. Fork 这个仓库
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交你的更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启一个 Pull Request

### 代码规范

#### Python 代码

- 遵循 PEP 8 规范
- 使用 Black 格式化代码
- 使用 type hints
- 编写文档字符串

```bash
# 格式化代码
black backend/

# 检查代码风格
flake8 backend/

# 类型检查
mypy backend/
```

#### TypeScript/React 代码

- 遵循 ESLint 配置
- 使用 Prettier 格式化代码
- 使用 TypeScript 严格模式

```bash
# 格式化代码
npm run format

# 检查代码风格
npm run lint

# 类型检查
npm run type-check
```

### 提交信息规范

使用语义化的提交信息：

- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档更新
- `style:` 代码格式调整
- `refactor:` 代码重构
- `test:` 测试相关
- `chore:` 构建/工具相关

示例：
```
feat: 添加智能体模板功能
fix: 修复任务分解时的空指针异常
docs: 更新 API 文档
```

### 测试

在提交 PR 之前，请确保：

- 所有现有测试通过
- 为新功能添加测试
- 测试覆盖率不降低

```bash
# 后端测试
cd backend
pytest

# 前端测试
cd frontend
npm test
```

### 文档

- 更新相关文档
- 为新功能添加使用示例
- 保持 README 和 API 文档同步

## 开发环境设置

### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 前端

```bash
cd frontend
npm install
```

### 数据库

```bash
docker-compose up -d postgres redis minio milvus
```

## 项目结构

请遵循现有的项目结构：

```
backend/
├── api/          # API 端点
├── agents/       # 智能体框架
├── tasks/        # 任务管理
├── memory/       # 记忆系统
├── knowledge/    # 知识库
└── tests/        # 测试

frontend/
├── src/
│   ├── components/  # 可复用组件
│   ├── pages/       # 页面组件
│   ├── services/    # API 服务
│   └── utils/       # 工具函数
└── tests/           # 测试
```

## 行为准则

- 尊重所有贡献者
- 保持专业和友好
- 接受建设性的批评
- 关注对项目最有利的事情

## 问题？

如有任何问题，请：

- 查看 [文档](./docs)
- 在 [Issues](https://github.com/asmoyou/LinX/issues) 中提问
- 联系维护者

再次感谢你的贡献！
