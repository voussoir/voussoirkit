import copy
import datetime
import dateutil.parser
import exifread
import io
import PIL.ExifTags
import PIL.Image
import re

from voussoirkit import pathclass

_exifread = exifread

ORIENTATION_KEY = None
for (ORIENTATION_KEY, val) in PIL.ExifTags.TAGS.items():
    if val == 'Orientation':
        break

def checkerboard_image(color_1, color_2, image_size, checker_size) -> PIL.Image:
    '''
    Generate a PIL Image with a checkerboard pattern.

    color_1:
        The color starting in the top left. Either RGB tuple or a string
        that PIL understands.
    color_2:
        The alternate color
    image_size:
        Tuple of two integers, the image size in pixels.
    checker_size:
        Tuple of two integers, the size of each checker in pixels.
    '''
    image = PIL.Image.new('RGB', image_size, color_1)
    checker = PIL.Image.new('RGB', (checker_size, checker_size), color_2)
    offset = True
    for y in range(0, image_size[1], checker_size):
        for x in range(0, image_size[0], checker_size * 2):
            x += offset * checker_size
            image.paste(checker, (x, y))
        offset = not offset
    return image

def fit_into_bounds(
        image_width,
        image_height,
        frame_width,
        frame_height,
        *,
        only_shrink=False,
    ) -> tuple:
    '''
    Given the w+h of the image and the w+h of the frame,
    return new w+h that fits the image into the frame
    while maintaining the aspect ratio.

    (1920, 1080, 400, 400) -> (400, 225)
    '''
    width_ratio = frame_width / image_width
    height_ratio = frame_height / image_height
    ratio = min(width_ratio, height_ratio)

    new_width = int(image_width * ratio)
    new_height = int(image_height * ratio)

    if only_shrink and (new_width > image_width or new_height > image_height):
        return (image_width, image_height)

    return (new_width, new_height)

def _get_exif_datetime_pil(image):
    exif = image.getexif()
    if not exif:
        return

    exif = {
        PIL.ExifTags.TAGS[key]: value
        for (key, value) in exif.items()
        if key in PIL.ExifTags.TAGS
    }
    exif_date = exif.get('DateTimeOriginal') or exif.get('DateTime') or exif.get('DateTimeDigitized')

    if not exif_date:
        return None

    return exif_date

def _get_exif_datetime_exifread(path):
    path = pathclass.Path(path)
    exif = _exifread.process_file(path.open('rb'))
    exif_date = (
        exif.get('EXIF DateTimeOriginal') or
        exif.get('Image DateTime') or
        exif.get('EXIF DateTimeDigitized')
    )
    if not exif_date:
        return None

    exif_date = exif_date.values
    return exif_date

def get_exif_datetime(image) -> datetime.datetime:
    # Thanks Payne
    # https://stackoverflow.com/a/4765242
    if isinstance(image, (str, pathclass.Path)):
        exif_date = _get_exif_datetime_exifread(image)
    elif isinstance(image, PIL.Image.Image):
        exif_date = _get_exif_datetime_pil(image)

    if not exif_date:
        return None

    if exif_date.startswith('0000:'):
        return None

    exif_date = re.sub(r'(\d\d\d\d):(\d\d):(\d\d)', r'\1-\2-\3', exif_date)
    return dateutil.parser.parse(exif_date)

def exifread(path) -> dict:
    if isinstance(path, PIL.Image.Image):
        handle = io.BytesIO()
        path.save(handle, format='JPEG', exif=path.getexif(), quality=10)
        handle.seek(0)
    elif isinstance(path, pathclass.Path):
        handle = path.open('rb')
    elif isinstance(path, str):
        handle = open(path, 'rb')

    return _exifread.process_file(handle)

def pad_to_square(image, background_color=None) -> PIL.Image:
    '''
    If the given image is not already square, return a new, square image with
    additional padding on top and bottom or left and right.
    '''
    if image.size[0] == image.size[1]:
        return image

    dimension = max(image.size)
    diff_w = int((dimension - image.size[0]) / 2)
    diff_h = int((dimension - image.size[1]) / 2)
    new_image = PIL.Image.new(image.mode, (dimension, dimension), background_color)
    new_image.paste(image, (diff_w, diff_h))
    return new_image

def replace_color(image, from_color, to_color):
    image = image.copy()
    pixels = image.load()
    for y in range(image.size[1]):
        for x in range(image.size[0]):
            if pixels[x, y] == from_color:
                pixels[x, y] = to_color
    return image

def rotate_by_exif(image):
    '''
    Rotate the image according to its exif data, so that it will display
    correctly even if saved without the exif.

    Returns (image, exif) where exif has the orientation key set to 1,
    the upright position, if the rotation was successful.

    You should be able to call image.save('filename.jpg', exif=exif) with
    these returned values.
    (To my knowledge, I can not put the exif back into the Image object itself.
    There is getexif but no setexif or putexif, etc.)
    '''
    # Thank you Scabbiaza
    # https://stackoverflow.com/a/26928142

    try:
        exif = image.getexif()
    except AttributeError:
        return (image, exif)

    if exif is None:
        return (image, exif)

    try:
        rotation = exif[ORIENTATION_KEY]
    except KeyError:
        return (image, exif)

    fp = getattr(exif, 'fp', None)
    if isinstance(fp, io.BufferedReader):
        exif.fp = io.BytesIO()
        exif.fp.write(fp.read())
        exif.fp.seek(0)
    exif = copy.deepcopy(exif)

    if rotation == 1:
        pass
    elif rotation == 2:
        image = image.transpose(PIL.Image.FLIP_LEFT_RIGHT)
    elif rotation == 3:
        image = image.transpose(PIL.Image.ROTATE_180)
    elif rotation == 4:
        image = image.transpose(PIL.Image.FLIP_LEFT_RIGHT)
        image = image.transpose(PIL.Image.ROTATE_180)
    elif rotation == 5:
        image = image.transpose(PIL.Image.FLIP_LEFT_RIGHT)
        image = image.transpose(PIL.Image.ROTATE_90)
    elif rotation == 6:
        image = image.transpose(PIL.Image.ROTATE_270)
    elif rotation == 7:
        image = image.transpose(PIL.Image.FLIP_LEFT_RIGHT)
        image = image.transpose(PIL.Image.ROTATE_270)
    elif rotation == 8:
        image = image.transpose(PIL.Image.ROTATE_90)

    exif[ORIENTATION_KEY] = 1

    return (image, exif)
