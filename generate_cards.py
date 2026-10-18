import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONT_DIR = os.path.join(BASE_DIR, "output", "front")
BACK_DIR = os.path.join(BASE_DIR, "output", "back")
os.makedirs(FRONT_DIR, exist_ok=True)
os.makedirs(BACK_DIR, exist_ok=True)

NUM_CARDS = 45
CARD_SIZE = 700          # px, square card
MARKER_SIZE = 320        # px, ArUco marker in the center
EDGE_BAND = 90           # px thickness of each colour band

# Fixed mapping: edge position -> (letter, colour). Same on every card.
# Front view (camera-facing):
# Top: A (Red)
# Right: B (Yellow)
# Bottom: C (Blue)
# Left: D (Green)
EDGE_MAP = {
    "top":    {"letter": "A", "color": (231, 76, 60),  "text_color": (255, 255, 255)},  # red
    "right":  {"letter": "B", "color": (241, 196, 15), "text_color": (20, 20, 20)},    # yellow
    "bottom": {"letter": "C", "color": (52, 152, 219), "text_color": (255, 255, 255)},  # blue
    "left":   {"letter": "D", "color": (46, 204, 113), "text_color": (255, 255, 255)},  # green
}

aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_5X5_100)

font_big = None
font_small = None

for font_path in [
    "C:/Windows/Fonts/arialbd.ttf",
    "arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]:
    try:
        font_big = ImageFont.truetype(font_path, 54)
        font_small = ImageFont.truetype(font_path, 33)  # 10% larger text (was 30)
        break
    except Exception:
        continue

if font_big is None:
    font_big = ImageFont.load_default()
    font_small = ImageFont.load_default()


def generate_marker(marker_id):
    img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, MARKER_SIZE)
    return Image.fromarray(img).convert("RGB")


def draw_letter_centered(draw, box, text, font, fill):
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    draw.text((cx - w / 2 - bbox[0], cy - h / 2 - bbox[1]), text, font=font, fill=fill)


def make_card(card_id, mirror_lr=False):
    canvas = Image.new("RGB", (CARD_SIZE, CARD_SIZE), "white")
    draw = ImageDraw.Draw(canvas)

    edges = dict(EDGE_MAP)
    if mirror_lr:
        # Long-edge duplex flip: Left and Right swap
        edges["left"], edges["right"] = EDGE_MAP["right"], EDGE_MAP["left"]

    # 1. Top band (Option A - Red)
    draw.rectangle([0, 0, CARD_SIZE, EDGE_BAND], fill=edges["top"]["color"])
    draw_letter_centered(draw, [0, 0, CARD_SIZE, EDGE_BAND], edges["top"]["letter"], font_big, edges["top"]["text_color"])

    # 2. Bottom band (Option C - Blue)
    draw.rectangle([0, CARD_SIZE - EDGE_BAND, CARD_SIZE, CARD_SIZE], fill=edges["bottom"]["color"])
    draw_letter_centered(draw, [0, CARD_SIZE - EDGE_BAND, CARD_SIZE, CARD_SIZE], edges["bottom"]["letter"], font_big, edges["bottom"]["text_color"])

    # 3. Left band (Option D on front, Option B on back)
    draw.rectangle([0, EDGE_BAND, EDGE_BAND, CARD_SIZE - EDGE_BAND], fill=edges["left"]["color"])
    draw_letter_centered(draw, [0, EDGE_BAND, EDGE_BAND, CARD_SIZE - EDGE_BAND], edges["left"]["letter"], font_big, edges["left"]["text_color"])

    # 4. Right band (Option B on front, Option D on back)
    draw.rectangle([CARD_SIZE - EDGE_BAND, EDGE_BAND, CARD_SIZE, CARD_SIZE - EDGE_BAND], fill=edges["right"]["color"])
    draw_letter_centered(draw, [CARD_SIZE - EDGE_BAND, EDGE_BAND, CARD_SIZE, CARD_SIZE - EDGE_BAND], edges["right"]["letter"], font_big, edges["right"]["text_color"])

    # Inner border
    draw.rectangle([EDGE_BAND, EDGE_BAND, CARD_SIZE - EDGE_BAND, CARD_SIZE - EDGE_BAND], outline=(20, 20, 20), width=3)

    if not mirror_lr:
        # Front side: ArUco marker + Roll number
        marker_img = generate_marker(card_id)
        mx = (CARD_SIZE - MARKER_SIZE) // 2
        my = (CARD_SIZE - MARKER_SIZE) // 2
        canvas.paste(marker_img, (mx, my))

        # Human-readable Roll Number in 10% larger text
        label = f"Roll {card_id:02d}"
        draw.rectangle([EDGE_BAND + 10, EDGE_BAND + 10, EDGE_BAND + 190, EDGE_BAND + 55], fill=(255, 255, 255))
        draw.text((EDGE_BAND + 15, EDGE_BAND + 12), label, font=font_small, fill=(20, 20, 20))
    else:
        # Back side: Clean square with colors and letters A,B,C,D — zero jargon!
        pass

    return canvas


def main():
    for cid in range(1, NUM_CARDS + 1):
        front = make_card(cid, mirror_lr=False)
        front.save(os.path.join(FRONT_DIR, f"card_{cid:02d}_front.png"))
        back = make_card(cid, mirror_lr=True)
        back.save(os.path.join(BACK_DIR, f"card_{cid:02d}_back.png"))

    print(f"Generated {NUM_CARDS} front + {NUM_CARDS} back card images in {os.path.join(BASE_DIR, 'output')}.")


if __name__ == "__main__":
    main()
