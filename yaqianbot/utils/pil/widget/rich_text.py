from .widget import Widget, Argument
from typing import List, Union, Tuple
from PIL import Image
from PIL import ImageFont
from PIL import ImageDraw
import re
from ..misc import paste
from functools import partial
from typing import Union
class LineFeed:
    def __init__(self):
        pass

def _pre1_split_content_linefeed(contents):
    ret = []
    for i in contents:
        if (isinstance(i, str)):
            for jdx, j in enumerate(i.splitlines()):
                if (jdx):
                    ret.append(LineFeed())
                ret.append(j)
        else:
            ret.append(i)
    return ret
def _pre2_split_words(contents):
    ret = []
    for i in contents:
        if (isinstance(i, str)):
            ret.extend(re.findall(r"([a-zA-Z0-9_]+|[^a-zA-Z0-9_])", i))
        else:
            ret.append(i)
    return ret

def _get_elem_size(i, font: ImageFont.ImageFont):
    if (isinstance(i, Image.Image)):
        return (i.width, i.height)
    else:
        ret = font.getbbox(i)
        return ret[-2:]

def _render_line(line, font_size, font, fill, back, align_y, image_spacing, return_width=False) -> Union[int, Image.Image]:
    if (not line):
        if (return_width):
            return 1
        return Image.new("RGBA", (1, font_size), back)
    left = 0
    height = 0
    for idx, i in enumerate(line):
        if (idx):
            if (isinstance(i, Image.Image) or isinstance(line[idx-1], Image.Image)):
                left += image_spacing
        w, h = _get_elem_size(i, font)
        left += w
        height = max(height, h)
    if (return_width):
        return left
    ret = Image.new("RGBA", (left, height), back)
    dr = ImageDraw.Draw(ret)
    left = 0
    for idx, i in enumerate(line):
        if (idx):
            if (isinstance(i, Image.Image) or isinstance(line[idx-1], Image.Image)):
                left += image_spacing
        w, h = _get_elem_size(i, font)
        top = int((height-h)*align_y)
        if (isinstance(i, Image.Image)):
            ret = paste(ret, i, (left, top))
        else:
            dr.text((left, top), i, fill=fill, font=font)
        left += w
    return ret

class RichText(Widget):
    def __init__(self,
                 contents: List[Union[str, Image.Image, Widget]],
                 width: float = 720,
                 font: Union[str, ImageFont.ImageFont] = None,
                 font_size: float = 32,
                 fill: Tuple = (0, 0, 0, 255),
                 back: Tuple = (255, 255, 255, 0),
                 align_x: float = 0,
                 align_y: float = 1,
                 line_spacing: float = 10,
                 image_spacing: float = 3,
                 trim_width: bool = True):
        self.contents = contents
        self.width = width
        self.font_size = font_size
        self.font = font
        self.fill = fill
        self.back = back
        self.align_x = align_x
        self.align_y = align_y
        self.line_spacing = line_spacing
        self.image_spacing = image_spacing
        self.trim_width = trim_width
    def render(self, **kwargs):
        contents = self.get("contents", **kwargs)
        width = self.get("width", **kwargs)
        font_size = self.get("font_size", **kwargs)
        font = self.get("font", **kwargs)
        fill = self.get("fill", **kwargs)
        back = self.get("back", **kwargs)
        align_x = self.get("align_x", **kwargs)
        align_y = self.get("align_y", **kwargs)
        line_spacing = self.get("line_spacing", **kwargs)
        image_spacing = self.get("image_spacing", **kwargs)
        trim_width = self.get("trim_width", **kwargs)
        if (isinstance(font, str)):
            try:
                font = ImageFont.load(font_size)
            except Exception:
                font = ImageFont.truetype(font, size=font_size)
        
        contents = _pre1_split_content_linefeed(contents)
        contents = _pre2_split_words(contents)
        locals_render_line = partial(_render_line, font_size=font_size, font=font, fill=fill, back=(0, 0, 0, 0), align_y=align_y, image_spacing=image_spacing)
        

        lines = []
        for i in contents:
            if (isinstance(i, LineFeed)):
                lines.append([])
            elif (not lines):
                lines.append([i])
            else:
                last_line = lines[-1]
                if (last_line):
                    last_elem = lines[-1][-1]
                else:
                    last_elem = None
                ext_text = isinstance(i, str) and isinstance(last_elem, str)
                
                if (ext_text):
                    last_line[-1] = last_elem+i
                    w = locals_render_line(last_line, return_width=True)
                    if (w>width):
                        last_line[-1] = last_elem
                        lines.append([i])
                else:
                    last_line.append(i)
                    w = locals_render_line(last_line, return_width=True)
                    if (w > width):
                        last_line.pop()
                        lines.append([i])
        lines = [locals_render_line(line) for line in lines]
        
        line_width = max(i.width for i in lines)
        if (trim_width):
            width = line_width
        
        
        height = sum(i.height for i in lines) + line_spacing*(len(lines)-1)
        top = 0
        ret = Image.new("RGBA", (width, height), back)
        for i in lines:
            left = int((width-i.width)*align_x)
            ret = paste(ret, i, (left, top))
            # i.show()
            top += i.height+line_spacing
        return ret

if (__name__=="__main__"):
    a = RichText(contents=["aa\nbc\nhello world\nfoo bar"], font=ImageFont.load_default())
    a.render().show()

            


