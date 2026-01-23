# Agent Testing Feature

Test your AI agents with real-time streaming conversations.

## Overview

The agent testing feature allows you to interact with your configured agents in a chat interface before deploying them to production tasks. This helps validate agent behavior, system prompts, and model configurations.

## How to Test an Agent

### From Agent Card

1. Navigate to the **Agents** page
2. Find the agent you want to test
3. Click the **Test Agent** button at the bottom of the agent card
4. Or click the three-dot menu and select **Test Agent**

### From Agent Details

1. Click on an agent to view its details
2. Click the **Test Agent** button in the header
3. The test modal will open

## Test Interface

The test interface provides:

- **Real-time streaming responses**: See the agent's response as it's generated
- **Chat history**: View the conversation history during the test session
- **Message input**: Send messages to test different scenarios
- **Error handling**: Clear error messages if something goes wrong

### Keyboard Shortcuts

- **Enter**: Send message
- **Shift + Enter**: New line in message

## What Gets Tested

When you test an agent, the system uses:

- Agent's configured system prompt
- Selected LLM model and provider
- Temperature, max tokens, and other model parameters
- Agent's capabilities and skills (if configured)

## Tips for Effective Testing

1. **Test edge cases**: Try unusual inputs to see how the agent handles them
2. **Verify system prompt**: Check if the agent follows its configured instructions
3. **Test different scenarios**: Use various types of questions relevant to the agent's role
4. **Check response quality**: Evaluate if the model and temperature settings are appropriate

## Limitations

- Test sessions are temporary and not saved
- Test conversations don't affect agent statistics or task counts
- Memory and knowledge base access may be limited in test mode

## Troubleshooting

### "Failed to load available providers"

- Check that at least one LLM provider is configured in Settings
- Verify the provider is running and accessible
- Check network connectivity

### "No response from agent"

- Verify the selected model is available
- Check LLM provider logs for errors
- Ensure the model has sufficient resources

### Streaming stops unexpectedly

- Check network connection
- Verify max tokens setting isn't too low
- Review backend logs for errors

## Related Documentation

- [Agent Configuration](./agent-configuration.md)
- [LLM Provider Setup](../backend/llm-providers.md)
- [API Documentation](../api/agents-api.md)
