#!/usr/bin/env python3
"""
Logo Processing Script
Extracts logo, removes background, and converts to WebP format
"""

from PIL import Image
import os
import sys

def remove_background(input_path, output_path):
    """
    Remove background from logo and save as WebP
    
    Args:
        input_path: Path to input PNG file
        output_path: Path to output WebP file
    """
    try:
        # Open the image
        img = Image.open(input_path)
        
        # Convert to RGBA if not already
        if img.mode != 'RGBA':
            img = img.convert('RGBA')
        
        # Get image data
        data = img.getdata()
        
        # Create new image data with transparent background
        new_data = []
        for item in data:
            # Change all white (also shades of whites)
            # to transparent
            if item[0] > 200 and item[1] > 200 and item[2] > 200:
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(item)
        
        # Update image data
        img.putdata(new_data)
        
        # Save as WebP with optimization
        img.save(output_path, 'WEBP', quality=90, method=6)
        print(f"✅ Logo processed successfully: {output_path}")
        
        # Also create a favicon (32x32)
        favicon_path = output_path.replace('.webp', '-favicon.webp')
        img_resized = img.resize((32, 32), Image.Resampling.LANCZOS)
        img_resized.save(favicon_path, 'WEBP', quality=90)
        print(f"✅ Favicon created: {favicon_path}")
        
        # Create different sizes for various uses
        sizes = {
            'logo-sm.webp': (64, 64),
            'logo-md.webp': (128, 128),
            'logo-lg.webp': (256, 256),
        }
        
        output_dir = os.path.dirname(output_path)
        for filename, size in sizes.items():
            size_path = os.path.join(output_dir, filename)
            img_resized = img.resize(size, Image.Resampling.LANCZOS)
            img_resized.save(size_path, 'WEBP', quality=90)
            print(f"✅ Created {filename}: {size_path}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error processing logo: {e}")
        return False

def main():
    # Paths
    input_logo = "examples-of-reference/logo.png"
    output_logo = "frontend/public/logo.webp"
    
    # Check if input exists
    if not os.path.exists(input_logo):
        print(f"❌ Input logo not found: {input_logo}")
        sys.exit(1)
    
    # Create output directory if needed
    os.makedirs(os.path.dirname(output_logo), exist_ok=True)
    
    # Process the logo
    success = remove_background(input_logo, output_logo)
    
    if success:
        print("\n✅ Logo processing complete!")
        print(f"\nGenerated files:")
        print(f"  - frontend/public/logo.webp (main logo)")
        print(f"  - frontend/public/logo-favicon.webp (favicon)")
        print(f"  - frontend/public/logo-sm.webp (64x64)")
        print(f"  - frontend/public/logo-md.webp (128x128)")
        print(f"  - frontend/public/logo-lg.webp (256x256)")
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
