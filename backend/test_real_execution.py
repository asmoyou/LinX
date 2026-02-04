"""Quick test for real code execution in Docker containers.

This is a standalone test to verify that code execution works with Docker.
Run with: python test_real_execution.py
"""

import asyncio
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def test_python_execution():
    """Test executing Python code in a container."""
    from virtualization.code_execution_sandbox import get_code_execution_sandbox
    
    print("\n" + "="*60)
    print("Testing Python Code Execution")
    print("="*60)
    
    sandbox = get_code_execution_sandbox()
    
    # Simple Python code
    code = """
import sys
print(f"Python version: {sys.version}")
print("Hello from Docker container!")

# Do some calculation
result = 2 + 2
print(f"2 + 2 = {result}")
"""
    
    print("\nExecuting code:")
    print(code)
    print("\n" + "-"*60)
    
    result = await sandbox.execute_code(
        code=code,
        language="python",
        context={"test": "value"},
    )
    
    print("\nExecution Result:")
    print(f"Success: {result.success}")
    print(f"Status: {result.status.value}")
    print(f"Execution Time: {result.execution_time_seconds:.3f}s")
    
    if result.output:
        print(f"\nOutput:\n{result.output}")
    
    if result.error:
        print(f"\nError:\n{result.error}")
    
    print("="*60)
    
    return result.success


async def test_python_with_dependencies():
    """Test executing Python code with dependencies."""
    from virtualization.code_execution_sandbox import get_code_execution_sandbox
    
    print("\n" + "="*60)
    print("Testing Python Code with Standard Library")
    print("="*60)
    
    sandbox = get_code_execution_sandbox()
    
    # Code that uses standard library (no network needed)
    code = """
import json
import sys
import os

# Test JSON functionality (stdlib, should work)
data = {"message": "Hello", "value": 42, "python_version": sys.version}
print(json.dumps(data, indent=2))

# Test os module
print(f"\\nCurrent directory: {os.getcwd()}")
print(f"Environment variables: {len(os.environ)}")
"""
    
    print("\nExecuting code:")
    print(code)
    print("\n" + "-"*60)
    
    result = await sandbox.execute_code(
        code=code,
        language="python",
        context={},
    )
    
    print("\nExecution Result:")
    print(f"Success: {result.success}")
    print(f"Status: {result.status.value}")
    print(f"Execution Time: {result.execution_time_seconds:.3f}s")
    
    if result.output:
        print(f"\nOutput:\n{result.output}")
    
    if result.error:
        print(f"\nError:\n{result.error}")
    
    print("="*60)
    
    return result.success


async def test_bash_execution():
    """Test executing Bash script in a container."""
    from virtualization.code_execution_sandbox import get_code_execution_sandbox
    
    print("\n" + "="*60)
    print("Testing Bash Script Execution")
    print("="*60)
    
    sandbox = get_code_execution_sandbox()
    
    # Simple bash script
    code = """#!/bin/bash
echo "Hello from Bash!"
echo "Current directory: $(pwd)"
echo "Files in /tmp:"
ls -la /tmp
"""
    
    print("\nExecuting code:")
    print(code)
    print("\n" + "-"*60)
    
    result = await sandbox.execute_code(
        code=code,
        language="bash",
        context={},
    )
    
    print("\nExecution Result:")
    print(f"Success: {result.success}")
    print(f"Status: {result.status.value}")
    print(f"Execution Time: {result.execution_time_seconds:.3f}s")
    
    if result.output:
        print(f"\nOutput:\n{result.output}")
    
    if result.error:
        print(f"\nError:\n{result.error}")
    
    print("="*60)
    
    return result.success


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("REAL CODE EXECUTION TEST SUITE")
    print("="*60)
    print("\nThis test verifies that code execution works with Docker.")
    print("Make sure Docker is running before executing this test.")
    print("="*60)
    
    results = []
    
    # Test 1: Basic Python execution
    try:
        success = await test_python_execution()
        results.append(("Python Execution", success))
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        results.append(("Python Execution", False))
    
    # Test 2: Python with standard library
    try:
        success = await test_python_with_dependencies()
        results.append(("Python with Standard Library", success))
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        results.append(("Python with Standard Library", False))
    
    # Test 3: Bash execution
    try:
        success = await test_bash_execution()
        results.append(("Bash Execution", success))
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        results.append(("Bash Execution", False))
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for _, success in results if success)
    
    print(f"\nTotal: {passed}/{total} tests passed")
    print("="*60)
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
