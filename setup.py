"""Setup module."""

import re
from setuptools import setup


RGX = re.compile('([\w-]+[<>=]{1}=[\d.]+)')


def read_file(filename):
    """Read file correctly."""
    with open(filename) as _file:
        return _file.read().strip()


def requirements(filename):
    """Parse requirements from file."""
    return re.findall(RGX, read_file(filename)) or []


setup(
    name='aiosonic',
    version='0.0.1',
    description='Async http client',
    author='Johanderson Mogollon',
    author_email='johanderson@mogollon.com.ve',
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    license='MIT',
    packages=['aiosonic'],
    setup_requires=['pytest-runner'],
    test_requires=['pytest'],
    install_requires=requirements('./requirements.txt'),
    extras_require={
        'test': requirements('./test-requirements.txt')
    }
)
