# Message Bus Module

Redis-based inter-agent communication infrastructure for the Digital Workforce Platform.

## Overview

The Message Bus module provides reliable, scalable communication between agents using Redis. It supports both broadcast messaging (Pub/Sub) and point-to-point messaging (Streams) with built-in authorization and audit logging.

## Features

- **Connection Pooling**: Efficient Redis connection management
- **Pub/Sub Broadcasting**: Broadcast messages to all agents in a task
- **Redis Streams**: Reliable point-to-point messaging with acknowledgment
- **Message Authorization**: Verify agents can only message within assigned tasks
- **Audit Logging**: Track all message attempts and deliveries
- **JSON Serialization**: Automatic message serialization/deserialization

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Message Bus                          │
│                                                         │
│  ┌──────────────┐         ┌──────────────┐            │
│  │   Pub/Sub    │         │   Streams    │            │
│  │   Manager    │         │   Manager    │            │
│  │              │         │              │            │
│  │ - Broadcast  │         │ - Direct     │            │
│  │ - Subscribe  │         │ - Reliable   │            │
│  │ - Real-time  │         │ - Queued     │            │
│  └──────┬───────┘         └──────┬───────┘            │
│         │                        │                     │
│         └────────┬───────────────┘                     │
│                  │                                     │
│         ┌────────▼────────┐                           │
│         │ Redis Manager   │                           │
│         │ (Connection     │                           │
│         │  Pooling)       │                           │
│         └────────┬────────┘                           │
│                  │                                     │
│  ┌───────────────┼───────────────┐                   │
│  │               │               │                   │
│  ▼               ▼               ▼                   │
│ Authorization  Message        Audit                  │
│               Format         Logger                  │
└─────────────────────────────────────────────────────────┘
```

## Components

### 1. Redis Connection Manager

Manages Redis connections with connection pooling.

```python
from message_bus import get_redis_manager

# Get global manager instance
manager = get_redis_manager()

# Check health
if manager.health_check():
    print("Redis is healthy")

# Get pool statistics
stats = manager.get_pool_stats()
print(f"Active connections: {stats['in_use_connections']}")
```

### 2. Message Format

Standard message structure for inter-agent communication.

```python
from message_bus import Message, MessageType

# Create a direct message
message = Message.create(
    from_agent_id="agent-1",
    to_agent_id="agent-2",
    task_id="task-123",
    message_type=MessageType.DIRECT,
    payload={
        "content": "Hello, Agent 2!",
        "data": {"key": "value"}
    }
)

# Serialize to JSON
json_str = message.to_json()

# Deserialize from JSON
restored = Message.from_json(json_str)
```

**Message Types:**
- `DIRECT`: Agent A → Agent B
- `BROADCAST`: Agent A → All agents in task
- `REQUEST`: Agent A requests info from Agent B
- `RESPONSE`: Agent B responds to Agent A
- `EVENT`: Agent A notifies completion/status

### 3. Pub/Sub Manager

Broadcast messaging using Redis Pub/Sub.

```python
from message_bus import PubSubManager, Message, MessageType

manager = PubSubManager()

# Subscribe to task messages
def handle_message(message: Message):
    print(f"Received: {message.payload}")

manager.subscribe("task-123", handle_message)

# Publish broadcast message
message = Message.create(
    from_agent_id="agent-1",
    task_id="task-123",
    message_type=MessageType.BROADCAST,
    payload={"announcement": "Task completed!"}
)
manager.publish(message)

# Cleanup
manager.stop()
```

### 4. Streams Manager

Point-to-point messaging using Redis Streams.

```python
from message_bus import StreamsManager, Message, MessageType

manager = StreamsManager()

# Start consuming messages for an agent
def handle_message(message: Message):
    print(f"Received: {message.payload}")

manager.start_consumer("agent-2", handle_message)

# Send direct message
message = Message.create(
    from_agent_id="agent-1",
    to_agent_id="agent-2",
    task_id="task-123",
    message_type=MessageType.DIRECT,
    payload={"content": "Direct message"}
)
manager.send_message(message)

