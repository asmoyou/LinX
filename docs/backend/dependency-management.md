# 依赖管理系统 (Dependency Management System)

代码执行沙盒的依赖管理系统，支持自动检测、缓存和安装依赖包。

## 概述

依赖管理系统解决了代码执行中的包依赖问题，提供：

1. **自动检测** - 从代码中自动识别需要的依赖包
2. **智能缓存** - 缓存已安装的依赖，加速后续执行
3. **按需安装** - 在沙盒中动态安装缺失的依赖
4. **多语言支持** - 支持 Python (pip) 和 Node.js (npm)

## 架构设计

```
┌─────────────────────────────────────────────────────────┐
│           CodeExecutionSandbox                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │         DependencyManager                         │  │
│  │  ┌────────────────┐  ┌────────────────────────┐  │  │
│  │  │ DependencyDetector │  │  DependencyCache    │  │  │
│  │  │ - Python AST   │  │  - Hash-based keys  │  │  │
│  │  │ - JS Regex     │  │  - TTL management   │  │  │
│  │  └────────────────┘  └────────────────────────┘  │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │   Docker Container     │
              │   - pip install        │
              │   - npm install        │
              │   - Cached layers      │
              └────────────────────────┘
```

## 核心组件

### 1. DependencyDetector (依赖检测器)

自动从代码中检测依赖：

**Python 依赖检测**：
- 使用 AST (抽象语法树) 解析代码
- 识别 `import` 和 `from ... import` 语句
- 过滤标准库模块
- 提取第三方包名

```python
# 示例代码
import requests
from pandas import DataFrame
import numpy as np

# 检测结果：
# - requests
# - pandas
# - numpy
```

**JavaScript 依赖检测**：
- 使用正则表达式匹配
- 识别 `import ... from '...'` 语句
- 识别 `require('...')` 语句
- 过滤相对路径导入

```javascript
// 示例代码
import axios from 'axios';
const express = require('express');

// 检测结果：
// - axios
// - express
```

### 2. DependencyCache (依赖缓存)

基于哈希的缓存系统：

**缓存键生成**：
```python
# 依赖集合
dependencies = {
    "requests==2.28.0",
    "pandas==1.5.0",
    "numpy==1.23.0"
}

# 生成缓存键
cache_key = sha256(sorted(dependencies)).hexdigest()[:16]
# 结果: "a3f5c8d9e2b1f4a7"
```

**缓存结构**：
```json
{
  "cache_key": "a3f5c8d9e2b1f4a7",
  "dependencies": [
    {"name": "requests", "version": "2.28.0", "language": "python"},
    {"name": "pandas", "version": "1.5.0", "language": "python"}
  ],
  "installed_at": "2024-02-04T10:30:00",
  "image_tag": "linx-deps:a3f5c8d9e2b1f4a7"
}
```

**缓存策略**：
- TTL (Time-To-Live): 24小时默认
- 自动清理过期条目
- 持久化到磁盘 (`/tmp/linx_dependency_cache/`)

### 3. DependencyManager (依赖管理器)

统一的依赖管理接口：

**主要功能**：
1. 检测代码依赖
2. 检查缓存状态
3. 生成安装脚本
4. 管理缓存生命周期

## 工作流程

### 完整执行流程

```
1. 代码提交
   ↓
2. 依赖检测
   - 解析代码
   - 识别导入语句
   - 提取包名
   ↓
3. 缓存查询
   - 生成缓存键
   - 检查是否已缓存
   ↓
4a. 缓存命中          4b. 缓存未命中
   - 使用缓存镜像        - 创建新沙盒
   - 快速启动            - 生成安装脚本
   ↓                     - 执行安装
5. 代码执行              - 缓存结果
   ↓                     ↓
6. 返回结果          5. 代码执行
                        ↓
                     6. 返回结果
```

### Python 依赖安装

```bash
#!/bin/bash
set -e

echo "Installing Python dependencies..."

# 创建 requirements.txt
cat > /tmp/requirements.txt <<'EOF'
requests==2.28.0
pandas==1.5.0
numpy==1.23.0
EOF

# 使用 pip 安装
pip install --no-cache-dir -r /tmp/requirements.txt

echo "Python dependencies installed successfully"
```

