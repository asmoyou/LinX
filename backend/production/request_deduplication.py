"""Request deduplication.

References:
- All requirements
- Design Section 10: Scalability and Performance
"""

import logging
import hashlib
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Any
import json

logger = logging.getLogger(__name__)


@dataclass
class RequestRecord:
    """Request record for deduplication."""
    
    request_id: str
    request_hash: str
    timestamp: float
    response: Optional[Any] = None
    status: str = "pending"  # pending, completed, failed


class RequestDeduplicator:
    """Request deduplicator.
    
    Prevents duplicate request processing:
    - Generates unique request hash
    - Tracks in-flight requests
    - Returns cached response for duplicates
    - Cleans up old records
    """
    
    def __init__(self, ttl_seconds: int = 300):
        """Initialize request deduplicator.
        
        Args:
            ttl_seconds: Time to live for request records
        """
        self.ttl_seconds = ttl_seconds
        self.requests: Dict[str, RequestRecord] = {}
        
        logger.info("RequestDeduplicator initialized")
    
    def generate_request_hash(
        self,
        method: str,
        path: str,
        body: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """Generate unique hash for request.
        
        Args:
            method: HTTP method
            path: Request path
            body: Request body
            user_id: User ID
            
        Returns:
            Request hash
        """
        # Create hash from request components
        hash_input = {
            "method": method,
            "path": path,
            "body": body or {},
            "user_id": user_id,
        }
        
        hash_str = json.dumps(hash_input, sort_keys=True)
        request_hash = hashlib.sha256(hash_str.encode()).hexdigest()
        
        return request_hash
    
    def check_duplicate(
        self,
        request_hash: str,
    ) -> Optional[RequestRecord]:
        """Check if request is duplicate.
        
        Args:
            request_hash: Request hash
            
        Returns:
            Existing request record if duplicate, None otherwise
        """
        # Clean up old records first
        self._cleanup_old_records()
        
        # Check if request exists
        if request_hash in self.requests:
            record = self.requests[request_hash]
            
            # Check if record is still valid
            age = time.time() - record.timestamp
            if age < self.ttl_seconds:
                logger.info(
                    f"Duplicate request detected: {request_hash[:8]}...",
                    extra={
                        "request_hash": request_hash,
                        "status": record.status,
                        "age_seconds": age,
                    },
                )
                return record
            else:
                # Record expired, remove it
                del self.requests[request_hash]
        
        return None
    
    def register_request(
        self,
        request_hash: str,
        request_id: str,
    ) -> RequestRecord:
        """Register new request.
        
        Args:
            request_hash: Request hash
            request_id: Request ID
            
        Returns:
            Request record
        """
        record = RequestRecord(
            request_id=request_id,
            request_hash=request_hash,
            timestamp=time.time(),
            status="pending",
        )
        
        self.requests[request_hash] = record
        
        logger.debug(f"Registered request: {request_hash[:8]}...")
        
        return record
    
    def complete_request(
        self,
        request_hash: str,
        response: Any,
        success: bool = True,
    ):
        """Mark request as completed.
        
        Args:
            request_hash: Request hash
            response: Response data
            success: Whether request succeeded
        """
        if request_hash in self.requests:
            record = self.requests[request_hash]
            record.status = "completed" if success else "failed"
            record.response = response
            
            logger.debug(
                f"Request completed: {request_hash[:8]}...",
                extra={"status": record.status},
            )
    
    def get_cached_response(
        self,
        request_hash: str,
    ) -> Optional[Any]:
        """Get cached response for request.
        
        Args:
            request_hash: Request hash
            
        Returns:
            Cached response or None
        """
        record = self.check_duplicate(request_hash)
        
        if record and record.status == "completed":
            logger.info(f"Returning cached response: {request_hash[:8]}...")
            return record.response
        
        return None
    
    def _cleanup_old_records(self):
        """Remove expired request records."""
        now = time.time()
        expired = []
        
        for request_hash, record in self.requests.items():
            age = now - record.timestamp
            if age >= self.ttl_seconds:
                expired.append(request_hash)
        
        for request_hash in expired:
            del self.requests[request_hash]
        
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired request records")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics.
        
        Returns:
            Statistics dictionary
        """
        now = time.time()
        
        pending = sum(1 for r in self.requests.values() if r.status == "pending")
        completed = sum(1 for r in self.requests.values() if r.status == "completed")
        failed = sum(1 for r in self.requests.values() if r.status == "failed")
        
        # Calculate average age
        ages = [now - r.timestamp for r in self.requests.values()]
        avg_age = sum(ages) / len(ages) if ages else 0
        
        return {
            "total_records": len(self.requests),
            "pending": pending,
            "completed": completed,
            "failed": failed,
            "average_age_seconds": avg_age,
            "ttl_seconds": self.ttl_seconds,
        }
    
    def clear(self):
        """Clear all request records."""
        self.requests.clear()
        logger.info("Request deduplicator cleared")


# Global deduplicator instance
_deduplicator: Optional[RequestDeduplicator] = None


def get_request_deduplicator() -> RequestDeduplicator:
    """Get global request deduplicator.
    
    Returns:
        Request deduplicator
    """
    global _deduplicator
    
    if _deduplicator is None:
        _deduplicator = RequestDeduplicator()
    
    return _deduplicator


# Decorator for automatic deduplication
def deduplicate_request(ttl_seconds: int = 300):
    """Decorator for request deduplication.
    
    Args:
        ttl_seconds: Time to live for cached responses
        
    Returns:
        Decorator function
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            deduplicator = get_request_deduplicator()
            
            # Generate request hash from arguments
            # This is a simplified version - in practice, you'd extract
            # method, path, body, user_id from the request context
            request_data = {
                "func": func.__name__,
                "args": str(args),
                "kwargs": str(kwargs),
            }
            request_hash = hashlib.sha256(
                json.dumps(request_data, sort_keys=True).encode()
            ).hexdigest()
            
            # Check for duplicate
            cached_response = deduplicator.get_cached_response(request_hash)
            if cached_response is not None:
                return cached_response
            
            # Check if request is in progress
            duplicate = deduplicator.check_duplicate(request_hash)
            if duplicate and duplicate.status == "pending":
                # Wait for original request to complete
                # In production, this would use async waiting
                import asyncio
                await asyncio.sleep(0.1)
                return deduplicator.get_cached_response(request_hash)
            
            # Register new request
            request_id = f"req_{int(time.time() * 1000)}"
            deduplicator.register_request(request_hash, request_id)
            
            try:
                # Execute function
                result = await func(*args, **kwargs)
                
                # Cache response
                deduplicator.complete_request(request_hash, result, success=True)
                
                return result
                
            except Exception as e:
                # Mark as failed
                deduplicator.complete_request(request_hash, None, success=False)
                raise e
        
        return wrapper
    return decorator
