# LinX Platform - Management Scripts

This directory contains utility scripts for managing the LinX platform.

## Available Scripts

### 1. Create Admin User (`create_admin.py`)

Creates a new admin user with elevated privileges.

**Usage:**

```bash
# Create admin with default credentials
python scripts/create_admin.py

# Create admin with custom credentials
python scripts/create_admin.py \
  --username myadmin \
  --email myadmin@example.com \
  --password "MySecurePass123!@#"
```

**Default Credentials:**
- Username: `admin`
- Email: `admin@linx.local`
- Password: `Admin123!@#`
- Role: `admin`

**Admin Privileges:**
- Max Agents: 100
- Max Storage: 1000 GB
- Max CPU Cores: 50
- Max Memory: 100 GB

⚠️ **Security Note**: Change the default password immediately after first login!

### 2. Promote User (`promote_user.py`)

Promotes an existing user to admin role.

**Usage:**

```bash
# Promote user to admin
python scripts/promote_user.py --username johndoe
```

This will change the user's role from their current role to `admin`.

## Current Admin Accounts

After running the initialization scripts, you have:

1. **superadmin**
   - Email: superadmin@linx.local
   - Password: Admin123!@#
   - Role: admin

2. **admin**
   - Email: admin@linx.com
   - Password: Admin123!@#
   - Role: admin (promoted from user)

## Best Practices

1. **Change Default Passwords**: Always change default passwords after first login
2. **Use Strong Passwords**: Passwords must contain:
   - At least 8 characters
   - Uppercase letter
   - Lowercase letter
   - Digit
   - Special character (!@#$%^&*()_+-=[]{}|;:,.<>?)
3. **Secure Email**: Use a real email address for password recovery
4. **Limit Admin Accounts**: Only create admin accounts when necessary
5. **Regular Audits**: Review admin accounts periodically

## Troubleshooting

### "User already exists" Error

If you get a duplicate user error, either:
- Use a different username/email
- Use `promote_user.py` to promote the existing user

### "Database connection error"

Ensure:
- PostgreSQL is running
- Database credentials in `.env` are correct
- Database has been initialized with migrations

### "Password validation error"

Ensure password meets requirements:
- Minimum 8 characters
- Contains uppercase, lowercase, digit, and special character
