'''
This module provides the ExpressionTree class, which parses a query expression
like "a AND (b OR c)" and then evaluates whether an input satisfies the query.

Basic usage:
>>> tree = ExpressionTree.parse('a AND (b OR c)')
>>> tree.evaluate('a b')
True
>>> tree.evaluate('a c')
True
>>> tree.evaluate('b c')
False
>>>

The available operators are:
a AND b
a OR b
a XOR b
NOT a

where a and b can be single tokens or a parenthesized group of tokens.

The operators must be capitalized as seen and can be enclosed in quotes if you
need to literally match the word "AND", etc.

If the tokens contain spaces, they must be enclosed in quotation marks:
tree = expressionmatch.ExpressionTree.parse('"mark hamill" OR "harrison ford"')
'''
from voussoirkit import sentinel

BINARY_OPERATORS = {'AND', 'OR', 'XOR'}
UNARY_OPERATORS = {'NOT'}
PRECEDENCE = ['NOT', 'AND', 'XOR', 'OR']
OPERATORS = BINARY_OPERATORS | UNARY_OPERATORS

# These sentinels help the parser distinguish between parens used for token
# grouping and parens that have been escaped by the user and should remain
# as strings.
PAREN_OPEN = sentinel.Sentinel('PAREN_OPEN')
PAREN_CLOSE = sentinel.Sentinel('PAREN_CLOSE')

DEFAULT_MATCH_FUNCTION = str.__contains__

MESSAGE_WRITE_YOUR_OWN_MATCHER = '''
The default match function is {function}.
Consider passing your own `match_function`, which accepts two
positional arguments:
1. The object being tested.
2. The Expression token, a string.
'''.strip()

def func_and(values):
    return all(values)

def func_or(values):
    return any(values)

def func_xor(values):
    values = list(values)
    return values.count(True) % 2 == 1

def func_not(value):
    value = list(value)
    if len(value) != 1:
        raise ValueError('NOT only takes 1 value')
    return not value[0]

OPERATOR_FUNCTIONS = {
    'AND': func_and,
    'OR': func_or,
    'XOR': func_xor,
    'NOT': func_not,
}

class NoTokens(Exception):
    pass

class ExpressionTree:
    def __init__(self, token, parent=None):
        '''
        This constructor is for each individual node of the tree.
        End-users should probably call ExpressionTree.parse instead of this
        constructor.
        '''
        self.children = []
        self.parent = parent
        self.token = token

    def __str__(self):
        if self.token is None:
            return '""'

        self_token = str(self.token)

        if self_token not in OPERATORS:
            t = self_token
            t = t.replace('\\', '\\\\')
            t = t.replace('"', '\\"')
            t = t.replace('(', '\\(')
            t = t.replace(')', '\\)')
            if ' ' in t:
                t = f'"{t}"'
            return t

        if len(self.children) == 1:
            child = self.children[0]
            childstring = str(child)
            if child.token in OPERATORS:
                return f'{self_token}({childstring})'
            return f'{self_token} {childstring}'

        children = []
        for child in self.children:
            childstring = str(child)
            if child.token in OPERATORS:
                childstring = f'({childstring})'
            children.append(childstring)

        if len(children) == 1:
            return f'{self_token} {children[0]}'

        s = f' {self_token} '
        s = s.join(children)
        return s

    @classmethod
    def parse(cls, tokens):
        '''
        Create an ExpressionTree from the given query string or list of tokens.
        '''
        if isinstance(tokens, str):
            tokens = tokenize(tokens)

        if tokens == []:
            raise NoTokens()

        if isinstance(tokens[0], list):
            current = cls.parse(tokens[0])
        else:
            current = cls(token=tokens[0])

        for token in tokens[1:]:
            if isinstance(token, list):
                new = cls.parse(token)
            else:
                new = cls(token=token)

            if 0 == 1:
                pass

            elif current.token not in OPERATORS:
                if new.token in BINARY_OPERATORS:
                    if len(new.children) == 0:
                        new.children.append(current)
                        current.parent = new
                        current = new
                else:
                    raise Exception(f'Expected binary operator, got {new.token}.')

            elif current.token in BINARY_OPERATORS:
                if new.token in BINARY_OPERATORS:
                    if new.token == current.token:
                        for child in new.children:
                            child.parent = current
                        current.children.extend(new.children)
                    else:
                        if len(new.children) == 0:
                            new.children.append(current)
                            current.parent = new
                            current = new
                        else:
                            current.children.append(new)
                            new.parent = current

                elif new.token in UNARY_OPERATORS:
                    if len(new.children) == 0:
                        current.children.append(new)
                        new.parent = current
                        current = new
                    else:
                        current.children.append(new)
                        new.parent = current

                elif new.token not in OPERATORS:
                    if len(current.children) > 0:
                        current.children.append(new)
                        new.parent = current
                    else:
                        raise Exception('Expected current children > 0.')

            elif current.token in UNARY_OPERATORS:
                if len(current.children) == 0:
                    current.children.append(new)
                    new.parent = current
                    if current.parent is not None:
                        current = current.parent
                elif new.token in BINARY_OPERATORS:
                    if len(new.children) == 0:
                        new.children.append(current)
                        current.parent = new
                        current = new
                    else:
                        current.children.append(new)
                        new.parent = current
                        if current.parent is not None:
                            current = current.parent
                else:
                    raise Exception('Expected new to be my operand or parent binary.')

        current = current.rootmost()
        return current

    def _evaluate(self, text, match_function=None):
        if self.token not in OPERATORS:
            if match_function is None:
                match_function = DEFAULT_MATCH_FUNCTION

            value = match_function(text, self.token)
            return value

        operator_function = OPERATOR_FUNCTIONS[self.token]
        children = (child.evaluate(text, match_function=match_function) for child in self.children)
        return operator_function(children)

    def diagram(self):
        if self.token is None:
            return '""'
        t = self.token
        if isinstance(t, str):
            if ' ' in t:
                t = f'"{t}"'
        else:
            t = repr(t)

        output = t
        indent = 1
        for child in self.children:
            child = child.diagram()
            for line in child.splitlines():
                output += (' ' * indent)
                output += line + '\n'
                indent = len(t) + 1
        output = output.strip()

        return output

    def evaluate(self, text, match_function=None):
        if match_function is None:
            match_function = DEFAULT_MATCH_FUNCTION

        try:
            return self._evaluate(text, match_function)
        except Exception as e:
            if match_function is DEFAULT_MATCH_FUNCTION:
                message = MESSAGE_WRITE_YOUR_OWN_MATCHER.format(function=DEFAULT_MATCH_FUNCTION)
                override = Exception(message)
                raise override from e
            raise e

    @property
    def is_leaf(self):
        return self.token not in OPERATORS

    @property
    def is_root(self):
        return self.parent is None

    def map(self, function):
        '''
        Apply this function to all of the operands.
        '''
        for node in self.walk_leaves():
            node.token = function(node.token)

    def prune(self):
        '''
        Remove any nodes where `token` is None.
        '''
        self.children = [child for child in self.children if child.token is not None]

        for child in self.children:
            child.prune()

        if self.token in OPERATORS and len(self.children) == 0:
            self.token = None
            if self.parent is not None:
                self.parent.children.remove(self)

    def rootmost(self):
        current = self
        while current.parent is not None:
            current = current.parent
        return current

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def walk_leaves(self):
        for node in self.walk():
            if node.is_leaf:
                yield node

