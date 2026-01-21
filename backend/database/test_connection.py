"""Test script for database connection and migrations.

This script tests:
1. Database connection
2. Migration status
3. Connection pool functionality
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from database import (
    User,
    get_connection_pool,
    get_migration_runner,
)


def test_database_connection():
    """Test database connection."""
    print("=" * 60)
    print("Testing Database Connection")
    print("=" * 60)

    try:
        pool = get_connection_pool()
        print(f"✓ Connection pool initialized: {pool}")

        # Test health check
        if pool.health_check():
            print("✓ Database health check passed")
        else:
            print("✗ Database health check failed")
            return False

        # Get pool status
        status = pool.get_pool_status()
        print(f"✓ Pool status: {status}")

        return True

    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False


def test_migrations():
    """Test migration status."""
    print("\n" + "=" * 60)
    print("Testing Database Migrations")
    print("=" * 60)

    try:
        runner = get_migration_runner()

        # Check database connection
        if runner.check_database_connection():
            print("✓ Database connection check passed")
        else:
            print("✗ Database connection check failed")
            return False

        # Get current version
        current = runner.get_current_version()
        print(f"✓ Current database version: {current}")

        # Get head version
        head = runner.get_head_version()
        print(f"✓ Head version: {head}")

        # Check if up to date
        if runner.is_up_to_date():
            print("✓ Database schema is up to date")
        else:
            print("⚠ Database schema is outdated")

        # Get migration history
        history = runner.get_migration_history()
        print(f"✓ Migration history: {len(history)} migrations")
        for migration in history:
            print(f"  - {migration['revision']}: {migration['description']}")

        return True

    except Exception as e:
        print(f"✗ Migration check failed: {e}")
        return False


def test_session():
    """Test database session."""
    print("\n" + "=" * 60)
    print("Testing Database Session")
    print("=" * 60)

    try:
        pool = get_connection_pool()

        # Test session creation
        with pool.get_session() as session:
            print("✓ Session created successfully")

            # Test query
            user_count = session.query(User).count()
            print(f"✓ Query executed successfully: {user_count} users in database")

        print("✓ Session closed successfully")
        return True

    except Exception as e:
        print(f"✗ Session test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("Database Connection and Migration Tests")
    print("=" * 60 + "\n")

    results = []

    # Test database connection
    results.append(("Database Connection", test_database_connection()))

    # Test migrations
    results.append(("Database Migrations", test_migrations()))

    # Test session
    results.append(("Database Session", test_session()))

    # Print summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"{test_name}: {status}")

    all_passed = all(result for _, result in results)

    print("\n" + "=" * 60)
    if all_passed:
        print("All tests passed! ✓")
    else:
        print("Some tests failed! ✗")
    print("=" * 60 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
