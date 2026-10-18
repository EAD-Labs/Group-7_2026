"""
generate_classroom_markers.py
Generates 15 classroom-ready ArUco fiducial response cards for Pi Jam Foundation polling.
Produces high-resolution front & back card images (300 DPI) and print-ready A4 PDFs
with exact front/back duplex registration.

Page 1 (Front - Camera View):
  - ArUco 5x5 fiducial marker centered
  - 4 outer color bands with options centered in the color:
      Top: A (Red)
      Right: B (Yellow)
      Bottom: C (Blue)
      Left: D (Green)
  - Roll number in 10% larger bold text (no grey boxes or outlines)
  - Zero grey lines, crop marks, or margin text on the A4 page

Page 2 (Back - Student View):
  - Pure minimal square with the 4 color boxes around the 4 edges
  - Options centered in the color (mirrored for long-edge duplex):
      Top: A (Red)
      Left: B (Yellow)
      Bottom: C (Blue)
      Right: D (Green)
  - Center is completely blank white with zero jargon, instructions, or clutter
  - Zero grey lines on the A4 page
"""

import os
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
FRONT_DIR = os.path.join(OUTPUT_DIR, "front")
BACK_DIR = os.path.join(OUTPUT_DIR, "back")
PDF_DIR = os.path.join(OUTPUT_DIR, "pdf")

os.makedirs(FRONT_DIR, exist_ok=True)
os.makedirs(BACK_DIR, exist_ok=True)
os.makedirs(PDF_DIR, exist_ok=True)

# Card dimensions (Square, 2000x2000 at 300 DPI = ~16.9 x 16.9 cm)
CARD_SIZE = 2000
EDGE_BAND = 260
MARKER_SIZE = 910  # 7 * 130 px (integer bit alignment)

# Standard A4 size at 300 DPI: 2480 x 3508 pixels
A4_WIDTH = 2480
A4_HEIGHT = 3508

# Standard edge colors
COLOR_RED = (231, 76, 60)      # Option A
COLOR_YELLOW = (241, 196, 15)  # Option B
COLOR_BLUE = (52, 152, 219)    # Option C
COLOR_GREEN = (46, 204, 113)   # Option D

aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)

# Load fonts
def load_font(size):
    font_candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for p in font_candidates:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

# 10% larger text for roll number (was 42 -> now 52)
font_roll_no = load_font(52)
# Large, bold option letters centered in the color bands
font_letter_huge = load_font(160)


def draw_centered_text(draw, box, text, font, fill):
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    draw.text((cx - w / 2 - bbox[0], cy - h / 2 - bbox[1]), text, font=font, fill=fill)


def make_front_card(roll_no):
    """
    Creates Front Card (Page 1):
    - 4 outer color bands with options centered in the color:
        Top: A (Red)
        Right: B (Yellow)
        Bottom: C (Blue)
        Left: D (Green)
    - Clean white center zone with ArUco 5x5 marker
    - Roll number in 10% larger bold text (no grey boxes or background rectangles)
    """
    canvas = Image.new("RGB", (CARD_SIZE, CARD_SIZE), "white")
    draw = ImageDraw.Draw(canvas)

    # 1. Four color bands
    # Top = Red (A)
    draw.rectangle([0, 0, CARD_SIZE, EDGE_BAND], fill=COLOR_RED)
    # Bottom = Blue (C)
    draw.rectangle([0, CARD_SIZE - EDGE_BAND, CARD_SIZE, CARD_SIZE], fill=COLOR_BLUE)
    # Left = Green (D)
    draw.rectangle([0, EDGE_BAND, EDGE_BAND, CARD_SIZE - EDGE_BAND], fill=COLOR_GREEN)
    # Right = Yellow (B)
    draw.rectangle([CARD_SIZE - EDGE_BAND, EDGE_BAND, CARD_SIZE, CARD_SIZE - EDGE_BAND], fill=COLOR_YELLOW)

    # 2. Options centered inside each color band
    draw_centered_text(draw, [0, 0, CARD_SIZE, EDGE_BAND], "A", font_letter_huge, (255, 255, 255))
    draw_centered_text(draw, [CARD_SIZE - EDGE_BAND, EDGE_BAND, CARD_SIZE, CARD_SIZE - EDGE_BAND], "B", font_letter_huge, (20, 20, 20))
    draw_centered_text(draw, [0, CARD_SIZE - EDGE_BAND, CARD_SIZE, CARD_SIZE], "C", font_letter_huge, (255, 255, 255))
    draw_centered_text(draw, [0, EDGE_BAND, EDGE_BAND, CARD_SIZE - EDGE_BAND], "D", font_letter_huge, (255, 255, 255))

    # 3. Clean borders
    draw.rectangle([EDGE_BAND, EDGE_BAND, CARD_SIZE - EDGE_BAND, CARD_SIZE - EDGE_BAND], outline=(20, 20, 20), width=4)
    draw.rectangle([0, 0, CARD_SIZE - 1, CARD_SIZE - 1], outline=(20, 20, 20), width=4)

    # 4. ArUco marker in center
    marker_img_arr = cv2.aruco.generateImageMarker(aruco_dict, roll_no, MARKER_SIZE)
    marker_pil = Image.fromarray(marker_img_arr).convert("RGB")
    mx = (CARD_SIZE - MARKER_SIZE) // 2
    my = (CARD_SIZE - MARKER_SIZE) // 2
    canvas.paste(marker_pil, (mx, my))

    # 5. Roll number in 10% larger text (clean dark text on white, no grey boxes or outlines)
    # Top-Left
    draw.text((EDGE_BAND + 30, EDGE_BAND + 22), f"Roll {roll_no:02d}", font=font_roll_no, fill=(20, 20, 20))
    # Bottom-Right (inverted so legible from any viewing angle)
    draw.text((CARD_SIZE - EDGE_BAND - 210, CARD_SIZE - EDGE_BAND - 72), f"Roll {roll_no:02d}", font=font_roll_no, fill=(20, 20, 20))

    return canvas


