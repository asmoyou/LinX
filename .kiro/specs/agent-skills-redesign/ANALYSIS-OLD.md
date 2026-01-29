# Agent Skills Structure Analysis

## Executive Summary

After analyzing the reference implementations (Moltbot and Claude Code), I've identified key structural differences and compatibility considerations for the Agent Skills redesign. This document provides a systematic comparison and recommendations.

---

## 1. Current LinX Implementation

### Structure
```
backend/skill_library/templates/agent_skill_template/
├── config.yaml          # ❓ Moltbot-specific, not in Claude Code
├── README.md            # Standard documentation
├── requirements.txt     # Python dependencies
├── SKILL.md            # Core skill definition
├── utils.py            # Helper functions
└── weather_helper.py   # Implementation code
```

### Key Characteristics
- **config.yaml**: Moltbot-inspired configuration file for API settings, rate limiting, caching
- **Python code**: Includes actual implementation (utils.py, weather_helper.py)
- **SKILL.md**: Natural language instructions
- **No assets/ directory**: Currently not present in template

---

## 2. Moltbot Implementation

### Structure
```
moltbot/skills/weather/
└── SKILL.md            # Only file needed!

moltbot/skills/bitwarden/
├── SKILL.md
├── references/         # Optional: Additional documentation
│   └── templates.md
└── scripts/            # Optional: Helper scripts
    └── bw-session.sh

moltbot/skills/local-places/
├── SKILL.md
├── SERVER_README.md    # Optional: Server setup docs
├── pyproject.toml      # Optional: Python package config
└── src/                # Optional: MCP server implementation
    └── local_places/
```

### Key Characteristics
- **Minimal by default**: Most skills are just SKILL.md
- **Optional structure**: Can include scripts/, references/, src/ as needed
- **No config.yaml**: Configuration is embedded in SKILL.md or environment variables
- **Gating metadata**: In SKILL.md frontmatter
  ```yaml
  metadata: {"moltbot":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
  ```

### SKILL.md Format (Moltbot)
```markdown
---
name: weather
description: Get current weather and forecasts (no API key required).
homepage: https://wttr.in/:help
metadata: {"moltbot":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
---

# Weather

Two free services, no API keys needed.

## wttr.in (primary)

Quick one-liner:
```bash
curl -s "wttr.in/London?format=3"
# Output: London: ⛅️ +8°C
```

[... rest of instructions ...]
```

---

## 3. Claude Code Implementation

### Structure
```
claude-code/plugins/hookify/skills/
└── [skill-name]/
    ├── SKILL.md
    └── references/      # Optional: Additional docs
        └── *.md

claude-code/plugins/frontend-design/skills/
└── frontend-design/
    └── SKILL.md
```

### Key Characteristics
- **Plugin-based**: Skills are part of plugins
- **SKILL.md focused**: Primary content is natural language instructions
- **No config.yaml**: No separate configuration files
- **Rich frontmatter**: More structured metadata
  ```yaml
  name: frontend-design
  description: Create distinctive, production-grade frontend interfaces
  license: Complete terms in LICENSE.txt
  ```
- **References directory**: Optional additional documentation

### SKILL.md Format (Claude Code)
```markdown
---
name: claude-opus-4-5-migration
description: Migrate prompts and code from Claude Sonnet 4.0...
---

# Opus 4.5 Migration Guide

One-shot migration from Sonnet 4.0, Sonnet 4.5, or Opus 4.1 to Opus 4.5.

## Migration Workflow

1. Search codebase for model strings and API calls
2. Update model strings to Opus 4.5
[... detailed instructions ...]

## Reference

See `references/prompt-snippets.md` for the full text...
```

---

## 4. Key Differences Comparison

| Aspect | Moltbot | Claude Code | Current LinX |
|--------|---------|-------------|--------------|
| **Core File** | SKILL.md | SKILL.md | SKILL.md |
| **Config File** | ❌ No | ❌ No | ✅ config.yaml |
| **Python Code** | Optional (src/) | ❌ No | ✅ Yes (utils.py, etc.) |
| **Assets Dir** | ❌ No | ❌ No | ❌ No |
| **References** | Optional | Optional | ❌ No |
| **Scripts** | Optional | ❌ No | ❌ No |
| **Gating** | In metadata | ❌ No | In config.yaml |
| **Emoji** | In metadata | ❌ No | ❌ No |
| **Homepage** | In frontmatter | ❌ No | ❌ No |

---

## 5. The config.yaml Question

### What is config.yaml?

**Current LinX template includes:**
```yaml
# Weather Skill Configuration

# API Configuration
api:
  base_url: "https://api.openweathermap.org/data/2.5"
  timeout: 30
  retry_attempts: 3

# Default Settings
defaults:
  units: "metric"
  language: "en"

# Rate Limiting
rate_limit:
  calls_per_minute: 60
  burst_size: 10

# Caching
cache:
  enabled: true
  ttl_seconds: 300

# Logging
logging:
  level: "INFO"
  log_api_calls: true
```

