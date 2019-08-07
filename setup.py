"""Setup module."""

import re
from setuptools import setup

from aiosonic.version import VERSION


RGX = re.compile(r'([\w-]+[<>=]{1}=[\d.]+)')


def read_file(filename):
    """Read file correctly."""
    with open(filename) as _file:
        return _file.read().strip()


def requirements(filename):
    """Parse requirements from file."""
    return re.findall(RGX, read_file(filename)) or []


setup(
    name='aiosonic',
    version=VERSION,
    description='Async http client',
    author='Johanderson Mogollon',
    author_email='johanderson@mogollon.com.ve',
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    license='MIT',
    packages=[
        'aiosonic',
        'aiosonic_utils',
    ],
    classifiers=[
        # 'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development',
        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    setup_requires=['pytest-runner'],
    test_requires=['pytest'],
    install_requires=requirements('./requirements.txt'),
    extras_require={
        'test': requirements('./test-requirements.txt')
    }
)
