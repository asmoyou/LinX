#!/usr/bin/env python3
"""
Reset admin user password

Usage:
    python scripts/reset_admin_password.py
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import bcrypt
from sqlalchemy import create_engine, text

def hash_password(password: str) -> str:
    """Hash password using bcrypt"""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')

def reset_admin_password():
    """Reset admin password to RotaNova@2025"""
    
    # Get database connection info from environment or use defaults
    db_host = os.getenv('POSTGRES_HOST', 'localhost')
    db_port = os.getenv('POSTGRES_PORT', '5432')
    db_name = os.getenv('POSTGRES_DB', 'digital_workforce')
    db_user = os.getenv('POSTGRES_USER', 'dwp_user')
    db_password = os.getenv('POSTGRES_PASSWORD', 'dwp_password_change_me')
    
    # Build database URL
    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    print(f"Connecting to database: {db_host}:{db_port}/{db_name}")
    print(f"Using user: {db_user}")
    
    try:
        # Create engine
        engine = create_engine(db_url)
        
        # New password
        new_password = "RotaNova@2025"
        hashed_password = hash_password(new_password)
        
        print(f"Hashed password generated")
        
        # Update admin password
        with engine.connect() as conn:
            result = conn.execute(
                text("UPDATE users SET password_hash = :password WHERE username = 'admin'"),
                {"password": hashed_password}
            )
            conn.commit()
            
            if result.rowcount > 0:
                print(f"✅ Admin password has been reset successfully!")
                print(f"   Username: admin")
                print(f"   Password: {new_password}")
            else:
                print("❌ Admin user not found in database")
                print("   Creating admin user...")
                
                # Create admin user if not exists
                conn.execute(
                    text("""
                        INSERT INTO users (username, email, password_hash, role, is_active)
                        VALUES ('admin', 'admin@linx.local', :password, 'admin', true)
                    """),
                    {"password": hashed_password}
                )
                conn.commit()
                print(f"✅ Admin user created successfully!")
                print(f"   Username: admin")
                print(f"   Password: {new_password}")
    except Exception as e:
        print(f"❌ Database error: {e}")
        raise

if __name__ == "__main__":
    try:
        reset_admin_password()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
