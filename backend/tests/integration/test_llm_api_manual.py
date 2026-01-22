#!/usr/bin/env python3
"""
Manual test script for LLM API endpoints.

This script tests the LLM API endpoints to verify:
1. Authentication is working correctly
2. Error responses are properly formatted
3. Endpoints return expected data structures

Usage:
    python test_llm_api_manual.py
"""

import sys
import requests
import json
from typing import Dict, Any


BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/v1"


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_response(response: requests.Response):
    """Print response details."""
    print(f"Status Code: {response.status_code}")
    print(f"Headers: {dict(response.headers)}")
    try:
        data = response.json()
        print(f"Body: {json.dumps(data, indent=2, ensure_ascii=False)}")
    except:
        print(f"Body (raw): {response.text}")


def test_without_auth():
    """Test accessing LLM endpoints without authentication."""
    print_section("Test 1: Access without authentication")
    
    try:
        response = requests.get(f"{API_BASE}/llm/providers")
        print_response(response)
        
        # Verify error format
        if response.status_code == 401:
            data = response.json()
            assert "error" in data, "Missing 'error' field in response"
            assert "message" in data, "Missing 'message' field in response"
            print("\n✅ Error format is correct: {error, message}")
        else:
            print(f"\n❌ Expected 401, got {response.status_code}")
            
    except Exception as e:
        print(f"\n❌ Test failed: {e}")


def test_with_invalid_token():
    """Test accessing LLM endpoints with invalid token."""
    print_section("Test 2: Access with invalid token")
    
    try:
        headers = {"Authorization": "Bearer invalid_token_here"}
        response = requests.get(f"{API_BASE}/llm/providers", headers=headers)
        print_response(response)
        
        # Verify error format
        if response.status_code == 401:
            data = response.json()
            assert "error" in data, "Missing 'error' field in response"
            assert "message" in data, "Missing 'message' field in response"
            assert data["error"] == "invalid_token", f"Expected error='invalid_token', got '{data['error']}'"
            print("\n✅ Error format is correct and error code matches")
        else:
            print(f"\n❌ Expected 401, got {response.status_code}")
            
    except Exception as e:
        print(f"\n❌ Test failed: {e}")


def test_login_and_access():
    """Test login and then access LLM endpoints."""
    print_section("Test 3: Login and access with valid token")
    
    try:
        # First, try to login (this will fail if no user exists)
        print("Attempting to login...")
        login_data = {
            "username": "admin",
            "password": "admin123"
        }
        response = requests.post(f"{API_BASE}/auth/login", json=login_data)
        print_response(response)
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("token")
            
            if token:
                print(f"\n✅ Login successful, got token: {token[:20]}...")
                
                # Now try to access LLM endpoints
                print("\nAccessing LLM providers endpoint...")
                headers = {"Authorization": f"Bearer {token}"}
                response = requests.get(f"{API_BASE}/llm/providers", headers=headers)
                print_response(response)
                
                if response.status_code == 200:
                    print("\n✅ Successfully accessed LLM providers endpoint")
                elif response.status_code == 503:
                    print("\n⚠️  LLM providers not configured (expected in dev)")
                else:
                    print(f"\n❌ Unexpected status code: {response.status_code}")
            else:
                print("\n❌ No token in login response")
        else:
            print(f"\n⚠️  Login failed (status {response.status_code})")
            print("This is expected if no admin user exists yet.")
            print("You can create one with: python scripts/create_admin.py")
            
    except Exception as e:
        print(f"\n❌ Test failed: {e}")


def test_error_format_consistency():
    """Test that all error responses follow the same format."""
    print_section("Test 4: Error format consistency")
    
    test_cases = [
        ("No auth", f"{API_BASE}/llm/providers", {}),
        ("Invalid token", f"{API_BASE}/llm/providers", {"Authorization": "Bearer invalid"}),
        ("Malformed auth", f"{API_BASE}/llm/providers", {"Authorization": "InvalidFormat"}),
    ]
    
    all_consistent = True
    
    for name, url, headers in test_cases:
        print(f"\nTesting: {name}")
        try:
            response = requests.get(url, headers=headers)
            data = response.json()
            
            has_error = "error" in data
            has_message = "message" in data
            no_detail = "detail" not in data  # Old format should not be present
            
            print(f"  - Has 'error': {has_error}")
            print(f"  - Has 'message': {has_message}")
            print(f"  - No 'detail': {no_detail}")
            
            if has_error and has_message and no_detail:
                print(f"  ✅ Format is consistent")
            else:
                print(f"  ❌ Format is inconsistent")
                all_consistent = False
                
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            all_consistent = False
    
    if all_consistent:
        print("\n✅ All error responses follow consistent format")
    else:
        print("\n❌ Some error responses have inconsistent format")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  LLM API Manual Test Suite")
    print("="*60)
    print("\nThis script tests the LLM API endpoints.")
    print("Make sure the backend server is running on http://localhost:8000")
    print("\nPress Ctrl+C to cancel, or Enter to continue...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\n\nTest cancelled.")
        sys.exit(0)
    
    # Run tests
    test_without_auth()
    test_with_invalid_token()
    test_error_format_consistency()
    test_login_and_access()
    
    print("\n" + "="*60)
    print("  Test Suite Complete")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
