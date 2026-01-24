"""Agent Management Endpoints for API Gateway.

References:
- Requirements 15: API and Integration Layer
- Task 2.1.7: Create agent endpoints
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID
import io
import base64

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user
from agent_framework.agent_registry import get_agent_registry
from object_storage.minio_client import get_minio_client
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class CreateAgentRequest(BaseModel):
    """Create agent request."""

    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=100)  # template type
    template_id: Optional[str] = None
    avatar: Optional[str] = None
    systemPrompt: Optional[str] = None
    skills: List[str] = []
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    maxTokens: Optional[int] = Field(default=2000, ge=1, le=8000)
    topP: Optional[float] = Field(default=0.9, ge=0.0, le=1.0)
    accessLevel: Optional[str] = Field(default="private")
    allowedKnowledge: List[str] = []
    allowedMemory: List[str] = []


class UpdateAgentRequest(BaseModel):
    """Update agent request."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    avatar: Optional[str] = None
    systemPrompt: Optional[str] = None
    skills: Optional[List[str]] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    maxTokens: Optional[int] = Field(None, ge=1, le=8000)
    topP: Optional[float] = Field(None, ge=0.0, le=1.0)
    accessLevel: Optional[str] = None
    allowedKnowledge: Optional[List[str]] = None
    allowedMemory: Optional[List[str]] = None
    # Knowledge Base Configuration
    embeddingModel: Optional[str] = None
    embeddingProvider: Optional[str] = None
    vectorDimension: Optional[int] = Field(None, ge=128, le=4096)
    topK: Optional[int] = Field(None, ge=1, le=20)
    similarityThreshold: Optional[float] = Field(None, ge=0.0, le=1.0)


class AgentResponse(BaseModel):
    """Agent response model."""

    id: str
    name: str
    type: str
    avatar: Optional[str] = None
    status: str
    currentTask: Optional[str] = None
    tasksCompleted: int = 0
    uptime: str = "0h 0m"
    systemPrompt: Optional[str] = None
    skills: List[str] = []
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: float = 0.7
    maxTokens: int = 2000
    topP: float = 0.9
    accessLevel: str = "private"
    allowedKnowledge: List[str] = []
    allowedMemory: List[str] = []
    # Knowledge Base Configuration
    embeddingModel: Optional[str] = None
    embeddingProvider: Optional[str] = None
    vectorDimension: Optional[int] = None
    topK: Optional[int] = None
    similarityThreshold: Optional[float] = None
    createdAt: datetime
    updatedAt: datetime


class AvailableProvidersResponse(BaseModel):
    """Available LLM providers and models for agent configuration."""
    
    providers: Dict[str, List[str]]  # provider_name -> list of model names


