import sys
sys.path.insert(0, '/Users/youqilin/Downloads/linX/backend')

from llm_providers.custom_openai_provider import CustomOpenAIChat
from langchain_core.messages import HumanMessage
import json

# 创建LLM实例
llm = CustomOpenAIChat(
    base_url="http://localhost:11434",
    model="qwen2.5:7b",
    temperature=0.7,
    max_tokens=100,
)

# 测试非流式调用
print("=== Testing non-streaming mode ===")
messages = [HumanMessage(content="你好")]
result = llm.invoke(messages)

print(f"Result type: {type(result)}")
print(f"Content: {result.content[:100]}")
print(f"Response metadata: {result.response_metadata}")
if hasattr(result, 'usage_metadata'):
    print(f"Usage metadata: {result.usage_metadata}")

# 测试流式调用
print("\n=== Testing streaming mode ===")
chunk_count = 0
last_chunk = None
for chunk in llm.stream(messages):
    chunk_count += 1
    last_chunk = chunk
    if chunk_count <= 2:
        print(f"Chunk {chunk_count}: {chunk}")
        print(f"  response_metadata: {chunk.response_metadata}")
        if hasattr(chunk, 'usage_metadata'):
            print(f"  usage_metadata: {chunk.usage_metadata}")

print(f"\nTotal chunks: {chunk_count}")
if last_chunk:
    print(f"Last chunk response_metadata: {last_chunk.response_metadata}")
    if hasattr(last_chunk, 'usage_metadata'):
        print(f"Last chunk usage_metadata: {last_chunk.usage_metadata}")
