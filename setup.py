from os.path import abspath, dirname, join
from setuptools import setup, Extension

def read(*pathcomponents):
    """Read the contents of a file located relative to setup.py"""
    with open(join(abspath(dirname(__file__)), *pathcomponents)) as thefile:
        return thefile.read()

setup(
    name='beets_similarity',
    version='0.1.0',
    description='Plugin for the music library manager Beets.',
    long_description=read('README.rst'),
    url='https://github.com/SusannaMaria/beets-similarity',
    download_url='https://github.com/SusannaMaria/beets-similarity.git',
    author='Susanna Maria Hepp',
    author_email='susanna@olsoni.de',
    license='MIT',
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],
    keywords='beets similarity',
    include_package_data=True,
    packages=['beetsplug'],
    install_requires=['beets>=1.4.3','pylast','networkx'],
)

