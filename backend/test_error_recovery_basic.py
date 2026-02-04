"""Basic test for error recovery functionality."""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from agent_framework.base_agent import (
    ParseError, ToolCall, ToolResult, ErrorFeedback, ConversationState,
    AgentConfig
)
from uuid import uuid4


def test_data_structures():
    """Test that all data structures can be instantiated."""
    print("Testing data structures...")
    
    # Test ParseError
    parse_error = ParseError(
        error_type="json_decode_error",
        message="Test error",
        malformed_input='{"tool": "test"'
    )
    assert parse_error.error_type == "json_decode_error"
    print("✓ ParseError works")
    
    # Test ToolCall
    tool_call = ToolCall(
        tool_name="calculator",
        arguments={"expression": "1+1"},
        raw_json='{"tool": "calculator", "expression": "1+1"}'
    )
    assert tool_call.tool_name == "calculator"
    print("✓ ToolCall works")
    
    # Test ToolResult
    tool_result = ToolResult(
        tool_name="calculator",
        status="success",
        result=2
    )
    assert tool_result.status == "success"
    print("✓ ToolResult works")
    
    # Test ErrorFeedback
    feedback = ErrorFeedback(
        error_type="JSON Format Error",
        error_message="Test error",
        malformed_input='{"tool": "test"',
        expected_format='{"tool": "tool_name"}',
        retry_count=1,
        max_retries=3,
        suggestions=["Check quotes"]
    )
    prompt = feedback.to_prompt()
    assert "JSON Format Error" in prompt
    assert "Attempt 1/3" in prompt
    print("✓ ErrorFeedback works")
    print(f"  Sample prompt:\n{prompt[:200]}...")
    
    # Test ConversationState
    state = ConversationState(max_rounds=20)
    assert state.round_number == 0
    assert state.max_rounds == 20
    assert not state.is_terminated
    print("✓ ConversationState works")
    
    # Test AgentConfig with new fields
    config = AgentConfig(
        agent_id=uuid4(),
        name="TestAgent",
        agent_type="test",
        owner_user_id=uuid4(),
        capabilities=["test"],
        max_parse_retries=3,
        max_execution_retries=3,
        tool_timeout_seconds=30.0,
        enable_error_recovery=True
    )
    assert config.max_parse_retries == 3
    assert config.enable_error_recovery is True
    print("✓ AgentConfig with error recovery settings works")
    
    print("\n✅ All data structure tests passed!")


def test_error_feedback_formatting():
    """Test error feedback formatting."""
    print("\nTesting error feedback formatting...")
    
    # Test JSON decode error feedback
    feedback = ErrorFeedback(
        error_type="JSON Format Error",
        error_message="Unterminated string starting at: line 1 column 36",
        malformed_input='{"tool": "code_execution", "code": "print(\'hello)"}',
        expected_format='{"tool": "code_execution", "code": "print(\'hello\')"}',
        retry_count=1,
        max_retries=3,
        suggestions=[
            "Check for unterminated strings (missing closing quotes)",
            "Ensure all quotes are properly escaped"
        ]
    )
    
    prompt = feedback.to_prompt()
    
    # Verify all components are present
    assert "⚠️" in prompt
    assert "JSON Format Error" in prompt
    assert "Attempt 1/3" in prompt
    assert "Unterminated string" in prompt
    assert "Your input" in prompt
    assert "Expected format" in prompt
    assert "Suggestions" in prompt
    assert "Check for unterminated strings" in prompt
    assert "Please try again" in prompt
    
    print("✓ JSON decode error feedback formatted correctly")
    print(f"\nSample feedback:\n{prompt}\n")
    
    # Test max retries exceeded
    feedback_max = ErrorFeedback(
        error_type="JSON Format Error",
        error_message="Still failing",
        malformed_input='{"tool": "test"',
        expected_format='{"tool": "test"}',
        retry_count=3,
        max_retries=3,
        suggestions=["Fix the JSON"]
    )
    
    prompt_max = feedback_max.to_prompt()
    assert "Attempt 3/3" in prompt_max
    assert "Maximum retry attempts reached" in prompt_max
    assert "provide a final answer without using tools" in prompt_max
    
    print("✓ Max retries feedback formatted correctly")
    
    print("\n✅ All feedback formatting tests passed!")


if __name__ == "__main__":
    try:
        test_data_structures()
        test_error_feedback_formatting()
        print("\n" + "="*60)
        print("🎉 All basic tests passed successfully!")
        print("="*60)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
