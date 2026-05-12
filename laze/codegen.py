"""Laze codegen: AST -> C code (piped to cc)"""

def codegen(ast):
    g = CGen()
    g.emit(ast)
    return g.output()

class CGen:
    def __init__(self):
        self.lines = []
        self.indent = 0

    def w(self, s=''):
        self.lines.append('  ' * self.indent + s)

    def output(self):
        return '\n'.join(self.lines)

    def emit(self, ast):
        self.w('#include <stdint.h>')
        self.w('#include <stdlib.h>')
        self.w('#include <string.h>')
        self.w('#include <unistd.h>')
        self.w('#include <fcntl.h>')
        self.w('#include <stdio.h>')
        # Check if SDL is used
        for node in ast:
            if node[0] == 'link' and node[1] == 'SDL2':
                self.w('#include <SDL.h>')
                break
        self.w('')
        # Extern declarations (for non-standard functions)
        for node in ast:
            if node[0] == 'extern':
                name = node[1].lstrip('_')
                # Skip standard lib functions and SDL (already declared via headers)
                if name.startswith('SDL_') or name in ('malloc', 'free', 'memset', 'memcpy',
                    'open', 'read', 'write', 'close', 'exit', 'printf', 'lseek', 'sprintf'):
                    continue
                self.w(f'extern uint64_t {name}();')
        self.w('')
        # Forward declarations
        for node in ast:
            if node[0] == 'fn':
                _, name, params, ret, _ = node
                self.w(self.fn_proto(name, params, ret) + ';')
        self.w('')
        # Functions
        for node in ast:
            if node[0] == 'fn':
                self.emit_fn(node)

    def fn_proto(self, name, params, ret):
        if name == 'main':
            if params:
                return 'int main(int argc, char** argv)'
            return 'int main(void)'
        elif ret:
            ret_type = self.map_type(ret)
        else:
            ret_type = 'void'
        param_str = ', '.join(f'{self.map_type(t)} {n}' for n, t in params) if params else 'void'
        return f'{ret_type} {name}({param_str})'

    def map_type(self, t):
        if t is None:
            return 'void'
        t = t.strip()
        if t == 'ptr':
            return 'uint8_t*'
        if t in ('u8', 'u16', 'u32', 'u64'):
            return f'uint{t[1:]}_t'
        if t in ('i8', 'i16', 'i32', 'i64'):
            return f'int{t[1:]}_t'
        return 'uint64_t'

    def emit_fn(self, node):
        _, name, params, ret, stmts = node
        self.w(self.fn_proto(name, params, ret) + ' {')
        self.indent += 1
        # Declare all locals at top (Laze has function-scoped vars)
        decls = set()
        self.collect_decls(stmts, decls)
        # Remove params from decls
        for pname, _ in (params or []):
            decls.discard(pname)
        for d in sorted(decls):
            self.w(f'uint64_t {d} = 0;')
        self.emit_stmts(stmts)
        self.indent -= 1
        self.w('}')
        self.w('')

    def collect_decls(self, stmts, decls):
        for s in stmts:
            if s[0] == 'decl':
                decls.add(s[1])

    def emit_stmts(self, stmts):
        i = [0]  # use list for mutability in nested function

        def next_stmt():
            if i[0] < len(stmts):
                s = stmts[i[0]]
                i[0] += 1
                return s
            return None

        def emit_one(s):
            if s[0] == 'decl':
                self.w(f'{s[1]} = (uint64_t)({self.expr(s[2])});')
            elif s[0] == 'assign':
                lhs = s[1]
                rhs = s[2]
                if '[' in lhs and lhs.endswith(']'):
                    base, idx = self.parse_array_access(lhs)
                    self.w(f'((uint8_t*)(uintptr_t){base})[{self.expr(idx)}] = (uint8_t)({self.expr(rhs)});')
                else:
                    self.w(f'{lhs} = (uint64_t)({self.expr(rhs)});')
            elif s[0] == 'return':
                if s[1]:
                    self.w(f'return ({self.expr(s[1])});')
                else:
                    self.w('return;')
            elif s[0] == 'expr':
                self.w(f'{self.expr(s[1])};')
            elif s[0] == 'if':
                self.w(f'if ({self.expr(s[1])}) {{')
                self.indent += 1
                term = emit_until('end', 'else')
                if term == 'else':
                    self.indent -= 1
                    self.w('} else {')
                    self.indent += 1
                    emit_until('end')
                self.indent -= 1
                self.w('}')
            elif s[0] == 'while':
                self.w(f'while ({self.expr(s[1])}) {{')
                self.indent += 1
                emit_until('end')
                self.indent -= 1
                self.w('}')
            elif s[0] == 'break':
                self.w('break;')
            elif s[0] == 'continue':
                self.w('continue;')
            elif s[0] == 'label':
                self.indent -= 1
                self.w(f'{s[1]}:;')
                self.indent += 1
            elif s[0] == 'goto':
                self.w(f'goto {s[1]};')

        def emit_until(*terminators):
            while i[0] < len(stmts):
                s = stmts[i[0]]
                if s[0] in terminators:
                    i[0] += 1
                    return s[0]
                i[0] += 1
                emit_one(s)
            return None

        while i[0] < len(stmts):
            s = stmts[i[0]]
            i[0] += 1
            emit_one(s)

    def parse_array_access(self, s):
        depth = 0
        for i in range(len(s) - 1, -1, -1):
            if s[i] == ']':
                depth += 1
            elif s[i] == '[':
                depth -= 1
                if depth == 0:
                    return s[:i], s[i+1:-1]
        return s, '0'

    def expr(self, e):
        e = e.strip()
        if not e:
            return '0'
        # String literal
        if e.startswith('"'):
            return f'((uint8_t*){e})'
        # Array access as top-level: name[idx]
        if '[' in e and e.endswith(']'):
            base, idx = self.parse_array_access(e)
            if base.isidentifier():
                return f'((uint64_t)((uint8_t*)(uintptr_t){base})[{self.expr(idx)}])'
        # Function call
        if '(' in e and e.endswith(')'):
            paren = e.index('(')
            fname = e[:paren]
            if fname.isidentifier():
                args = e[paren+1:-1]
                return f'{fname}({args})'
        # For compound expressions, transform embedded array accesses
        import re
        # Replace identifier[expr] patterns with cast versions
        result = re.sub(r'([a-zA-Z_]\w*)\[', r'((uint8_t*)(uintptr_t)\1)[', e)
        return result
