# Testing Guide

LinX 后端测试指南

## 测试结构

所有测试文件统一放在 `backend/tests/` 目录下，按类型组织：

```
backend/tests/
├── unit/              # 单元测试 - 测试单个函数/类
├── integration/       # 集成测试 - 测试模块间交互
├── e2e/              # 端到端测试 - 测试完整流程
├── performance/      # 性能测试 - 测试系统性能
├── security/         # 安全测试 - 测试安全漏洞
└── *.py              # 通用测试（config, logging等）
```

## 快速开始

### 运行所有测试

```bash
cd backend
./run_tests.sh
```

### 运行特定类型的测试

```bash
# 只运行单元测试
./run_tests.sh unit

# 只运行集成测试
./run_tests.sh integration

# 只运行端到端测试
./run_tests.sh e2e
```

### 生成覆盖率报告

```bash
# 运行所有测试并生成覆盖率报告
./run_tests.sh --coverage

# 运行单元测试并生成覆盖率报告
./run_tests.sh unit --coverage

# 覆盖率报告会生成在 backend/htmlcov/index.html
```

### 详细输出

```bash
# 显示详细的测试输出
./run_tests.sh --verbose

# 或简写
./run_tests.sh -v
```

### 并行运行测试

```bash
# 使用多核并行运行测试（更快）
./run_tests.sh --parallel

# 或简写
./run_tests.sh -p
```

### 组合选项

```bash
# 运行单元测试，生成覆盖率，详细输出
./run_tests.sh unit --coverage --verbose

# 运行所有测试，并行执行，生成覆盖率
./run_tests.sh --parallel --coverage
```

## 使用 pytest 直接运行

如果你需要更多控制，可以直接使用 pytest：

```bash
cd backend

# 运行所有测试
pytest tests/

# 运行特定目录的测试
pytest tests/unit/

# 运行特定文件的测试
pytest tests/unit/access_control/test_rbac.py

# 运行特定测试函数
pytest tests/unit/access_control/test_rbac.py::test_role_assignment

# 运行匹配特定模式的测试
pytest -k "test_rbac"

# 显示详细输出
pytest -v

# 显示打印语句
pytest -s

# 在第一个失败时停止
pytest -x

# 并行运行（需要 pytest-xdist）
pytest -n auto

# 生成覆盖率报告
pytest --cov=. --cov-report=html --cov-report=term
```

## Commit 前的测试流程

在提交代码前，建议运行以下命令：

```bash
cd backend

# 1. 运行单元测试（快速验证）
./run_tests.sh unit

# 2. 如果单元测试通过，运行所有测试
./run_tests.sh --coverage

# 3. 检查覆盖率报告
# 打开 htmlcov/index.html 查看覆盖率
```

## 编写测试

### 单元测试示例

单元测试应该放在 `tests/unit/<module_name>/` 目录下：

```python
# tests/unit/access_control/test_rbac.py
import pytest
from access_control.rbac import RoleManager, Role

def test_role_assignment():
    """Test role assignment to user."""
    manager = RoleManager()
    user_id = "user-123"
    
    # Assign role
    manager.assign_role(user_id, Role.ADMIN)
    
    # Verify
    assert manager.has_role(user_id, Role.ADMIN)
    assert not manager.has_role(user_id, Role.USER)

def test_role_removal():
    """Test role removal from user."""
    manager = RoleManager()
    user_id = "user-123"
    
    # Setup
    manager.assign_role(user_id, Role.ADMIN)
    
    # Remove role
    manager.remove_role(user_id, Role.ADMIN)
    
    # Verify
    assert not manager.has_role(user_id, Role.ADMIN)
```

### 集成测试示例

集成测试应该放在 `tests/integration/` 目录下：

```python
# tests/integration/test_agent_context_integration.py
import pytest
from types import SimpleNamespace

from agent_framework.runtime_context_service import RuntimeContextService


@pytest.mark.asyncio
async def test_runtime_context_reads_user_memory_and_skills():
    """Test runtime context assembles the reset-era context sources."""
    service = RuntimeContextService()
    service.retrieve_user_memory = lambda **_: [
        SimpleNamespace(content="用户的配偶是王敏", memory_type="user_memory")
    ]
    service.retrieve_skills = lambda **_: [
        SimpleNamespace(content="agent.experience.goal=Stable PDF delivery path", memory_type="skill_experience")
    ]

    user_memories = service.retrieve_user_memory(user_id="user-1", query="配偶", top_k=3)
    skills = service.retrieve_skills(agent_id="agent-1", user_id="user-1", query="pdf", top_k=3)

    assert user_memories[0].content == "用户的配偶是王敏"
    assert skills[0].memory_type == "skill_experience"
```

## 测试最佳实践

1. **测试命名**：使用描述性的测试名称
   - ✅ `test_user_can_login_with_valid_credentials`
   - ❌ `test_login`

2. **测试隔离**：每个测试应该独立运行
   - 使用 fixtures 进行 setup/teardown
   - 不要依赖其他测试的状态

3. **测试覆盖率**：目标是 80% 以上
   - 重点测试核心业务逻辑
   - 测试边界条件和错误处理

4. **使用 fixtures**：复用测试设置
   ```python
   @pytest.fixture
   def user():
       return User(username="test", email="test@example.com")
   
   def test_user_creation(user):
       assert user.username == "test"
   ```

5. **Mock 外部依赖**：使用 mock 隔离外部服务
   ```python
   from unittest.mock import Mock, patch
   
   @patch('llm_providers.openai_provider.OpenAI')
   def test_llm_call(mock_openai):
       mock_openai.return_value.generate.return_value = "response"
       # Test code here
   ```

## 持续集成

项目配置了 GitHub Actions，每次 push 和 PR 都会自动运行测试：

- 单元测试
- 集成测试
- 代码覆盖率检查
- 代码质量检查（flake8, mypy）

确保本地测试通过后再提交代码。

## 故障排查

### 测试失败

1. 查看详细输出：`./run_tests.sh -v`
2. 运行特定失败的测试：`pytest tests/path/to/test.py::test_name -v`
3. 检查测试日志和错误信息

### 导入错误

确保在 backend 目录下运行测试，并且虚拟环境已激活：

```bash
cd backend
source .venv/bin/activate  # macOS/Linux
# 或
.venv\Scripts\activate     # Windows
```

### 数据库连接错误

确保测试数据库正在运行：

```bash
docker-compose up -d postgres
```

### 依赖缺失

安装开发依赖：

```bash
pip install -r requirements-dev.txt
```

## 参考资料

- [pytest 文档](https://docs.pytest.org/)
- [pytest-asyncio 文档](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov 文档](https://pytest-cov.readthedocs.io/)
- [unittest.mock 文档](https://docs.python.org/3/library/unittest.mock.html)
