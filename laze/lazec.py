#!/usr/bin/env python3
"""Laze compiler: .laze -> C (in memory) -> cc -O2 -> binary"""
import sys, os, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    if len(sys.argv) < 2:
        print("Usage: lazec <file.laze> [output]")
        sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0]
    with open(src) as f:
        source = f.read()
    from laze.parser import parse
    from laze.codegen import codegen
    ast = parse(source)
    c_code = codegen(ast)
    # Build cc command
    cmd = ['cc', '-O2', '-x', 'c', '-', '-o', out, '-lSystem',
           '-Wno-int-conversion', '-Wno-incompatible-pointer-types',
           '-Wno-pointer-to-int-cast', '-Wno-int-to-pointer-cast',
           '-Wno-format', '-Wno-unused-value', '-Wno-pointer-sign']
    for node in ast:
        if node[0] == 'framework':
            cmd += ['-framework', node[1]]
        elif node[0] == 'link':
            cmd += ['-l' + node[1]]
            if node[1] == 'SDL2':
                cmd += ['-I/opt/homebrew/include/SDL2', '-D_THREAD_SAFE']
        elif node[0] == 'linkpath':
            cmd += ['-L' + node[1]]
            cmd += ['-Wl,-rpath,' + node[1]]
    result = subprocess.run(cmd, input=c_code.encode(), capture_output=True)
    if result.returncode != 0:
        # Dump C for debugging
        with open('/tmp/laze_debug.c', 'w') as f:
            f.write(c_code)
        print("Compile error (C saved to /tmp/laze_debug.c):")
        print(result.stderr.decode())
        sys.exit(1)
    os.chmod(out, 0o755)
    print(f"Built: {out}")

if __name__ == '__main__':
    main()