### Analysis

**Origin:** This appears to be inspired by Moltbot's approach, but Moltbot doesn't use config.yaml files. Instead:

1. **Moltbot approach:**
   - Configuration is in environment variables
   - Gating requirements in SKILL.md metadata
   - No separate config files

2. **Claude Code approach:**
   - No configuration files at all
   - Everything is in SKILL.md instructions
   - Agent interprets and uses tools directly

3. **Why LinX has config.yaml:**
   - Likely added for structured configuration
   - Useful for Python-based skills with complex settings
   - But contradicts the "instructions-only" philosophy

### The Fundamental Issue

**Agent Skills should be instructions, not executable code.**

Current LinX template includes:
- ✅ SKILL.md (instructions) ← Correct
- ❌ config.yaml (configuration) ← Contradicts philosophy
- ❌ utils.py (helper code) ← Contradicts philosophy
- ❌ weather_helper.py (implementation) ← Contradicts philosophy

**The template is mixing two concepts:**
1. **Agent Skills** (instructions for agents)
2. **LangChain Tools** (executable Python code)

---

## 6. The assets/ Directory Question

### What would assets/ contain?

Based on reference implementations, assets could include:

1. **Reference Documentation** (Moltbot style)
   - `references/templates.md`
   - `references/api-docs.md`
   - Additional context for the skill

2. **Helper Scripts** (Moltbot style)
   - `scripts/setup.sh`
   - `scripts/helper.sh`
   - Bash scripts referenced in SKILL.md

3. **Static Files**
   - Images for documentation
   - Example data files
   - Configuration templates

### Why assets/ doesn't exist in references?

**Moltbot:** Uses specific directories (references/, scripts/) instead of generic assets/

**Claude Code:** Uses references/ for additional docs, no other assets

**Conclusion:** An assets/ directory is not standard in either reference implementation. Instead:
- Use `references/` for additional documentation
- Use `scripts/` for helper scripts
- Keep structure minimal and purpose-specific

---

## 7. Recommended Structure

### ✅ Correct Understanding: Agent Skills = Instructions + Executable Tools

**Agent Skills包含两个核心部分：**

1. **SKILL.md**：指令文档，教 agent **如何使用**工具
2. **可执行代码**：预先写好的工具，agent **调用执行**

### 标准结构（基于 Moltbot 和 Claude Code）

#### 简单模式（仅脚本）

```
skill-name/
├── SKILL.md           # 指令：如何使用这个 skill（必需）
├── README.md          # 包文档（可选）
├── requirements.txt   # Python 依赖（如果有 Python 代码）
├── scripts/           # 可执行脚本（Python, Shell, etc.）
│   ├── main.py
│   ├── helper.py
│   └── setup.sh
└── references/        # 额外文档（可选）
    └── api-docs.md
```

**示例：openai-image-gen**
```
openai-image-gen/
├── SKILL.md           # 教 agent 如何生成图片
└── scripts/
    └── gen.py         # 完整的图片生成工具
```

#### 完整包模式（Python 包）

```
skill-name/
├── SKILL.md           # 指令文档（必需）
├── README.md          # 包文档（可选）
├── pyproject.toml     # Python 包配置
├── src/               # 完整的 Python 包
│   └── skill_name/
│       ├── __init__.py
│       ├── main.py
│       └── utils.py
└── references/        # 额外文档（可选）
    └── api-docs.md
```

**示例：local-places**
```
local-places/
├── SKILL.md           # 教 agent 如何搜索地点
├── SERVER_README.md   # 服务器文档
├── pyproject.toml     # Python 包配置
└── src/               # FastAPI MCP 服务器
    └── local_places/
        ├── main.py
        ├── google_places.py
        └── schemas.py
```

#### 带辅助资源模式

```
skill-name/
├── SKILL.md           # 指令文档（必需）
├── scripts/           # 可执行脚本
│   └── helper.sh
├── references/        # 参考文档
│   └── templates.md
└── assets/            # 输出资源（模板、图片等）
    └── template.html
```

**示例：bitwarden**
```
bitwarden/
├── SKILL.md           # 教 agent 如何使用 bw CLI
├── scripts/
│   └── bw-session.sh  # 辅助脚本：解锁 vault
└── references/
    └── templates.md   # jq 模板参考
```

### ❌ 不推荐的结构（当前 LinX 模板）

```
skill-name/
├── SKILL.md           # ✅ 正确
├── config.yaml        # ❌ 应该移除
├── utils.py           # ⚠️ 应该在 scripts/ 或 src/
└── weather_helper.py  # ⚠️ 应该在 scripts/ 或 src/
```

