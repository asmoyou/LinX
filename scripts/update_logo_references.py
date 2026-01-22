#!/usr/bin/env python3
"""
Update Logo References Script
Updates all logo references throughout the project
"""

import os
import re

def update_file(filepath, replacements):
    """Update file with replacements"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        for old, new in replacements.items():
            content = content.replace(old, new)
        
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Updated: {filepath}")
            return True
        return False
    except Exception as e:
        print(f"❌ Error updating {filepath}: {e}")
        return False

def main():
    print("🔄 Updating logo references throughout the project...\n")
    
    updates = []
    
    # 1. Update index.html
    html_replacements = {
        '<link rel="icon" type="image/svg+xml" href="/vite.svg" />': 
        '<link rel="icon" type="image/webp" href="/logo-favicon.webp" />\n    <link rel="apple-touch-icon" href="/logo-lg.webp" />',
    }
    if update_file('frontend/index.html', html_replacements):
        updates.append('frontend/index.html')
    
    print(f"\n✅ Updated {len(updates)} files")
    print("\n📝 Manual updates needed:")
    print("  1. Update Sidebar.tsx to use /logo-sm.webp")
    print("  2. Update Login.tsx to use /logo-md.webp")
    print("  3. Update Register.tsx to use /logo-md.webp")
    print("  4. Update README.md to reference the new logo")
    print("\nRun the frontend to see the changes!")

if __name__ == "__main__":
    main()
