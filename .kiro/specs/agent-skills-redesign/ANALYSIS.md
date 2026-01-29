# Agent Skills Structure Analysis - CORRECTED

## Executive Summary

经过深入分析 Moltbot 和 Claude Code 的源码，我现在完全理解了 Agent Skills 的正确结构：

**核心理解：Agent Skills = 指令文档（SKILL.md）+ 可执行工具（scripts/或src/）**

- **SKILL.md**：教 agent **如何使用**工具的 SOP（标准操作流程）
- **可执行代码**：预先写好的工具，agent **调用执行**

---

## 1. Moltbot 的实际结构

### 统计数据
- 总共 54 个 skills
- 60 个 markdown 文件（SKILL.md + 文档）
- 15 个可执行文件（Python, Shell, JavaScript）

### 实际示例

#### 示例 1：openai-image-gen（简单脚本模式）
```
openai-image-gen/
├── SKILL.md           # 教 agent 如何生成图片
└── scripts/
    └── gen.py         # 完整的图片生成工具（300+ 行）
```

**SKILL.md 内容：**
- 描述如何运行 `scripts/gen.py`
- 提供命令行参数示例
- 说明输出格式

**scripts/gen.py：**
- 完整的可执行 Python 脚本
- 调用 OpenAI API
- 生成图片和 HTML 画廊

#### 示例 2：local-places（完整包模式）
```
local-places/
├── SKILL.md           # 教 agent 如何搜索地点
├── SERVER_README.md   # 服务器文档
├── pyproject.toml     # Python 包配置
└── src/               # 完整的 FastAPI MCP 服务器
    └── local_places/
        ├── __init__.py
        ├── main.py          # FastAPI 应用
        ├── google_places.py # Google Places API 客户端
        └── schemas.py       # Pydantic 模型
```

**SKILL.md 内容：**
- 描述如何启动服务器
- 提供 API 端点示例
- 说明请求/响应格式

**src/ 代码：**
- 完整的 FastAPI 服务器
- Google Places API 集成
- 数据验证和错误处理

#### 示例 3：bitwarden（带辅助资源）
```
bitwarden/
├── SKILL.md           # 教 agent 如何使用 bw CLI
├── scripts/
│   └── bw-session.sh  # 辅助脚本：解锁 vault
└── references/
    └── templates.md   # jq 模板参考
```

**SKILL.md 内容：**
- 描述如何使用 `bw` CLI
- 提供常见操作示例
- 引用 `scripts/bw-session.sh` 和 `references/templates.md`

**scripts/bw-session.sh：**
- Bash 脚本，解锁 Bitwarden vault
- 设置环境变量

**references/templates.md：**
- jq 模板示例
- 详细的 API 文档

---

## 2. Claude Code 的实际结构

### 统计数据
- 多个 plugins
- 25 个可执行文件（Python, TypeScript, Shell）
- Skills 主要是纯指令文档

### 实际示例

#### 示例 1：hookify plugin
```
hookify/
├── skills/
│   └── writing-rules/
│       └── SKILL.md       # 教 agent 如何编写 hookify 规则
├── hooks/                 # 可执行的 hook 脚本
│   ├── userpromptsubmit.py
│   ├── stop.py
│   ├── pretooluse.py
│   └── posttooluse.py
├── core/                  # 核心引擎代码
│   ├── rule_engine.py
│   └── config_loader.py
├── matchers/              # 匹配器代码
└── utils/                 # 工具函数
```

**SKILL.md 内容：**
- 教 agent 如何编写 hookify 规则
- 提供规则语法和示例
- 纯指令文档，不包含可执行代码

**hooks/ 代码：**
- Python 脚本，实现 hook 功能
- 读取规则文件
- 执行规则引擎

**core/ 代码：**
- 规则引擎实现
- 配置加载器
- 完整的 Python 包

#### 示例 2：frontend-design skill
```
frontend-design/
└── skills/
    └── frontend-design/
        └── SKILL.md       # 教 agent 如何设计前端
```

**SKILL.md 内容：**
- 纯指令文档
- 设计原则和指南
- 不包含可执行代码（因为 agent 直接生成代码）

