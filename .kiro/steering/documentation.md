---
inclusion: always
---

# Documentation Management Rules

## Critical Principles

**NEVER** create documentation files inside code directories. All documentation must be centrally managed in the `docs/` directory at the project root.

## Directory Structure

```
project-root/
├── backend/                    # Code only - NO documentation
│   ├── module_name/
│   │   ├── __init__.py
│   │   ├── core.py
│   │   └── test_core.py       # Tests are OK
│   └── README.md              # Only one README at backend root (entry point)
│
├── frontend/                   # Code only - NO documentation
│   └── README.md              # Only one README at frontend root (entry point)
│
├── docs/                       # All documentation goes here
│   ├── api/                   # API documentation
│   ├── architecture/          # Architecture diagrams and docs
│   ├── backend/               # Backend-specific documentation
│   │   ├── configuration-validation.md
│   │   ├── logging.md
│   │   └── module-guides/     # Module usage guides (if needed)
│   ├── deployment/            # Deployment guides
│   ├── developer/             # Developer guides
│   └── user-guide/            # User documentation
│
├── .kiro/                      # Kiro AI workspace
│   ├── specs/                 # Feature specifications and tasks
│   │   └── feature-name/
│   │       ├── requirements.md
│   │       ├── design.md
│   │       └── tasks.md
│   └── steering/              # Development rules (this file)
│
└── README.md                   # Main project README
```

## Forbidden Practices

### ❌ DO NOT Create These Files in Code Directories

1. **Implementation summaries**: `IMPLEMENTATION_SUMMARY.md`, `TASKS_COMPLETED.md`
2. **Module READMEs**: Individual README files in each module
3. **Feature documentation**: Detailed feature docs in code folders
4. **Design documents**: Architecture or design docs in code folders
5. **Usage guides**: How-to guides in code folders
6. **Examples**: Example code files (use separate examples/ at root if needed)

### ❌ DO NOT Create These Directories in Code Folders

1. `docs/` inside backend/ or frontend/
2. `examples/` inside backend/ or frontend/
3. `guides/` inside any module

## Allowed Files in Code Directories

### ✅ Backend Modules

Each backend module should ONLY contain:

```
backend/module_name/
├── __init__.py              # Module exports
├── *.py                     # Python source files
├── test_*.py                # Test files
└── .gitkeep                 # For empty directories
```

### ✅ Backend Root

Only ONE README at backend root:

```
backend/
├── [module directories]
├── README.md               # Brief entry point (Quick Start only)
├── requirements.txt
├── requirements-dev.txt
├── config.yaml
├── pyproject.toml
└── setup.py
```

**Backend README should be minimal** (< 100 lines):
- Quick start commands
- Project structure overview
- Link to main docs

## Documentation Organization

### API Documentation

Location: `docs/api/`

- OpenAPI/Swagger specs
- API endpoint documentation
- Authentication guides
- Rate limiting documentation

### Architecture Documentation

Location: `docs/architecture/`

- System architecture diagrams
- Component interaction diagrams
- Data flow diagrams
- Technology stack overview

### Backend Documentation

Location: `docs/backend/`

- Configuration guides
- Logging system documentation
- Database schema documentation
- Module interaction guides
- Development patterns

### Deployment Documentation

Location: `docs/deployment/`

- Installation guides (Linux, macOS, Windows)
- Docker deployment
- Kubernetes deployment
- Environment configuration
- Troubleshooting guides

### Developer Documentation

Location: `docs/developer/`

- Development setup
- Coding standards
- Testing guidelines
- Contributing guide
- Git workflow

### User Documentation

Location: `docs/user-guide/`

- User manual
- Feature guides
- Tutorials
- FAQ

## Task and Spec Documentation

### Feature Specifications

Location: `.kiro/specs/feature-name/`

All feature-related documentation goes here:

```
.kiro/specs/feature-name/
├── requirements.md         # User stories and acceptance criteria
├── design.md              # Technical design and architecture
└── tasks.md               # Implementation task list
```

**NEVER** create separate implementation summary files. All implementation details should be:
1. In the design.md during planning
2. In code comments during implementation
3. In commit messages when completing tasks

