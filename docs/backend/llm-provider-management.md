# LLM Provider Management

管理 LLM 提供商配置的完整指南。

## 概述

LinX 平台采用**混合配置模式**，支持两种方式配置 LLM 提供商：

1. **config.yaml 静态配置**：系统默认提供商，启动时加载
2. **数据库动态配置**：通过 API 动态添加，立即生效

**优先级**：数据库配置 > config.yaml 配置（同名提供商时）

## 架构设计

### 为什么保留 config.yaml？

1. **开箱即用**：提供默认配置，快速部署
2. **环境隔离**：不同环境（开发/测试/生产）使用不同配置文件
3. **基础设施即代码**：配置文件可版本控制
4. **启动保障**：确保系统启动时至少有一个可用提供商

### 混合模式工作流程

```
系统启动
    ↓
1. 加载 config.yaml 中 enabled=true 的提供商
    ↓
2. 加载数据库中 enabled=true 的提供商
    ↓
3. 数据库提供商覆盖同名 config.yaml 提供商
    ↓
系统就绪
```

## 提供商来源

### Config.yaml 提供商

在 `backend/config.yaml` 中配置：

```yaml
llm:
  providers:
    ollama:
      enabled: true  # 必须设置为 true 才会加载
      base_url: "http://192.168.0.29:11434"
      models:
        chat: "qwen3-vl:30b"
    
    vllm:
      enabled: false  # 设置为 false 不会加载
      base_url: "http://localhost:8000"
```

**特点**：
- 只有 `enabled: true` 的提供商会被初始化
- 系统启动时加载
- 需要重启服务才能生效
- **不能通过 API 删除**
- 适合生产环境的稳定配置

**为什么只显示 ollama？**

因为你的 config.yaml 中：
- `ollama.enabled: true` ✅ 会显示
- `vllm.enabled: false` ❌ 不会显示
- `openai.enabled: false` ❌ 不会显示
- `anthropic.enabled: false` ❌ 不会显示

**如何显示更多提供商？**

方案 1：启用 config.yaml 中的提供商
```yaml
vllm:
  enabled: true  # 改为 true
  base_url: "http://localhost:8000"
```
然后重启服务。

方案 2：通过 API 动态添加（推荐）
```bash
POST /api/v1/llm/providers
{
  "name": "my_vllm",
  "protocol": "openai_compatible",
  "base_url": "http://localhost:8000",
  "selected_models": ["llama-3-70b"]
}
```
立即生效，无需重启。

### 数据库提供商

通过 API 动态添加：

```bash
POST /api/v1/llm/providers
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "name": "custom_ollama",
  "protocol": "ollama",
  "base_url": "http://custom-server:11434",
  "selected_models": ["llama2", "codellama"],
  "timeout": 30,
  "max_retries": 3
}
```

**特点**：
- 动态添加，**立即生效（无需重启）** ✨
- 可以通过 API 删除
- 存储在数据库中
- 适合测试和临时配置
- **同名时覆盖 config.yaml 提供商**
- **支持热重载（Hot Reload）**：创建、更新、删除操作自动重载提供商

## API 端点

### 列出所有提供商

```bash
GET /api/v1/llm/providers
Authorization: Bearer <token>
```

返回所有**运行中**的提供商（包括 config.yaml 和数据库）：

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
  },
  "default_provider": "ollama",
  "fallback_enabled": false
}
```

**注意**：
- 只显示 `enabled: true` 且成功初始化的提供商
- `is_config_based: true` = 来自 config.yaml，不能删除
- `is_config_based: false` = 来自数据库，可以删除

### 列出所有配置（管理界面）

```bash
GET /api/v1/llm/providers/list
Authorization: Bearer <admin_token>
```

返回所有配置的提供商（包括未启用的）：

```json
{
  "providers": [
    {
      "name": "ollama",
      "protocol": "ollama",
      "base_url": "http://192.168.0.29:11434",
      "enabled": true,
      "is_config_based": true
    },
    {
      "name": "vllm",
      "protocol": "openai_compatible",
      "base_url": "http://localhost:8000",
      "enabled": false,
      "is_config_based": true
    },
    {
      "name": "custom_ollama",
      "protocol": "ollama",
      "base_url": "http://custom:11434",
      "enabled": true,
      "is_config_based": false
    }
  ],
  "total": 3
}
```

### 添加提供商

```bash
POST /api/v1/llm/providers
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "name": "my_provider",
  "protocol": "ollama",  # 或 "openai_compatible"
  "base_url": "http://localhost:11434",
  "selected_models": ["model1", "model2"],
  "api_key": "optional_api_key",  # OpenAI compatible 需要
  "timeout": 30,
  "max_retries": 3
}
```

**立即生效**，无需重启服务。系统会自动热重载（Hot Reload）新添加的提供商。

### 更新提供商

```bash
PUT /api/v1/llm/providers/{name}
Authorization: Bearer <admin_token>
Content-Type: application/json