**问题：**
- config.yaml 不是标准做法（配置应该在 SKILL.md 中说明或用环境变量）
- Python 代码应该组织在 scripts/ 或 src/ 目录中
- 缺少清晰的目录结构

---

## 8. Compatibility Matrix

### Moltbot Compatibility

| Feature | Moltbot | LinX Current | Recommended |
|---------|---------|--------------|-------------|
| SKILL.md format | ✅ | ✅ | ✅ |
| Gating metadata | ✅ | ❌ | ✅ Adopt |
| Emoji support | ✅ | ❌ | ✅ Adopt |
| Homepage link | ✅ | ❌ | ✅ Adopt |
| references/ dir | ✅ | ❌ | ✅ Adopt |
| scripts/ dir | ✅ | ❌ | ✅ Adopt |
| config.yaml | ❌ | ✅ | ❌ Remove |
| Python code | Optional | ✅ | ❌ Remove |

### Claude Code Compatibility

| Feature | Claude Code | LinX Current | Recommended |
|---------|-------------|--------------|-------------|
| SKILL.md format | ✅ | ✅ | ✅ |
| Rich frontmatter | ✅ | Partial | ✅ Enhance |
| references/ dir | ✅ | ❌ | ✅ Adopt |
| License field | ✅ | ❌ | ✅ Adopt |
| No config files | ✅ | ❌ | ✅ Adopt |
| No Python code | ✅ | ❌ | ✅ Adopt |

---

## 9. Proposed Actions

### Phase 1: 重组模板结构（高优先级）

1. **移除：**
   - ❌ config.yaml（配置说明应该在 SKILL.md 中，或使用环境变量）

2. **保留：**
   - ✅ SKILL.md（核心指令文档）
   - ✅ README.md（包文档）
   - ✅ requirements.txt（如果有 Python 代码）
   - ✅ utils.py 和 weather_helper.py（但需要重新组织）

3. **重新组织：**
   - ✅ 创建 scripts/ 目录
   - ✅ 移动 utils.py → scripts/utils.py
   - ✅ 移动 weather_helper.py → scripts/weather_helper.py
   - ✅ 创建 references/ 目录（可选）
   - ✅ 创建 src/ 目录（用于完整 Python 包，可选）

### Phase 2: Enhance SKILL.md Format (Medium Priority)

**Adopt best practices from both references:**

```yaml
---
# Core fields (required)
name: weather
description: Get current weather and forecasts

# Moltbot-style metadata
homepage: https://wttr.in/:help
metadata:
  emoji: "🌤️"
  requires:
    bins: ["curl"]
    env: []
    config: []
  os: ["darwin", "linux"]  # Optional OS filter

# Claude Code-style fields
license: MIT
author: Your Name
version: 1.0.0
---
```

### Phase 3: Update Documentation (Medium Priority)

1. **Clarify distinction:**
   - Agent Skills = Instructions (SKILL.md)
   - LangChain Tools = Executable code (@tool decorator)

2. **Provide examples:**
   - Pure instruction skills (weather, github)
   - Skills with helper scripts (bitwarden)
   - Skills with MCP servers (local-places)

3. **Migration guide:**
   - How to convert current template
   - When to use Agent Skills vs LangChain Tools
   - How to structure skill packages

### Phase 4: Template Generator (Low Priority)

Create template generator that produces:

```
skill-name/
├── SKILL.md           # Generated from prompts
├── README.md          # Package documentation
├── references/        # Optional
│   └── .gitkeep
└── scripts/           # Optional
    └── .gitkeep
```

---

## 10. Decision Points

### Decision 1: config.yaml

**Question:** Should Agent Skills support config.yaml?

**Options:**
- **A) Remove entirely** (Recommended)
  - Pros: Aligns with philosophy, simpler, matches references
  - Cons: Less structured configuration
  
- **B) Keep as optional**
  - Pros: Flexibility for complex skills
  - Cons: Contradicts instructions-only philosophy

**Recommendation:** **Option A** - Remove config.yaml. Use environment variables or embed configuration in SKILL.md instructions.

### Decision 2: Python Code in Skills

**Question:** Should Agent Skills include Python code?

**Options:**
- **A) No Python code** (Recommended)
  - Pros: Clear separation, aligns with philosophy
  - Cons: Can't package helper utilities
  
- **B) Allow optional Python code**
  - Pros: Flexibility for complex skills
  - Cons: Blurs line with LangChain Tools

**Recommendation:** **Option A** - No Python code in Agent Skills. If code is needed, create a LangChain Tool instead.

### Decision 3: Directory Structure

**Question:** What optional directories should be supported?

