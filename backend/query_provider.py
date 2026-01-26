import sys
sys.path.insert(0, '/Users/youqilin/Downloads/linX/backend')

from database.connection import get_db_session
from llm_providers.db_manager import ProviderDBManager

with get_db_session() as session:
    db_manager = ProviderDBManager(session)
    provider = db_manager.get_provider("llm-pool")
    if provider:
        print(f"Provider: {provider.name}")
        print(f"Protocol: {provider.protocol}")
        print(f"Base URL: {provider.base_url}")
        print(f"Enabled: {provider.enabled}")
        
        # 解密API key
        if provider.api_key_encrypted:
            api_key = db_manager._decrypt_api_key(provider.api_key_encrypted)
            print(f"API Key: {api_key[:20]}...")
    else:
        print("Provider not found")