{
  "base_url": "http://new-url:11434",
  "enabled": true,
  "selected_models": ["new-model"]
}
```

**注意**：
- 只能更新数据库中的提供商
- config.yaml 提供商需要编辑配置文件并重启
- **更新后自动热重载**，立即生效

### 获取提供商详情（用于编辑）

```bash
GET /api/v1/llm/providers/{name}
Authorization: Bearer <admin_token>
```

返回提供商的完整配置信息：

```json
{
  "name": "ollama",
  "protocol": "ollama",
  "base_url": "http://192.168.0.29:11434",
  "timeout": 120,
  "max_retries": 3,
  "selected_models": ["qwen3-vl:30b", "nomic-embed-text"],
  "enabled": true,
  "has_api_key": false,
  "is_config_based": true
}
```

**用途**：
- 前端编辑提供商时获取完整配置
- 回显现有配置信息到编辑表单
- 支持 config.yaml 和数据库提供商

### 删除提供商

```bash
DELETE /api/v1/llm/providers/{name}
Authorization: Bearer <admin_token>
```

**限制**：
- 只能删除数据库中的提供商
- 尝试删除 config.yaml 提供商会返回 400 错误：

```json
{
  "detail": "Provider 'ollama' is defined in config.yaml and cannot be deleted via API. Please edit config.yaml directly."
}
```

**删除后自动热重载**，提供商立即从运行时移除。

### 手动重载提供商（可选）

```bash
POST /api/v1/llm/providers/reload
Authorization: Bearer <admin_token>
```

返回：
```json
{
  "success": true,
  "message": "Reloaded 3 database providers",
  "providers_count": 3
}
```

**用途**：
- 通常不需要手动调用（创建/更新/删除会自动重载）
- 用于故障排除或强制刷新提供商列表
- 只重载数据库提供商，不影响 config.yaml 提供商

## 热重载（Hot Reload）

### 什么是热重载？

热重载允许在不重启服务的情况下，动态加载、更新或删除数据库中的提供商配置。

### 自动热重载

以下操作会自动触发热重载：

1. **创建提供商**：`POST /api/v1/llm/providers`
   - 新提供商立即加载到运行时
   - 可以立即使用，无需重启

2. **更新提供商**：`PUT /api/v1/llm/providers/{name}`
   - 提供商配置立即更新
   - 正在进行的请求不受影响

3. **删除提供商**：`DELETE /api/v1/llm/providers/{name}`
   - 提供商立即从运行时移除
   - 新请求无法使用该提供商

### 手动热重载

如果需要手动刷新提供商列表：

```bash
POST /api/v1/llm/providers/reload
Authorization: Bearer <admin_token>
```

**使用场景**：
- 数据库直接修改后需要刷新
- 故障排除
- 确保运行时与数据库同步

### 热重载行为

- ✅ **加载数据库提供商**：所有 `enabled=true` 的数据库提供商
- ✅ **更新现有提供商**：如果提供商已存在，更新其配置
- ✅ **移除已删除提供商**：从数据库中删除的提供商会从运行时移除
- ❌ **不影响 config.yaml 提供商**：config.yaml 提供商保持不变

### 示例工作流

```bash
# 1. 添加新提供商（自动热重载）
curl -X POST http://localhost:8000/api/v1/llm/providers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "test_ollama",
    "protocol": "ollama",
    "base_url": "http://test-server:11434",
    "selected_models": ["llama2"]
  }'

# 2. 立即可用，无需重启
curl http://localhost:8000/api/v1/llm/providers \
  -H "Authorization: Bearer $TOKEN"
# 返回结果中包含 "test_ollama"

