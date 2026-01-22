#!/usr/bin/env python3
"""
Advanced Logo Processing Script
Uses rembg for AI-powered background removal
Install: pip install rembg pillow
"""

from PIL import Image
import os
import sys

def remove_background_advanced(input_path, output_path):
    """
    Remove background using rembg (AI-powered)
    
    Args:
        input_path: Path to input PNG file
        output_path: Path to output WebP file
    """
    try:
        from rembg import remove
        
        # Open and process image
        with open(input_path, 'rb') as input_file:
            input_data = input_file.read()
            output_data = remove(input_data)
        
        # Open as PIL Image
        img = Image.open(io.BytesIO(output_data))
        
        # Save as WebP with optimization
        img.save(output_path, 'WEBP', quality=95, method=6)
        print(f"✅ Logo processed with AI background removal: {output_path}")
        
        # Create different sizes
        create_logo_variants(img, os.path.dirname(output_path))
        
        return True
        
    except ImportError:
        print("⚠️  rembg not installed. Install with: pip install rembg")
        print("Falling back to simple background removal...")
        return False
    except Exception as e:
        print(f"❌ Error processing logo: {e}")
        return False

def create_logo_variants(img, output_dir):
    """Create different size variants of the logo"""
    import io
    
    variants = {
        'logo-favicon.webp': (32, 32),
        'logo-sm.webp': (64, 64),
        'logo-md.webp': (128, 128),
        'logo-lg.webp': (256, 256),
        'logo-xl.webp': (512, 512),
    }
    
    for filename, size in variants.items():
        output_path = os.path.join(output_dir, filename)
        img_resized = img.resize(size, Image.Resampling.LANCZOS)
        img_resized.save(output_path, 'WEBP', quality=95)
        print(f"✅ Created {filename}: {size[0]}x{size[1]}")

def main():
    import io
    
    # Paths
    input_logo = "examples-of-reference/logo.png"
    output_logo = "frontend/public/logo.webp"
    
    # Check if input exists
    if not os.path.exists(input_logo):
        print(f"❌ Input logo not found: {input_logo}")
        sys.exit(1)
    
    # Create output directory
    os.makedirs(os.path.dirname(output_logo), exist_ok=True)
    
    # Try advanced processing first
    success = remove_background_advanced(input_logo, output_logo)
    
    if not success:
        # Fallback to simple processing
        from process_logo import remove_background
        success = remove_background(input_logo, output_logo)
    
    if success:
        print("\n✅ Logo processing complete!")
        print(f"\nGenerated files in frontend/public/:")
        print(f"  - logo.webp (main logo)")
        print(f"  - logo-favicon.webp (32x32 favicon)")
        print(f"  - logo-sm.webp (64x64)")
        print(f"  - logo-md.webp (128x128)")
        print(f"  - logo-lg.webp (256x256)")
        print(f"  - logo-xl.webp (512x512)")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