### Task Status Tracking

- Task status is tracked in `tasks.md` using checkbox syntax
- Mark tasks complete: `- [x] Task description`
- Update tasks.md immediately after completing implementation
- NEVER create separate `TASKS_COMPLETED.md` files

## When to Create Documentation

### During Development

1. **Code comments**: Document complex logic inline
2. **Docstrings**: Document all public APIs
3. **Type hints**: Use type hints as inline documentation
4. **Commit messages**: Explain what and why

### After Feature Completion

1. **Update design.md**: Document any design changes
2. **Update tasks.md**: Mark tasks as complete
3. **Create user guide**: If user-facing feature (in `docs/user-guide/`)
4. **Update API docs**: If API changes (in `docs/api/`)

### Never Create

1. ❌ Implementation summary files
2. ❌ Task completion tracking files
3. ❌ Module-specific README files
4. ❌ Duplicate documentation

## Documentation Format

### File Naming

- Use kebab-case: `configuration-validation.md`
- Be descriptive: `api-authentication-guide.md`
- Avoid abbreviations: `database-setup.md` not `db-setup.md`

### Content Structure

```markdown
# Title

Brief description (1-2 sentences)

## Overview

What this document covers

## Quick Start

Minimal example to get started

## Detailed Sections

Organized by topic

## References

- Link to related docs
- Link to code
- Link to specs
```

### Code Examples

- Keep examples minimal and focused
- Use real, working code
- Include necessary imports
- Show expected output

## Enforcement

### During Code Review

Check for:
- [ ] No documentation files in code directories
- [ ] No implementation summaries
- [ ] No task completion files
- [ ] Backend README is minimal
- [ ] All docs are in `docs/` or `.kiro/specs/`

### During Development

When completing a task:
1. Write the code
2. Write the tests
3. Update tasks.md status
4. Update relevant docs in `docs/` (if needed)
5. Commit everything together

### Automated Checks

Consider adding pre-commit hooks:

```bash
# Check for forbidden files
find backend -name "*IMPLEMENTATION*.md" -o -name "*TASKS_COMPLETED*.md" -o -name "README.md" ! -path "backend/README.md"
```

## Migration Guide

If you find documentation in code directories:

1. **Identify the document type**:
   - Implementation summary → Delete (info should be in design.md)
   - Module README → Move to `docs/backend/module-guides/` or delete
   - Task completion → Delete (use tasks.md)
   - Configuration guide → Move to `docs/backend/`

2. **Move or delete**:
   ```bash
   # Move useful docs
   mv backend/module/README.md docs/backend/module-guide.md
   
   # Delete redundant docs
   rm backend/module/IMPLEMENTATION_SUMMARY.md
   rm backend/module/TASKS_COMPLETED.md
   ```

3. **Update references**:
   - Update any links in other docs
   - Update import paths if needed

## Examples

### ✅ Good Structure

```
backend/
├── access_control/
│   ├── __init__.py
│   ├── rbac.py
│   ├── abac.py
│   └── test_rbac.py
└── README.md

docs/
├── backend/
│   ├── access-control-guide.md
│   └── authentication-flow.md
└── api/
    └── authentication-endpoints.md

.kiro/specs/access-control/
├── requirements.md
├── design.md
└── tasks.md
```

### ❌ Bad Structure

```
backend/
├── access_control/
│   ├── __init__.py
│   ├── rbac.py
│   ├── README.md                          # ❌ Module README
│   ├── RBAC_IMPLEMENTATION_SUMMARY.md     # ❌ Implementation summary
│   ├── TASKS_COMPLETED.md                 # ❌ Task tracking
│   └── docs/                              # ❌ Docs in code dir
│       └── usage-guide.md
└── README.md (300+ lines)                 # ❌ Too detailed
```

## Summary

**Golden Rule**: Code directories contain ONLY code and tests. All documentation lives in `docs/` or `.kiro/specs/`.

**Remember**:
- 📝 Documentation in `docs/`
- 📋 Specs and tasks in `.kiro/specs/`
- 💻 Code and tests in `backend/` and `frontend/`
- 🚫 Never mix documentation with code

This keeps the project clean, maintainable, and professional.
