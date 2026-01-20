# LinX - 数字员工管理平台

LinX 是一个企业级数字员工管理平台，用于管理和协调 AI 智能体和未来的机器人员工。

## 项目概述

LinX 建立了一个数字化公司结构，通过分层任务管理、协作智能体协调和全面的知识管理，实现自主目标完成。

## 核心特性

- 🤖 **智能体管理**: 基于 LangChain 的 AI 智能体框架
- 📋 **分层任务管理**: 自动将高层目标分解为可执行任务
- 🧠 **多层记忆系统**: 智能体记忆、公司记忆和用户上下文
- 📚 **知识库**: 企业文档和知识的集中管理
- 🔒 **隐私优先**: 本地 LLM 部署，数据完全私有化
- 🐳 **容器化部署**: Docker 和 Kubernetes 支持
- 🌐 **跨平台支持**: Linux、macOS、Windows

## 技术栈

### 后端
- **框架**: FastAPI
- **智能体**: LangChain
- **主数据库**: PostgreSQL
- **向量数据库**: Milvus
- **对象存储**: MinIO
- **消息总线**: Redis
- **LLM**: Ollama (主要), vLLM (高性能)

### 前端
- **框架**: React 19 + TypeScript
- **构建工具**: Vite
- **样式**: TailwindCSS
- **图标**: Lucide React
- **图表**: Recharts
- **流程图**: React Flow

### 基础设施
- **容器化**: Docker
- **编排**: Docker Compose / Kubernetes
- **监控**: Prometheus + Grafana
- **日志**: ELK Stack / Loki

## 快速开始

### 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+
- Node.js 18+
- Git

### 安装步骤

1. 克隆仓库
```bash
git clone https://github.com/asmoyou/LinX.git
cd LinX
```

2. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，配置必要的环境变量
```

3. 启动服务（开发环境）
```bash
docker-compose up -d
```

4. 初始化数据库
```bash
docker-compose exec api python scripts/init_db.py
```

5. 访问应用
- 前端: http://localhost:3000
- API 文档: http://localhost:8000/docs

## 项目结构

```
LinX/
├── backend/              # 后端服务
│   ├── api/             # API 网关
│   ├── agents/          # 智能体框架
│   ├── tasks/           # 任务管理
│   ├── memory/          # 记忆系统
│   ├── knowledge/       # 知识库
│   └── skills/          # 技能库
├── frontend/            # 前端应用
│   ├── src/
│   │   ├── components/  # React 组件
│   │   ├── pages/       # 页面
│   │   ├── services/    # API 服务
│   │   └── utils/       # 工具函数
│   └── public/          # 静态资源
├── infrastructure/      # 基础设施配置
│   ├── docker/         # Docker 配置
│   ├── kubernetes/     # K8s 配置
│   └── scripts/        # 部署脚本
├── docs/               # 文档
└── tests/              # 测试

```

## 开发指南

### 后端开发

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.main:app --reload
```

### 前端开发

```bash
cd frontend
npm install
npm run dev
```

### 运行测试

```bash
# 后端测试
cd backend
pytest

# 前端测试
cd frontend
npm test
```

## 部署

### Docker Compose (开发/测试)

```bash
docker-compose -f docker-compose.yml up -d
```

### Kubernetes (生产)

```bash
kubectl apply -f infrastructure/kubernetes/
```

## 文档

- [需求文档](.kiro/specs/digital-workforce-platform/requirements.md)
- [设计文档](.kiro/specs/digital-workforce-platform/design.md)
- [任务清单](.kiro/specs/digital-workforce-platform/tasks.md)
- [API 文档](http://localhost:8000/docs) (启动后访问)

## 安全性

- 所有敏感数据在本地处理
- 支持本地 LLM 部署
- 数据加密（传输中和静态）
- 容器隔离和沙箱执行
- 基于角色的访问控制 (RBAC)

## 许可证

[待定]

## 贡献

欢迎贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详情。

## 联系方式

- GitHub: https://github.com/asmoyou/LinX
- Issues: https://github.com/asmoyou/LinX/issues

## 致谢

感谢所有为这个项目做出贡献的开发者。
