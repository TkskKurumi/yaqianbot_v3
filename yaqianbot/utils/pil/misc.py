from PIL import Image

# paste upper with mask = upper, result is not desired when 'upper has pixel which alpha in (0, 255) and color not equal lower color'
# lets say, lower is (0, 0, 0, 0)
# upper is (255, 255, 255, 128)
# color becomes (128, 128, 128, 128) instead of (255, 255, 255, 128)
# thus we need alpha_composite to replace paste

def paste(lower, upper, lefttop):
    upper1 = Image.new("RGBA", lower.size, (0, 0, 0, 0))
    upper1.paste(upper, box=lefttop)
    return Image.alpha_composite(lower, upper1)