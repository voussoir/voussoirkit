py setup.py sdist
twine upload -r pypi dist\*
rmdir /s /q dist
rmdir /s /q voussoirkit.egg-info
