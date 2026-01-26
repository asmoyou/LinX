import sys
sys.path.insert(0, '/Users/youqilin/Downloads/linX/backend')

from database.connection import get_db_session
from database.models import Agent
import json

with get_db_session() as session:
    agent = session.query(Agent).filter(Agent.name == "小新客服").first()
    if agent:
        print(f"Agent ID: {agent.agent_id}")
        print(f"Name: {agent.name}")
        print(f"LLM Provider: {agent.llm_provider}")
        print(f"LLM Model: {agent.llm_model}")
        print(f"Temperature: {agent.temperature}")
        print(f"Max Tokens: {agent.max_tokens}")
        print(f"Embedding Provider: {agent.embedding_provider}")
        print(f"Embedding Model: {agent.embedding_model}")
        print(f"Vector Dimension: {agent.vector_dimension}")
    else:
        print("Agent not found")
