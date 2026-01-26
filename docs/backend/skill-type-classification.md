# Skill Type Classification

## Overview

LinX平台支持两大类技能系统，满足不同的使用场景：

1. **LangChain Tools** - 简单、标准化的函数工具
2. **Agent Skills (Claude Code风格)** - 高度自由、完整的项目技能

## 分类架构

```
技能分类
├── LangChain Tools (简单函数)
│   └── langchain_tool
│       - 单个@tool装饰器函数
│       - 存储：数据库inline
│       - 用途：标准化、简单的工具
│
└── Agent Skills (Claude Code风格)
    ├── agent_skill_simple (单文件)
    │   - 单个Python文件
    │   - 存储：数据库inline
    │   - 用途：复杂的单文件技能
    │
    ├── agent_skill_module (多文件模块)
    │   - 多个Python文件
    │   - 存储：MinIO
    │   - 用途：需要辅助文件的技能
    │
    └── agent_skill_package (完整项目)
        - 完整项目结构
        - 存储：MinIO
        - 用途：复杂系统，带依赖、配置、数据
```

## 详细对比

### 1. LangChain Tools

**特点：**
- ✅ 简单、标准化
- ✅ 符合LangChain规范
- ✅ 快速创建和部署
- ✅ 轻量级，无额外依赖
- ❌ 功能相对简单
- ❌ 不支持复杂项目结构

**存储方式：**
- 代码存储在数据库的`code`字段
- `storage_type = "inline"`

**适用场景：**
- 简单的API调用
- 基础计算（计算器）
- 简单的数据处理
- 标准化的工具函数

**示例：**
```python
from langchain_core.tools import tool

@tool
def calculator(expression: str) -> str:
    """Simple calculator."""
    result = eval(expression, {"__builtins__": {}}, {})
    return f"{expression} = {result}"
```

### 2. Agent Skills - Simple (单文件)

**特点：**
- ✅ 比LangChain Tool更灵活
- ✅ 可以有更复杂的逻辑
- ✅ 支持更多参数和配置
- ✅ 仍然是单文件，易于管理
- ❌ 不支持多文件结构

**存储方式：**
- 代码存储在数据库的`code`字段
- `storage_type = "inline"`

**适用场景：**
- 复杂的API客户端
- 高级数据分析
- 文件操作
- 需要错误处理和重试逻辑的功能

**示例：**
```python
from langchain_core.tools import tool
import requests
from typing import Dict, Any, Optional

@tool
def api_call(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: int = 30
) -> str:
    """Advanced HTTP API client with full control."""
    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            json=body,
            timeout=timeout
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.Timeout:
        return f"Error: Request timed out after {timeout} seconds"
    except requests.exceptions.RequestException as e:
        return f"Error: {str(e)}"
```

### 3. Agent Skills - Module (多文件模块)

**特点：**
- ✅ 支持多个Python文件
- ✅ 可以有辅助函数和类
- ✅ 代码组织更清晰
- ✅ 支持模块化设计
- ❌ 需要MinIO存储
- ❌ 部署稍复杂

**存储方式：**
- 完整项目存储在MinIO
- `storage_type = "minio"`
- `storage_path = "skills-storage/{skill_id}/"`

**项目结构：**
```
skills-storage/{skill_id}/
├── main.py              # 入口点，包含@tool函数
├── utils.py             # 辅助函数
├── config.py            # 配置
└── models.py            # 数据模型
```

**适用场景：**
- 需要多个辅助模块的技能
- 复杂的业务逻辑
- 需要代码复用的场景

### 4. Agent Skills - Package (完整项目)

**特点：**
- ✅ 最高灵活性
- ✅ 完整的项目结构
- ✅ 支持自定义依赖
- ✅ 支持配置文件
- ✅ 支持数据文件
- ✅ 支持测试
- ❌ 最复杂的部署
- ❌ 需要manifest文件

**存储方式：**
- 完整项目存储在MinIO
- `storage_type = "minio"`
- `storage_path = "skills-storage/{skill_id}/"`
- 包含`skill.yaml` manifest

**项目结构：**
```
skills-storage/{skill_id}/
├── skill.yaml           # Manifest文件
├── README.md            # 文档
├── requirements.txt     # Python依赖
├── config.yaml          # 配置模板
├── src/                 # 源代码
│   ├── __init__.py
│   ├── main.py         # 入口点
│   ├── scraper.py
│   └── parser.py
├── data/                # 数据文件
│   └── selectors.json
├── tests/               # 测试
│   └── test_scraper.py
└── .env.example        # 环境变量模板
```

**Manifest示例 (skill.yaml):**
```yaml
name: web_scraper_advanced
version: 1.0.0
type: agent_skill_package
description: Advanced web scraper with JavaScript rendering

entry_point: src/main.py
function: scrape_website

interface:
  inputs:
    - name: url
      type: string
      required: true
    - name: selectors
      type: dict
      required: false
  outputs:
    - name: data
      type: dict

dependencies:
  python: ">=3.11"
  packages:
    - requests>=2.31.0
    - beautifulsoup4>=4.12.0
    - selenium>=4.15.0

config:
  timeout: 30
  max_retries: 3

resources:
  cpu: 0.5
  memory: 512Mi
  timeout: 60s

tags:
  - web
  - scraping
```

