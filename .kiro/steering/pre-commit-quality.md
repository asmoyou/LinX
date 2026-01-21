# Pre-Commit Quality Control Rules

## Critical Principle

**NEVER commit code that will fail CI/CD pipelines.** All code must pass quality checks locally before committing. If issues are found, they MUST be fixed before the commit is allowed.

## Mandatory Pre-Commit Workflow

### 1. Before Every Commit

Run the complete quality check suite locally to ensure CI/CD will pass:

```bash
# Navigate to backend directory
cd backend

# Run all quality checks in sequence
make pre-commit-check  # Or follow manual steps below
```

### 2. Quality Check Sequence

Execute these checks in order. **STOP and FIX** if any check fails:

#### Step 1: Code Formatting

```bash
# Backend - Auto-format code
cd backend
black .
isort .

# Frontend - Auto-format code
cd frontend
npm run format  # or: npx prettier --write "src/**/*.{ts,tsx,js,jsx,json,css,md}"
```

**Action**: These commands auto-fix formatting. Review changes before committing.

#### Step 2: Linting

```bash
# Backend - Check for code quality issues
cd backend
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --max-complexity=10 --max-line-length=100 --statistics

# Frontend - Check for code quality issues
cd frontend
npm run lint
```

**Action**: If errors found, fix them manually. Common issues:
- Unused imports
- Undefined variables
- Syntax errors
- Complexity violations

#### Step 3: Type Checking

```bash
# Backend - Type checking
cd backend
mypy . --config-file=mypy.ini

# Frontend - Type checking
cd frontend
npm run type-check  # or: npx tsc --noEmit
```

**Action**: Fix type errors:
- Add missing type hints
- Fix type mismatches
- Add proper return types
- Fix any/unknown types

#### Step 4: Security Scanning

```bash
# Backend - Security checks
cd backend
bandit -r . -ll  # Check for security issues
pip-audit        # Check for vulnerable dependencies

# Frontend - Security checks
cd frontend
npm audit --audit-level=high
```

**Action**: Fix security vulnerabilities:
- Update vulnerable dependencies
- Fix security anti-patterns
- Remove hardcoded secrets

#### Step 5: Unit Tests

```bash
# Backend - Run all tests with coverage
cd backend
pytest --cov=. --cov-report=term --cov-report=html -v

# Frontend - Run all tests
cd frontend
npm test -- --run --coverage
```

**Action**: Ensure all tests pass:
- Fix failing tests
- Add tests for new code
- Maintain minimum coverage (aim for 80%+)

#### Step 6: Build Verification

```bash
# Backend - Verify imports and setup
cd backend
python -c "import api_gateway.main; print('Backend imports OK')"

# Frontend - Build the application
cd frontend
npm run build
```

**Action**: Fix build errors:
- Resolve import errors
- Fix compilation errors
- Ensure all dependencies are installed

### 3. Pre-Commit Hooks (Automated)

Install and use pre-commit hooks to automate checks:

```bash
# Install pre-commit (one-time setup)
pip install pre-commit

# Install hooks for the repository (one-time setup)
cd backend
pre-commit install

# Run hooks manually on all files
pre-commit run --all-files

# Hooks will run automatically on git commit
```

**The pre-commit hooks will automatically**:
- Format code (Black, isort, Prettier)
- Run linting (flake8, ESLint)
- Check types (mypy, TypeScript)
- Scan for security issues (bandit)
- Validate YAML/JSON files
- Check for secrets
- Enforce docstring coverage

### 4. Commit Only When All Checks Pass

```bash
# After all checks pass, commit your changes
git add .
git commit -m "feat: your feature description"

# If pre-commit hooks fail, fix issues and try again
# DO NOT use --no-verify to skip hooks
```

## Makefile Targets (Recommended)

Add these targets to `backend/Makefile` for convenience:

```makefile
.PHONY: format lint type-check security test pre-commit-check

# Auto-format code
format:
	black .
	isort .

# Run linting
lint:
	flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
	flake8 . --count --max-complexity=10 --max-line-length=100 --statistics

# Run type checking
type-check:
	mypy . --config-file=mypy.ini

# Run security checks
security:
	bandit -r . -ll
	pip-audit

# Run tests with coverage
test:
	pytest --cov=. --cov-report=term --cov-report=html -v

# Run all pre-commit checks
pre-commit-check: format lint type-check security test
	@echo "✅ All pre-commit checks passed!"

# Quick check (without tests)
quick-check: format lint type-check
	@echo "✅ Quick checks passed!"
```

Usage:

```bash
cd backend

# Run all checks before commit
make pre-commit-check

# Quick check (faster, no tests)
make quick-check

# Individual checks
make format
make lint
make type-check
make security
make test
```

## Frontend Package.json Scripts

Add these scripts to `frontend/package.json`:

```json
{
  "scripts": {
    "format": "prettier --write \"src/**/*.{ts,tsx,js,jsx,json,css,md}\"",
    "format:check": "prettier --check \"src/**/*.{ts,tsx,js,jsx,json,css,md}\"",
    "lint": "eslint src --ext .ts,.tsx",
    "lint:fix": "eslint src --ext .ts,.tsx --fix",
    "type-check": "tsc --noEmit",
    "test": "vitest",
    "test:run": "vitest --run",
    "test:coverage": "vitest --run --coverage",
    "build": "vite build",
    "pre-commit": "npm run format && npm run lint && npm run type-check && npm run test:run && npm run build"
  }
}
```

Usage:

```bash
cd frontend

# Run all checks before commit
npm run pre-commit

# Individual checks
npm run format
npm run lint
npm run type-check
npm run test:run
npm run build
```

## CI/CD Alignment

Your local checks must match CI/CD pipeline requirements:

### Backend CI/CD Checks

From `.github/workflows/backend-tests.yml`:
- ✅ Python 3.11
- ✅ flake8 linting
- ✅ mypy type checking
- ✅ pytest with coverage
- ✅ Black formatting
- ✅ isort import sorting

### Frontend CI/CD Checks

From `.github/workflows/frontend-tests.yml`:
- ✅ Node.js 20.x
- ✅ ESLint linting
- ✅ TypeScript type checking
- ✅ Tests (when configured)
- ✅ Prettier formatting
- ✅ Build verification

### Security CI/CD Checks

From `.github/workflows/security-scan.yml`:
- ✅ Trivy vulnerability scanning
- ✅ Dependency review
- ✅ Secret scanning (TruffleHog)

## Fixing Common Issues

### Backend Issues

#### Import Errors
```bash
# Fix: Ensure proper __init__.py files
touch module/__init__.py

# Fix: Add to PYTHONPATH
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
```

#### Type Errors
```python
# Bad
def process(data):
    return data

# Good
def process(data: dict[str, Any]) -> dict[str, Any]:
    return data
```

#### Linting Errors
```python
# Fix unused imports
# Remove or use the import

# Fix line length
# Break long lines
result = some_function(
    arg1,
    arg2,
    arg3
)
```

### Frontend Issues

#### Type Errors
```typescript
// Bad
const data = response.data;

// Good
const data: UserData = response.data;
```

#### Linting Errors
```typescript
// Fix: Use const instead of let when not reassigning
const value = 10;

// Fix: Add missing dependencies to useEffect
useEffect(() => {
  fetchData();
}, [fetchData]);
```

## Enforcement Rules

### ❌ NEVER Do This

1. **Skip pre-commit hooks**: `git commit --no-verify`
2. **Commit with failing tests**: Tests must pass
3. **Ignore linting errors**: Fix all errors
4. **Commit with type errors**: Fix all type issues
5. **Push without local verification**: Always check locally first

### ✅ ALWAYS Do This

1. **Run quality checks before commit**: Use `make pre-commit-check`
2. **Fix all issues before committing**: No exceptions
3. **Run tests locally**: Ensure they pass
4. **Review changes**: Use `git diff` before committing
5. **Write meaningful commit messages**: Follow conventional commits

## Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```bash
git commit -m "feat(auth): add JWT token refresh"
git commit -m "fix(api): resolve memory leak in websocket handler"
git commit -m "test(agents): add unit tests for agent lifecycle"
git commit -m "docs(readme): update installation instructions"
```

## Quick Reference Checklist

Before every commit, verify:

- [ ] Code is formatted (Black, isort, Prettier)
- [ ] Linting passes (flake8, ESLint)
- [ ] Type checking passes (mypy, TypeScript)
- [ ] Security checks pass (bandit, npm audit)
- [ ] All tests pass locally
- [ ] Build succeeds
- [ ] No debug code or console.logs
- [ ] No commented-out code
- [ ] No hardcoded secrets or credentials
- [ ] Commit message follows conventional format
- [ ] Related tasks.md updated (if applicable)

## Continuous Integration Expectations

When you push to GitHub, these workflows will run:

1. **Backend Tests** (`.github/workflows/backend-tests.yml`)
   - Runs on: Python 3.11
   - Services: PostgreSQL, Redis
   - Checks: Linting, type checking, tests, coverage

2. **Frontend Tests** (`.github/workflows/frontend-tests.yml`)
   - Runs on: Node.js 20.x
   - Checks: Linting, type checking, tests, build

3. **Security Scan** (`.github/workflows/security-scan.yml`)
   - Trivy vulnerability scanning
   - Dependency review
   - Secret scanning

**All workflows must pass** before merging to main/develop branches.

## Troubleshooting

### Pre-commit hooks not running

```bash
# Reinstall hooks
cd backend
pre-commit uninstall
pre-commit install

# Update hooks to latest versions
pre-commit autoupdate
```

### Tests fail in CI but pass locally

```bash
# Ensure same environment
# Check Python/Node versions match CI
python --version  # Should be 3.11+
node --version    # Should be 20.x

# Clear caches
rm -rf .pytest_cache __pycache__ .mypy_cache
rm -rf node_modules package-lock.json
npm install
```

### Type checking fails in CI

```bash
# Run with same strictness as CI
mypy . --config-file=mypy.ini --strict

# Install missing type stubs
pip install types-redis types-PyYAML types-python-dateutil
```

## Summary

**Golden Rules**:

1. 🔍 **Check locally first** - Run all quality checks before committing
2. 🛠️ **Fix all issues** - Don't commit with known problems
3. ✅ **Tests must pass** - No exceptions
4. 🚫 **Never skip hooks** - They exist for a reason
5. 📝 **Update tasks.md** - Mark completed tasks
6. 💬 **Write good commits** - Follow conventional commits format

**Remember**: Time spent fixing issues locally is much less than time spent fixing failed CI/CD pipelines and reverting commits.

**Workflow Summary**:
```bash
# 1. Make changes
# 2. Run quality checks
make pre-commit-check  # Backend
npm run pre-commit     # Frontend

# 3. Fix any issues
# 4. Commit when all checks pass
git add .
git commit -m "feat: your feature"

# 5. Push with confidence
git push
```

Your CI/CD pipeline will thank you! 🎉