# 3. 更新提供商（自动热重载）
curl -X PUT http://localhost:8000/api/v1/llm/providers/test_ollama \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "base_url": "http://new-server:11434",
    "enabled": true
  }'

# 4. 删除提供商（自动热重载）
curl -X DELETE http://localhost:8000/api/v1/llm/providers/test_ollama \
  -H "Authorization: Bearer $TOKEN"

# 5. 立即生效，提供商已移除
curl http://localhost:8000/api/v1/llm/providers \
  -H "Authorization: Bearer $TOKEN"
# 返回结果中不再包含 "test_ollama"
```

## 前端界面

在设置页面（Settings），提供商列表会显示：

- **Config.yaml 提供商**：
  - 删除按钮被禁用（灰色）
  - 鼠标悬停显示："Cannot delete config.yaml provider"
  - 编辑按钮可用，会回显完整配置信息
  - 需要编辑 config.yaml 并重启服务才能永久生效

- **数据库提供商**：
  - 删除按钮可用
  - 编辑按钮可用，会回显完整配置信息
  - 修改立即生效

### 编辑提供商

点击编辑按钮时：
1. 前端调用 `GET /api/v1/llm/providers/{name}` 获取完整配置
2. 编辑表单自动填充现有配置信息：
   - 提供商名称（禁用编辑）
   - 协议类型
   - Base URL
   - 超时时间
   - 最大重试次数
   - 已选择的模型列表
3. 用户修改后保存，调用 `PUT /api/v1/llm/providers/{name}`

**注意**：
- config.yaml 提供商的修改不会持久化到配置文件
- 重启服务后会恢复 config.yaml 中的配置
- 如需永久修改 config.yaml 提供商，请直接编辑配置文件

## 最佳实践

### 生产环境

1. **主要提供商放在 config.yaml**
   ```yaml
   ollama:
     enabled: true
     base_url: "http://production-ollama:11434"
   ```

2. **使用环境变量管理敏感信息**
   ```yaml
   openai:
     enabled: true
     api_key: "${OPENAI_API_KEY}"
   ```

3. **临时提供商通过数据库添加**
   - 测试新模型
   - 临时扩容

### 开发环境

1. **快速测试**：通过 API 动态添加提供商
2. **稳定后**：移到 config.yaml 作为默认配置

### 启用更多提供商

**方案 A：启用 config.yaml 中的提供商**

编辑 `backend/config.yaml`：
```yaml
vllm:
  enabled: true  # 改为 true
  base_url: "http://localhost:8000"
  models:
    chat: "llama-3-70b"
```

重启服务：
```bash
docker-compose restart api
```

**方案 B：通过 API 动态添加（推荐）**

```bash
curl -X POST http://localhost:8000/api/v1/llm/providers \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my_vllm",
    "protocol": "openai_compatible",
    "base_url": "http://localhost:8000",
    "selected_models": ["llama-3-70b"]
  }'
```

立即生效，无需重启！

## 故障排除

### 为什么只显示 ollama？

**原因**：config.yaml 中只有 ollama 设置了 `enabled: true`

**解决方案**：
1. 检查 config.yaml 中其他提供商的 `enabled` 字段
2. 设置为 `true` 并重启服务
3. 或通过 API 动态添加新提供商

### 删除提供商失败

**错误**：`Provider 'vllm' not found`

**原因**：提供商只在 config.yaml 中配置，不在数据库中

**解决方案**：
1. 检查 config.yaml 是否有该提供商
2. 如需删除，编辑 config.yaml 设置 `enabled: false`
3. 重启服务

### 提供商不健康

**原因**：提供商服务未运行或 URL 不正确

**解决方案**：
1. 检查提供商服务是否运行
2. 验证 base_url 是否正确
3. 检查网络连接
4. 查看后端日志

### 数据库提供商未加载

**症状**：新添加的提供商在列表中不显示

**原因**：
1. ~~系统启动时数据库连接失败~~ （已修复：支持热重载）
2. 提供商初始化失败（URL 错误、服务不可用等）

**解决方案**：
1. 检查提供商配置是否正确
2. 查看后端日志中的错误信息
3. 手动触发热重载：
   ```bash
   POST /api/v1/llm/providers/reload
   ```
4. 如果仍然失败，检查提供商服务是否运行

### 提供商显示但不健康

**症状**：提供商在列表中显示，但标记为 unhealthy

**原因**：提供商服务未运行或健康检查失败

**解决方案**：
1. 检查提供商服务是否运行
2. 验证 base_url 是否正确
3. 检查网络连接和防火墙规则
4. 查看后端日志中的详细错误信息

## 配置优先级

当同名提供商同时存在于 config.yaml 和数据库时：

```
数据库配置 > config.yaml 配置
```

例如：
- config.yaml 中有 `ollama` 指向 `http://server1:11434`
- 数据库中有 `ollama` 指向 `http://server2:11434`
- **实际使用**：`http://server2:11434`（数据库配置）