### Node.js 依赖安装

```bash
#!/bin/bash
set -e

echo "Installing Node.js dependencies..."

# 使用 npm 安装
npm install --no-save axios express lodash

echo "Node.js dependencies installed successfully"
```

## 使用示例

### 基本用法

```python
from virtualization.code_execution_sandbox import get_code_execution_sandbox

# 创建沙盒（启用依赖管理）
sandbox = get_code_execution_sandbox(
    enable_dependency_management=True
)

# 执行代码（自动检测和安装依赖）
code = """
import requests
import pandas as pd

response = requests.get('https://api.example.com/data')
df = pd.DataFrame(response.json())
print(df.head())
"""

result = await sandbox.execute_code(
    code=code,
    language='python'
)
```

### 显式指定依赖

```python
# 显式指定依赖版本
result = await sandbox.execute_code(
    code=code,
    language='python',
    explicit_dependencies=[
        'requests==2.28.0',
        'pandas==1.5.0',
        'numpy==1.23.0'
    ]
)
```

### 检查缓存状态

```python
from virtualization.dependency_manager import get_dependency_manager

dep_manager = get_dependency_manager()

# 检测依赖
dependencies = dep_manager.get_dependencies(
    code=code,
    language='python'
)

# 检查是否已缓存
is_cached = dep_manager.is_cached(dependencies)
print(f"Dependencies cached: {is_cached}")

# 获取缓存的镜像
if is_cached:
    image_tag = dep_manager.get_cached_image(dependencies)
    print(f"Cached image: {image_tag}")
```

## 性能优化

### 1. Docker 层缓存

利用 Docker 的层缓存机制：

```dockerfile
# 基础镜像（很少变化）
FROM python:3.11-slim

# 安装常用依赖（缓存层）
RUN pip install --no-cache-dir \
    requests pandas numpy scipy

# 应用代码（经常变化）
COPY code.py /app/
```

### 2. 依赖预热

预先安装常用依赖：

```python
# 常用 Python 包
COMMON_PYTHON_PACKAGES = [
    'requests', 'pandas', 'numpy', 'scipy',
    'matplotlib', 'scikit-learn', 'pillow'
]

# 常用 Node.js 包
COMMON_NODE_PACKAGES = [
    'axios', 'lodash', 'express', 'moment'
]
```

### 3. 缓存预加载

启动时加载缓存：

```python
# 在系统启动时
dep_manager = get_dependency_manager()
dep_manager._load_cache()  # 从磁盘加载缓存

# 定期清理过期缓存
dep_manager.clear_expired_cache()
```

## 缓存管理

### 缓存位置

```
/tmp/linx_dependency_cache/
├── dependency_cache.json    # 缓存索引
└── images/                  # Docker 镜像缓存
    ├── a3f5c8d9e2b1f4a7/
    └── b2c4d6e8f0a2c4d6/
```

### 缓存清理

```python
# 手动清理过期缓存
dep_manager.clear_expired_cache()

# 清理所有缓存
dep_manager.cache.clear()
dep_manager._save_cache()
```

### 缓存统计

```python
# 查看缓存统计
print(f"Total cache entries: {len(dep_manager.cache)}")

for key, entry in dep_manager.cache.items():
    print(f"Key: {key}")
    print(f"  Dependencies: {len(entry.dependencies)}")
    print(f"  Installed: {entry.installed_at}")
    print(f"  Expired: {entry.is_expired()}")
```

## 配置选项

### 环境变量

```bash
# 缓存目录
DEPENDENCY_CACHE_DIR=/var/cache/linx/dependencies

# 缓存 TTL（小时）
DEPENDENCY_CACHE_TTL=24

# 启用依赖管理
ENABLE_DEPENDENCY_MANAGEMENT=true

# 预安装常用包
PREINSTALL_COMMON_PACKAGES=true
```

### 配置文件

