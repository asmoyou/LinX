"""Integration tests for Inter-agent communication.

Tests the communication between multiple agents.

References:
- Task 8.2.7: Test Inter-agent communication
"""

import pytest
from uuid import uuid4
from unittest.mock import Mock, patch, AsyncMock


@pytest.fixture
def mock_message_bus():
    """Mock message bus."""
    with patch('message_bus.pubsub.PubSubManager') as mock:
        bus = Mock()
        bus.publish = AsyncMock(return_value=True)
        bus.subscribe = AsyncMock()
        bus.get_messages = AsyncMock(return_value=[])
        mock.return_value = bus
        yield bus


@pytest.fixture
def mock_communicator():
    """Mock inter-agent communicator."""
    with patch('agent_framework.inter_agent_communication.get_communicator') as mock:
        communicator = Mock()
        communicator.send_message = AsyncMock(return_value={
            'message_id': str(uuid4()),
            'status': 'delivered'
        })
        communicator.request_assistance = AsyncMock(return_value={
            'response': 'Assistance provided',
            'from_agent': str(uuid4())
        })
        mock.return_value = communicator
        yield communicator


class TestInterAgentCommunication:
    """Test Inter-agent communication."""
    
    @pytest.mark.asyncio
    async def test_agent_sends_message_to_another_agent(self, mock_communicator):
        """Test that one agent can send a message to another agent."""
        from agent_framework.base_agent import BaseAgent, AgentConfig
        
        sender_config = AgentConfig(
            agent_id=uuid4(),
            name="Sender Agent",
            agent_type="assistant",
            owner_user_id=uuid4(),
            capabilities=["communication"]
        )
        
        sender = BaseAgent(config=sender_config)
        recipient_id = uuid4()
        
        # Send message
        result = await sender.send_message(
            to_agent_id=recipient_id,
            message="Can you help with data analysis?",
            message_type="request"
        )
        
        assert result['status'] == 'delivered'
        assert 'message_id' in result
        
        # Verify communicator was called
        mock_communicator.send_message.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_agent_receives_and_processes_message(self, mock_message_bus):
        """Test that agent can receive and process messages."""
        from agent_framework.base_agent import BaseAgent, AgentConfig
        
        receiver_config = AgentConfig(
            agent_id=uuid4(),
            name="Receiver Agent",
            agent_type="assistant",
            owner_user_id=uuid4(),
            capabilities=["data_analysis"]
        )
        
        receiver = BaseAgent(config=receiver_config)
        
        # Mock incoming message
        mock_message_bus.get_messages = AsyncMock(return_value=[
            {
                'message_id': str(uuid4()),
                'from_agent': str(uuid4()),
                'to_agent': str(receiver_config.agent_id),
                'content': 'Can you analyze this data?',
                'type': 'request'
            }
        ])
        
        # Receive messages
        messages = await receiver.receive_messages()
        
        assert len(messages) > 0
        assert messages[0]['type'] == 'request'
        
        # Process message
        response = await receiver.process_message(messages[0])
        
        assert response is not None
        assert 'reply' in response or 'action' in response
    
    @pytest.mark.asyncio
    async def test_agent_requests_assistance_from_capable_agent(self, mock_communicator):
        """Test that agent can request assistance from another agent with specific capabilities."""
        from agent_framework.base_agent import BaseAgent, AgentConfig
        
        requester_config = AgentConfig(
            agent_id=uuid4(),
            name="Requester Agent",
            agent_type="assistant",
            owner_user_id=uuid4(),
            capabilities=["task_coordination"]
        )
        
        requester = BaseAgent(config=requester_config)
        
        # Request assistance
        result = await requester.request_assistance(
            required_capability="data_visualization",
            request="Create a chart from this data",
            data={'values': [1, 2, 3, 4, 5]}
        )
        
        assert 'response' in result
        assert 'from_agent' in result
        
        # Verify request was sent
        mock_communicator.request_assistance.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_agent_collaboration_on_complex_task(self):
        """Test that multiple agents can collaborate on a complex task."""
        from agent_framework.base_agent import BaseAgent, AgentConfig
        
        # Create multiple agents with different capabilities
        coordinator_config = AgentConfig(
            agent_id=uuid4(),
            name="Coordinator",
            agent_type="coordinator",
            owner_user_id=uuid4(),
            capabilities=["task_coordination"]
        )
        
        analyst_config = AgentConfig(
            agent_id=uuid4(),
            name="Analyst",
            agent_type="analyst",
            owner_user_id=uuid4(),
            capabilities=["data_analysis"]
        )
        
        writer_config = AgentConfig(
            agent_id=uuid4(),
            name="Writer",
            agent_type="writer",
            owner_user_id=uuid4(),
            capabilities=["report_writing"]
        )
        
        coordinator = BaseAgent(config=coordinator_config)
        analyst = BaseAgent(config=analyst_config)
        writer = BaseAgent(config=writer_config)
        
        with patch('agent_framework.inter_agent_communication.InterAgentCommunicator') as mock_comm:
            comm_instance = Mock()
            mock_comm.return_value = comm_instance
            
            # Coordinator delegates to analyst
            comm_instance.send_message = AsyncMock(return_value={'status': 'delivered'})
            await coordinator.delegate_task(
                to_agent_id=analyst_config.agent_id,
                task="Analyze sales data"
            )
            
            # Analyst completes and notifies coordinator
            comm_instance.send_message = AsyncMock(return_value={'status': 'delivered'})
            await analyst.send_result(
                to_agent_id=coordinator_config.agent_id,
                result={'analysis': 'Sales increased by 20%'}
            )
            
            # Coordinator delegates to writer
            comm_instance.send_message = AsyncMock(return_value={'status': 'delivered'})
            await coordinator.delegate_task(
                to_agent_id=writer_config.agent_id,
                task="Write report based on analysis"
            )
            
            # Verify all communications occurred
            assert comm_instance.send_message.call_count >= 3
    
    @pytest.mark.asyncio
    async def test_message_routing_to_correct_agent(self, mock_message_bus):
        """Test that messages are routed to the correct recipient agent."""
        from agent_framework.inter_agent_communication import InterAgentCommunicator
        
        communicator = InterAgentCommunicator()
        
        sender_id = uuid4()
        recipient_id = uuid4()
        
        # Send message
        await communicator.send_message(
            from_agent_id=sender_id,
            to_agent_id=recipient_id,
            message="Test message",
            message_type="info"
        )
        
        # Verify message was published to correct channel
        mock_message_bus.publish.assert_called_once()
        call_args = mock_message_bus.publish.call_args
        
        # Check that recipient_id is in the channel or message
        assert str(recipient_id) in str(call_args)
    
    @pytest.mark.asyncio
    async def test_broadcast_message_to_multiple_agents(self, mock_message_bus):
        """Test that agent can broadcast message to multiple agents."""
        from agent_framework.inter_agent_communication import InterAgentCommunicator
        
        communicator = InterAgentCommunicator()
        
        sender_id = uuid4()
        recipient_ids = [uuid4(), uuid4(), uuid4()]
        
        # Broadcast message
        result = await communicator.broadcast_message(
            from_agent_id=sender_id,
            to_agent_ids=recipient_ids,
            message="Important announcement",
            message_type="broadcast"
        )
        
        assert result['delivered_count'] == len(recipient_ids)
        
        # Verify message was published for each recipient
        assert mock_message_bus.publish.call_count == len(recipient_ids)
    
    @pytest.mark.asyncio
    async def test_message_acknowledgment(self, mock_communicator):
        """Test that message delivery is acknowledged."""
        from agent_framework.inter_agent_communication import InterAgentCommunicator
        
        communicator = InterAgentCommunicator()
        
        sender_id = uuid4()
        recipient_id = uuid4()
        
        # Send message with acknowledgment request
        result = await communicator.send_message(
            from_agent_id=sender_id,
            to_agent_id=recipient_id,
            message="Please acknowledge",
            message_type="request",
            require_ack=True
        )
        
        assert 'message_id' in result
        
        # Wait for acknowledgment
        ack = await communicator.wait_for_acknowledgment(
            message_id=result['message_id'],
            timeout=5
        )
        
        assert ack['acknowledged'] is True
        assert ack['by_agent'] == str(recipient_id)
