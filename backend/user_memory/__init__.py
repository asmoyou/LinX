"""Lazy exports for the user-memory package."""

from importlib import import_module

_EXPORTS = {
    "RetrievedMemoryItem": ("user_memory.items", "RetrievedMemoryItem"),
    "UserMemoryConsolidator": ("user_memory.consolidator", "UserMemoryConsolidator"),
    "MemoryEntryData": ("user_memory.session_ledger_repository", "MemoryEntryData"),
    "MemoryLinkData": ("user_memory.session_ledger_repository", "MemoryLinkData"),
    "MemoryProjectionData": (
        "user_memory.session_ledger_repository",
        "MemoryProjectionData",
    ),
    "MemoryObservationData": ("user_memory.session_ledger_repository", "MemoryObservationData"),
    "MemorySessionEventData": ("user_memory.session_ledger_repository", "MemorySessionEventData"),
    "MemorySessionSnapshot": ("user_memory.session_ledger_repository", "MemorySessionSnapshot"),
    "UserMemoryProjector": ("user_memory.projector", "UserMemoryProjector"),
    "UserMemoryRepository": ("user_memory.repository", "UserMemoryRepository"),
    "SessionLedgerRepository": (
        "user_memory.session_ledger_repository",
        "SessionLedgerRepository",
    ),
    "SessionLedgerService": ("user_memory.session_ledger_service", "SessionLedgerService"),
    "UserMemoryBuilder": ("user_memory.builder", "UserMemoryBuilder"),
    "UserMemoryRetriever": ("user_memory.retriever", "UserMemoryRetriever"),
    "SessionLedgerRetentionManager": (
        "user_memory.retention_manager",
        "SessionLedgerRetentionManager",
    ),
    "SessionLedgerRetentionSettings": (
        "user_memory.retention_manager",
        "SessionLedgerRetentionSettings",
    ),
    "get_session_ledger_repository": (
        "user_memory.session_ledger_repository",
        "get_session_ledger_repository",
    ),
    "get_session_ledger_service": (
        "user_memory.session_ledger_service",
        "get_session_ledger_service",
    ),
    "get_user_memory_consolidator": (
        "user_memory.consolidator",
        "get_user_memory_consolidator",
    ),
    "get_user_memory_builder": ("user_memory.builder", "get_user_memory_builder"),
    "get_user_memory_projector": ("user_memory.projector", "get_user_memory_projector"),
    "get_user_memory_repository": ("user_memory.repository", "get_user_memory_repository"),
    "get_user_memory_retriever": ("user_memory.retriever", "get_user_memory_retriever"),
    "get_session_ledger_retention_manager": (
        "user_memory.retention_manager",
        "get_session_ledger_retention_manager",
    ),
    "initialize_session_ledger_retention_manager": (
        "user_memory.retention_manager",
        "initialize_session_ledger_retention_manager",
    ),
    "load_session_ledger_retention_settings": (
        "user_memory.retention_manager",
        "load_session_ledger_retention_settings",
    ),
    "run_session_ledger_retention_once": (
        "user_memory.retention_manager",
        "run_session_ledger_retention_once",
    ),
    "shutdown_session_ledger_retention_manager": (
        "user_memory.retention_manager",
        "shutdown_session_ledger_retention_manager",
    ),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module 'user_memory' has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
