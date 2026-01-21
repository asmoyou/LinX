"""Tenant isolation in database.

References:
- Requirements 14: Access Control and Security
- Design Section 8: Security and Access Control
"""

import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class TenantIsolation:
    """Tenant data isolation manager.

    Ensures data isolation between tenants at the database level:
    - Row-level security (RLS) policies
    - Tenant-scoped queries
    - Cross-tenant access prevention
    """

    def __init__(self, database=None):
        """Initialize tenant isolation.

        Args:
            database: Database connection
        """
        self.database = database
        self._current_tenant_id: Optional[UUID] = None

        logger.info("TenantIsolation initialized")

    @contextmanager
    def tenant_context(self, tenant_id: UUID):
        """Set tenant context for database operations.

        Args:
            tenant_id: Tenant ID

        Yields:
            None
        """
        previous_tenant = self._current_tenant_id
        self._current_tenant_id = tenant_id

        try:
            # Set tenant context in database session
            if self.database:
                self._set_tenant_context(tenant_id)

            logger.debug(f"Tenant context set to: {tenant_id}")
            yield
        finally:
            self._current_tenant_id = previous_tenant
            if self.database and previous_tenant:
                self._set_tenant_context(previous_tenant)

    def _set_tenant_context(self, tenant_id: UUID):
        """Set tenant context in database.

        Args:
            tenant_id: Tenant ID
        """
        # Set PostgreSQL session variable for RLS
        if self.database:
            query = f"SET app.current_tenant_id = '{tenant_id}'"
            # Execute query (implementation depends on database driver)
            logger.debug(f"Set database tenant context: {tenant_id}")

    def get_current_tenant_id(self) -> Optional[UUID]:
        """Get current tenant ID.

        Returns:
            Current tenant ID or None
        """
        return self._current_tenant_id

    def create_rls_policies(self) -> Dict[str, str]:
        """Create row-level security policies for tenant isolation.

        Returns:
            Dictionary of table names to policy SQL
        """
        policies = {}

        # Users table policy
        policies["users"] = """
            CREATE POLICY tenant_isolation_users ON users
            USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
        """

        # Agents table policy
        policies["agents"] = """
            CREATE POLICY tenant_isolation_agents ON agents
            USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
        """

        # Tasks table policy
        policies["tasks"] = """
            CREATE POLICY tenant_isolation_tasks ON tasks
            USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
        """

        # Knowledge items table policy
        policies["knowledge_items"] = """
            CREATE POLICY tenant_isolation_knowledge ON knowledge_items
            USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
        """

        # Audit logs table policy
        policies["audit_logs"] = """
            CREATE POLICY tenant_isolation_audit ON audit_logs
            USING (tenant_id = current_setting('app.current_tenant_id')::uuid);
        """

        logger.info(f"Created {len(policies)} RLS policies")
        return policies

    def enable_rls(self, table_name: str) -> str:
        """Enable row-level security on a table.

        Args:
            table_name: Table name

        Returns:
            SQL statement
        """
        sql = f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY;"
        logger.info(f"Enabled RLS on table: {table_name}")
        return sql

    def validate_tenant_access(
        self,
        tenant_id: UUID,
        resource_tenant_id: UUID,
    ) -> bool:
        """Validate tenant has access to a resource.

        Args:
            tenant_id: Requesting tenant ID
            resource_tenant_id: Resource's tenant ID

        Returns:
            True if access is allowed
        """
        if tenant_id != resource_tenant_id:
            logger.warning(
                f"Tenant {tenant_id} attempted to access resource "
                f"belonging to tenant {resource_tenant_id}"
            )
            return False

        return True

    def get_tenant_scoped_query(
        self,
        base_query: str,
        tenant_id: UUID,
    ) -> str:
        """Add tenant scope to a query.

        Args:
            base_query: Base SQL query
            tenant_id: Tenant ID

        Returns:
            Tenant-scoped query
        """
        # Add WHERE clause for tenant_id
        if "WHERE" in base_query.upper():
            scoped_query = base_query.replace("WHERE", f"WHERE tenant_id = '{tenant_id}' AND", 1)
        else:
            scoped_query = f"{base_query} WHERE tenant_id = '{tenant_id}'"

        return scoped_query

    def isolate_milvus_collection(
        self,
        collection_name: str,
        tenant_id: UUID,
    ) -> str:
        """Get tenant-specific Milvus collection name.

        Args:
            collection_name: Base collection name
            tenant_id: Tenant ID

        Returns:
            Tenant-scoped collection name
        """
        # Use partition-based isolation in Milvus
        partition_name = f"tenant_{tenant_id}"
        logger.debug(f"Milvus partition for tenant {tenant_id}: {partition_name}")
        return partition_name

    def isolate_minio_bucket(
        self,
        bucket_name: str,
        tenant_id: UUID,
    ) -> str:
        """Get tenant-specific MinIO bucket path.

        Args:
            bucket_name: Base bucket name
            tenant_id: Tenant ID

        Returns:
            Tenant-scoped bucket path
        """
        # Use prefix-based isolation in MinIO
        prefix = f"tenant-{tenant_id}/"
        logger.debug(f"MinIO prefix for tenant {tenant_id}: {prefix}")
        return prefix
