import sys
sys.path.insert(0, '/Users/youqilin/Downloads/linX/backend')

from database.connection import get_db_session
from llm_providers.db_manager import ProviderDBManager
from llm_providers.custom_openai_provider import CustomOpenAIChat
from langchain_core.messages import HumanMessage
import json

# 获取provider配置
with get_db_session() as session:
    db_manager = ProviderDBManager(session)
    provider = db_manager.get_provider("llm-pool")
    api_key = db_manager._decrypt_api_key(provider.api_key_encrypted)

# 创建LLM实例
llm = CustomOpenAIChat(
    base_url=provider.base_url,
    model="Qwen/Qwen3-VL-32B-Thinking",
    temperature=0.7,
    max_tokens=100,
    api_key=api_key,
)

# 测试非流式调用
print("=== Testing non-streaming mode ===")
messages = [HumanMessage(content="你好")]
try:
    result = llm.invoke(messages)
    print(f"Result type: {type(result)}")
    print(f"Content length: {len(result.content)}")
    print(f"Response metadata: {json.dumps(result.response_metadata, indent=2, ensure_ascii=False)}")
    if hasattr(result, 'usage_metadata'):
        print(f"Usage metadata: {result.usage_metadata}")
except Exception as e:
    print(f"Error: {e}")

# 测试流式调用
print("\n=== Testing streaming mode ===")
chunk_count = 0
last_chunk = None
try:
    for chunk in llm.stream(messages):
        chunk_count += 1
        last_chunk = chunk
        if chunk_count <= 2:
            print(f"\nChunk {chunk_count}:")
            print(f"  Content: {chunk.content[:50] if chunk.content else 'None'}")
            print(f"  response_metadata: {chunk.response_metadata}")
            if hasattr(chunk, 'usage_metadata'):
                print(f"  usage_metadata: {chunk.usage_metadata}")

    print(f"\nTotal chunks: {chunk_count}")
    if last_chunk:
        print(f"\nLast chunk:")
        print(f"  response_metadata: {json.dumps(last_chunk.response_metadata, indent=2, ensure_ascii=False)}")
        if hasattr(last_chunk, 'usage_metadata'):
            print(f"  usage_metadata: {last_chunk.usage_metadata}")
except Exception as e:
    print(f"Error: {e}")
