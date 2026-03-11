# LinX Platform - Management Scripts

This directory contains utility scripts for managing the LinX platform.

## Available Scripts

### 1. First-Run Admin Initialization

The first administrator account is created through the web setup flow when the
platform detects that no admin account exists.

**Flow:**

1. Open the frontend when the platform has no admin account
2. Complete the `/setup` initialization page
3. The system creates the fixed first admin username `admin`
4. Email, password, language, timezone, and theme are saved during setup

### 2. Promote User (`promote_user.py`)

Promotes an existing user to admin role.

**Usage:**

```bash
# Promote user to admin
python scripts/promote_user.py --username johndoe
```

This will change the user's role from their current role to `admin`.

## Best Practices

1. **Protect Initial Setup Access**: Complete the first-run setup in a trusted environment
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
- Verify whether the platform has already been initialized
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
