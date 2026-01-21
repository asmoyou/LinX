---
inclusion: always
---

# Task Management and Tracking Rules

## Critical Task Completion Workflow

**MANDATORY**: When completing ANY task from a spec's tasks.md file, you MUST follow this workflow:

### 1. Before Starting a Task
- Read the spec's tasks.md file to understand the task requirements
- Read the spec's requirements.md and design.md for context
- Identify the specific task(s) you will be working on

### 2. During Task Execution
- Implement the required functionality
- Write tests for the implementation
- Create documentation as needed

### 3. After Completing a Task - CRITICAL STEP
**YOU MUST ALWAYS DO THIS - NO EXCEPTIONS:**

1. **Update tasks.md immediately** after completing implementation
2. Change task status from `- [ ]` to `- [x]` for completed tasks
3. Update ALL sub-tasks if the parent task is complete
4. **Commit the tasks.md update** along with your code changes

### Task Status Format

Tasks use markdown checkbox syntax:
- `- [ ]` = Not started (INCOMPLETE)
- `- [x]` = Completed (COMPLETE)
- `- [-]` = In progress
- `- [~]` = Queued

### Example Workflow

```bash
# 1. Implement the feature
# ... write code, tests, docs ...

# 2. Update tasks.md (MANDATORY)
# Change: - [ ] 2.3.1 Create LLM provider interface
# To:     - [x] 2.3.1 Create LLM provider interface

# 3. Commit everything together
git add backend/llm_providers/ .kiro/specs/*/tasks.md
git commit -m "feat: implement feature X (task Y.Z)"
```

## Why This Matters

- **Progress Tracking**: Users need to see what's been completed
- **Project Management**: Tasks.md is the single source of truth for project status
- **Collaboration**: Other developers need to know what's done
- **Accountability**: Completed tasks should be marked immediately

## Common Mistakes to Avoid

❌ **DON'T**: Complete implementation and forget to update tasks.md
❌ **DON'T**: Update tasks.md in a separate commit later
❌ **DON'T**: Mark tasks as complete before they're actually done

✅ **DO**: Update tasks.md immediately after completing implementation
✅ **DO**: Include tasks.md in the same commit as your code
✅ **DO**: Verify all sub-tasks are marked complete before marking parent task

## Reminder Checklist

Before committing any spec-related work, ask yourself:

- [ ] Did I update the tasks.md file?
- [ ] Did I mark the correct task(s) as complete?
- [ ] Did I include tasks.md in my git commit?
- [ ] Are all sub-tasks marked complete if I completed a parent task?

## Task File Locations

Spec task files are located at:
- `.kiro/specs/{spec-name}/tasks.md`

Always update the tasks.md file in the SAME spec directory as the work you're completing.