---

## 3. 关键发现

### 发现 1：Agent Skills 包含可执行代码

**Moltbot：**
- 15 个可执行文件（Python, Shell, JavaScript）
- 大多数复杂 skills 都有 scripts/ 目录
- 有些 skills 有完整的 Python 包（src/）

**Claude Code：**
- 25 个可执行文件（Python, TypeScript, Shell）
- Plugins 包含大量可执行代码
- Skills 可以是纯指令，也可以引用 plugin 的代码

### 发现 2：config.yaml 不是标准做法

**Moltbot：**
- ❌ 没有 config.yaml 文件
- ✅ 配置通过环境变量
- ✅ 配置说明在 SKILL.md 中

**Claude Code：**
- ❌ 没有 config.yaml 文件
- ✅ 配置通过 frontmatter 或环境变量

### 发现 3：目录结构

**Moltbot 使用：**
- `scripts/` - 可执行脚本
- `src/` - 完整的 Python 包
- `references/` - 参考文档
- ❌ 没有 `assets/` 目录

**Claude Code 使用：**
- `hooks/` - Hook 脚本
- `core/` - 核心代码
- `skills/` - Skill 文档
- `utils/` - 工具函数
- ❌ 没有 `assets/` 目录

**Moltbot skill-creator 文档提到：**
- `scripts/` - 可执行代码
- `references/` - 参考文档
- `assets/` - 输出资源（模板、图片等）

---

## 4. 正确的理解

### Agent Skills 的组成

```
┌─────────────────────────────────────────┐
│         Agent Skill Package             │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  SKILL.md (指令文档)              │  │
│  │  - 教 agent 如何使用工具          │  │
│  │  - 提供使用示例                   │  │
│  │  - 说明配置方法                   │  │
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  可执行代码                       │  │
│  │  - scripts/ (Python, Shell, etc.) │  │
│  │  - src/ (完整的 Python 包)        │  │
│  │  - Agent 调用执行                 │  │
│  └──────────────────────────────────┘  │
│                                         │
│  ┌──────────────────────────────────┐  │
│  │  可选资源                         │  │
│  │  - references/ (参考文档)         │  │
│  │  - assets/ (输出资源)             │  │
│  └──────────────────────────────────┘  │
│                                         │
└─────────────────────────────────────────┘
```

### 与 LangChain Tools 的区别

| 特性 | Agent Skills | LangChain Tools |
|------|-------------|-----------------|
| **核心** | SKILL.md + 可执行代码 | Python 函数 + @tool 装饰器 |
| **用途** | 教 agent 如何使用工具 | 直接执行的工具 |
| **结构** | 包（多个文件） | 单个 Python 文件 |
| **调用方式** | Agent 读取指令后调用脚本 | Agent 直接调用函数 |
| **灵活性** | 高（可以包含任何工具） | 低（仅 Python 函数） |

---

## 5. 推荐的模板结构

### 模式 1：简单脚本模式（推荐用于大多数 skills）

```
skill-name/
├── SKILL.md           # 指令文档（必需）
├── README.md          # 包文档（可选）
├── requirements.txt   # Python 依赖（如果有 Python 代码）
├── scripts/           # 可执行脚本
│   ├── main.py
│   ├── helper.py
│   └── setup.sh
└── references/        # 参考文档（可选）
    └── api-docs.md
```

**适用场景：**
- 简单的工具脚本
- 独立的命令行工具
- 不需要复杂包结构

**示例：openai-image-gen, bitwarden**

### 模式 2：完整包模式（推荐用于复杂 skills）

```
skill-name/
├── SKILL.md           # 指令文档（必需）
├── README.md          # 包文档（可选）
├── pyproject.toml     # Python 包配置
├── src/               # 完整的 Python 包
│   └── skill_name/
│       ├── __init__.py
│       ├── main.py
│       ├── api.py
│       └── utils.py
└── references/        # 参考文档（可选）
    └── api-docs.md
```

**适用场景：**
- 复杂的 Python 包
- MCP 服务器
- 需要模块化结构

