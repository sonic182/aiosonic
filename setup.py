"""Setup module."""

import re
from setuptools import setup


RGX = re.compile(r'([\w-]+[<>=]{1}=[\d.\w]+)')


def read_file(filename):
    """Read file correctly."""
    with open(filename) as _file:
        return _file.read().strip()


def requirements(filename):
    """Parse requirements from file."""
    return re.findall(RGX, read_file(filename)) or []


def version():
    data = read_file('./aiosonic/version.py')
    return re.findall(r"VERSION = '([a-z0-9.]*)'", data)[0]


# copied form uvicorn, mark to not install uvloop in windows
env_marker = (
    "sys_platform != 'win32'"
    " and sys_platform != 'cygwin'"
    " and platform_python_implementation != 'pypy'"
)


def add_marks(dependencies, marks):
    """Add markers to dependencies.

    Example:
        uvloop==0.12.0 -> uvloop==0.12.0 ; sys_platform != 'win32'...
    """
    def _map_func(dependency):
        for item, marker in marks.items():
            if item in dependency:
                return dependency + marker
        return dependency

    return list(map(_map_func, dependencies))


setup(
    name='aiosonic',
    version=version(),
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
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development',
        'License :: OSI Approved :: MIT License',

        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    setup_requires=['pytest-runner'],
    install_requires=requirements('./requirements.txt'),
    extras_require={
        'test': add_marks(
            requirements('./test-requirements.txt'),
            {
                'uvloop': ' ;' + env_marker,
                'httptools': ' ;' + env_marker,
            }
        )
    }
)
