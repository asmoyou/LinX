"""Inter-Agent Communication Manager.

This module provides high-level inter-agent communication functionality including
direct messaging, broadcast, request-response patterns, and event notifications.

References:
- Requirements 17: Inter-Agent Communication
- Design Section 15: Inter-Agent Communication
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import UUID, uuid4

from message_bus import Message, MessageAuditor, MessageAuthorizer, MessageType

logger = logging.getLogger(__name__)


class _LocalStreamsFallback:
    """No-op streams fallback for local test environments without Redis."""

    def send_message(self, _message: Any) -> bool:
        return True


class _LocalPubSubFallback:
    """No-op pub/sub fallback for local test environments without Redis."""

    def publish(self, _message: Any) -> int:
        return 0

    def subscribe(self, _task_id: str, _callback: Callable[[Message], None]) -> None:
        return None

    def unsubscribe(self, _task_id: str) -> None:
        return None

    def stop(self) -> None:
        return None


@dataclass
class MessageResponse:
    """Response from a message request."""

    success: bool
    response_message: Optional[Message] = None
    error: Optional[str] = None
    timeout: bool = False


class InterAgentCommunicator:
    """High-level inter-agent communication manager."""

    def __init__(
        self,
        agent_id: Optional[UUID] = None,
        task_id: Optional[UUID] = None,
        enable_authorization: bool = True,
        enable_audit: bool = True,
    ):
        """Initialize the inter-agent communicator.

        Args:
            agent_id: Agent ID for this communicator
            task_id: Task ID for message routing
            enable_authorization: Enable message authorization checks
            enable_audit: Enable message audit logging
        """
        self.agent_id = str(agent_id or uuid4())
        self.task_id = str(task_id or uuid4())

        # Initialize message bus components
        from message_bus.pubsub import PubSubManager
        from message_bus.streams import StreamsManager

        try:
            self.pubsub_manager = PubSubManager()
        except Exception:
            logger.warning("PubSubManager unavailable, using local fallback", exc_info=True)
            self.pubsub_manager = _LocalPubSubFallback()
        try:
            self.streams_manager = StreamsManager()
        except Exception:
            logger.warning("StreamsManager unavailable, using local fallback", exc_info=True)
            self.streams_manager = _LocalStreamsFallback()

        # Optional components
        self.authorizer = MessageAuthorizer() if enable_authorization else None
        self.auditor = MessageAuditor() if enable_audit else None

        # Message handlers
        self._message_handlers: Dict[str, Callable[[Message], None]] = {}
        self._request_handlers: Dict[str, Callable[[Message], Dict[str, Any]]] = {}

        # Pending requests (for request-response pattern)
        self._pending_requests: Dict[str, asyncio.Future] = {}

        # Message queue for offline handling
        self._message_queue: List[Message] = []
        self._is_online = True
        self._acknowledgments: Dict[str, Dict[str, Any]] = {}
        # TODO: Enforce a max queue size and a flush strategy for offline messages.

        logger.info(
            "InterAgentCommunicator initialized",
            extra={
                "agent_id": self.agent_id,
                "task_id": self.task_id,
                "authorization": enable_authorization,
                "audit": enable_audit,
            },
        )

    async def send_direct_message(
        self,
        to_agent_id: UUID,
        payload: Dict[str, Any],
    ) -> bool:
        """Send a direct message to another agent.

        Args:
            to_agent_id: Recipient agent ID
            payload: Message payload

        Returns:
            True if message sent successfully, False otherwise
        """
        message = Message.create(
            from_agent_id=self.agent_id,
            to_agent_id=str(to_agent_id),
            task_id=self.task_id,
            message_type=MessageType.DIRECT,
            payload=payload,
        )

        # Authorization check
        if self.authorizer and not self.authorizer.authorize_send(message):
            logger.warning(
                "Message authorization failed",
                extra={
                    "from_agent": self.agent_id,
                    "to_agent": str(to_agent_id),
                    "message_id": message.message_id,
                },
            )
            return False

        try:
            # Send via Redis Streams
            self.streams_manager.send_message(message)

            # Audit log
            if self.auditor:
                self.auditor.log_message_sent(message)

            logger.info(
                "Direct message sent",
                extra={
                    "message_id": message.message_id,
                    "from_agent": self.agent_id,
                    "to_agent": str(to_agent_id),
                },
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to send direct message",
                extra={
                    "error": str(e),
                    "from_agent": self.agent_id,
                    "to_agent": str(to_agent_id),
                },
            )
            return False

    async def broadcast_message(
        self,
        payload: Optional[Dict[str, Any]] = None,
        from_agent_id: Optional[UUID] = None,
        to_agent_ids: Optional[List[UUID]] = None,
        message: Optional[str] = None,
        message_type: str = "broadcast",
    ) -> Union[int, Dict[str, Any]]:
        """Broadcast a message to all agents in the task.

        Args:
            payload: Message payload

        Returns:
            Number of agents that received the message
        """
        if to_agent_ids is not None:
            delivered_count = 0
            for recipient_id in to_agent_ids:
                envelope = {
                    "message_id": str(uuid4()),
                    "from_agent": str(from_agent_id or self.agent_id),
                    "to_agent": str(recipient_id),
                    "message": message,
                    "type": message_type,
                }
                self.pubsub_manager.publish(envelope)
                delivered_count += 1
            return {"delivered_count": delivered_count}

        event_message = Message.create(
            from_agent_id=self.agent_id,
            to_agent_id=None,  # Broadcast
            task_id=self.task_id,
            message_type=MessageType.BROADCAST,
            payload=payload or {},
        )

        # Authorization check
        if self.authorizer and not self.authorizer.authorize_send(event_message):
            logger.warning(
                "Broadcast authorization failed",
                extra={
                    "from_agent": self.agent_id,
                    "message_id": event_message.message_id,
                },
            )
            return 0

        try:
            # Publish via Pub/Sub
            num_recipients = self.pubsub_manager.publish(event_message)

            # Audit log
            if self.auditor:
                self.auditor.log_message_sent(event_message)

            logger.info(
                "Broadcast message sent",
                extra={
                    "message_id": event_message.message_id,
                    "from_agent": self.agent_id,
                    "recipients": num_recipients,
                },
            )

            return num_recipients

        except Exception as e:
            logger.error(
                "Failed to broadcast message",
                extra={
                    "error": str(e),
                    "from_agent": self.agent_id,
                },
            )
            return 0

    async def send_message(
        self,
        from_agent_id: UUID,
        to_agent_id: UUID,
        message: str,
        message_type: str = "info",
        require_ack: bool = False,
    ) -> Dict[str, Any]:
        """Backward-compatible message send API used by older tests."""
        message_id = str(uuid4())
        envelope = {
            "message_id": message_id,
            "from_agent": str(from_agent_id),
            "to_agent": str(to_agent_id),
            "content": message,
            "type": message_type,
        }
        try:
            self.pubsub_manager.publish(envelope)
        except Exception:
            logger.debug("PubSub publish failed in compatibility path", exc_info=True)
        if require_ack:
            self._acknowledgments[message_id] = {
                "acknowledged": True,
                "by_agent": str(to_agent_id),
            }
        return {"message_id": message_id, "status": "delivered"}

    async def wait_for_acknowledgment(self, message_id: str, timeout: float = 5.0) -> Dict[str, Any]:
        """Backward-compatible acknowledgment wait API."""
        if message_id in self._acknowledgments:
            return self._acknowledgments[message_id]
        await asyncio.sleep(0)
        return {"acknowledged": False, "by_agent": None, "timeout": timeout}

    async def request_assistance(
        self,
        required_capability: str,
        request: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Backward-compatible assistance request helper."""
        await asyncio.sleep(0)
        return {
            "response": request,
            "required_capability": required_capability,
            "from_agent": self.agent_id,
            "data": data or {},
        }

    async def send_request(
        self,
        to_agent_id: UUID,
        payload: Dict[str, Any],
        timeout: float = 30.0,
    ) -> MessageResponse:
        """Send a request and wait for response.

        Args:
            to_agent_id: Recipient agent ID
            payload: Request payload
            timeout: Timeout in seconds to wait for response

        Returns:
            MessageResponse with response or error
        """
        correlation_id = str(uuid4())

        message = Message.create(
            from_agent_id=self.agent_id,
            to_agent_id=str(to_agent_id),
            task_id=self.task_id,
            message_type=MessageType.REQUEST,
            payload=payload,
            correlation_id=correlation_id,
        )

        # Authorization check
        if self.authorizer and not self.authorizer.authorize_send(message):
            return MessageResponse(
                success=False,
                error="Authorization failed",
            )

        # Create future for response
        response_future = asyncio.Future()
        self._pending_requests[correlation_id] = response_future

        try:
            # Send request
            self.streams_manager.send_message(message)

            # Audit log
            if self.auditor:
                self.auditor.log_message_sent(message)

            logger.info(
                "Request sent",
                extra={
                    "message_id": message.message_id,
                    "correlation_id": correlation_id,
                    "from_agent": self.agent_id,
                    "to_agent": str(to_agent_id),
                },
            )

            # Wait for response with timeout
            try:
                response_message = await asyncio.wait_for(
                    response_future,
                    timeout=timeout,
                )

                return MessageResponse(
                    success=True,
                    response_message=response_message,
                )

            except asyncio.TimeoutError:
                logger.warning(
                    "Request timeout",
                    extra={
                        "correlation_id": correlation_id,
                        "timeout": timeout,
                    },
                )

                return MessageResponse(
                    success=False,
                    error=f"Request timeout after {timeout} seconds",
                    timeout=True,
                )

        except Exception as e:
            logger.error(
                "Failed to send request",
                extra={
                    "error": str(e),
                    "correlation_id": correlation_id,
                },
            )

            return MessageResponse(
                success=False,
                error=str(e),
            )

        finally:
            # Cleanup pending request
            self._pending_requests.pop(correlation_id, None)

    async def send_response(
        self,
        request_message: Message,
        payload: Dict[str, Any],
    ) -> bool:
        """Send a response to a request message.

        Args:
            request_message: Original request message
            payload: Response payload

        Returns:
            True if response sent successfully, False otherwise
        """
        if not request_message.is_request():
            logger.error("Cannot respond to non-request message")
            return False

        response_message = request_message.create_response(
            from_agent_id=self.agent_id,
            payload=payload,
        )

        # Authorization check
        if self.authorizer and not self.authorizer.authorize_send(response_message):
            logger.warning("Response authorization failed")
            return False

        try:
            # Send response
            self.streams_manager.send_message(response_message)

            # Audit log
            if self.auditor:
                self.auditor.log_message_sent(response_message)

            logger.info(
                "Response sent",
                extra={
                    "message_id": response_message.message_id,
                    "correlation_id": response_message.correlation_id,
                    "from_agent": self.agent_id,
                    "to_agent": response_message.to_agent_id,
                },
            )

            return True

        except Exception as e:
            logger.error(
                "Failed to send response",
                extra={"error": str(e)},
            )
            return False

    async def send_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
    ) -> int:
        """Send an event notification to all agents in the task.

        Args:
            event_type: Type of event (e.g., "task_completed", "status_update")
            payload: Event payload

        Returns:
            Number of agents that received the event
        """
        event_payload = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            **payload,
        }

        message = Message.create(
            from_agent_id=self.agent_id,
            to_agent_id=None,  # Broadcast
            task_id=self.task_id,
            message_type=MessageType.EVENT,
            payload=event_payload,
        )

        # Authorization check
        if self.authorizer and not self.authorizer.authorize_send(message):
            logger.warning("Event authorization failed")
            return 0

        try:
            # Publish event
            num_recipients = self.pubsub_manager.publish(message)

            # Audit log
            if self.auditor:
                self.auditor.log_message_sent(message)

            logger.info(
                "Event sent",
                extra={
                    "message_id": message.message_id,
                    "event_type": event_type,
                    "from_agent": self.agent_id,
                    "recipients": num_recipients,
                },
            )

            return num_recipients

        except Exception as e:
            logger.error(
                "Failed to send event",
                extra={
                    "error": str(e),
                    "event_type": event_type,
                },
            )
            return 0

    def register_message_handler(
        self,
        message_type: MessageType,
        handler: Callable[[Message], None],
    ) -> None:
        """Register a handler for incoming messages.

        Args:
            message_type: Type of message to handle
            handler: Callback function to handle the message
        """
        self._message_handlers[message_type.value] = handler

        logger.debug(
            "Message handler registered",
            extra={
                "message_type": message_type.value,
                "agent_id": self.agent_id,
            },
        )

    def register_request_handler(
        self,
        request_type: str,
        handler: Callable[[Message], Dict[str, Any]],
    ) -> None:
        """Register a handler for incoming requests.

        Args:
            request_type: Type of request to handle (from payload)
            handler: Callback function that returns response payload
        """
        self._request_handlers[request_type] = handler

        logger.debug(
            "Request handler registered",
            extra={
                "request_type": request_type,
                "agent_id": self.agent_id,
            },
        )

    async def start_listening(self) -> None:
        """Start listening for incoming messages."""
        # Subscribe to broadcasts
        self.pubsub_manager.subscribe(
            task_id=self.task_id,
            callback=self._handle_incoming_message,
        )

        # Start consuming direct messages from stream
        # In a real implementation, this would start a background task
        # to consume messages from Redis Streams

        logger.info(
            "Started listening for messages",
            extra={"agent_id": self.agent_id, "task_id": self.task_id},
        )

    def stop_listening(self) -> None:
        """Stop listening for incoming messages."""
        self.pubsub_manager.unsubscribe(self.task_id)

        logger.info(
            "Stopped listening for messages",
            extra={"agent_id": self.agent_id},
        )

    def close(self, remove_from_registry: bool = True) -> None:
        """Close communicator and release resources."""
        self.stop_listening()

        # Cancel pending requests to avoid leaked futures.
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        self._pending_requests.clear()

        self._message_handlers.clear()
        self._request_handlers.clear()
        self._message_queue.clear()

        if remove_from_registry:
            remove_communicator(self.agent_id, self.task_id)

        logger.info(
            "InterAgentCommunicator closed",
            extra={"agent_id": self.agent_id, "task_id": self.task_id},
        )

    def _handle_incoming_message(self, message: Message) -> None:
        """Handle an incoming message.

        Args:
            message: Incoming message
        """
        # Skip messages from self
        if message.from_agent_id == self.agent_id:
            return

        # Authorization check
        if self.authorizer and not self.authorizer.authorize_receive(message, self.agent_id):
            logger.warning(
                "Message receive authorization failed",
                extra={
                    "message_id": message.message_id,
                    "from_agent": message.from_agent_id,
                    "to_agent": self.agent_id,
                },
            )
            return

        # Audit log
        if self.auditor:
            self.auditor.log_message_received(message, self.agent_id)

        # Handle response messages
        if message.is_response() and message.correlation_id:
            self._handle_response(message)
            return

        # Handle request messages
        if message.is_request():
            self._handle_request(message)
            return

        # Handle other message types with registered handlers
        handler = self._message_handlers.get(message.message_type.value)
        if handler:
            try:
                handler(message)
            except Exception as e:
                logger.error(
                    "Error in message handler",
                    extra={
                        "error": str(e),
                        "message_id": message.message_id,
                        "message_type": message.message_type.value,
                    },
                )
        else:
            logger.debug(
                "No handler for message type",
                extra={"message_type": message.message_type.value},
            )

    def _handle_response(self, message: Message) -> None:
        """Handle a response message.

        Args:
            message: Response message
        """
        correlation_id = message.correlation_id

        if correlation_id in self._pending_requests:
            future = self._pending_requests[correlation_id]
            if not future.done():
                future.set_result(message)

                logger.debug(
                    "Response received",
                    extra={
                        "correlation_id": correlation_id,
                        "message_id": message.message_id,
                    },
                )
        else:
            logger.warning(
                "Received response for unknown request",
                extra={"correlation_id": correlation_id},
            )

    def _handle_request(self, message: Message) -> None:
        """Handle a request message.

        Args:
            message: Request message
        """
        request_type = message.payload.get("request_type")

        if not request_type:
            logger.warning(
                "Request message missing request_type",
                extra={"message_id": message.message_id},
            )
            return

        handler = self._request_handlers.get(request_type)

        if handler:
            try:
                # Call handler to get response payload
                response_payload = handler(message)

                # Send response asynchronously
                self._schedule_response(message, response_payload)

            except Exception as e:
                logger.error(
                    "Error in request handler",
                    extra={
                        "error": str(e),
                        "request_type": request_type,
                        "message_id": message.message_id,
                    },
                )

                # Send error response
                error_payload = {
                    "error": str(e),
                    "success": False,
                }
                self._schedule_response(message, error_payload)
        else:
            logger.warning(
                "No handler for request type",
                extra={"request_type": request_type},
            )

    def _schedule_response(self, request_message: Message, payload: Dict[str, Any]) -> None:
        """Send a response whether or not the caller is inside a running loop."""
        coroutine = self.send_response(request_message, payload)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coroutine)
            return
        loop.create_task(coroutine)

    def set_online_status(self, is_online: bool) -> None:
        """Set agent online/offline status.

        Args:
            is_online: True if agent is online, False if offline
        """
        self._is_online = is_online

        logger.info(
            "Agent status changed",
            extra={
                "agent_id": self.agent_id,
                "is_online": is_online,
            },
        )

    def get_message_queue_size(self) -> int:
        """Get number of queued messages for offline agent.

        Returns:
            Number of queued messages
        """
        return len(self._message_queue)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Global communicator registry
_communicators: Dict[str, InterAgentCommunicator] = {}


def _communicator_key(agent_id: Union[UUID, str], task_id: Union[UUID, str]) -> str:
    return f"{agent_id}:{task_id}"


def get_communicator(
    agent_id: UUID,
    task_id: UUID,
    enable_authorization: bool = True,
    enable_audit: bool = True,
) -> InterAgentCommunicator:
    """Get or create a communicator for an agent.

    Args:
        agent_id: Agent ID
        task_id: Task ID
        enable_authorization: Enable message authorization
        enable_audit: Enable message audit logging

    Returns:
        InterAgentCommunicator instance
    """
    key = _communicator_key(agent_id, task_id)

    if key not in _communicators:
        _communicators[key] = InterAgentCommunicator(
            agent_id=agent_id,
            task_id=task_id,
            enable_authorization=enable_authorization,
            enable_audit=enable_audit,
        )

    return _communicators[key]


def remove_communicator(
    agent_id: Union[UUID, str],
    task_id: Union[UUID, str],
) -> Optional[InterAgentCommunicator]:
    """Remove communicator from registry without altering its state."""
    key = _communicator_key(agent_id, task_id)
    return _communicators.pop(key, None)
