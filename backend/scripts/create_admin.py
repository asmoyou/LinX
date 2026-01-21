#!/usr/bin/env python3
"""Create initial admin user.

This script creates a default admin user for the platform.
Run this after database setup to create the first admin account.

Usage:
    python scripts/create_admin.py
    
Or with custom credentials:
    python scripts/create_admin.py --username admin --email admin@example.com --password YourSecurePassword123!
"""

import argparse
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_db_session
from access_control.registration import register_user_admin, DuplicateUserError, ValidationError


def create_admin_user(username: str, email: str, password: str):
    """Create admin user with elevated privileges.
    
    Args:
        username: Admin username
        email: Admin email
        password: Admin password
    """
    try:
        with get_db_session() as session:
            response = register_user_admin(
                session=session,
                username=username,
                email=email,
                password=password,
                role="admin",
                attributes={"created_by": "init_script"},
                resource_quotas={
                    "max_agents": 100,
                    "max_storage_gb": 1000,
                    "max_cpu_cores": 50,
                    "max_memory_gb": 100,
                }
            )
            session.commit()
        
        print("✅ Admin user created successfully!")
        print(f"   User ID: {response.user_id}")
        print(f"   Username: {response.username}")
        print(f"   Email: {response.email}")
        print(f"   Role: {response.role}")
        print(f"\n⚠️  Please save these credentials securely!")
        print(f"   Username: {username}")
        print(f"   Password: {password}")
        
    except DuplicateUserError as e:
        print(f"❌ Error: {e}")
        print(f"   Admin user '{username}' or email '{email}' already exists.")
        sys.exit(1)
    except ValidationError as e:
        print(f"❌ Validation Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Create initial admin user for LinX platform"
    )
    parser.add_argument(
        "--username",
        default="admin",
        help="Admin username (default: admin)"
    )
    parser.add_argument(
        "--email",
        default="admin@linx.local",
        help="Admin email (default: admin@linx.local)"
    )
    parser.add_argument(
        "--password",
        default="Admin123!@#",
        help="Admin password (default: Admin123!@#)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("LinX Platform - Admin User Creation")
    print("=" * 60)
    print(f"\nCreating admin user:")
    print(f"  Username: {args.username}")
    print(f"  Email: {args.email}")
    print(f"  Role: admin")
    print()
    
    # Confirm if using default password
    if args.password == "Admin123!@#":
        print("⚠️  WARNING: Using default password!")
        print("   It is strongly recommended to change this password after first login.")
        print()
        response = input("Continue with default password? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Aborted.")
            sys.exit(0)
    
    create_admin_user(args.username, args.email, args.password)


if __name__ == "__main__":
    main()