# Get stream info
info = manager.get_stream_info("agent-2")
print(f"Messages in stream: {info['length']}")

# Cleanup
manager.stop()
```

### 5. Message Authorization

Verify agents can only message within assigned tasks.

```python
from message_bus import MessageAuthorizer, AgentPermissions

authorizer = MessageAuthorizer()

# Register agent permissions
authorizer.register_agent(AgentPermissions(
    agent_id="agent-1",
    assigned_tasks={"task-123", "task-456"},
    can_broadcast=True,
    can_send_direct=True
))

# Authorize message
message = Message.create(
    from_agent_id="agent-1",
    to_agent_id="agent-2",
    task_id="task-123",
    message_type=MessageType.DIRECT,
    payload={"content": "Hello"}
)

authorized, reason = authorizer.authorize_message(message)
if not authorized:
    print(f"Message denied: {reason}")
```

### 6. Message Auditor

Track all message attempts and deliveries.

```python
from message_bus import MessageAuditor

auditor = MessageAuditor()

# Log message attempt
log_entry = auditor.log_message_attempt(
    message,
    authorized=True
)

# Log delivery status
auditor.log_message_delivery(
    message.message_id,
    delivered=True
)

# Get statistics
stats = auditor.get_statistics()
print(f"Authorization rate: {stats['authorization_rate']:.2%}")
print(f"Delivery rate: {stats['delivery_rate']:.2%}")

# Export logs
auditor.export_logs("audit_logs.json")
```

## Communication Patterns

### Pattern 1: Collaboration

Agents collaborate on a task by broadcasting completion events.

```python
# Agent A completes sub-task
message = Message.create(
    from_agent_id="agent-a",
    task_id="task-123",
    message_type=MessageType.EVENT,
    payload={
        "event": "subtask_completed",
        "subtask_id": "subtask-1",
        "result": {"data": "..."}
    }
)
pubsub_manager.publish(message)

# Agent B receives event and proceeds
def handle_event(message: Message):
    if message.payload["event"] == "subtask_completed":
        # Retrieve result from Company Memory
        # Proceed with dependent sub-task
        pass

pubsub_manager.subscribe("task-123", handle_event)
```

### Pattern 2: Request-Response

Agent A requests information from Agent B.

```python
# Agent A sends request
request = Message.create(
    from_agent_id="agent-a",
    to_agent_id="agent-b",
    task_id="task-123",
    message_type=MessageType.REQUEST,
    payload={"query": "status"},
    correlation_id="req-456"
)
streams_manager.send_message(request)

# Agent B processes and responds
def handle_request(message: Message):
    if message.is_request():
        response = message.create_response(
            from_agent_id="agent-b",
            payload={"status": "running", "progress": 0.75}
        )
        streams_manager.send_message(response)

streams_manager.start_consumer("agent-b", handle_request)

# Agent A receives response
def handle_response(message: Message):
    if message.is_response() and message.correlation_id == "req-456":
        print(f"Status: {message.payload['status']}")

streams_manager.start_consumer("agent-a", handle_response)
```

### Pattern 3: Coordination

Task Manager coordinates agent assignments.

```python
# Task Manager broadcasts assignments
message = Message.create(
    from_agent_id="task-manager",
    task_id="task-123",
    message_type=MessageType.BROADCAST,
    payload={
        "event": "task_assigned",
        "assignments": {
            "agent-a": "subtask-1",
            "agent-b": "subtask-2"
        }
    }
)
pubsub_manager.publish(message)

# Agents report progress
progress_message = Message.create(
    from_agent_id="agent-a",
    to_agent_id="task-manager",
    task_id="task-123",
    message_type=MessageType.EVENT,
    payload={
        "event": "progress_update",
        "progress": 0.5
    }
)
streams_manager.send_message(progress_message)
```

## Configuration

Redis configuration is in `backend/config.yaml`:

```yaml
database:
  redis:
    host: "localhost"
    port: 6379
    password: ""
    db: 0
    max_connections: 50
    socket_timeout: 5
    socket_connect_timeout: 5
    retry_on_timeout: true
    max_retries: 3
