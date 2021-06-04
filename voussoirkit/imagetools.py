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

def rotate_by_exif(image):
    '''
    Rotate the image according to its exif data, so that it will display
    correctly even if saved without the exif.
    '''
    # Thank you Scabbiaza
    # https://stackoverflow.com/a/26928142

    try:
        exif = image.getexif()
    except AttributeError:
        return image

    if exif is None:
        return image

    try:
        rotation = exif[ORIENTATION_KEY]
    except KeyError:
        return image

    if rotation == 3:
        image = image.rotate(180, expand=True)
    elif rotation == 6:
        image = image.rotate(270, expand=True)
    elif rotation == 8:
        image = image.rotate(90, expand=True)

    return image
