#!/usr/bin/env python
""" A simple tool for importing the cffi version into pypy, should sync
whatever version you provide. Usage:

import_cffi.py <path-to-cffi>
"""

import sys, py

def mangle(lines, ext):
    if ext == '.py':
        yield "# Generated by pypy/tool/import_cffi.py\n"
        for line in lines:
            line = line.replace('from testing', 'from extra_tests.cffi_tests')
            yield line
    elif ext in ('.c', '.h'):
        yield "/* Generated by pypy/tool/import_cffi.py */\n"
        for line in lines:
            yield line
    else:
        raise AssertionError(ext)

def fixeol(s):
    s = s.replace('\r\n', '\n')
    return s

def main(cffi_dir):
    cffi_dir = py.path.local(cffi_dir)
    rootdir = py.path.local(__file__).join('..', '..', '..')
    cffi_dest = rootdir / 'lib_pypy' / 'cffi'
    cffi_dest.ensure(dir=1)
    test_dest = rootdir / 'extra_tests' / 'cffi_tests'
    test_dest.ensure(dir=1)
    for p in (list(cffi_dir.join('cffi').visit(fil='*.py')) +
              list(cffi_dir.join('cffi').visit(fil='*.h'))):
        cffi_dest.join('..', p.relto(cffi_dir)).write_binary(fixeol(p.read()))
    for p in (list(cffi_dir.join('testing').visit(fil='*.py')) +
              list(cffi_dir.join('testing').visit(fil='*.h')) +
              list(cffi_dir.join('testing').visit(fil='*.c'))):
        path = test_dest.join(p.relto(cffi_dir.join('testing')))
        path.join('..').ensure(dir=1)
        path.write_binary(fixeol(''.join(mangle(p.readlines(), p.ext))))

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print __doc__
        sys.exit(2)
    main(sys.argv[1])