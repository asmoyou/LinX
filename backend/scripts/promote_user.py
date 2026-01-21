#!/usr/bin/env python3
"""Promote user to admin role.

This script promotes an existing user to admin role.

Usage:
    python scripts/promote_user.py --username admin
"""

import argparse
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_db_session  # noqa: E402
from database.models import User  # noqa: E402


def promote_user(username: str):
    """Promote user to admin role.

    Args:
        username: Username to promote
    """
    try:
        with get_db_session() as session:
            user = session.query(User).filter(User.username == username).first()

            if not user:
                print(f"❌ Error: User '{username}' not found.")
                sys.exit(1)

            old_role = user.role
            user.role = "admin"
            session.commit()

        print("✅ User promoted successfully!")
        print(f"   Username: {username}")
        print(f"   Old Role: {old_role}")
        print("   New Role: admin")

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Promote user to admin role")
    parser.add_argument("--username", required=True, help="Username to promote")

    args = parser.parse_args()

    print("=" * 60)
    print("LinX Platform - User Promotion")
    print("=" * 60)
    print(f"\nPromoting user '{args.username}' to admin role...")
    print()

    promote_user(args.username)


if __name__ == "__main__":
    main()