**示例：local-places**

### 模式 3：混合模式（推荐用于多种工具）

```
skill-name/
├── SKILL.md           # 指令文档（必需）
├── README.md          # 包文档（可选）
├── requirements.txt   # Python 依赖
├── scripts/           # 简单脚本
│   ├── quick_check.py
│   └── setup.sh
├── src/               # 复杂包
│   └── skill_name/
│       └── api.py
├── references/        # 参考文档
│   └── api-docs.md
└── assets/            # 输出资源（可选）
    └── template.html
```

**适用场景：**
- 既有简单脚本又有复杂包
- 需要多种类型的工具
- 需要输出资源（模板、图片等）

---

## 6. 当前 LinX 模板的问题和修正

### 当前结构
```
agent_skill_template/
├── SKILL.md           # ✅ 正确
├── README.md          # ✅ 正确
├── config.yaml        # ❌ 应该移除
├── requirements.txt   # ✅ 正确
├── utils.py           # ⚠️ 应该在 scripts/ 或 src/
└── weather_helper.py  # ⚠️ 应该在 scripts/ 或 src/
```

### 问题分析

1. **config.yaml**
   - ❌ 不是标准做法
   - ❌ Moltbot 和 Claude Code 都不使用
   - ✅ 应该移除，配置说明放在 SKILL.md 中

2. **Python 代码位置**
   - ⚠️ utils.py 和 weather_helper.py 在根目录
   - ✅ 应该组织在 scripts/ 或 src/ 目录中

3. **缺少目录结构**
   - ❌ 没有 scripts/ 目录
   - ❌ 没有 references/ 目录
   - ❌ 没有清晰的组织结构

### 推荐的修正（模式 1：简单脚本）

```
agent_skill_template/
├── SKILL.md           # 指令文档
├── README.md          # 包文档
├── requirements.txt   # Python 依赖
├── scripts/           # 可执行脚本
│   ├── weather_helper.py
│   └── utils.py
└── references/        # 参考文档（可选）
    └── .gitkeep
```

### 推荐的修正（模式 2：完整包）

```
agent_skill_template/
├── SKILL.md           # 指令文档
├── README.md          # 包文档
├── pyproject.toml     # Python 包配置
├── src/               # Python 包
│   └── weather_skill/
│       ├── __init__.py
│       ├── client.py
│       └── utils.py
└── references/        # 参考文档（可选）
    └── api-docs.md
```

---

## 7. SKILL.md 格式建议

### 推荐的 frontmatter 格式

```yaml
---
# 核心字段（必需）
name: weather
description: Get current weather and forecasts. Use when user asks about weather, temperature, or forecasts.

# Moltbot 风格的 metadata（推荐）
homepage: https://wttr.in/:help
metadata:
  emoji: "🌤️"
  requires:
    bins: ["curl", "python3"]
    env: ["WEATHER_API_KEY"]
    config: []
  os: ["darwin", "linux"]  # 可选的 OS 过滤

# Claude Code 风格的字段（可选）
license: MIT
author: Your Name
version: 1.0.0
---
```

### 推荐的 body 结构

```markdown
# Weather Skill

## Quick Start

Run the weather script:
```bash
python3 {baseDir}/scripts/weather_helper.py --city London
```

## Configuration

Set environment variables:
```bash
export WEATHER_API_KEY=your_key_here
```

## Usage Examples

Get current weather:
```bash
python3 {baseDir}/scripts/weather_helper.py --city "New York" --format json
```

Get forecast:
```bash
python3 {baseDir}/scripts/weather_helper.py --city "Tokyo" --forecast 5
```

## Scripts

- `scripts/weather_helper.py` - Main weather fetching tool
- `scripts/utils.py` - Utility functions for data processing

## References

See `references/api-docs.md` for detailed API documentation.

## Troubleshooting

Common issues and solutions...
```

---

## 8. 具体行动步骤

### 步骤 1：移除 config.yaml（立即执行）

**原因：**
- 不是标准做法
- Moltbot 和 Claude Code 都不使用
- 配置应该通过环境变量或在 SKILL.md 中说明

