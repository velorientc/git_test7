#!/usr/bin/env python
"""Run a set of tests by nosetests

To run all tests::

    % HGPATH=path/to/mercurial ./run-tests.py

For details, please see:

- `./run-tests.py --help`
- http://readthedocs.org/docs/nose/en/latest/
- http://docs.python.org/library/unittest.html
"""
import nose, os

import nosecaptureexc, nosehgenv

ignorefiles = [
    r'^[._]',
    r'^setup\.py$',
    r'^TortoiseHgOverlayServer\.py$',
    # exclude platform-dependent modules
    r'^bugtraq\.py$',
    r'^shellconf\.py$',
    ]

def main():
    env = os.environ.copy()
    if 'NOSE_IGNORE_FILES' not in env:
        env['NOSE_IGNORE_FILES'] = ignorefiles
    if 'NOSE_WITH_DOCTEST' not in env:
        env['NOSE_WITH_DOCTEST'] = 't'
    nose.main(env=env,
              addplugins=[nosecaptureexc.CaptureExcPlugin(),
                          nosehgenv.HgEnvPlugin()])

if __name__ == '__main__':
    main()
