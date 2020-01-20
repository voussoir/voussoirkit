import setuptools

setuptools.setup(
    name='voussoirkit',
    packages=setuptools.find_packages(),
    version='0.0.41',
    author='voussoir',
    author_email='pypi@voussoir.net',
    description='voussoir\'s toolkit',
    url='https://github.com/voussoir/voussoirkit',
    install_requires=[
        'pyperclip',
        'pywin32;platform_system=="Windows"',
        'winshell;platform_system=="Windows"',
    ]
)
