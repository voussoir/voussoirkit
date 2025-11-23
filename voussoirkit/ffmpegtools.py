import subprocess
import os
import tempfile

from voussoirkit import pathclass

def concatenate(input_files, output_file):
    '''
    Conveniently runs `ffmpeg -f concat` via subprocess.
    '''
    if len(input_files) < 2:
        raise ValueError('Only one input file.')

    input_files = [pathclass.Path(f) for f in input_files]

    for file in input_files:
        file.assert_is_file()

    output_file = pathclass.Path(output_file)

    names = [f.absolute_path for f in input_files]
    names = [name.replace("'", "'\\''") for name in names]
    cat_lines = [f'file \'{x}\'' for x in names]
    cat_text = '\n'.join(cat_lines)
    cat_file = tempfile.TemporaryFile('w', encoding='utf-8', delete=False)
    cat_file.write(cat_text)
    cat_file.close()

    command = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', cat_file.name,
        '-map', '0:v?',
        '-map', '0:a?',
        '-map', '0:s?',
        '-c', 'copy',
        output_file.absolute_path,
    ]

    subprocess.check_call(command)

    os.remove(cat_file.name)

    return output_file