def make_back_card(roll_no):
    """
    Creates Back Card (Page 2 - Student View):
    - Just a square with the 4 colors around the edges and nothing else!
    - Zero jargon, zero instructions, zero banners, center is completely clean white.
    - Options A, B, C, D centered in the color boxes (mirrored for long-edge duplex):
        Top: A (Red)
        Left: B (Yellow)
        Bottom: C (Blue)
        Right: D (Green)
    """
    canvas = Image.new("RGB", (CARD_SIZE, CARD_SIZE), "white")
    draw = ImageDraw.Draw(canvas)

    # 1. Four color bands (Left & Right mirrored for duplex flip)
    # Top = Red (A)
    draw.rectangle([0, 0, CARD_SIZE, EDGE_BAND], fill=COLOR_RED)
    # Bottom = Blue (C)
    draw.rectangle([0, CARD_SIZE - EDGE_BAND, CARD_SIZE, CARD_SIZE], fill=COLOR_BLUE)
    # Left = Yellow (B)
    draw.rectangle([0, EDGE_BAND, EDGE_BAND, CARD_SIZE - EDGE_BAND], fill=COLOR_YELLOW)
    # Right = Green (D)
    draw.rectangle([CARD_SIZE - EDGE_BAND, EDGE_BAND, CARD_SIZE, CARD_SIZE - EDGE_BAND], fill=COLOR_GREEN)

    # 2. Options centered inside each color band
    draw_centered_text(draw, [0, 0, CARD_SIZE, EDGE_BAND], "A", font_letter_huge, (255, 255, 255))
    draw_centered_text(draw, [0, EDGE_BAND, EDGE_BAND, CARD_SIZE - EDGE_BAND], "B", font_letter_huge, (20, 20, 20))
    draw_centered_text(draw, [0, CARD_SIZE - EDGE_BAND, CARD_SIZE, CARD_SIZE], "C", font_letter_huge, (255, 255, 255))
    draw_centered_text(draw, [CARD_SIZE - EDGE_BAND, EDGE_BAND, CARD_SIZE, CARD_SIZE - EDGE_BAND], "D", font_letter_huge, (255, 255, 255))

    # 3. Clean borders
    draw.rectangle([EDGE_BAND, EDGE_BAND, CARD_SIZE - EDGE_BAND, CARD_SIZE - EDGE_BAND], outline=(20, 20, 20), width=4)
    draw.rectangle([0, 0, CARD_SIZE - 1, CARD_SIZE - 1], outline=(20, 20, 20), width=4)

    # Center is completely blank white — NO JARGON, NO TEXT, NO CLUTTER!
    return canvas


def make_a4_page(card_image):
    """
    Pastes the 2000x2000 card in the exact center of a standard 300 DPI A4 page
    (2480 x 3508 pixels).
    ZERO grey lines, zero crop marks, zero margin text. Just the clean card on white paper.
    """
    page = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), "white")

    cx = (A4_WIDTH - CARD_SIZE) // 2   # 240 px
    cy = (A4_HEIGHT - CARD_SIZE) // 2  # 754 px

    # Paste card centered
    page.paste(card_image, (cx, cy))

    return page


def generate_all(num_cards=15):
    print(f"=== Generating {num_cards} Minimal Classroom Response Cards ===")
    combined_pages = []

    for r in range(1, num_cards + 1):
        print(f"[*] Processing Roll No. {r:02d}...")

        # 1. Generate Card Canvases
        front_card = make_front_card(r)
        back_card = make_back_card(r)

        # Save high-res PNGs
        front_png_path = os.path.join(FRONT_DIR, f"card_{r:02d}_front.png")
        back_png_path = os.path.join(BACK_DIR, f"card_{r:02d}_back.png")
        front_card.save(front_png_path, "PNG", dpi=(300, 300))
        back_card.save(back_png_path, "PNG", dpi=(300, 300))

        # 2. Render onto clean A4 Pages (no grey lines or margin text)
        front_a4 = make_a4_page(front_card)
        back_a4 = make_a4_page(back_card)

        # Save Individual 2-Page PDF
        pdf_path = os.path.join(PDF_DIR, f"Card_Roll_{r:02d}.pdf")
        front_a4.save(pdf_path, "PDF", resolution=300.0, save_all=True, append_images=[back_a4])

        combined_pages.extend([front_a4, back_a4])

    # 3. Save Master Combined 30-Page PDF
    combined_pdf_path = os.path.join(PDF_DIR, f"Cards_Roll_01_to_{num_cards:02d}_Combined.pdf")
    combined_pages[0].save(
        combined_pdf_path,
        "PDF",
        resolution=300.0,
        save_all=True,
        append_images=combined_pages[1:]
    )

    print(f"\n[+] SUCCESS! Generated:")
    print(f"    - {num_cards} Individual 2-page PDFs in: {PDF_DIR}")
    print(f"    - 1 Master 30-page PDF ready for duplex printing: {combined_pdf_path}")
    print(f"    - High-res front PNGs in: {FRONT_DIR}")
    print(f"    - High-res back PNGs in: {BACK_DIR}")


if __name__ == "__main__":
    generate_all(15)
