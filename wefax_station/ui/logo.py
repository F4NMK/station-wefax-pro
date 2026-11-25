"""Logo par défaut de l'application."""

from PIL import Image, ImageDraw


def default_app_logo(size=192):
    image = Image.new("RGBA", (192, 192), (12, 23, 43, 255))
    d = ImageDraw.Draw(image)
    d.rounded_rectangle((9, 9, 183, 183), radius=32, outline=(53, 199, 226), width=4)
    d.rounded_rectangle((40, 52, 137, 154), radius=8, fill=(231, 242, 245))
    d.line((58, 77, 116, 77), fill=(20, 47, 74), width=5)
    for y, x2 in ((94, 115), (108, 106), (122, 117), (136, 99)):
        d.line((58, y, x2, y), fill=(20, 47, 74), width=3)
    d.line((127, 52, 127, 31), fill=(251, 191, 36), width=5)
    for r in (18, 31):
        d.arc((127 - r, 31 - r, 127 + r, 31 + r), -55, 55, fill=(251, 191, 36), width=4)
    d.line((45, 162, 73, 162, 82, 152, 91, 168, 103, 158, 143, 158), fill=(53, 199, 226), width=3)
    return image.resize((size, size), Image.Resampling.LANCZOS)
