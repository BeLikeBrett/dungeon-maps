"""Write the mipmapped DXT1 BLP2 format used by the working bundled WoW maps.

Pillow's palette BLP writer produces files Pillow can read but this client draws
green. DDS BC1 compression needs Pillow 11.2+ for this development tool only.
"""
import io
import struct

from PIL import Image


def write_blp(image, path):
    image = image.convert('RGB')
    width, height = image.size
    assert width > 0 and height > 0 and not (width & (width-1) or height & (height-1))
    levels = []
    while True:
        stream = io.BytesIO()
        image.save(stream, format='DDS', pixel_format='DXT1')
        dds = stream.getvalue()
        assert dds[:4] == b'DDS ' and dds[84:88] == b'DXT1'
        data = dds[128:]
        assert len(data) == max(1, (image.width+3)//4) * max(1, (image.height+3)//4) * 8
        levels.append(data)
        if image.size == (1, 1):
            break
        image = image.resize((max(1, image.width//2), max(1, image.height//2)), Image.Resampling.LANCZOS)
    offsets, offset = [], 1172
    for data in levels:
        offsets.append(offset)
        offset += len(data)
    header = struct.pack('<4sI4BII', b'BLP2', 1, 2, 0, 0, 1, width, height)
    header += struct.pack('<16I', *(offsets + [0]*(16-len(levels))))
    header += struct.pack('<16I', *([len(data) for data in levels] + [0]*(16-len(levels))))
    path.write_bytes(header + bytes(1024) + b''.join(levels))
