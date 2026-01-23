"""Agent Management Endpoints for API Gateway.

References:
- Requirements 15: API and Integration Layer
- Task 2.1.7: Create agent endpoints
"""

from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user
from agent_framework.agent_registry import get_agent_registry
from agent_framework.default_templates import get_default_templates
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class CreateAgentRequest(BaseModel):
    """Create agent request."""

    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=100)  # template type
    template_id: Optional[str] = None
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


class AgentResponse(BaseModel):
    """Agent response model."""

    id: str
    name: str
    type: str
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
    createdAt: datetime
    updatedAt: datetime


class AgentTemplateResponse(BaseModel):
    """Agent template response."""

    id: str
    name: str
    description: str
    default_skills: List[str]
    default_config: dict


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


@router.get("/templates", response_model=List[AgentTemplateResponse])
async def list_templates(current_user: CurrentUser = Depends(get_current_user)):
    """List available agent templates."""
    try:
        templates = get_default_templates()
        
        return [
            AgentTemplateResponse(
                id=template.template_id,
                name=template.name,
                description=template.description,
                default_skills=template.default_skills,
                default_config=template.default_config,
            )
            for template in templates
        ]
        
    except Exception as e:
        logger.error(f"Failed to list templates: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list templates: {str(e)}",
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


@router.post("/{agent_id}/test")
async def test_agent(
    agent_id: str,
    request: TestAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Test agent with a message (streaming response)."""
    from fastapi.responses import StreamingResponse
    import json
    import asyncio
    from llm_providers.router import get_llm_router
    
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
                detail="You don't have permission to test this agent",
            )
        
        logger.info(
            f"Testing agent: {agent.name}",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )
        
        async def generate_response():
            """Generate streaming response."""
            try:
                # Get LLM router
                llm_router = get_llm_router()
                
                # Get agent configuration
                system_prompt = agent.system_prompt or f"You are {agent.name}, a helpful AI assistant."
                model = agent.llm_model or "llama3.2:latest"  # Use agent's configured model
                provider = agent.llm_provider  # Use agent's configured provider
                temperature = agent.temperature or 0.7
                max_tokens = agent.max_tokens or 2000
                
                # Prepare messages
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": request.message},
                ]
                
                # Send initial status
                yield f"data: {json.dumps({'type': 'status', 'content': 'Connecting to LLM...'})}\n\n"
                await asyncio.sleep(0.1)
                
                # Stream response from LLM
                full_response = ""
                async for chunk in llm_router.generate_stream(
                    messages=messages,
                    model=model,
                    provider=provider,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ):
                    if chunk:
                        full_response += chunk
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk})}\n\n"
                
                # Send completion status
                yield f"data: {json.dumps({'type': 'done', 'content': full_response})}\n\n"
                
                logger.info(
                    f"Agent test completed: {agent.name}",
                    extra={"agent_id": agent_id, "response_length": len(full_response)},
                )
                
            except Exception as e:
                logger.error(f"Error during agent test: {e}")
                error_msg = f"Error: {str(e)}"
                yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
        
        return StreamingResponse(
            generate_response(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test agent: {str(e)}",
        )
