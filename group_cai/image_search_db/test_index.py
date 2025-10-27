from .index import volce_img_match_desc
from ..database.image import rand_img

image_id = rand_img()
print(image_id, volce_img_match_desc(image_id, "银发", "黑发", "红发"))