```

Message Bus configuration:

```yaml
message_bus:
  enable_pubsub: true
  enable_streams: true
  enable_queues: true
  
  retention:
    pubsub_ttl_seconds: 3600
    stream_max_length: 10000
    stream_ttl_days: 7
  
  consumer_groups:
    enabled: true
    max_consumers_per_group: 10
  
  serialization: "json"
  audit_messages: true
```

## Testing

Run tests with pytest:

```bash
# Run all message bus tests
pytest backend/message_bus/test_message_bus.py -v

# Run specific test class
pytest backend/message_bus/test_message_bus.py::TestPubSubManager -v

# Run with coverage
pytest backend/message_bus/test_message_bus.py --cov=message_bus --cov-report=html
```

## Performance Considerations

### Connection Pooling

- Default pool size: 50 connections
- Adjust based on concurrent agent count
- Monitor pool statistics for optimization

### Message Retention

- Pub/Sub: Messages not persisted (real-time only)
- Streams: Last 10,000 messages kept per agent
- Configure `stream_max_length` based on message volume

### Consumer Groups

- Use consumer groups for load balancing
- Multiple consumers can process messages in parallel
- Each message delivered to only one consumer in group

### Monitoring

```python
# Check Redis health
if not redis_manager.health_check():
    logger.error("Redis connection unhealthy")

# Monitor pool usage
stats = redis_manager.get_pool_stats()
if stats['in_use_connections'] > stats['max_connections'] * 0.8:
    logger.warning("Connection pool near capacity")

# Monitor stream backlog
info = streams_manager.get_stream_info("agent-id")
if info['length'] > 1000:
    logger.warning(f"Large message backlog: {info['length']}")
```

## Error Handling

### Connection Failures

```python
from redis.exceptions import ConnectionError

try:
    manager = get_redis_manager()
    manager.health_check()
except ConnectionError as e:
    logger.error(f"Redis connection failed: {e}")
    # Implement fallback or retry logic
```

### Message Delivery Failures

```python
try:
    streams_manager.send_message(message)
    auditor.log_message_delivery(message.message_id, delivered=True)
except Exception as e:
    logger.error(f"Message delivery failed: {e}")
    auditor.log_message_delivery(
        message.message_id,
        delivered=False,
        error=str(e)
    )
```

### Authorization Failures

```python
authorized, reason = authorizer.authorize_message(message)
if not authorized:
    logger.warning(f"Message authorization failed: {reason}")
    auditor.log_message_attempt(message, authorized=False, authorization_reason=reason)
    return
```

## Best Practices

1. **Always authorize messages** before sending
2. **Log all message attempts** for audit trail
3. **Use appropriate message types** (Pub/Sub for broadcast, Streams for direct)
4. **Handle consumer errors gracefully** to avoid message loss
5. **Monitor connection pool** usage and adjust as needed
6. **Set reasonable timeouts** for message operations
7. **Clean up resources** when stopping consumers
8. **Use correlation IDs** for request-response patterns

## References

- **Requirements**: Section 17 - Inter-Agent Communication
- **Design**: Section 15 - Inter-Agent Communication
- **Tasks**: Section 1.5 - Message Bus Setup - Redis

## Implementation Status

- [x] 1.5.1 Create Redis connection manager with connection pooling
- [x] 1.5.2 Implement Pub/Sub message publishing
- [x] 1.5.3 Implement Pub/Sub message subscription
- [x] 1.5.4 Implement Redis Streams for point-to-point messaging
- [x] 1.5.5 Add message serialization/deserialization (JSON)
- [x] 1.5.6 Implement message authorization checks
- [x] 1.5.7 Add message audit logging

## Future Enhancements

- Database persistence for audit logs
- Message encryption for sensitive data
- Rate limiting per agent
- Message priority queues
- Dead letter queue for failed messages
- Metrics export to Prometheus
- WebSocket integration for real-time UI updates