**适用场景：**
- 复杂的网络爬虫
- ML模型推理
- 需要大量配置的系统
- 需要数据文件的技能
- 需要独立测试的技能

## 选择指南

### 何时使用 LangChain Tool？

- ✅ 功能简单明确
- ✅ 不需要复杂的错误处理
- ✅ 不需要外部文件
- ✅ 符合LangChain标准即可

**例子：** 计算器、简单的文本处理、基础API调用

### 何时使用 Agent Skill Simple？

- ✅ 需要更复杂的逻辑
- ✅ 需要详细的错误处理
- ✅ 需要更多配置选项
- ✅ 但仍然是单文件可以搞定

**例子：** 高级HTTP客户端、复杂数据分析、文件操作

### 何时使用 Agent Skill Module？

- ✅ 需要多个Python文件
- ✅ 需要代码模块化
- ✅ 有辅助函数和类
- ✅ 但不需要外部依赖和配置

**例子：** 多步骤数据处理、复杂业务逻辑

### 何时使用 Agent Skill Package？

- ✅ 需要完整项目结构
- ✅ 需要自定义依赖
- ✅ 需要配置文件
- ✅ 需要数据文件
- ✅ 需要独立测试

**例子：** 网络爬虫、ML模型、复杂系统集成

## 技术实现

### 数据库字段

```python
class Skill(Base):
    skill_id = Column(UUID)
    name = Column(String)
    description = Column(Text)
    
    # 类型分类
    skill_type = Column(String)  # langchain_tool, agent_skill_simple, etc.
    
    # 存储方式
    storage_type = Column(String)  # inline, minio
    storage_path = Column(String)  # MinIO路径（如果storage_type=minio）
    
    # 代码（inline存储）
    code = Column(Text)  # 用于inline存储
    
    # Manifest（package类型）
    manifest = Column(JSONB)  # 解析后的skill.yaml
```

### 存储映射

| Skill Type | Storage Type | Storage Location |
|------------|--------------|------------------|
| `langchain_tool` | `inline` | Database `code` field |
| `agent_skill_simple` | `inline` | Database `code` field |
| `agent_skill_module` | `minio` | MinIO `skills-storage/{id}/` |
| `agent_skill_package` | `minio` | MinIO `skills-storage/{id}/` |

### API端点

```
# 创建技能
POST /api/v1/skills/upload-simple      # LangChain Tool 或 Agent Skill Simple
POST /api/v1/skills/upload-module      # Agent Skill Module
POST /api/v1/skills/upload-package     # Agent Skill Package

# 查询技能
GET  /api/v1/skills                     # 列出所有技能
GET  /api/v1/skills/{id}                # 获取技能详情
GET  /api/v1/skills/templates           # 获取模板列表

# 测试技能
POST /api/v1/skills/{id}/test           # 测试技能执行

# 下载技能（仅MinIO存储）
GET  /api/v1/skills/{id}/download       # 下载完整项目
GET  /api/v1/skills/{id}/readme         # 获取README
```

## 前端UI设计

### 创建技能界面

```
┌─────────────────────────────────────┐
│ 选择技能类型                          │
├─────────────────────────────────────┤
│                                     │
│  ○ LangChain Tool (简单函数)         │
│     快速创建标准化工具                │
│                                     │
│  ○ Agent Skill - Simple (单文件)     │
│     更灵活的单文件技能                │
│                                     │
│  ○ Agent Skill - Module (多文件)     │
│     支持多文件的模块化技能            │
│                                     │
│  ○ Agent Skill - Package (完整项目)  │
│     最高灵活性的完整项目              │
│                                     │
└─────────────────────────────────────┘
```

### 技能卡片显示

```
┌──────────────────────────────────┐
│ 🔧 Web Search                    │
│ [LangChain Tool]                 │
│                                  │
│ Search the internet using        │
│ Tavily API                       │
│                                  │
│ 📦 Storage: Inline               │
│ ⚡ Executions: 1,234             │
└──────────────────────────────────┘

┌──────────────────────────────────┐
│ 🤖 Advanced Scraper              │
│ [Agent Skill - Package]          │
│                                  │
│ Full-featured web scraper with   │
│ JS rendering and data extraction │
│                                  │
│ 📦 Storage: MinIO                │
│ ⚡ Executions: 56                │
│ 📄 Has README, Tests, Config     │
└──────────────────────────────────┘
```

## 迁移路径

### 从简单到复杂

1. **开始：** LangChain Tool
2. **需要更多功能：** 升级到 Agent Skill Simple
3. **需要多文件：** 升级到 Agent Skill Module
4. **需要完整项目：** 升级到 Agent Skill Package

### 向后兼容

- 所有类型都使用`@tool`装饰器
- 所有类型都可以被Agent使用
- 统一的执行接口

## 总结

这个分类系统提供了：

1. **清晰的区分** - LangChain Tool vs Agent Skill
2. **渐进式复杂度** - 从简单到复杂的平滑过渡
3. **灵活性** - 支持从单函数到完整项目
4. **兼容性** - 所有类型都兼容LangChain
5. **可扩展性** - 未来可以添加更多类型

用户可以根据需求选择合适的技能类型，从最简单的LangChain Tool开始，逐步升级到更复杂的Agent Skill Package。