@router.get("/available-providers", response_model=AvailableProvidersResponse)
async def get_available_providers(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get available LLM providers and their models for agent configuration.
    
    Returns only enabled and healthy providers with their available models.
    This endpoint is used by the agent configuration UI to populate provider/model dropdowns.
    """
    try:
        from llm_providers.router import get_llm_provider
        
        llm_router = get_llm_provider()
        
        # Get all available providers
        provider_names = await llm_router.list_all_providers()
        
        # Get models for each provider
        providers_dict = {}
        for provider_name in provider_names:
            try:
                provider = await llm_router._get_provider(provider_name)
                if provider:
                    models = await provider.list_models()
                    if models:
                        providers_dict[provider_name] = models
            except Exception as e:
                logger.warning(f"Failed to get models for provider {provider_name}: {e}")
                continue
        
        return AvailableProvidersResponse(providers=providers_dict)
        
    except Exception as e:
        logger.error(f"Failed to get available providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available providers: {str(e)}",
        )


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: CreateAgentRequest, current_user: CurrentUser = Depends(get_current_user)
):
    """Create a new agent."""
    try:
        registry = get_agent_registry()
        
        # Register agent in database with LLM configuration
        agent_info = registry.register_agent(
            name=request.name,
            agent_type=request.type,
            owner_user_id=UUID(current_user.user_id),
            capabilities=request.skills or [],
            llm_provider=request.provider,
            llm_model=request.model,
            system_prompt=request.systemPrompt,
            temperature=request.temperature or 0.7,
            max_tokens=request.maxTokens or 2000,
            top_p=request.topP or 0.9,
            access_level=request.accessLevel or "private",
            allowed_knowledge=request.allowedKnowledge or [],
            allowed_memory=request.allowedMemory or [],
        )
        
        # Update status to idle after creation
        agent_info = registry.update_agent(
            agent_id=agent_info.agent_id,
            status="idle",
        )
        
        logger.info(
            f"Agent created: {agent_info.name}",
            extra={"agent_id": str(agent_info.agent_id), "user_id": current_user.user_id},
        )
        
        return AgentResponse(
            id=str(agent_info.agent_id),
            name=agent_info.name,
            type=agent_info.agent_type,
            avatar=agent_info.avatar,
            status=agent_info.status,
            currentTask=None,
            tasksCompleted=0,
            uptime="0h 0m",
            systemPrompt=agent_info.system_prompt,
            skills=agent_info.capabilities,
            model=agent_info.llm_model,
            provider=agent_info.llm_provider,
            temperature=agent_info.temperature,
            maxTokens=agent_info.max_tokens,
            topP=agent_info.top_p,
            accessLevel=agent_info.access_level,
            allowedKnowledge=agent_info.allowed_knowledge,
            allowedMemory=agent_info.allowed_memory,
            embeddingModel=agent_info.embedding_model,
            embeddingProvider=agent_info.embedding_provider,
            vectorDimension=agent_info.vector_dimension,
            topK=agent_info.top_k,
            similarityThreshold=agent_info.similarity_threshold,
            createdAt=agent_info.created_at,
            updatedAt=agent_info.updated_at,
        )
        
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create agent: {str(e)}",
        )


@router.get("", response_model=List[AgentResponse])
async def list_agents(current_user: CurrentUser = Depends(get_current_user)):
    """List user's agents."""
    try:
        registry = get_agent_registry()
        
        # Get agents for current user
        agents = registry.list_agents(owner_user_id=UUID(current_user.user_id))
        
        return [
            AgentResponse(
                id=str(agent.agent_id),
                name=agent.name,
                type=agent.agent_type,
                avatar=agent.avatar,
                status=agent.status,
                currentTask=None,  # TODO: Get from task manager
                tasksCompleted=0,  # TODO: Count from tasks table
                uptime="0h 0m",  # TODO: Calculate from created_at
                systemPrompt=agent.system_prompt,
                skills=agent.capabilities,
                model=agent.llm_model,
                provider=agent.llm_provider,
                temperature=agent.temperature,
                maxTokens=agent.max_tokens,
                topP=agent.top_p,
                accessLevel=agent.access_level,
                allowedKnowledge=agent.allowed_knowledge,
                allowedMemory=agent.allowed_memory,
                embeddingModel=agent.embedding_model,
                embeddingProvider=agent.embedding_provider,
                vectorDimension=agent.vector_dimension,
                topK=agent.top_k,
                similarityThreshold=agent.similarity_threshold,
                createdAt=agent.created_at,
                updatedAt=agent.updated_at,
            )
            for agent in agents
        ]
        
    except Exception as e:
        logger.error(f"Failed to list agents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(e)}",
        )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Get agent details."""
    try:
        registry = get_agent_registry()
        agent = registry.get_agent(UUID(agent_id))
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        
        # Check ownership
        if str(agent.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this agent",
            )
        
        return AgentResponse(
            id=str(agent.agent_id),
            name=agent.name,
            type=agent.agent_type,
            avatar=agent.avatar,
            status=agent.status,
            currentTask=None,
            tasksCompleted=0,
            uptime="0h 0m",
            systemPrompt=agent.system_prompt,
            skills=agent.capabilities,
            model=agent.llm_model,
            provider=agent.llm_provider,
            temperature=agent.temperature,
            maxTokens=agent.max_tokens,
            topP=agent.top_p,
            accessLevel=agent.access_level,
            allowedKnowledge=agent.allowed_knowledge,
            allowedMemory=agent.allowed_memory,
            embeddingModel=agent.embedding_model,
            embeddingProvider=agent.embedding_provider,
            vectorDimension=agent.vector_dimension,
            topK=agent.top_k,
            similarityThreshold=agent.similarity_threshold,
            createdAt=agent.created_at,
            updatedAt=agent.updated_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent: {str(e)}",
        )


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    request: UpdateAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update agent configuration."""
    try:
        registry = get_agent_registry()
        agent = registry.get_agent(UUID(agent_id))
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        
        # Check ownership
        if str(agent.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this agent",
            )
        
        # Update agent with all configuration fields
        updated_agent = registry.update_agent(
            agent_id=UUID(agent_id),
            name=request.name,
            avatar=request.avatar,
            capabilities=request.skills,
            llm_provider=request.provider,
            llm_model=request.model,
            system_prompt=request.systemPrompt,
            temperature=request.temperature,
            max_tokens=request.maxTokens,
            top_p=request.topP,
            access_level=request.accessLevel,
            allowed_knowledge=request.allowedKnowledge,
            allowed_memory=request.allowedMemory,
            embedding_model=request.embeddingModel,
            embedding_provider=request.embeddingProvider,
            vector_dimension=request.vectorDimension,
            top_k=request.topK,
            similarity_threshold=request.similarityThreshold,
        )
        
        if not updated_agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        
        logger.info(
            f"Agent updated: {updated_agent.name}",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )
        
        return AgentResponse(
            id=str(updated_agent.agent_id),
            name=updated_agent.name,
            type=updated_agent.agent_type,
            avatar=updated_agent.avatar,
            status=updated_agent.status,
            currentTask=None,
            tasksCompleted=0,
            uptime="0h 0m",
            systemPrompt=updated_agent.system_prompt,
            skills=updated_agent.capabilities,
            model=updated_agent.llm_model,
            provider=updated_agent.llm_provider,
            temperature=updated_agent.temperature,
            maxTokens=updated_agent.max_tokens,
            topP=updated_agent.top_p,
            accessLevel=updated_agent.access_level,
            allowedKnowledge=updated_agent.allowed_knowledge,
            allowedMemory=updated_agent.allowed_memory,
            embeddingModel=updated_agent.embedding_model,
            embeddingProvider=updated_agent.embedding_provider,
            vectorDimension=updated_agent.vector_dimension,
            topK=updated_agent.top_k,
            similarityThreshold=updated_agent.similarity_threshold,
            createdAt=updated_agent.created_at,
            updatedAt=updated_agent.updated_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update agent: {str(e)}",
        )


@router.post("/{agent_id}/avatar", response_model=Dict[str, str])
async def upload_agent_avatar(
    agent_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Upload agent avatar image.
    
    Accepts image files (JPEG, PNG, WebP) and stores them in MinIO.
    Returns the avatar URL.
    """
    try:
        registry = get_agent_registry()
        agent = registry.get_agent(UUID(agent_id))
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        
        # Check ownership
        if str(agent.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this agent",
            )
        
        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}",
            )
        
        # Read file data
        file_data = await file.read()
        file_stream = io.BytesIO(file_data)
        
        # Upload to MinIO
        minio_client = get_minio_client()
        bucket_name, object_key = minio_client.upload_file(
            bucket_type="images",
            file_data=file_stream,
            filename=f"avatar_{agent_id}.webp",
            user_id=current_user.user_id,
            task_id=None,
            agent_id=agent_id,
            content_type=file.content_type,
            metadata={
                "agent_id": agent_id,
                "agent_name": agent.name,
            }
        )
        
        # Generate presigned URL (valid for 7 days)
        from datetime import timedelta
        avatar_url = minio_client.get_presigned_url(
            bucket_name=bucket_name,
            object_key=object_key,
            expires=timedelta(days=7)
        )
        
        # Update agent with avatar URL
        updated_agent = registry.update_agent(
            agent_id=UUID(agent_id),
            avatar=avatar_url,
        )
        
        logger.info(
            f"Avatar uploaded for agent: {agent.name}",
            extra={"agent_id": agent_id, "user_id": current_user.user_id, "object_key": object_key},
        )
        
        return {
            "avatar_url": avatar_url,
            "bucket": bucket_name,
            "key": object_key,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload avatar: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload avatar: {str(e)}",
        )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Delete an agent."""
    try:
        registry = get_agent_registry()
        agent = registry.get_agent(UUID(agent_id))
        
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        
        # Check ownership
        if str(agent.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this agent",
            )
        
        # Delete agent
        deleted = registry.delete_agent(UUID(agent_id))
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        
        logger.info(
            f"Agent deleted: {agent_id}",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete agent: {str(e)}",
        )


class TestAgentRequest(BaseModel):
    """Test agent request."""

    message: str = Field(..., min_length=1, max_length=5000)
    history: Optional[List[Dict[str, str]]] = Field(default=None, description="Conversation history with role and content")


@router.post("/{agent_id}/test")
async def test_agent(
    agent_id: str,
    request: TestAgentRequest,
    stream: bool = True,  # Query parameter to enable/disable streaming
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Test agent with a message (streaming SSE response or single response).
    
    This endpoint tests the full agent capabilities including:
    - System prompt
    - Skills/functions
    - Memory access
    - Real agent execution via AgentExecutor
    
    Args:
        agent_id: Agent ID
        request: Test request with message
        stream: Enable streaming (default: True)
        current_user: Current authenticated user
    """
    from fastapi.responses import StreamingResponse
    from agent_framework.agent_executor import get_agent_executor, ExecutionContext
    from agent_framework.base_agent import BaseAgent, AgentConfig
    from langchain_community.chat_models import ChatOllama
    from langchain_openai import ChatOpenAI
    from llm_providers.custom_openai_provider import CustomOpenAIChat
    import json
    import asyncio
    import queue
    import threading
    
    try:
        registry = get_agent_registry()
        agent_info = registry.get_agent(UUID(agent_id))
        
        if not agent_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        
        # Check ownership
        if str(agent_info.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to test this agent",
            )
        
        logger.info(
            f"Testing agent: {agent_info.name}",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )
        
        async def generate_stream():
            """Generate SSE stream for agent execution with real streaming."""
            try:
                # Send start event
                yield f"data: {json.dumps({'type': 'start', 'content': 'Agent execution started'})}\n\n"
                
                # Track timing and tokens
                import time
                start_time = time.time()
                first_token_time = None
                total_tokens = 0
                input_tokens = 0
                output_tokens = 0
                
                # Create agent config
                config = AgentConfig(
                    agent_id=UUID(agent_id),
                    name=agent_info.name,
                    agent_type=agent_info.agent_type,
                    owner_user_id=UUID(current_user.user_id),
                    capabilities=agent_info.capabilities or [],
                    llm_model=agent_info.llm_model or "llama3.2:latest",
                    temperature=agent_info.temperature or 0.7,
                    max_iterations=10,
                    system_prompt=agent_info.system_prompt,
                )
                
                # Create agent instance
                agent = BaseAgent(config)
                
                from shared.config import get_config
                cfg = get_config()
                llm_config = cfg.get_section("llm")
                providers = llm_config.get("providers", {})
                
                provider_name = agent_info.llm_provider or "ollama"
                model_name = agent_info.llm_model or "llama3.2:latest"
                temperature = agent_info.temperature or 0.7
                
                yield f"data: {json.dumps({'type': 'info', 'content': 'Initializing agent...'})}\n\n"
                
                # Create LLM instance
                llm = None
                
                try:
                    from database.connection import get_db_session
                    from llm_providers.db_manager import ProviderDBManager
                    
                    with get_db_session() as db:
                        db_manager = ProviderDBManager(db)
                        db_provider = db_manager.get_provider(provider_name)
                        
                        if db_provider and db_provider.enabled:
                            if db_provider.protocol == "openai_compatible":
                                api_key = None
                                if db_provider.api_key_encrypted:
                                    api_key = db_manager._decrypt_api_key(db_provider.api_key_encrypted)
                                
                                llm = CustomOpenAIChat(
                                    base_url=db_provider.base_url,
                                    model=model_name,
                                    temperature=temperature,
                                    api_key=api_key,
                                    timeout=db_provider.timeout,
                                    max_retries=db_provider.max_retries,
                                )
                                logger.info(f"Using Custom OpenAI-compatible provider: {provider_name}")
                            
                            elif db_provider.protocol == "ollama":
                                llm = ChatOllama(
                                    base_url=db_provider.base_url,
                                    model=model_name,
                                    temperature=temperature,
                                )
                                logger.info(f"Using Ollama provider: {provider_name}")
                
                except Exception as db_error:
                    logger.warning(f"Failed to load provider from database: {db_error}")
                
                if llm is None:
                    if provider_name == "ollama" or provider_name not in providers:
                        ollama_config = providers.get("ollama", {})
                        base_url = ollama_config.get("base_url", "http://localhost:11434")
                        llm = ChatOllama(
                            base_url=base_url,
                            model=model_name,
                            temperature=temperature,
                        )
                        logger.info(f"Using Ollama (config.yaml): {base_url}")
                    elif provider_name in providers:
                        provider_config = providers.get(provider_name, {})
                        base_url = provider_config.get("base_url")
                        
                        if base_url:
                            llm = ChatOpenAI(
                                base_url=base_url,
                                model=model_name,
                                temperature=temperature,
                                api_key="dummy-key",
                            )
                            logger.info(f"Using provider from config.yaml: {provider_name}")
                
                if llm is None:
                    raise ValueError(f"Could not create LLM for provider: {provider_name}")
                
                agent.llm = llm
                
                # Initialize agent
                await asyncio.to_thread(agent.initialize)
                
                model_info = f"{model_name} via {provider_name}"
                yield f"data: {json.dumps({'type': 'info', 'content': f'Using model: {model_info}'})}\n\n"
                
                if config.capabilities:
                    yield f"data: {json.dumps({'type': 'info', 'content': f'Available skills: {', '.join(config.capabilities)}'})}\n\n"
                
                yield f"data: {json.dumps({'type': 'thinking', 'content': 'Retrieving relevant memories and processing...'})}\n\n"
                
                # Get memory context
                context = {}
                try:
                    from memory_system.memory_system import get_memory_system
                    from memory_system.memory_interface import SearchQuery, MemoryType
                    
                    memory_system = get_memory_system()
                    
                    # Search agent memories
                    agent_query = SearchQuery(
                        query_text=request.message,
                        agent_id=str(agent_id),
                        memory_type=MemoryType.AGENT,
                        top_k=5,
                    )
                    agent_memories = memory_system.retrieve_memories(agent_query)
                    context["agent_memories"] = [m.content for m in agent_memories]
                    
                    # Search company memories
                    company_query = SearchQuery(
                        query_text=request.message,
                        user_id=current_user.user_id,
                        memory_type=MemoryType.COMPANY,
                        top_k=5,
                    )
                    company_memories = memory_system.retrieve_memories(company_query)
                    context["company_memories"] = [m.content for m in company_memories]
                except Exception as mem_error:
                    logger.warning(f"Failed to retrieve memories: {mem_error}")
                
                # Build messages with conversation history
                from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
                
                system_prompt = agent._create_system_prompt()
                messages = [SystemMessage(content=system_prompt)]
                
                # Add conversation history if provided
                if request.history:
                    for msg in request.history:
                        if msg.get("role") == "user":
                            messages.append(HumanMessage(content=msg.get("content", "")))
                        elif msg.get("role") == "assistant":
                            messages.append(AIMessage(content=msg.get("content", "")))
                
                # Add current message
                user_message = request.message
                if context:
                    context_info = []
                    if context.get("agent_memories"):
                        context_info.append(f"Relevant memories: {', '.join(context['agent_memories'][:3])}")
                    if context.get("company_memories"):
                        context_info.append(f"Company knowledge: {', '.join(context['company_memories'][:3])}")
                    
                    if context_info:
                        user_message = f"{request.message}\n\nContext:\n" + "\n".join(context_info)
                
                messages.append(HumanMessage(content=user_message))
                
                # Estimate input tokens (rough approximation: 1 token ≈ 4 characters)
                input_text = system_prompt + user_message
                if request.history:
                    for msg in request.history:
                        input_text += msg.get("content", "")
                input_tokens = len(input_text) // 4
                
                # Use a queue to collect streamed tokens from the agent
                token_queue = queue.Queue()
                error_holder = [None]
                token_count = [0]  # Use list to allow modification in nested function
                
                def stream_callback(token: str):
                    """Callback for streaming tokens from agent."""
                    nonlocal first_token_time
                    if first_token_time is None:
                        first_token_time = time.time()
                    token_queue.put(token)
                    token_count[0] += len(token) // 4  # Rough token count
                
                def execute_agent():
                    """Execute agent in a separate thread."""
                    try:
                        # Stream tokens from LLM
                        final_output = ""
                        chunk_count = 0
                        
                        try:
                            for chunk in agent.llm.stream(messages):
                                if hasattr(chunk, 'content') and chunk.content:
                                    stream_callback(chunk.content)
                                    final_output += chunk.content
                                    chunk_count += 1
                            
                            if chunk_count == 0:
                                logger.warning("LLM streaming returned no chunks")
                                result = agent.llm.invoke(messages)
                                if hasattr(result, 'content'):
                                    final_output = result.content
                                else:
                                    final_output = str(result)
                                stream_callback(final_output)
                        
                        except Exception as stream_error:
                            logger.warning(f"Streaming failed: {stream_error}")
                            result = agent.llm.invoke(messages)
                            if hasattr(result, 'content'):
                                final_output = result.content
                            else:
                                final_output = str(result)
                            stream_callback(final_output)
                        
                        # Signal completion
                        token_queue.put(None)
                        
                    except Exception as e:
                        logger.error(f"Agent execution error: {e}", exc_info=True)
                        error_holder[0] = str(e)
                        token_queue.put(None)
                
                # Start agent execution in background thread
                exec_thread = threading.Thread(target=execute_agent)
                exec_thread.start()
                
                # Stream tokens as they arrive
                while True:
                    try:
                        # Wait for token with timeout
                        token = token_queue.get(timeout=0.1)
                        
                        if token is None:
                            # Execution complete
                            break
                        
                        # Send token to client
                        yield f"data: {json.dumps({'type': 'content', 'content': token})}\n\n"
                        
                    except queue.Empty:
                        # No token yet, continue waiting
                        continue
                
                # Wait for thread to complete
                exec_thread.join(timeout=5)
                
                # Calculate statistics
                end_time = time.time()
                total_time = end_time - start_time
                output_tokens = token_count[0]
                total_tokens = input_tokens + output_tokens
                
                # Calculate speeds
                time_to_first_token = (first_token_time - start_time) if first_token_time else 0
                tokens_per_second = output_tokens / (end_time - (first_token_time or start_time)) if first_token_time and output_tokens > 0 else 0
                
                # Check for errors
                if error_holder[0]:
                    yield f"data: {json.dumps({'type': 'error', 'content': f'Agent execution failed: {error_holder[0]}'})}\n\n"
                else:
                    # Send statistics
                    stats = {
                        'type': 'stats',
                        'timeToFirstToken': round(time_to_first_token, 2),
                        'tokensPerSecond': round(tokens_per_second, 1),
                        'inputTokens': input_tokens,
                        'outputTokens': output_tokens,
                        'totalTokens': total_tokens,
                        'totalTime': round(total_time, 2)
                    }
                    yield f"data: {json.dumps(stats)}\n\n"
                    yield f"data: {json.dumps({'type': 'done', 'content': 'Agent execution completed'})}\n\n"
                
                logger.info(f"Agent test completed: {agent_info.name}")
                
            except Exception as e:
                logger.error(f"Error during agent test streaming: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'content': f'Error: {str(e)}'})}\n\n"
        
        if stream:
            # Return streaming response
            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                },
            )
        else:
            # Non-streaming response - execute and return complete result
            try:
                # Create agent config
                config = AgentConfig(
                    agent_id=UUID(agent_id),
                    name=agent_info.name,
                    agent_type=agent_info.agent_type,
                    owner_user_id=UUID(current_user.user_id),
                    capabilities=agent_info.capabilities or [],
                    llm_model=agent_info.llm_model or "llama3.2:latest",
                    temperature=agent_info.temperature or 0.7,
                    max_iterations=10,
                    system_prompt=agent_info.system_prompt,
                )
                
                agent = BaseAgent(config)
                
                # Setup LLM (same as streaming)
                from shared.config import get_config
                cfg = get_config()
                llm_config = cfg.get_section("llm")
                providers = llm_config.get("providers", {})
                
                provider_name = agent_info.llm_provider or "ollama"
                model_name = agent_info.llm_model or "llama3.2:latest"
                temperature = agent_info.temperature or 0.7
                
                llm = None
                try:
                    from database.connection import get_db_session
                    from llm_providers.db_manager import ProviderDBManager
                    
                    with get_db_session() as db:
                        db_manager = ProviderDBManager(db)
                        db_provider = db_manager.get_provider(provider_name)
                        
                        if db_provider and db_provider.enabled:
                            if db_provider.protocol == "openai_compatible":
                                api_key = None
                                if db_provider.api_key_encrypted:
                                    api_key = db_manager._decrypt_api_key(db_provider.api_key_encrypted)
                                
                                llm = CustomOpenAIChat(
                                    base_url=db_provider.base_url,
                                    model=model_name,
                                    temperature=temperature,
                                    api_key=api_key,
                                    timeout=db_provider.timeout,
                                    max_retries=db_provider.max_retries,
                                )
                            elif db_provider.protocol == "ollama":
                                llm = ChatOllama(
                                    base_url=db_provider.base_url,
                                    model=model_name,
                                    temperature=temperature,
                                )
                except Exception as db_error:
                    logger.warning(f"Failed to load provider from database: {db_error}")
                
                if llm is None:
                    if provider_name == "ollama" or provider_name not in providers:
                        ollama_config = providers.get("ollama", {})
                        base_url = ollama_config.get("base_url", "http://localhost:11434")
                        llm = ChatOllama(base_url=base_url, model=model_name, temperature=temperature)
                    elif provider_name in providers:
                        provider_config = providers.get(provider_name, {})
                        base_url = provider_config.get("base_url")
                        if base_url:
                            llm = ChatOpenAI(base_url=base_url, model=model_name, temperature=temperature, api_key="dummy-key")
                
                if llm is None:
                    raise ValueError(f"Could not create LLM for provider: {provider_name}")
                
                agent.llm = llm
                await asyncio.to_thread(agent.initialize)
                
                # Execute without streaming
                exec_context = ExecutionContext(
                    agent_id=UUID(agent_id),
                    user_id=UUID(current_user.user_id),
                    task_description=request.message,
                )
                
                executor = get_agent_executor()
                result = await asyncio.to_thread(executor.execute, agent, exec_context)
                
                return {
                    "success": result.get("success"),
                    "output": result.get("output"),
                    "error": result.get("error"),
                }
                
            except Exception as e:
                logger.error(f"Non-streaming execution failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Execution failed: {str(e)}",
                )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test agent: {str(e)}",
        )
