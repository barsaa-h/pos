"""Generate app icon in multiple formats from scratch using Pillow."""
from PIL import Image, ImageDraw

def create_app_icon(size=512):
    """Create a modern POS/store app icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size / 2, size / 2
    s = size  # shorthand

    # ── Background circle (gradient via concentric circles) ──
    colors_bg = [
        (240, 240, 250),  # outer
        (100, 150, 230),
        (40, 80, 200),    # inner
    ]
    for i, color in enumerate(colors_bg):
        r = s * (0.48 - i * 0.12)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)

    # ── Shopping bag body ──
    bag_color = (255, 255, 255)
    bag_left   = cx - s * 0.22
    bag_right  = cx + s * 0.22
    bag_top    = cy - s * 0.02
    bag_bottom = cy + s * 0.30
    bag_radius = s * 0.04
    draw.rounded_rectangle(
        [bag_left, bag_top, bag_right, bag_bottom],
        radius=int(bag_radius), fill=bag_color
    )

    # ── Shopping bag handles (left and right arcs) ──
    handle_width = s * 0.04
    handle_color = (50, 50, 60)
    # Left handle
    lh_left  = bag_left + s * 0.02
    lh_right = bag_left + s * 0.10
    lh_top   = bag_top - s * 0.18
    lh_bot   = bag_top
    draw.arc([lh_left, lh_top, lh_right, lh_bot + s * 0.06], start=0, end=180,
             fill=handle_color, width=int(handle_width))
    # Right handle
    rh_left  = bag_right - s * 0.10
    rh_right = bag_right - s * 0.02
    draw.arc([rh_left, lh_top, rh_right, lh_bot + s * 0.06], start=0, end=180,
             fill=handle_color, width=int(handle_width))

    # ── Receipt/paper roll on top ──
    roll_left   = cx - s * 0.10
    roll_right  = cx + s * 0.10
    roll_top    = bag_top - s * 0.22
    roll_bottom = bag_top - s * 0.04
    draw.rounded_rectangle(
        [roll_left, roll_top, roll_right, roll_bottom],
        radius=int(s * 0.025), fill=(255, 255, 255), outline=(200, 200, 210), width=max(1, int(s * 0.008))
    )
    # Receipt lines
    line_color = (180, 180, 190)
    for i in range(3):
        ly = roll_top + s * 0.03 + i * s * 0.04
        lw = s * 0.10 - i * s * 0.02
        lx = cx - lw / 2
        draw.rectangle([lx, ly, lx + lw, ly + s * 0.012], fill=line_color)

    # ── POS barcode on bag ──
    barcode_left  = cx - s * 0.12
    barcode_right = cx + s * 0.12
    barcode_top   = bag_top + s * 0.06
    barcode_bot   = bag_top + s * 0.14
    bar_colors = [(30, 30, 40), (60, 60, 70), (90, 90, 100), (50, 50, 60)]
    bar_count = 18
    bar_area_width = barcode_right - barcode_left
    for i in range(bar_count):
        bar_width = s * 0.008 + (i % 4) * s * 0.004
        bx = barcode_left + (i + 0.5) * bar_area_width / bar_count - bar_width / 2
        bar_h = barcode_bot - barcode_top - (i % 3) * s * 0.015
        draw.rectangle([bx, barcode_top, bx + bar_width, barcode_top + bar_h],
                       fill=bar_colors[i % len(bar_colors)])

    # ── Mongolian-style ornamental accent ──
    accent_color = (230, 200, 50)  # gold
    accent_top = bag_bottom - s * 0.06
    accent_bot = bag_bottom
    draw.rounded_rectangle(
        [bag_left + s * 0.02, accent_top, bag_right - s * 0.02, accent_bot],
        radius=int(s * 0.03), fill=accent_color
    )

    # ── Check mark ✓ on bag ──
    check_color = (40, 180, 70)
    check_size = s * 0.08
    cx_check, cy_check = cx, bag_top + s * 0.19
    pts = [
        (cx_check - check_size * 0.5, cy_check),
        (cx_check - check_size * 0.15, cy_check + check_size * 0.55),
        (cx_check + check_size * 0.6, cy_check - check_size * 0.4),
    ]
    draw.line(pts, fill=check_color, width=max(2, int(s * 0.015)), joint="curve")

    return img

def main():
    icon = create_app_icon(512)
    # Save PNG versions
    for sz in [16, 24, 32, 48, 64, 128, 256, 512]:
        resized = icon.resize((sz, sz), Image.LANCZOS)
        resized.save(f"static/pos-icon-{sz}.png")
    # Save main PNG
    icon.save("static/pos-icon.png")
    # Save ICO (Windows)
    fav = icon.resize((256, 256), Image.LANCZOS)
    fav.save("static/pos-icon.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("Icons generated in static/")

if __name__ == "__main__":
    main()