def implied_tokens(tokens):
    '''
    This function returns a new list of tokens which has all of the implied
    tokens added explicitly and meaningless tokens removed, by the
    following rules:

    1. If two operands are directly next to each other, or an operand is
        followed by a unary operator, it is implied that there is an AND
        between them.
        '1 2' -> '1 AND 2'
        '1 NOT 2' -> '1 AND NOT 2'

    2. If an expression begins or ends with an invalid operator, remove it.
        'AND 2' -> '2'
        '2 AND' -> '2'

    3. If a parenthetical term contains only 1 item, the parentheses can be removed.
        '(a)' -> 'a'
        '(NOT a)' -> 'NOT a'
        '(a OR)' -> '(a)' (by rule 2) -> 'a'

    4. If two operators are next to each other, except for binary-unary,
        keep only the first.
        '1 OR AND 2' -> '1 OR 2'
        '1 NOT AND 2' -> '1 AND NOT AND 2' (by rule 1) -> '1 AND NOT 2'
        'NOT NOT 1' -> 'NOT 1'
        '1 AND NOT NOT 2' -> '1 AND NOT 2'
    '''
    final_tokens = []
    has_operand = False
    has_binary_operator = False
    has_unary_operator = False

    if len(tokens) == 1 and not isinstance(tokens[0], str):
        # [['A' 'AND' 'B']] -> ['A' 'AND' 'B']
        tokens = tokens[0]

    for token in tokens:
        skip_this = False
        while isinstance(token, (list, tuple)):
            if len(token) == 0:
                # Delete empty parentheses.
                skip_this = True
                break
            if len(token) == 1:
                # Take singular terms out of their parentheses.
                token = token[0]
            else:
                previous = token
                token = implied_tokens(token)
                if previous == token:
                    break

        if skip_this:
            continue

        if isinstance(token, str) and token in OPERATORS:
            this_binary = token in BINARY_OPERATORS
            this_unary = not this_binary

            # 'NOT AND' and 'AND AND' are malformed...
            if this_binary and (has_binary_operator or has_unary_operator):
                continue
            # ...'NOT NOT' is malformed...
            if this_unary and has_unary_operator:
                continue
            # ...but AND NOT is okay.

            # 'AND test' is malformed
            if this_binary and not has_operand:
                continue

            if this_unary and has_operand:
                final_tokens.append('AND')

            has_unary_operator = this_unary
            has_binary_operator = this_binary
            has_operand = False

        else:
            if has_operand:
                final_tokens.append('AND')
            has_unary_operator = False
            has_binary_operator = False
            has_operand = True

        final_tokens.append(token)

    if has_binary_operator or has_unary_operator:
        final_tokens.pop(-1)

    return final_tokens

