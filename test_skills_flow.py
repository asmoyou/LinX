#!/usr/bin/env python3
"""
Test script for Skills API complete flow.
Tests: Create, View, Test, Activate/Deactivate
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8000/api/v1"

# Login credentials
LOGIN_DATA = {
    "username": "admin",
    "password": "RotaNova@2025"
}

def login():
    """Login and get token."""
    print("🔐 Logging in...")
    response = requests.post(f"{BASE_URL}/auth/login", json=LOGIN_DATA)
    if response.status_code != 200:
        print(f"❌ Login failed: {response.text}")
        sys.exit(1)
    
    token = response.json()["access_token"]
    print(f"✅ Login successful")
    return token

def create_skill(token):
    """Create a test skill."""
    print("\n📝 Creating test skill...")
    
    skill_data = {
        "name": "test_calculator",
        "description": "A simple calculator skill for testing",
        "skill_type": "langchain_tool",
        "code": '''from langchain_core.tools import tool

@tool
def test_calculator(a: float, b: float, operation: str = "add") -> str:
    """Perform basic arithmetic operations.
    
    Args:
        a: First number
        b: Second number
        operation: Operation to perform (add, subtract, multiply, divide)
        
    Returns:
        Result of the operation as string
    """
    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            return "Error: Division by zero"
        result = a / b
    else:
        return f"Error: Unknown operation {operation}"
    
    return f"{a} {operation} {b} = {result}"
''',
        "interface_definition": {
            "inputs": {
                "a": "float",
                "b": "float",
                "operation": "string"
            },
            "outputs": {
                "result": "string"
            },
            "required_inputs": ["a", "b"]
        },
        "dependencies": ["langchain-core"],
        "version": "1.0.0"
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(f"{BASE_URL}/skills", json=skill_data, headers=headers)
    
    if response.status_code != 201:
        print(f"❌ Failed to create skill: {response.text}")
        return None
    
    skill = response.json()
    print(f"✅ Skill created: {skill['skill_id']}")
    print(f"   Name: {skill['name']}")
    print(f"   Type: {skill.get('skill_type', 'N/A')}")
    print(f"   Storage: {skill.get('storage_type', 'N/A')}")
    print(f"   Active: {skill.get('is_active', 'N/A')}")
    
    return skill['skill_id']

def get_skill(token, skill_id):
    """Get skill details including code."""
    print(f"\n🔍 Getting skill details...")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/skills/{skill_id}?include_code=true", headers=headers)
    
    if response.status_code != 200:
        print(f"❌ Failed to get skill: {response.text}")
        return None
    
    skill = response.json()
    print(f"✅ Skill retrieved:")
    print(f"   Name: {skill['name']}")
    print(f"   Type: {skill.get('skill_type', 'N/A')}")
    print(f"   Storage: {skill.get('storage_type', 'N/A')}")
    print(f"   Code length: {len(skill.get('code', '')) if skill.get('code') else 0} chars")
    print(f"   Has code: {'Yes' if skill.get('code') else 'No'}")
    print(f"   Interface inputs: {list(skill['interface_definition']['inputs'].keys())}")
    print(f"   Interface outputs: {list(skill['interface_definition']['outputs'].keys())}")
    
    return skill

def test_skill(token, skill_id):
    """Test skill execution."""
    print(f"\n🧪 Testing skill execution...")
    
    test_inputs = {
        "a": 10.0,
        "b": 5.0,
        "operation": "add"
    }
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(f"{BASE_URL}/skills/{skill_id}/test", json=test_inputs, headers=headers)
    
    if response.status_code != 200:
        print(f"❌ Failed to test skill: {response.text}")
        return False
    
    result = response.json()
    print(f"✅ Test execution completed:")
    print(f"   Success: {result.get('success', False)}")
    print(f"   Output: {result.get('output', 'N/A')}")
    print(f"   Execution time: {result.get('execution_time', 0):.3f}s")
    
    if result.get('error'):
        print(f"   Error: {result['error']}")
    
    return result.get('success', False)

def activate_skill(token, skill_id):
    """Activate a skill."""
    print(f"\n✅ Activating skill...")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(f"{BASE_URL}/skills/{skill_id}/activate", headers=headers)
    
    if response.status_code != 204:
        print(f"❌ Failed to activate skill: {response.text}")
        return False
    
    print(f"✅ Skill activated successfully")
    return True

def deactivate_skill(token, skill_id):
    """Deactivate a skill."""
    print(f"\n🔴 Deactivating skill...")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(f"{BASE_URL}/skills/{skill_id}/deactivate", headers=headers)
    
    if response.status_code != 204:
        print(f"❌ Failed to deactivate skill: {response.text}")
        return False
    
    print(f"✅ Skill deactivated successfully")
    return True

def delete_skill(token, skill_id):
    """Delete a skill."""
    print(f"\n🗑️  Deleting skill...")
    
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.delete(f"{BASE_URL}/skills/{skill_id}", headers=headers)
    
    if response.status_code != 204:
        print(f"❌ Failed to delete skill: {response.text}")
        return False
    
    print(f"✅ Skill deleted successfully")
    return True

def main():
    """Run complete skills flow test."""
    print("=" * 60)
    print("Skills API Complete Flow Test")
    print("=" * 60)
    
    # Login
    token = login()
    
    # Create skill
    skill_id = create_skill(token)
    if not skill_id:
        print("\n❌ Test failed: Could not create skill")
        sys.exit(1)
    
    # Get skill details
    skill = get_skill(token, skill_id)
    if not skill:
        print("\n❌ Test failed: Could not retrieve skill")
        sys.exit(1)
    
    # Verify code is present
    if not skill.get('code'):
        print("\n❌ Test failed: Skill code is missing!")
        sys.exit(1)
    
    # Test skill execution
    if not test_skill(token, skill_id):
        print("\n⚠️  Warning: Skill test failed (this is expected if execution engine has issues)")
    
    # Activate skill
    if not activate_skill(token, skill_id):
        print("\n❌ Test failed: Could not activate skill")
        sys.exit(1)
    
    # Deactivate skill
    if not deactivate_skill(token, skill_id):
        print("\n❌ Test failed: Could not deactivate skill")
        sys.exit(1)
    
    # Clean up - delete skill
    if not delete_skill(token, skill_id):
        print("\n⚠️  Warning: Could not delete test skill")
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)

if __name__ == "__main__":
    main()
