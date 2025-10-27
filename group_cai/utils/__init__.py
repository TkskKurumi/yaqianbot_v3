from PIL import Image
from io import BytesIO
def bytes2pil(bytes):
    bio = BytesIO()
    bio.write(bytes)
    bio.seek(0)
    return Image.open(bio)
