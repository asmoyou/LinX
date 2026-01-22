# LLM Provider Management

管理 LLM 提供商配置的指南。

## 概述

LinX 平台支持两种方式配置 LLM 提供商：

1. **config.yaml 静态配置**：系统级配置，需要重启服务生效
2. **数据库动态配置**：通过 API 动态添加，无需重启

## 提供商来源

### Config.yaml 提供商

在 `backend/config.yaml` 中配置的提供商：

```yaml
llm:
  providers:
    ollama:
      enabled: true
      base_url: "http://192.168.0.29:11434"
      models:
        chat: "qwen3-vl:30b"
    
    vllm:
      enabled: false
      base_url: "http://localhost:8000"
      models:
        chat: "llama-3-70b"
```

**特点**：
- 系统启动时加载
- 需要重启服务才能生效
- **不能通过 API 删除**
- 适合生产环境的稳定配置

### 数据库提供商

通过 API 动态添加的提供商：

```bash
POST /api/v1/llm/providers
{
  "name": "custom_ollama",
  "protocol": "ollama",
  "base_url": "http://custom-server:11434",
  "selected_models": ["llama2", "codellama"]
}
```

**特点**：
- 动态添加，立即生效
- 可以通过 API 删除
- 存储在数据库中
- 适合测试和临时配置

## API 端点

### 列出所有提供商

```bash
GET /api/v1/llm/providers
```

返回所有提供商（包括 config.yaml 和数据库）：

```json
{
  "providers": {
    "ollama": {
      "name": "ollama",
      "healthy": true,
      "available_models": ["qwen3-vl:30b"],
      "is_config_based": true
    },
    "custom_ollama": {
      "name": "custom_ollama",
      "healthy": true,
      "available_models": ["llama2"],
      "is_config_based": false
    }
  }
}
```

`is_config_based` 字段说明：
- `true`：来自 config.yaml，不能删除
- `false`：来自数据库，可以删除

### 添加提供商

```bash
POST /api/v1/llm/providers
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "name": "my_provider",
  "protocol": "ollama",
  "base_url": "http://localhost:11434",
  "selected_models": ["model1", "model2"],
  "timeout": 30,
  "max_retries": 3
}
```

### 删除提供商

```bash
DELETE /api/v1/llm/providers/{name}
Authorization: Bearer <admin_token>
```

**注意**：
- 只能删除数据库中的提供商
- 尝试删除 config.yaml 提供商会返回 400 错误：

```json
{
  "detail": "Provider 'vllm' is defined in config.yaml and cannot be deleted via API. Please edit config.yaml directly."
}
```

## 前端界面

在设置页面（Settings），提供商列表会显示：

- **Config.yaml 提供商**：删除按钮被禁用，鼠标悬停显示提示
- **数据库提供商**：删除按钮可用

## 最佳实践

### 生产环境

1. 在 config.yaml 中配置主要提供商
2. 使用环境变量管理敏感信息（API keys）
3. 通过数据库添加临时或测试提供商

### 开发环境

1. 可以使用数据库动态添加提供商进行测试
2. 测试完成后可以将配置移到 config.yaml

### 删除提供商

- **数据库提供商**：直接通过 API 删除
- **Config.yaml 提供商**：编辑 config.yaml，设置 `enabled: false` 或删除配置，然后重启服务

## 故障排除

### 删除提供商失败

**错误**：`Provider 'vllm' not found`

**原因**：提供商只在 config.yaml 中配置，不在数据库中

**解决方案**：
1. 检查 config.yaml 是否有该提供商配置
2. 如需删除，编辑 config.yaml 并重启服务
3. 或者设置 `enabled: false` 禁用该提供商

### 提供商列表不显示

**原因**：可能是 LLM router 未初始化

**解决方案**：
1. 检查 config.yaml 配置是否正确
2. 查看后端日志是否有错误
3. 确保至少有一个提供商启用

## 参考

- [LLM Provider Configuration](../deployment/configuration.md)
- [API Documentation](../api/llm-endpoints.md)
- [Settings Page User Guide](../user-guide/settings.md)
