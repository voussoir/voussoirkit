import copy
import PIL.ExifTags

ORIENTATION_KEY = None
for (ORIENTATION_KEY, val) in PIL.ExifTags.TAGS.items():
    if val == 'Orientation':
        break

def fit_into_bounds(
        image_width,
        image_height,
        frame_width,
        frame_height,
        only_shrink=False,
    ):
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

def pad_to_square(image, background_color=None):
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
