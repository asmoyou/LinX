# Logo Usage Guide

This guide explains how to use the LinX platform logo in various contexts.

## Available Logo Files

All logo files are located in `frontend/public/` and are in WebP format for optimal web performance:

| File | Size | Usage |
|------|------|-------|
| `logo.webp` | Original | High-resolution displays, print materials |
| `logo-xl.webp` | 512×512 | Large displays, hero sections |
| `logo-lg.webp` | 256×256 | README, documentation headers |
| `logo-md.webp` | 128×128 | Login/Register pages, modals |
| `logo-sm.webp` | 64×64 | Sidebar navigation, small UI elements |
| `logo-favicon.webp` | 32×32 | Browser favicon, app icons |

## Usage in Frontend Components

### React/TypeScript Components

```tsx
// Sidebar navigation
<img 
  src="/logo-sm.webp" 
  alt="LinX Logo" 
  className="w-9 h-9 object-contain"
/>

// Login/Register pages
<img 
  src="/logo-md.webp" 
  alt="LinX Logo" 
  className="w-16 h-16 object-contain"
/>

// Hero section
<img 
  src="/logo-lg.webp" 
  alt="LinX Logo" 
  className="w-32 h-32 object-contain"
/>
```

### HTML

```html
<!-- Favicon -->
<link rel="icon" type="image/webp" href="/logo-favicon.webp" />
<link rel="apple-touch-icon" href="/logo-lg.webp" />
```

## Usage in Documentation

### Markdown

```markdown
<!-- README header -->
<div align="center">
  <img src="frontend/public/logo-lg.webp" alt="LinX Logo" width="200"/>
</div>

<!-- Inline reference -->
![LinX Logo](frontend/public/logo-md.webp)
```

## Logo Processing

The logo was processed from the original PNG file using the following steps:

1. Background removal (transparent background)
2. Conversion to WebP format for optimal compression
3. Generation of multiple sizes for different use cases

### Regenerating Logo Files

If you need to regenerate the logo files from a new source:

```bash
# Install dependencies
source backend/.venv/bin/activate
pip install Pillow

# Run the processing script
python3 scripts/process_logo.py
```

For AI-powered background removal (better quality):

```bash
# Install rembg
pip install rembg

# Run advanced processing
python3 scripts/process_logo_advanced.py
```

## Best Practices

1. **Always use WebP format** for web applications (better compression, transparency support)
2. **Use appropriate sizes** - don't load large images for small UI elements
3. **Include alt text** for accessibility
4. **Use object-contain** CSS class to maintain aspect ratio
5. **Lazy load** large logo images when possible

## File Sizes

The WebP format provides excellent compression:

- `logo-favicon.webp`: ~1KB (32×32)
- `logo-sm.webp`: ~2KB (64×64)
- `logo-md.webp`: ~4KB (128×128)
- `logo-lg.webp`: ~8KB (256×256)
- `logo-xl.webp`: ~15KB (512×512)
- `logo.webp`: ~100KB (original size)

## Color and Transparency

The logo has a transparent background, making it suitable for use on any background color. The logo works well on both light and dark themes.

## References

- Logo processing scripts: `scripts/process_logo.py`, `scripts/process_logo_advanced.py`
- Frontend components: `frontend/src/components/layout/Sidebar.tsx`
- Login page: `frontend/src/pages/Login.tsx`
- Register page: `frontend/src/pages/Register.tsx`
- Main README: `README.md`
