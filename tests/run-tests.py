#!/usr/bin/env python
"""Run a set of tests by nosetests

To run all tests::

    % HGPATH=path/to/mercurial ./run-tests.py

For details, please see:

- `./run-tests.py --help`
- http://readthedocs.org/docs/nose/en/latest/
- http://docs.python.org/library/unittest.html
"""
import os, sys
import nose

import nosehgenv

if __name__ == '__main__':
    nose.main(addplugins=[nosehgenv.HgEnvPlugin()])
