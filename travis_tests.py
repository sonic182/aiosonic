#!/usr/bin/env python

import subprocess
import platform
import sys

command = 'pytest --cov=aiosonic --doctest-modules'
if platform.python_implementation() != 'PyPy':
    command += ' --mypy --mypy-ignore-missing-imports'
sys.exit(subprocess.call(command, shell=True))