## 参考

- [LLM Provider Configuration](../deployment/configuration.md)
- [API Documentation](../api/llm-endpoints.md)
- [Settings Page User Guide](../user-guide/settings.md)
- [Config.yaml Example](../../backend/config.yaml.example)


## Agent Configuration

### 获取可用提供商和模型

在配置 Agent 时，系统会自动获取当前可用的提供商和模型列表。

#### API 端点

```bash
GET /api/v1/llm/providers/available
Authorization: Bearer <token>
```

**返回示例**：

```json
{
  "ollama": ["qwen3-vl:30b", "nomic-embed-text", "llama2"],
  "openai": ["gpt-4", "gpt-3.5-turbo"],
  "anthropic": ["claude-3-opus", "claude-3-sonnet"]
}
```

**特点**：
- 只返回**健康且启用**的提供商
- 只返回有可用模型的提供商
- 自动过滤不健康的提供商
- 用于 Agent 配置界面的下拉选择

#### 前端使用

在 Agent 配置模态框中：

1. **加载提供商列表**：
   - 打开配置界面时自动调用 API
   - 显示加载状态
   - 处理错误情况

2. **选择提供商**：
   - 下拉列表显示所有可用提供商
   - 选择提供商后自动加载该提供商的模型列表

3. **选择模型**：
   - 根据选择的提供商显示对应的模型列表
   - 自动选择第一个模型作为默认值

4. **错误处理**：
   - 无可用提供商时显示警告信息
   - 提供重试按钮
   - 引导用户配置 LLM 提供商

#### 示例代码

```typescript
// 获取可用提供商和模型
const fetchAvailableProviders = async () => {
  try {
    const response = await api.get<Record<string, string[]>>(
      '/llm/providers/available'
    );
    setAvailableProviders(response);
    
    // 自动选择第一个提供商和模型
    if (Object.keys(response).length > 0) {
      const firstProvider = Object.keys(response)[0];
      const firstModel = response[firstProvider][0];
      setFormData({
        ...formData,
        provider: firstProvider,
        model: firstModel,
      });
    }
  } catch (error) {
    console.error('Failed to fetch providers:', error);
    setProvidersError('Failed to load available providers');
  }
};

// 提供商变更时更新模型列表
const handleProviderChange = (newProvider: string) => {
  const models = availableProviders[newProvider] || [];
  setFormData({
    ...formData,
    provider: newProvider,
    model: models[0] || '', // 自动选择第一个模型
  });
};
```

#### 用户体验

**正常流程**：
1. 用户打开 Agent 配置界面
2. 系统自动加载可用提供商和模型
3. 用户从下拉列表选择提供商
4. 系统自动显示该提供商的模型列表
5. 用户选择模型并保存配置

**无提供商场景**：
1. 系统检测到没有可用提供商
2. 显示警告信息："No LLM providers configured"
3. 提示用户："Please configure at least one LLM provider in the system settings"
4. 提供链接跳转到设置页面

**错误场景**：
1. 加载失败时显示错误信息
2. 提供重试按钮
3. 不阻止用户继续配置其他选项

### 最佳实践

1. **确保至少有一个健康的提供商**：
   - 在配置 Agent 之前，先在设置页面配置 LLM 提供商
   - 确保提供商状态为健康（healthy）

2. **选择合适的模型**：
   - 根据 Agent 的任务类型选择合适的模型
   - 考虑模型的性能和成本

3. **配置合理的参数**：
   - Temperature: 0.7（平衡创造性和准确性）
   - Max Tokens: 2000（根据任务调整）
   - Top P: 0.9（控制输出多样性）

4. **测试配置**：
   - 保存配置后测试 Agent 是否正常工作
   - 检查生成的响应质量
   - 根据需要调整参数
