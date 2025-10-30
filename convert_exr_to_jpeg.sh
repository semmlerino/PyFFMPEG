#!/bin/bash
# EXR to JPEG conversion using available tools in Rez environment
# Usage: convert_exr_to_jpeg.sh input.exr output.jpg [size]

INPUT_EXR="$1"
OUTPUT_JPG="$2"
SIZE="${3:-512}"

if [ -z "$INPUT_EXR" ] || [ -z "$OUTPUT_JPG" ]; then
    echo "Usage: $0 input.exr output.jpg [size]"
    echo "Example: $0 /path/to/image.exr /tmp/thumb.jpg 256"
    exit 1
fi

if [ ! -f "$INPUT_EXR" ]; then
    echo "Error: Input file $INPUT_EXR not found"
    exit 1
fi

echo "Converting $INPUT_EXR -> $OUTPUT_JPG (${SIZE}px)"

# Method 1: OpenImageIO tools (oiiotool, iconvert) - preferred for VFX
if command -v oiiotool >/dev/null 2>&1; then
    echo "Trying OpenImageIO oiiotool..."
    if oiiotool "$INPUT_EXR" --resize "${SIZE}x${SIZE}" -o "$OUTPUT_JPG" 2>/dev/null; then
        echo "✅ OpenImageIO oiiotool conversion successful"
        exit 0
    fi
fi

if command -v iconvert >/dev/null 2>&1; then
    echo "Trying OpenImageIO iconvert..."
    if iconvert "$INPUT_EXR" --resize "${SIZE}x${SIZE}" "$OUTPUT_JPG" 2>/dev/null; then
        echo "✅ OpenImageIO iconvert conversion successful"
        exit 0
    fi
fi

# Method 2: ImageMagick (magick command - newer versions)
if command -v magick >/dev/null 2>&1; then
    echo "Trying ImageMagick magick..."
    if magick "$INPUT_EXR" -resize "${SIZE}x${SIZE}>" -quality 90 "$OUTPUT_JPG" 2>/dev/null; then
        echo "✅ ImageMagick magick conversion successful"
        exit 0
    fi
fi

# Method 3: ImageMagick (convert command - older versions)
if command -v convert >/dev/null 2>&1; then
    echo "Trying ImageMagick convert..."
    if convert "$INPUT_EXR" -resize "${SIZE}x${SIZE}>" -quality 90 "$OUTPUT_JPG" 2>/dev/null; then
        echo "✅ ImageMagick convert conversion successful"
        exit 0
    fi
fi

# Method 4: FFmpeg (good for EXR, often available in VFX environments)
if command -v ffmpeg >/dev/null 2>&1; then
    echo "Trying FFmpeg..."
    if ffmpeg -i "$INPUT_EXR" -vf "scale=${SIZE}:${SIZE}:force_original_aspect_ratio=decrease,pad=${SIZE}:${SIZE}:(ow-iw)/2:(oh-ih)/2:black" -q:v 2 "$OUTPUT_JPG" -y 2>/dev/null; then
        echo "✅ FFmpeg conversion successful"  
        exit 0
    fi
fi

# Method 5: OpenEXR native tools + conversion (multi-step)
if command -v exrheader >/dev/null 2>&1 && command -v convert >/dev/null 2>&1; then
    echo "Trying OpenEXR tools + ImageMagick chain..."
    
    # First check if we can read the EXR
    if exrheader "$INPUT_EXR" >/dev/null 2>&1; then
        echo "EXR file validated with exrheader"
        
        # Try to use exr2aces as intermediate step if available
        if command -v exr2aces >/dev/null 2>&1; then
            TEMP_ACE=$(mktemp --suffix=.exr)
            if exr2aces "$INPUT_EXR" "$TEMP_ACE" 2>/dev/null; then
                if convert "$TEMP_ACE" -resize "${SIZE}x${SIZE}>" -quality 90 "$OUTPUT_JPG" 2>/dev/null; then
                    rm -f "$TEMP_ACE"
                    echo "✅ OpenEXR tools + ImageMagick chain successful"
                    exit 0
                fi
                rm -f "$TEMP_ACE"
            fi
        fi
    fi
fi

# Method 6: GraphicsMagick (alternative to ImageMagick)
if command -v gm >/dev/null 2>&1; then
    echo "Trying GraphicsMagick..."
    if gm convert "$INPUT_EXR" -resize "${SIZE}x${SIZE}>" -quality 90 "$OUTPUT_JPG" 2>/dev/null; then
        echo "✅ GraphicsMagick conversion successful"
        exit 0
    fi
fi

# Method 7: GIMP command-line (if available)
if command -v gimp >/dev/null 2>&1; then
    echo "Trying GIMP command-line..."
    GIMP_SCRIPT=$(cat <<'EOF'
(let* ((image (car (gimp-file-load RUN-NONINTERACTIVE input-file input-file)))
       (drawable (car (gimp-image-get-active-layer image))))
  (gimp-image-scale-full image size size INTERPOLATION-CUBIC)
  (file-jpeg-save RUN-NONINTERACTIVE image drawable output-file output-file 0.9 0 1 1 "" 0 1 0 0)
  (gimp-image-delete image))
EOF
)
    
    # This is complex and may not work in headless environments, so skip for now
    echo "GIMP available but skipping (requires display)"
fi

echo "❌ All conversion methods failed"
echo "Available tools checked:"
echo "  - oiiotool, iconvert (OpenImageIO)"  
echo "  - magick, convert (ImageMagick)"
echo "  - ffmpeg (FFmpeg)"
echo "  - exrheader, exr2aces (OpenEXR native)"
echo "  - gm (GraphicsMagick)"

exit 1