def order_operations(tokens):
    for (index, token) in enumerate(tokens):
        if isinstance(token, list):
            tokens[index] = order_operations(token)

    if len(tokens) < 5:
        return tokens

    index = 0
    slice_start = None
    slice_end = None
    precedence_stack = []
    while index < len(tokens):
        token = tokens[index]
        try:
            precedence = PRECEDENCE.index(token)
        except ValueError:
            precedence = None

        if precedence is None:
            index += 1
            continue
        precedence_stack.append(precedence)

        if token in UNARY_OPERATORS:
            slice_start = index
            slice_end = index + 2

        elif len(precedence_stack) > 1:
            if precedence_stack[-1] < precedence_stack[-2]:
                slice_start = index - 1
                slice_end = None
            elif precedence_stack[-2] < precedence_stack[-1]:
                slice_end = index

        if slice_start is None or slice_end is None:
            index += 1
            continue

        tokens[slice_start:slice_end] = [tokens[slice_start:slice_end]]
        slice_start = None
        slice_end = None
        for x in range(2):
            if not precedence_stack:
                break

            delete = precedence_stack[-1]
            while precedence_stack and precedence_stack[-1] == delete:
                index -= 1
                precedence_stack.pop(-1)

        index += 1

    if slice_start is not None:
        slice_end = len(tokens)
        tokens[slice_start:slice_end] = [tokens[slice_start:slice_end]]

    return tokens

def sublist_tokens(tokens, _from_index=0, depth=0):
    '''
    Given a list of tokens, replace parentheses with actual sublists.
    ['1', 'AND', '(', '3', 'OR', '4', ')'] ->
    ['1', 'AND', ['3', 'OR', '4']]

    Unclosed parentheses are automatically closed at the end.
    '''
    final_tokens = []
    index = _from_index
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if token is PAREN_OPEN:
            (token, index) = sublist_tokens(tokens, _from_index=index, depth=depth+1)
        if token is PAREN_CLOSE:
            break
        final_tokens.append(token)
    if _from_index == 0:
        return final_tokens
    else:
        return (final_tokens, index)

def tokenize(expression):
    '''
    Break the string into a list of tokens. Spaces are the delimiter unless
    they are inside quotation marks.

    Quotation marks and parentheses can be escaped by preceeding with a
    backslash '\\'.

    Opening and closing parentheses are put into their own token unless
    escaped / quoted.

    Extraneous closing parentheses are ignored completely.

    '1 AND(4 OR "5 6") OR \\(test\\)' ->
    ['1', 'AND', '(', '4', 'OR', '5 6', ')', 'OR', '\\(test\\)']
    '''
    current_word = []
    in_escape = False
    in_quotes = False
    paren_depth = 0
    tokens = []
    for character in expression:
        if in_escape:
            in_escape = False

        elif character in {'(', ')'} and not in_quotes:
            if character == '(':
                sentinel = PAREN_OPEN
                paren_depth += 1
            elif character == ')':
                sentinel = PAREN_CLOSE
                paren_depth -= 1

            if paren_depth >= 0:
                tokens.append(''.join(current_word))
                tokens.append(sentinel)
                current_word.clear()
                continue
            else:
                continue

        elif character == '\\':
            in_escape = True
            continue

        elif character == '"':
            in_quotes = not in_quotes
            continue

        elif character.isspace() and not in_quotes:
            tokens.append(''.join(current_word))
            current_word.clear()
            continue

        current_word.append(character)

    tokens.append(''.join(current_word))
    tokens = [w for w in tokens if w != '']
    tokens = sublist_tokens(tokens)
    tokens = implied_tokens(tokens)
    tokens = order_operations(tokens)
    return tokens

if __name__ == '__main__':
    tests = [
        '[sci-fi] OR [pg-13]',
        '([sci-fi] OR [war]) AND [r]',
        '[r] XOR [sci-fi]',
        '"[mark hamill]" "[harrison ford]"',
    ]
    teststrings = {
        'Star Wars': '[harrison ford] [george lucas] [sci-fi] [pg] [carrie fisher] [mark hamill] [space]',
        'Blade Runner': '[harrison ford] [ridley scott] [neo-noir] [dystopian] [sci-fi] [r]',
        'Indiana Jones': '[harrison ford] [steven spielberg] [adventure] [pg-13]',
        'Apocalypse Now': '[harrison ford] [francis coppola] [r] [war] [drama]'
    }
    for test in tests:
        print('start:', test)
        tokens = tokenize(test)
        print('implied:', tokens)
        etree = ExpressionTree.parse(tokens)
        print('tree:', etree)
        print(etree.diagram())
        for (name, teststring) in teststrings.items():
            print('Matches', name, ':', etree.evaluate(teststring))
        print()
