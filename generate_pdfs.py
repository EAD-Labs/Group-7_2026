import os
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONT_DIR = os.path.join(BASE_DIR, "output", "front")
BACK_DIR = os.path.join(BASE_DIR, "output", "back")
PDF_DIR = os.path.join(BASE_DIR, "output", "pdf")

os.makedirs(PDF_DIR, exist_ok=True)

# Standard A4 size at 300 DPI: 2480 x 3508 pixels
A4_WIDTH = 2480
A4_HEIGHT = 3508
# Card size centered on A4: 2000 x 2000 pixels (leaving 240px left/right margins and 754px top/bottom margins)
CARD_RENDER_SIZE = 2000

def create_a4_centered_card(card_img_path):
    # Create clean white A4 page
    page = Image.new("RGB", (A4_WIDTH, A4_HEIGHT), "white")
    
    # Load card and scale cleanly with NEAREST for sharp ArUco bitgrid
    card_img = Image.open(card_img_path).convert("RGB")
    card_scaled = card_img.resize((CARD_RENDER_SIZE, CARD_RENDER_SIZE), Image.Resampling.NEAREST)
    
    # Calculate exact center position
    cx = (A4_WIDTH - CARD_RENDER_SIZE) // 2
    cy = (A4_HEIGHT - CARD_RENDER_SIZE) // 2
    
    # Paste centered
    page.paste(card_scaled, (cx, cy))
    return page

def generate_pdf_for_roll(roll_no):
    front_path = os.path.join(FRONT_DIR, f"card_{roll_no:02d}_front.png")
    back_path = os.path.join(BACK_DIR, f"card_{roll_no:02d}_back.png")

    if not os.path.exists(front_path) or not os.path.exists(back_path):
        print(f"[-] Missing images for Roll #{roll_no}")
        return None, None

    front_a4 = create_a4_centered_card(front_path)
    back_a4 = create_a4_centered_card(back_path)

    pdf_path = os.path.join(PDF_DIR, f"Card_Roll_{roll_no:02d}.pdf")
    front_a4.save(pdf_path, "PDF", resolution=300.0, save_all=True, append_images=[back_a4])
    print(f"[+] Saved A4 Centered PDF: {pdf_path}")
    return front_a4, back_a4

def main():
    selected_rolls = [1, 2, 3, 4]
    all_pages = []

    print("Generating clean A4 centered PDFs for Roll Nos:", selected_rolls)
    for roll in selected_rolls:
        f_page, b_page = generate_pdf_for_roll(roll)
        if f_page and b_page:
            all_pages.extend([f_page, b_page])

    if all_pages:
        combined_path = os.path.join(PDF_DIR, "Cards_Roll_01_to_04_Combined.pdf")
        all_pages[0].save(combined_path, "PDF", resolution=300.0, save_all=True, append_images=all_pages[1:])
        print(f"[+] Saved Combined A4 PDF: {combined_path}")

    print("\nAll 4 A4 PDFs generated successfully with clean margins!")

if __name__ == "__main__":
    main()