```yaml
# config.yaml
dependency_management:
  enabled: true
  cache_dir: /var/cache/linx/dependencies
  cache_ttl_hours: 24
  
  # 预安装的包
  preinstall:
    python:
      - requests
      - pandas
      - numpy
    javascript:
      - axios
      - lodash
      - express
  
  # 安装超时
  install_timeout_seconds: 300
  
  # 最大缓存大小
  max_cache_entries: 100
```

## 故障排查

### 常见问题

**1. 依赖检测失败**

```python
# 问题：无法解析代码
# 解决：检查代码语法

try:
    dependencies = detector.detect_python_dependencies(code)
except SyntaxError as e:
    print(f"Syntax error: {e}")
    # 使用显式依赖
    dependencies = explicit_deps
```

**2. 安装超时**

```python
# 问题：依赖安装时间过长
# 解决：增加超时时间或使用镜像源

# 使用国内镜像
pip_config = """
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
"""
```

**3. 缓存失效**

```python
# 问题：缓存频繁失效
# 解决：增加 TTL 或固定版本号

# 使用固定版本
explicit_dependencies = [
    'requests==2.28.0',  # 固定版本
    'pandas==1.5.0',
]
```

### 调试日志

```python
import logging

# 启用详细日志
logging.basicConfig(level=logging.DEBUG)

# 查看依赖检测过程
logger = logging.getLogger('virtualization.dependency_manager')
logger.setLevel(logging.DEBUG)
```

## 最佳实践

### 1. 使用固定版本

```python
# ✅ 推荐：固定版本
dependencies = [
    'requests==2.28.0',
    'pandas==1.5.0'
]

# ❌ 不推荐：不固定版本
dependencies = [
    'requests',  # 版本不确定
    'pandas'
]
```

### 2. 预热常用依赖

```python
# 在基础镜像中预装常用包
# Dockerfile
FROM python:3.11-slim
RUN pip install requests pandas numpy
```

### 3. 监控缓存命中率

```python
# 记录缓存命中情况
cache_hits = 0
cache_misses = 0

if dep_manager.is_cached(dependencies):
    cache_hits += 1
else:
    cache_misses += 1

hit_rate = cache_hits / (cache_hits + cache_misses)
print(f"Cache hit rate: {hit_rate:.2%}")
```

### 4. 定期清理缓存

```python
# 定时任务清理过期缓存
import schedule

def cleanup_cache():
    dep_manager.clear_expired_cache()

# 每天凌晨 2 点清理
schedule.every().day.at("02:00").do(cleanup_cache)
```

## 性能指标

### 缓存命中 vs 未命中

| 场景 | 首次执行 | 缓存命中 | 提升 |
|------|---------|---------|------|
| 小型依赖 (1-3个包) | ~10s | ~2s | 5x |
| 中型依赖 (4-10个包) | ~30s | ~2s | 15x |
| 大型依赖 (10+个包) | ~60s | ~2s | 30x |

### 存储开销

| 缓存条目数 | 磁盘占用 | 内存占用 |
|-----------|---------|---------|
| 10 | ~50MB | ~1MB |
| 50 | ~250MB | ~5MB |
| 100 | ~500MB | ~10MB |

## 未来改进

### 计划功能

1. **Docker 镜像缓存**
   - 为每个依赖集合创建 Docker 镜像
   - 使用镜像标签管理版本
   - 支持镜像推送到私有仓库

2. **依赖冲突检测**
   - 检测版本冲突
   - 提供解决建议
   - 自动选择兼容版本

3. **增量安装**
   - 只安装新增的依赖
   - 复用已有的依赖
   - 减少安装时间

4. **分布式缓存**
   - 支持 Redis 缓存
   - 多节点共享缓存
   - 提高缓存命中率

## 参考资料

- [Python AST 文档](https://docs.python.org/3/library/ast.html)
- [Docker 层缓存](https://docs.docker.com/build/cache/)
- [pip 缓存机制](https://pip.pypa.io/en/stable/topics/caching/)
- [npm 缓存机制](https://docs.npmjs.com/cli/v9/using-npm/cache)

## 相关文档

- [代码执行沙盒](./code-execution-sandbox.md)
- [容器管理](./container-management.md)
- [资源限制](./resource-limits.md)
