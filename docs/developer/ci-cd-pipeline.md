# CI/CD Pipeline Documentation

This document describes the Continuous Integration and Continuous Deployment (CI/CD) pipeline for the Digital Workforce Management Platform.

## Table of Contents

1. [Overview](#overview)
2. [Workflows](#workflows)
3. [Setup](#setup)
4. [Branch Strategy](#branch-strategy)
5. [Deployment Process](#deployment-process)
6. [Security Scanning](#security-scanning)
7. [Troubleshooting](#troubleshooting)

## Overview

The platform uses GitHub Actions for CI/CD automation. The pipeline includes:

- **Automated Testing**: Unit tests, integration tests, and code quality checks
- **Security Scanning**: Vulnerability scanning with Snyk, Trivy, and CodeQL
- **Docker Image Building**: Multi-platform Docker images for all services
- **Automated Deployment**: Staging and production deployments
- **Release Automation**: Automated release creation and artifact generation

## Workflows

### 1. Backend Tests (`backend-tests.yml`)

**Triggers**:
- Push to `main` or `develop` branches (backend changes)
- Pull requests to `main` or `develop` (backend changes)

**Jobs**:
- **test**: Runs tests on Python 3.11 and 3.12
  - Sets up PostgreSQL and Redis services
  - Installs system dependencies (Tesseract, FFmpeg)
  - Runs linting (flake8)
  - Runs type checking (mypy)
  - Runs tests with coverage (pytest)
  - Uploads coverage to Codecov

- **security-scan**: Security analysis
  - Runs Bandit for security issues
  - Runs Safety for dependency vulnerabilities

- **code-quality**: Code formatting checks
  - Checks Black formatting
  - Checks isort import sorting

**Required Secrets**: None (uses GitHub token)

### 2. Frontend Tests (`frontend-tests.yml`)

**Triggers**:
- Push to `main` or `develop` branches (frontend changes)
- Pull requests to `main` or `develop` (frontend changes)

**Jobs**:
- **test**: Runs tests on Node.js 20.x and 22.x
  - Installs dependencies
  - Runs linting (ESLint)
  - Runs type checking (TypeScript)
  - Runs tests with coverage
  - Builds application
  - Checks bundle size

- **lighthouse**: Performance testing
  - Runs Lighthouse CI for performance metrics

- **security-scan**: Security analysis
  - Runs npm audit

- **code-quality**: Code formatting checks
  - Checks Prettier formatting

**Required Secrets**: None

### 3. Docker Build (`docker-build.yml`)

**Triggers**:
- Push to `main` or `develop` branches
- Push tags matching `v*`
- Pull requests to `main`

**Jobs**:
- **build-backend-images**: Builds backend service images
  - api-gateway
  - task-manager
  - agent-runtime
  - document-processor
  - Multi-platform builds (amd64, arm64)

- **build-frontend-image**: Builds frontend image
  - Multi-platform build (amd64, arm64)

- **scan-images**: Scans images for vulnerabilities
  - Runs Trivy on all images
  - Uploads results to GitHub Security

**Required Secrets**: 
- `GITHUB_TOKEN` (automatically provided)

**Image Registry**: GitHub Container Registry (ghcr.io)

### 4. Deploy to Staging (`deploy-staging.yml`)

**Triggers**:
- Push to `develop` branch
- Manual workflow dispatch

**Jobs**:
- **deploy**: Deploys to staging environment
  - Updates Kubernetes manifests with new image tags
  - Applies manifests to staging cluster
  - Waits for rollout completion
  - Runs smoke tests

- **run-integration-tests**: Runs integration tests
  - Tests against staging environment

**Required Secrets**:
- `KUBE_CONFIG_STAGING`: Base64-encoded kubeconfig for staging cluster
- `STAGING_TEST_USER`: Test user credentials
- `STAGING_TEST_PASSWORD`: Test user password

**Environment**: `staging`

### 5. Security Scanning (`security-scan.yml`)

**Triggers**:
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop`
- Daily schedule (2 AM UTC)

**Jobs**:
- **snyk-backend**: Snyk vulnerability scanning for Python
- **snyk-frontend**: Snyk vulnerability scanning for Node.js
- **trivy-repo-scan**: Trivy filesystem scanning
- **codeql-analysis**: CodeQL security analysis
- **dependency-review**: Dependency review for PRs
- **secret-scanning**: TruffleHog secret scanning

**Required Secrets**:
- `SNYK_TOKEN`: Snyk API token (optional, for Snyk scans)

### 6. Release (`release.yml`)

**Triggers**:
- Push tags matching `v*.*.*` (e.g., v1.0.0)

**Jobs**:
- **create-release**: Creates GitHub release
  - Generates changelog
  - Creates release notes
  - Uploads release artifacts

- **build-release-artifacts**: Creates deployment package
  - Packages infrastructure files
  - Creates tarball

- **deploy-production**: Deploys to production
  - Only for stable releases (not rc/beta/alpha)
  - Updates Kubernetes manifests
  - Deploys to production cluster
  - Runs smoke tests

- **notify-release**: Sends notifications

**Required Secrets**:
- `KUBE_CONFIG_PRODUCTION`: Base64-encoded kubeconfig for production cluster

**Environment**: `production`

## Setup

### 1. Repository Secrets

Configure the following secrets in GitHub repository settings:

**Required**:
- `KUBE_CONFIG_STAGING`: Staging Kubernetes configuration
- `KUBE_CONFIG_PRODUCTION`: Production Kubernetes configuration

**Optional**:
- `SNYK_TOKEN`: Snyk API token for vulnerability scanning
- `STAGING_TEST_USER`: Test user for staging integration tests
- `STAGING_TEST_PASSWORD`: Test password for staging integration tests
- `CODECOV_TOKEN`: Codecov token for coverage reporting

### 2. GitHub Environments

Create the following environments in repository settings:

**staging**:
- URL: `https://staging.your-domain.com`
- Protection rules: None (auto-deploy on develop)

**production**:
- URL: `https://your-domain.com`
- Protection rules:
  - Required reviewers: 2
  - Wait timer: 5 minutes
  - Deployment branches: Only tags matching `v*.*.*`

### 3. Container Registry

The pipeline uses GitHub Container Registry (ghcr.io). No additional setup required.

Images are automatically pushed to:
- `ghcr.io/<owner>/<repo>/api-gateway`
- `ghcr.io/<owner>/<repo>/task-manager`
- `ghcr.io/<owner>/<repo>/agent-runtime`
- `ghcr.io/<owner>/<repo>/document-processor`
- `ghcr.io/<owner>/<repo>/frontend`

### 4. Kubernetes Cluster Setup

Ensure your Kubernetes clusters have:
- Namespace: `digital-workforce`
- Ingress controller (NGINX)
- Storage class for PVCs
- Secrets configured (see `infrastructure/kubernetes/02-secrets.yaml`)

## Branch Strategy

### Main Branches

- **main**: Production-ready code
  - Protected branch
  - Requires PR reviews
  - Runs all CI checks
  - Deploys to production on tag push

- **develop**: Development branch
  - Integration branch for features
  - Auto-deploys to staging
  - Runs all CI checks

### Feature Branches

- **feature/\***: New features
  - Branch from `develop`
  - Merge to `develop` via PR
  - Runs CI checks on PR

- **bugfix/\***: Bug fixes
  - Branch from `develop` or `main`
  - Merge to source branch via PR

- **hotfix/\***: Critical production fixes
  - Branch from `main`
  - Merge to both `main` and `develop`

### Release Process

1. **Create release branch**: `release/v1.0.0` from `develop`
2. **Test and fix**: Make final adjustments
3. **Merge to main**: Create PR to `main`
4. **Tag release**: Create tag `v1.0.0` on `main`
5. **Auto-deploy**: Release workflow deploys to production
6. **Merge back**: Merge `main` to `develop`

## Deployment Process

### Staging Deployment

**Automatic**:
1. Push to `develop` branch
2. CI tests run
3. Docker images built and pushed
4. Staging deployment triggered
5. Smoke tests run
6. Integration tests run

**Manual**:
1. Go to Actions → Deploy to Staging
2. Click "Run workflow"
3. Select branch
4. Click "Run workflow"

### Production Deployment

**Via Release**:
1. Create and push tag: `git tag v1.0.0 && git push origin v1.0.0`
2. Release workflow creates GitHub release
3. Production deployment triggered (requires approval)
4. Smoke tests run
5. Notification sent

**Manual Rollback**:
```bash
# Rollback to previous version
kubectl rollout undo deployment/api-gateway -n digital-workforce
kubectl rollout undo deployment/task-manager -n digital-workforce
kubectl rollout undo deployment/document-processor -n digital-workforce
kubectl rollout undo deployment/frontend -n digital-workforce
```

## Security Scanning

### Vulnerability Scanning

**Snyk**:
- Scans Python and Node.js dependencies
- Runs on every push and PR
- Daily scheduled scans
- Results uploaded to GitHub Security

**Trivy**:
- Scans Docker images and filesystem
- Runs on image builds
- Results uploaded to GitHub Security

**CodeQL**:
- Static code analysis
- Scans Python and JavaScript code
- Runs on every push and PR
- Results uploaded to GitHub Security

### Secret Scanning

**TruffleHog**:
- Scans for leaked secrets
- Runs on every push
- Checks commit history

### Dependency Review

**GitHub Dependency Review**:
- Reviews dependency changes in PRs
- Blocks PRs with vulnerable dependencies
- Severity threshold: moderate

## Troubleshooting

### Failed Tests

**Backend tests failing**:
```bash
# Run tests locally
cd backend
pytest -v

# Check specific test
pytest tests/test_specific.py -v

# Run with coverage
pytest --cov=. --cov-report=html
```

**Frontend tests failing**:
```bash
# Run tests locally
cd frontend
npm test

# Run specific test
npm test -- ComponentName

# Run with coverage
npm test -- --coverage
```

### Docker Build Failures

**Check Dockerfile**:
```bash
# Build locally
docker build -f infrastructure/docker/Dockerfile.api-gateway -t test .

# Check build logs
docker build --progress=plain -f infrastructure/docker/Dockerfile.api-gateway -t test .
```

**Multi-platform build issues**:
```bash
# Set up buildx
docker buildx create --use

# Build for specific platform
docker buildx build --platform linux/amd64 -f infrastructure/docker/Dockerfile.api-gateway -t test .
```

### Deployment Failures

**Check pod status**:
```bash
kubectl get pods -n digital-workforce
kubectl describe pod <pod-name> -n digital-workforce
kubectl logs <pod-name> -n digital-workforce
```

**Check rollout status**:
```bash
kubectl rollout status deployment/api-gateway -n digital-workforce
kubectl rollout history deployment/api-gateway -n digital-workforce
```

**Rollback deployment**:
```bash
kubectl rollout undo deployment/api-gateway -n digital-workforce
```

### Security Scan Failures

**Review security alerts**:
1. Go to repository → Security → Code scanning alerts
2. Review findings
3. Fix vulnerabilities
4. Re-run workflow

**Snyk token issues**:
- Verify `SNYK_TOKEN` secret is set
- Check token has correct permissions
- Token can be obtained from https://snyk.io/

### Secrets Issues

**Kubeconfig not working**:
```bash
# Verify kubeconfig is valid
kubectl --kubeconfig=<path> get nodes

# Base64 encode for GitHub secret
cat kubeconfig.yaml | base64 -w 0

# Test decoding
echo "<base64-string>" | base64 -d > test-kubeconfig.yaml
kubectl --kubeconfig=test-kubeconfig.yaml get nodes
```

## Best Practices

### Commits

- Write clear commit messages
- Reference issue numbers
- Keep commits atomic
- Sign commits (optional)

### Pull Requests

- Keep PRs small and focused
- Write descriptive PR descriptions
- Link related issues
- Ensure all CI checks pass
- Request reviews from team members

### Testing

- Write tests for new features
- Maintain test coverage >80%
- Run tests locally before pushing
- Fix failing tests immediately

### Security

- Never commit secrets
- Use environment variables
- Scan dependencies regularly
- Review security alerts promptly

### Deployment

- Test in staging first
- Monitor deployments
- Have rollback plan ready
- Document changes in release notes

## Monitoring

### CI/CD Metrics

Monitor the following metrics:
- Build success rate
- Test pass rate
- Deployment frequency
- Mean time to recovery (MTTR)
- Change failure rate

### GitHub Actions Usage

Check Actions usage:
1. Go to repository → Settings → Billing
2. Review Actions minutes used
3. Optimize workflows if needed

## Support

For CI/CD issues:
1. Check workflow logs in Actions tab
2. Review this documentation
3. Check GitHub Actions documentation
4. Contact DevOps team

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Documentation](https://docs.docker.com/)
- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Snyk Documentation](https://docs.snyk.io/)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