**Options:**
- **A) references/ and scripts/** (Recommended)
  - Pros: Matches Moltbot, clear purpose
  - Cons: More specific than generic assets/
  
- **B) Generic assets/**
  - Pros: Flexible for any file type
  - Cons: Not standard in references, unclear purpose

**Recommendation:** **Option A** - Use references/ and scripts/ directories with clear purposes.

### Decision 4: Metadata Format

**Question:** How should metadata be structured?

**Options:**
- **A) Moltbot-style JSON in metadata field** (Recommended)
  - Pros: Compatible with Moltbot skills, proven format
  - Cons: JSON in YAML is less clean
  
- **B) Native YAML structure**
  - Pros: Cleaner YAML, easier to edit
  - Cons: Not compatible with Moltbot

**Recommendation:** **Option A** - Use Moltbot-compatible format for maximum compatibility, but also support native YAML as alternative.

---

## 11. Final Recommendations

### Immediate Actions (Do Now)

1. **Update template structure:**
   ```
   agent_skill_template/
   ├── SKILL.md           # Core instructions
   ├── README.md          # Package docs
   ├── references/        # Optional docs
   │   └── .gitkeep
   └── scripts/           # Optional scripts
       └── .gitkeep
   ```

2. **Remove from template:**
   - config.yaml
   - utils.py
   - weather_helper.py
   - requirements.txt

3. **Update SKILL.md format:**
   - Add emoji field
   - Add homepage field
   - Add gating metadata (requires.bins, requires.env)
   - Add OS filter support

4. **Update documentation:**
   - Clarify Agent Skills vs LangChain Tools
   - Provide migration guide
   - Show examples from both Moltbot and Claude Code

### Future Enhancements (Later)

1. **Skill discovery:**
   - Import skills from Moltbot repository
   - Import skills from Claude Code plugins
   - Skill marketplace integration

2. **Advanced features:**
   - Skill versioning
   - Skill dependencies
   - Skill composition
   - Multi-language support

3. **Testing improvements:**
   - Better natural language testing
   - Sandbox execution
   - Integration with actual tools

---

## 12. Migration Path

### For Existing Skills

**Current template-based skills need migration:**

1. **Identify skill type:**
   - Has executable Python code? → Convert to LangChain Tool
   - Only has instructions? → Keep as Agent Skill

2. **For Agent Skills:**
   - Remove config.yaml (move settings to env vars or SKILL.md)
   - Remove Python code (create separate LangChain Tool if needed)
   - Keep SKILL.md and enhance with metadata
   - Add references/ or scripts/ if needed

3. **For LangChain Tools:**
   - Change skill_type to 'langchain_tool'
   - Keep Python code
   - Remove SKILL.md (or keep as documentation)
   - Use @tool decorator

### Example Migration

**Before (Current):**
```
weather-skill/
├── SKILL.md
├── config.yaml
├── utils.py
└── weather_helper.py
```

**After (Agent Skill):**
```
weather-skill/
├── SKILL.md           # Enhanced with metadata
└── references/
    └── api-docs.md
```

**After (LangChain Tool):**
```
weather-tool/
└── weather_tool.py    # @tool decorator, executable code
```

---

## 13. Conclusion

### Key Insights

1. **config.yaml is not standard** in either Moltbot or Claude Code
2. **Python code contradicts** the Agent Skills philosophy
3. **assets/ directory is not used** in reference implementations
4. **Minimal structure is preferred** - just SKILL.md + optional references/scripts
5. **Clear separation needed** between Agent Skills (instructions) and LangChain Tools (code)

### Recommended Approach

**Adopt a hybrid format that:**
- ✅ Follows Moltbot's gating and metadata approach
- ✅ Uses Claude Code's rich frontmatter format
- ✅ Maintains clear separation from LangChain Tools
- ✅ Keeps structure minimal and purpose-driven
- ✅ Supports optional references/ and scripts/ directories

### Next Steps

1. **Review this analysis** with the team
2. **Decide on each decision point** (config.yaml, Python code, etc.)
3. **Update the design document** based on decisions
4. **Implement changes** following the migration path
5. **Update documentation** and examples

---

## Appendix: Reference Examples

### Moltbot Weather Skill (Minimal)
```
weather/
└── SKILL.md
```

### Moltbot Bitwarden Skill (With References)
```
bitwarden/
├── SKILL.md
├── references/
│   └── templates.md
└── scripts/
    └── bw-session.sh
```

### Claude Code Migration Skill (With References)
```
claude-opus-4-5-migration/
├── SKILL.md
└── references/
    ├── effort.md
    └── prompt-snippets.md
```

### Recommended LinX Structure
```
skill-name/
├── SKILL.md           # Core instructions (REQUIRED)
├── README.md          # Package documentation
├── references/        # Optional: Additional docs
│   ├── api-docs.md
│   └── examples.md
└── scripts/           # Optional: Helper scripts
    └── setup.sh
```