**行动：**
1. 删除 `config.yaml`
2. 将配置说明移到 SKILL.md 的 "Configuration" 部分
3. 更新文档，说明如何使用环境变量

### 步骤 2：重组 Python 代码（立即执行）

**原因：**
- 代码应该有清晰的组织结构
- 遵循 Moltbot 和 Claude Code 的最佳实践

**行动：**

**选项 A：简单脚本模式**
1. 创建 `scripts/` 目录
2. 移动 `utils.py` → `scripts/utils.py`
3. 移动 `weather_helper.py` → `scripts/weather_helper.py`
4. 更新 SKILL.md 中的路径引用

**选项 B：完整包模式**
1. 创建 `src/weather_skill/` 目录
2. 移动代码到 `src/weather_skill/`
3. 添加 `__init__.py`
4. 创建 `pyproject.toml`
5. 更新 SKILL.md

### 步骤 3：添加可选目录（立即执行）

**行动：**
1. 创建 `references/` 目录（添加 .gitkeep）
2. 创建 `assets/` 目录（如果需要输出资源）
3. 更新 README.md 说明目录结构

### 步骤 4：增强 SKILL.md（中优先级）

**行动：**
1. 更新 frontmatter，添加 metadata 字段
2. 添加 emoji, requires, os 等字段
3. 改进 body 结构，添加清晰的章节
4. 提供更多使用示例
5. 说明如何配置环境变量

### 步骤 5：更新文档（中优先级）

**行动：**
1. 更新 design.md，反映正确的结构
2. 更新 requirements.md，明确 Agent Skills 的定义
3. 创建模板生成器，支持多种模式
4. 提供迁移指南

### 步骤 6：实现模板生成器（低优先级）

**行动：**
1. 创建 `init_skill.py` 脚本（参考 Moltbot）
2. 支持多种模式（简单脚本、完整包、混合）
3. 自动生成目录结构
4. 生成 SKILL.md 模板

---

## 9. 决策确认

### 决策 1：移除 config.yaml ✅

**决定：移除**

**理由：**
- Moltbot 和 Claude Code 都不使用
- 配置应该通过环境变量或在 SKILL.md 中说明
- 简化结构

### 决策 2：保留 Python 代码 ✅

**决定：保留并重新组织**

**理由：**
- Agent Skills 应该包含可执行代码
- 代码应该组织在 scripts/ 或 src/ 目录中
- 这是 Moltbot 和 Claude Code 的标准做法

### 决策 3：目录结构 ✅

**决定：使用 scripts/ 和 references/**

**理由：**
- 遵循 Moltbot 的最佳实践
- 清晰的目录用途
- 支持多种模式（简单脚本、完整包、混合）

### 决策 4：支持多种模式 ✅

**决定：支持简单脚本、完整包、混合三种模式**

**理由：**
- 不同 skills 有不同的复杂度
- 灵活性更高
- 符合实际使用场景

---

## 10. 总结

### 核心理解

**Agent Skills = SKILL.md（指令）+ 可执行代码（scripts/或src/）**

- SKILL.md 教 agent **如何使用**工具
- 可执行代码是 agent **调用执行**的工具
- 两者缺一不可

### 关键变更

1. ❌ 移除 config.yaml
2. ✅ 保留并重组 Python 代码
3. ✅ 创建 scripts/ 目录
4. ✅ 创建 references/ 目录（可选）
5. ✅ 支持多种模式

### 下一步

1. 更新 design.md 文档
2. 更新 requirements.md 文档
3. 实施模板重组
4. 创建模板生成器
5. 更新相关文档

---

## 附录：参考示例

### Moltbot 示例

**简单脚本：**
- openai-image-gen
- video-frames
- tmux

**完整包：**
- local-places
- skill-creator

**带辅助资源：**
- bitwarden
- model-usage

### Claude Code 示例

**Plugin 结构：**
- hookify
- security-guidance
- ralph-wiggum

**纯指令 Skill：**
- frontend-design
- claude-opus-4-5-migration
- writing-rules
