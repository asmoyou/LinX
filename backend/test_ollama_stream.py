#!/usr/bin/env python3
"""Test Ollama streaming response format."""

import httpx
import json

url = "http://192.168.0.29:11434/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
}
data = {
    "model": "qwen3-vl:30b",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": True,
    "stream_options": {"include_usage": True}
}

print("Testing Ollama streaming...")
print("=" * 80)

with httpx.stream("POST", url, json=data, headers=headers, timeout=60) as response:
    response.raise_for_status()
    
    line_count = 0
    for line in response.iter_lines():
        line_count += 1
        
        if not line or line.startswith(":"):
            continue
        
        if line.startswith("data: "):
            data_str = line[6:]
            
            if data_str == "[DONE]":
                print(f"\n[Line {line_count}] DONE")
                break
            
            try:
                chunk_data = json.loads(data_str)
                
                # Print first 20 chunks in detail
                if line_count <= 20:
                    print(f"\n[Line {line_count}] Full chunk:")
                    print(json.dumps(chunk_data, indent=2, ensure_ascii=False))
                    
                    if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                        delta = chunk_data["choices"][0].get("delta", {})
                        print(f"  Delta keys: {list(delta.keys())}")
                        print(f"  Delta: {json.dumps(delta, ensure_ascii=False)}")
                
                # Count chunks with content
                if "choices" in chunk_data and len(chunk_data["choices"]) > 0:
                    delta = chunk_data["choices"][0].get("delta", {})
                    if delta.get("content") or delta.get("reasoning_content") or delta.get("reasoning"):
                        if line_count > 20:
                            print(".", end="", flush=True)
                
            except json.JSONDecodeError as e:
                print(f"\n[Line {line_count}] JSON decode error: {e}")
                print(f"  Raw: {data_str[:200]}")

print(f"\n\nTotal lines processed: {line_count}")
