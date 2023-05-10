from setuptools import setup

with open('version.txt') as file:
    version = file.read()

with open('README.md') as file:
    readme = file.read()

setup(name='fistop',
      version=version,
      license='GPLv3',
      long_description=readme,
      long_description_content_type='text/markdown',
      author='Petr Stovicek',
      author_email='petrstovicek1@gmail.com',
      url='https://github.com/Stovka/fistop',
      python_requires='>=3.9',
      install_requires=['fastapi~=0.85.1', 'uvicorn~=0.19.0'],
      )
