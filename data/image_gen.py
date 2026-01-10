from PIL import Image, ImageDraw, ImageFont, ImageFilter
import random
import os

def generate_placeholder_image(output_path, title, tags="NEWS"):
    """
    Generates a high-quality abstract gradient image with news text overlay.
    This serves as a placeholder until simpler GenAI integration is added.
    """
    width = 1200
    height = 630
    
    # Generate random gradient base
    base_color = (random.randint(0, 50), random.randint(0, 50), random.randint(50, 100))
    end_color = (random.randint(10, 60), random.randint(10, 60), random.randint(60, 120))
    
    img = Image.new('RGB', (width, height), color=base_color)
    draw = ImageDraw.Draw(img)
    
    # Draw simple gradient/noise
    for y in range(height):
        r = int(base_color[0] + (end_color[0] - base_color[0]) * y / height)
        g = int(base_color[1] + (end_color[1] - base_color[1]) * y / height)
        b = int(base_color[2] + (end_color[2] - base_color[2]) * y / height)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Add scanline effect
    for y in range(0, height, 4):
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, 50), width=1)
        
    # Attempt to load fonts details
    try:
        # Try finding a bold font on Mac
        font_path = "/System/Library/Fonts/HelveticaNeue-Bold.otf"
        if not os.path.exists(font_path):
             font_path = "/Library/Fonts/Arial Bold.ttf"
             
        if os.path.exists(font_path):
            headline_font = ImageFont.truetype(font_path, 60)
            tag_font = ImageFont.truetype(font_path, 30)
        else:
            headline_font = ImageFont.load_default()
            tag_font = ImageFont.load_default()
    except:
        headline_font = ImageFont.load_default()
        tag_font = ImageFont.load_default()

    # Draw Text - breaking title into lines
    import textwrap
    lines = textwrap.wrap(title, width=25) # approx chars
    
    y_text = 150
    for line in lines:
        left, top, right, bottom = draw.textbbox((0, 0), line, font=headline_font)
        w = right - left
        h = bottom - top
        draw.text(((width - w) / 2, y_text), line, font=headline_font, fill="white")
        y_text += h + 15

    # Draw Logo/Tag
    draw.text((50, 50), "THE NAVI MUMBAI RECORD", font=tag_font, fill=(255, 105, 180)) # Hot pink
    draw.text((50, height - 80), f"#{str(tags).upper()}", font=tag_font, fill="white")

    # Add noise texture
    # (Simple random pixels)
    pixels = img.load()
    for _ in range(20000):
        x = random.randint(0, width - 1)
        y = random.randint(0, height - 1)
        r, g, b = pixels[x, y]
        noise = random.randint(-20, 20)
        pixels[x, y] = (max(0, min(255, r + noise)), max(0, min(255, g + noise)), max(0, min(255, b + noise)))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path)
    return True
