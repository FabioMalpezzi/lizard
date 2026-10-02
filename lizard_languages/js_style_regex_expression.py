'''
generate token with javascript style regular expression.
'''

import re


# A regular expression literal: escapes, character classes (where a slash
# does not end the literal) and anything else up to the closing slash, with
# the flags. It never spans lines and is never empty ("//" is a comment).
_REGEX = r"/(?:\\.|\[(?:\\.|[^\]\\\n])*\]|[^/\\\[\n])+/\w*"
_REGEX_LITERAL = re.compile(_REGEX)

# What a regular expression literal can follow; after anything else, like an
# identifier, a number or a closing bracket, the slash is a division.
_BEFORE_REGEX_CHARACTERS = '=,({[?:!&|;'
_BEFORE_REGEX_TOKENS = frozenset((
    '=>', 'return', 'typeof', 'instanceof', 'in', 'of', 'new', 'delete',
    'void', 'throw', 'case', 'do', 'else', 'yield', 'await'))


# What matters inside a template literal: an escape, its end, an expression.
_TEMPLATE_PART = re.compile(r"\\.|`|\$\{", re.S)
# What matters inside the ${} of a template literal: strings, comments and
# regular expressions, whose braces, quotes and backticks are text, then
# braces and nested literals. A regular expression is recognized by the
# character before it.
_EXPRESSION_PART = re.compile(
    r"\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'"
    r"|//[^\n]*|/\*.*?\*/"
    r"|(?:(?<=[=,(\[!&|?:;{}])|(?<=[=,(\[!&|?:;{}] ))" + _REGEX +
    r"|[`{}]", re.S)
_ANYTHING = re.compile(r".*", re.S)


def _can_start_regex(previous):
    return (previous is None or
            previous in _BEFORE_REGEX_TOKENS or
            previous[-1] in _BEFORE_REGEX_CHARACTERS)


def _expression_end(source_code, position):
    '''
    The position after the brace that closes the ${} whose code starts at
    position; None when it is not closed.
    '''
    depth = 1
    while depth:
        found = _EXPRESSION_PART.search(source_code, position)
        if not found:
            return None
        position = found.end()
        if found.group(0) == '`':
            position = _template_literal_end(source_code, found.start())
            if position is None:
                return None
        else:
            depth += {'{': 1, '}': -1}.get(found.group(0), 0)
    return position


def _template_literal_end(source_code, start):
    '''
    The position after the template literal that starts at start; None when
    it does not end. A ${} can hold other template literals.
    '''
    position = start + 1
    while True:
        found = _TEMPLATE_PART.search(source_code, position)
        if not found:
            return None
        position = found.end()
        if found.group(0) == '`':
            return position
        if found.group(0) == '${':
            position = _expression_end(source_code, position)
            if position is None:
                return None


def js_template_literal_parts(literal):
    '''
    Split a template literal, given with its backticks, in the text between
    the expressions and the code of every ${}: yields (text, False) and
    (code, True). An empty text is not yielded.
    '''
    end = len(literal) - 1
    position = text_start = 1
    while True:
        found = _TEMPLATE_PART.search(literal, position, end)
        if not found:
            break
        position = found.end()
        if found.group(0) == '${':
            close = _expression_end(literal, position)
            if close is None or close > end:
                break
            if found.start() > text_start:
                yield literal[text_start:found.start()], False
            yield literal[position:close - 1], True
            position = text_start = close
    if end > text_start:
        yield literal[text_start:end], False


def js_style_literal_tokens(generate_tokens, source_code, addition='',
                            token_class=None):
    '''
    Generate the tokens of generate_tokens with every JavaScript regular
    expression literal and every template literal as one token.

    The literals are read from the source code and not put together from the
    tokens, because the tokenizer takes their content for something else. In
    a regular expression a "#" starts a preprocessor line, "//" a comment and
    a quote a string, and the code after the literal is lost. A template
    literal with another one inside a ${} ends at the first backtick of the
    inner one. A line comment ends at the end of its line, also when the
    line ends with a backslash. After such a literal or comment the tokenizer
    starts again from the character that follows it.

    generate_tokens must yield the source code in consecutive pieces.
    '''
    start = 0
    previous = None
    while start is not None:
        position, start = start, None
        for token in generate_tokens(
                source_code[position:], addition, token_class):
            end = None
            if token == '/' and _can_start_regex(previous):
                literal = _REGEX_LITERAL.match(source_code, position)
                end = literal and literal.end()
            elif token.startswith('`'):
                end = _template_literal_end(source_code, position)
            elif token.startswith('//') and '\n' in token:
                # A line comment ends at its line, also after a backslash
                end = position + token.index('\n')
            if end is not None and end != position + len(token):
                text = source_code[position:end]
                if not token.startswith('//'):
                    previous = text
                if token_class:
                    yield token_class(
                        _ANYTHING.match(source_code, position, end))
                else:
                    yield text
                start = end
                break
            yield token
            position += len(token)
            if not (token.isspace() or token.startswith(('//', '/*'))):
                previous = token


def js_style_regex_expression(func):
    def generate_tokens_with_regex(source_code, addition='', token_class=None):
        regx_regx = r"\/(\S*?[^\s\\]\/)+?(igm)*"
        regx_pattern = re.compile(regx_regx)
        tokens = list(func(source_code, addition, token_class))
        result = []
        i = 0
        while i < len(tokens):
            token = tokens[i]
            if token == '/':
                # Check if this could be a regex pattern
                is_regex = False
                if i == 0:
                    is_regex = True
                elif i > 0:
                    prev_token = tokens[i-1].strip()
                    if prev_token and prev_token[-1] in '=,({[?:!&|;':
                        is_regex = True

                if is_regex:
                    # This is likely a regex pattern start
                    regex_tokens = [token]
                    i += 1
                    while i < len(tokens) and not tokens[i].endswith('/'):
                        regex_tokens.append(tokens[i])
                        i += 1
                    if i < len(tokens):
                        regex_tokens.append(tokens[i])
                        i += 1
                        # Check for regex flags
                        if i < len(tokens) and re.match(r'^[igm]+$', tokens[i]):
                            regex_tokens.append(tokens[i])
                            i += 1
                    combined = ''.join(regex_tokens)
                    if regx_pattern.match(combined):
                        result.append(combined)
                    else:
                        result.extend(regex_tokens)
                    continue
                else:
                    # This is a division operator
                    result.append(token)
            else:
                result.append(token)
            i += 1
        return result
    return generate_tokens_with_regex
