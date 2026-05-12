"""Laze parser: source text -> AST (list of top-level nodes)"""

def parse(source):
    lines = source.split('\n')
    ast = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped.startswith(';'):
            i += 1
            continue
        if stripped.startswith('extern '):
            ast.append(('extern', stripped[7:].strip()))
            i += 1
        elif stripped.startswith('framework '):
            ast.append(('framework', stripped[10:].strip()))
            i += 1
        elif stripped.startswith('link '):
            ast.append(('link', stripped[5:].strip()))
            i += 1
        elif stripped.startswith('linkpath '):
            ast.append(('linkpath', stripped[9:].strip()))
            i += 1
        elif stripped.startswith('struct '):
            name, fields, next_i = parse_struct(lines, i)
            ast.append(('struct', name, fields))
            i = next_i
        elif stripped.startswith('fn '):
            func, next_i = parse_fn(lines, i)
            ast.append(func)
            i = next_i
        elif stripped.startswith('const '):
            ast.append(parse_const(stripped))
            i += 1
        elif stripped.startswith('global '):
            ast.append(parse_global(stripped))
            i += 1
        else:
            i += 1
    return ast

def parse_const(line):
    # const NAME = value
    rest = line[6:].strip()
    name, val = rest.split('=', 1)
    return ('const', name.strip(), val.strip())

def parse_global(line):
    # global name: type
    # global name: type = value
    rest = line[7:].strip()
    if '=' in rest:
        decl, val = rest.split('=', 1)
        name, typ = decl.strip().rsplit(':', 1)
        return ('global', name.strip(), typ.strip(), val.strip())
    else:
        name, typ = rest.rsplit(':', 1)
        return ('global', name.strip(), typ.strip(), None)

def parse_struct(lines, i):
    # struct Name
    #   field: type
    header = lines[i].strip()
    name = header[7:].strip()
    i += 1
    fields = []
    while i < len(lines):
        line = lines[i]
        if not line or not line[0].isspace():
            break
        stripped = line.strip()
        if not stripped or stripped.startswith(';'):
            i += 1
            continue
        fname, ftype = stripped.split(':', 1)
        fields.append((fname.strip(), ftype.strip()))
        i += 1
    return name, fields, i

def parse_fn(lines, i):
    header = lines[i].strip()
    # fn name(params) -> rettype
    # fn name(params)
    rest = header[3:]
    paren_start = rest.index('(')
    name = rest[:paren_start].strip()
    paren_end = rest.index(')')
    params_str = rest[paren_start+1:paren_end].strip()
    params = []
    if params_str:
        for p in split_params(params_str):
            pname, ptype = p.strip().split(':', 1)
            params.append((pname.strip(), ptype.strip()))
    ret = None
    after = rest[paren_end+1:].strip()
    if after.startswith('->'):
        ret = after[2:].strip()
    i += 1
    body = []
    while i < len(lines):
        line = lines[i]
        if not line or (line[0] != ' ' and line[0] != '\t'):
            # Check if it's a blank line between functions
            if not line.strip():
                # peek ahead - if next non-blank is top-level, stop
                j = i + 1
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j >= len(lines) or (lines[j][0] != ' ' and lines[j][0] != '\t'):
                    break
                body.append('')
                i += 1
                continue
            break
        body.append(line)
        i += 1
    stmts = parse_body(body)
    return ('fn', name, params, ret, stmts), i

def split_params(s):
    """Split on commas, respecting brackets."""
    parts = []
    depth = 0
    current = ''
    for c in s:
        if c in '([':
            depth += 1
        elif c in ')]':
            depth -= 1
        if c == ',' and depth == 0:
            parts.append(current)
            current = ''
        else:
            current += c
    if current.strip():
        parts.append(current)
    return parts

def parse_body(lines):
    stmts = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(';'):
            continue
        stmts.append(parse_stmt(stripped))
    return stmts

def parse_stmt(s):
    # Label
    if s.endswith(':') and not s.startswith('if') and ':=' not in s and '=' not in s.split(':')[0]:
        return ('label', s[:-1].strip())
    # Return
    if s.startswith('return'):
        val = s[6:].strip()
        return ('return', val if val else None)
    # If
    if s.startswith('if '):
        return parse_if(s)
    # While
    if s.startswith('while '):
        return ('while', s[6:].strip())
    # End
    if s == 'end':
        return ('end',)
    # Else
    if s == 'else':
        return ('else',)
    # Break/continue
    if s == 'break':
        return ('break',)
    if s == 'continue':
        return ('continue',)
    # Goto
    if s.startswith('goto '):
        return ('goto', s[5:].strip())
    # Declaration with :=
    if ':=' in s:
        name, expr = s.split(':=', 1)
        return ('decl', name.strip(), expr.strip())
    # Assignment with =
    if '=' in s and not s.startswith('if') and not s.startswith('while'):
        # Check it's not == inside an expression
        eq_pos = find_assignment_eq(s)
        if eq_pos >= 0:
            lhs = s[:eq_pos].strip()
            rhs = s[eq_pos+1:].strip()
            return ('assign', lhs, rhs)
    # Expression (function call, etc)
    return ('expr', s)

def find_assignment_eq(s):
    """Find the position of assignment = (not ==, !=, <=, >=)."""
    i = 0
    in_str = False
    while i < len(s):
        if s[i] == '"':
            in_str = not in_str
        if in_str:
            i += 1
            continue
        if s[i] == '=' and i > 0:
            if s[i-1] in '!<>=':
                i += 1
                continue
            if i + 1 < len(s) and s[i+1] == '=':
                i += 2
                continue
            return i
        i += 1
    return -1

def parse_if(s):
    # if condition
    cond = s[3:].strip()
    return ('if', cond)
