'''
Language parser for TypeScript
'''

import re
from .code_reader import CodeReader, CodeStateMachine
from .clike import CCppCommentsMixin
from .js_style_regex_expression import (
    js_style_literal_tokens, js_template_literal_parts)

# A template literal; quoted strings inside ${...} may contain backticks (#497).
TEMPLATE_LITERAL = (
    r"`(?:\\.|\$\{(?:\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'"
    r"|[^{}\"'`])*\}|[^`\\])*`"
)


# "??", "??=" and "?." are operators of their own, and the "?" of an optional
# parameter, member or chain stays with its name: none of them is a ternary.
QUESTION_MARK_TOKENS = (
    r"|(?:\?\?=?)"
    r"|(?:\?\.(?!\d))"
    r"|(?:\w+\?(?=\.(?!\d)|\s*[:,)]|\Z))"
)


class Parenthesis(str):
    '''
    An opening parenthesis that knows if the one that closes it is followed
    by the "=>" of an arrow function, at once or after a return type.
    '''
    def __new__(cls, arrow):
        token = super().__new__(cls, '(')
        token.arrow = arrow
        return token


class TypeArguments(str):
    '''
    The "<" that opens the type arguments of a call, f<A, B>(x), or the type
    parameters of a declaration, class C<T extends A> {}: what is up to its
    ">" is a type, not code.
    '''
    def __new__(cls):
        return super().__new__(cls, '<')


# What cannot be in the return type of an arrow function, outside brackets
_NOT_IN_A_RETURN_TYPE = frozenset((
    ';', ',', '=', '?', ':', '`', 'return', 'const', 'let', 'var',
    'if', 'for', 'while', 'throw', 'function', 'class', 'await', 'new',
    'yield', 'case', 'default'))
_OPENING = frozenset(('(', '[', '{', '<'))
_CLOSING = frozenset((')', ']', '}', '>'))


def _arrow_follows(tokens):
    '''
    True when the tokens after a ")" start with "=>", or with ":", a return
    type and "=>".
    '''
    tokens = (token for token in tokens
              if not (token.isspace() or token.startswith(('//', '/*'))))
    token = next(tokens, '')
    if token != ':':
        return token == '=>'
    depth = 0
    for token in tokens:
        if token == '=>' and not depth:
            return True
        if token in _OPENING:
            depth += 1
        elif token in _CLOSING:
            depth -= 1
            if depth < 0:
                break
        elif not depth and token in _NOT_IN_A_RETURN_TYPE:
            break
    return False


def _type_arguments_end(tokens, start):
    '''
    The index of the ">" that closes the type arguments opened by the "<" at
    start, when the "(" of a call or what can follow the name of a class
    comes after it; None when the "<" is a comparison.
    '''
    depth = 0
    for index in range(start, min(start + 80, len(tokens))):
        token = tokens[index]
        if token in _OPENING:
            depth += 1
        elif token in _CLOSING:
            depth -= 1
            if not depth:
                following = next(
                    (t for t in tokens[index + 1:index + 6]
                     if not t.isspace()), '')
                return index if token == '>' and following in (
                    '(', '{', 'extends', 'implements') else None
        elif token in (';', '&&', '||', '===', '!==', '==', '!='):
            break
    return None


def mark_parentheses(tokens):
    '''
    Replace the opening parentheses of the tokens with a Parenthesis. The
    states read the tokens one at a time, and cannot know from "(" alone if
    "x = (a, b) => a" or "x = (a + b) * c" follows.
    '''
    tokens = list(tokens)
    opened = []
    in_type_until = -1
    for index, token in enumerate(tokens):
        if token == '(':
            opened.append(index)
        elif token == ')' and opened:
            # In type arguments "(a: A) => B" is a function type
            tokens[opened.pop()] = Parenthesis(
                index > in_type_until
                and _arrow_follows(tokens[index + 1:index + 80]))
        elif token == '<' and index and index > in_type_until and (
                tokens[index - 1][-1:].isalnum() or tokens[index - 1] in '_$'):
            end = _type_arguments_end(tokens, index)
            if end:
                tokens[index] = TypeArguments()
                in_type_until = end
    return tokens


class Tokenizer(object):
    def __init__(self):
        self.sub_tokenizer = None
        self._ended = False

    def __call__(self, token):
        if self.sub_tokenizer:
            for tok in self.sub_tokenizer(token):
                yield tok
            if self.sub_tokenizer._ended:
                self.sub_tokenizer = None
            return
        for tok in self.process_token(token):
            yield tok

    def stop(self):
        self._ended = True

    def process_token(self, token):
        pass


class JSTokenizer(Tokenizer):
    def __init__(self):
        super().__init__()
        self.depth = 1

    def process_token(self, token):
        if token == "{":
            self.depth += 1
        elif token == "}":
            self.depth -= 1
            if self.depth == 0:
                self.stop()
                return
        yield token


class TypeScriptReader(CodeReader, CCppCommentsMixin):
    # pylint: disable=R0903

    ext = ['ts']
    language_names = ['typescript', 'ts']

    # Separated condition categories
    _control_flow_keywords = {'if', 'elseif', 'for', 'while', 'catch'}
    _logical_operators = {'&&', '||'}
    _case_keywords = {'case'}
    _ternary_operators = {'?'}

    def __init__(self, context):
        super().__init__(context)
        self.parallel_states = [TypeScriptStates(context)]

    def __call__(self, tokens, reader):
        return super().__call__(self._template_literals_for_states(tokens), reader)

    @staticmethod
    def _template_literals_for_states(tokens):
        '''
        The states read a template literal as its opening backtick followed
        by every ${} as an expression between parentheses, so that the
        functions in it are found. The text of the literal is not code, and
        "${" and "}" would not be a pair of brackets for a state that is
        reading a parameter list or a type. The counters and the extensions
        receive every token as it is.
        '''
        opened = None  # The brackets open in a template literal
        for token in tokens:
            if opened is None:
                if token == '`':
                    opened = []
                yield token
            elif token == '`' and not opened:
                opened = None
            elif token in ('${', '{'):
                opened.append(token)
                yield Parenthesis(False) if token == '${' else token
            elif token == '}' and opened:
                yield ')' if opened.pop() == '${' else token
            elif opened and not token.startswith('`'):
                yield token

    @staticmethod
    def generate_tokens(source_code, addition='', token_class=None):
        # Private method (#), dollar ($), optional chaining (?), template literals
        addition = addition + r"|(?:#\w+)" + r"|(?:\$\w+)" + QUESTION_MARK_TOKENS + r"|" + TEMPLATE_LITERAL
        return mark_parentheses(TypeScriptReader._generate_tokens(
            source_code, addition, token_class))

    @staticmethod
    def _generate_tokens(source_code, addition, token_class, nested=False):
        for token in js_style_literal_tokens(
                CodeReader.generate_tokens, source_code, addition, token_class):
            if (
                isinstance(token, str)
                and token.startswith('`')
                and token.endswith('`')
                and len(token) > 1
            ):
                for t in TypeScriptReader._split_template_literal(
                        token, addition, token_class, nested):
                    yield t
                continue
            yield token

    @staticmethod
    def _split_template_literal(token, addition, token_class, nested):
        '''
        Yield the backtick that opens the literal, its text between
        backticks, every ${} with the tokens of its code, and the backtick
        that closes it. The states do not read what is between the two
        backticks, so a literal nested in a ${} has none of its own.
        '''
        quote = token[0]
        if not nested:
            yield quote
        for part, is_code in js_template_literal_parts(token):
            if is_code:
                yield '${'
                for t in TypeScriptReader._generate_tokens(
                        part, addition, token_class, nested=True):
                    yield t
                yield '}'
            else:
                yield quote + part + quote
        if not nested:
            yield quote


# A name, also "_", "_unused" and "$element", with the "?" of an optional one
_IDENTIFIER = re.compile(r"(?:[^\W\d]|\$)[\w$]*\??$")

# An expression goes on at the next line after one of these tokens ...
_CONTINUED_AFTER = frozenset((
    '=>', '=', '+', '-', '*', '/', '%', '&&', '||', '??', '?', ':', '|', '&',
    '^', '==', '===', '!=', '!==', '<=', '>=', '+=', '-=', '*=', '/=', '??='))
# ... and a line that starts with one of these goes on with the expression
# of the line before.
_CONTINUED_BY = frozenset((
    '?', ':', '&&', '||', '??', '|', '&', '^', '%', '==', '===', '!=', '!==',
    '<=', '>=', '+', '-', '/', 'instanceof', 'in'))

# Statements that start with a keyword the states read before the new line
_STATEMENTS = frozenset(('if', 'switch', 'for', 'while', 'do', 'try'))

# TypeScript type keywords that should not be counted as parameters
_TS_TYPE_KEYWORDS = frozenset([
    'string', 'number', 'boolean', 'void', 'any',
    'object', 'unknown', 'never',
])


class TypeScriptStates(CodeStateMachine):
    typed = True  # A colon can be followed by a type

    def __init__(self, context):
        super().__init__(context)
        self.last_tokens = ''
        self.function_name = ''
        self.started_function = None
        self.as_object = False
        self._getter_setter_prefix = None

        self._ts_declare = False  # Track if 'declare' was seen
        self._static_seen = False  # Track if 'static' was seen
        self._async_seen = False  # Track if 'async' was seen
        self._prev_token = ''  # Track previous token to detect method calls
        self._in_prop_value = False  # Track if inside property value (after ':')
        self._in_field_value = False  # Track if inside field value (after '=')
        self._closed_by = None  # ']' when reading between square brackets
        self._expression_body = False  # In an arrow function without braces
        self._in_abstract_context = False  # Track abstract method declarations
        self._nesting_in_dec = 0  # Brackets open in a parameter list
        self._arrow_parameter = None  # The parameter of "x => ..."
        self._plain_colons = []  # Tokens whose colon is to come: ?, case, default
        self._after_label = False  # The last colon was the one of a case label
        self._token = None  # The token being read
        self._read_again = None  # The token that ended a type annotation
        self.in_class = False  # In a class body "name: Type" is not a value
        self._class_seen = False  # The next "{" opens a class body
        self._last_line = 0  # The line of the token before it

    def __call__(self, token, reader=None):
        self._token = token
        exiting = super().__call__(token, reader)
        while self._read_again is not None:
            # The token that ended a type annotation, read after the
            # callback of the annotation: the callback it sets is kept.
            token, self._read_again = self._read_again, None
            self._token = token
            exiting = super().__call__(token, reader)
        self._token = None
        self._last_line = self.context.current_line
        return exiting

    def statemachine_before_return(self):
        # Ensure the main function is closed at the end
        if self.started_function:
            self._pop_function_from_stack()

    def _state_global(self, token):
        if (self._expression_body and self.started_function
                and self.context.newline and token in _STATEMENTS):
            # A statement on a new line ends an arrow function without braces
            self._pop_function_from_stack()

        if token == 'declare':
            self._ts_declare = True
            return
        if token == 'function' and getattr(self, '_ts_declare', False):
            # Skip declared function
            self._ts_declare = False
            # Skip tokens until semicolon or newline

            def skip_declared_function(t):
                if t == ';' or self.context.newline:
                    self.next(self._state_global)
                    return True
                return False
            self.next(skip_declared_function)
            return
        self._ts_declare = False

        # The colon of "a ? b : c", of "case x:" and of "default:" is not the
        # one of a property or of a type annotation.
        if token in ('?', 'case', 'default'):
            self._plain_colons.append(token)
        elif token == ':' and self._plain_colons:
            self._after_label = self._plain_colons.pop() != '?'
            self.last_tokens = token
            if self._prev_token not in ('new', '.'):
                self._prev_token = token
            return

        if isinstance(token, TypeArguments):
            # f<A, B>(x): what is up to the ">" is a type, not code
            self._consume_generic_type_params()
            return
        if token in ('as', 'satisfies') and self.typed:
            # x as T, x satisfies T
            self._consume_type_annotation()
            return
        if token == 'class' and self._prev_token != '.':
            self._class_seen = True

        # Skip type alias declarations: type Name = { ... }
        # These contain arrow signatures that are not runtime functions.
        if token == 'type' and not self.as_object:
            phase = [0]        # 0=expect name, 1=expect =, 3=in <...>
            generic_depth = [0]

            def handle_type_alias(t):
                if phase[0] == 0:
                    if t and t[0].isalpha():
                        phase[0] = 1
                    else:
                        self.last_tokens = 'type'
                        self.next(self._state_global)
                        self._state_global(t)
                        return True
                elif phase[0] == 1:
                    if t == '<':
                        generic_depth[0] = 1
                        phase[0] = 3
                    elif t == '=':
                        # The type is read up to its end, on any number
                        # of lines
                        self.next(self._state_global)
                        self._consume_type_annotation()
                    elif t == ';':
                        self.next(self._state_global)
                        return True
                elif phase[0] == 3:
                    if t == '<':
                        generic_depth[0] += 1
                    elif t == '>':
                        generic_depth[0] -= 1
                        if generic_depth[0] == 0:
                            phase[0] = 1
                return False

            self.next(handle_type_alias)
            return

        # Skip interface declarations — method signatures are not runtime functions
        if token == 'interface':
            brace_count = 0
            angle_count = 0  # In the type parameters, before the body
            interface_started = False

            def skip_interface(t):
                nonlocal brace_count, angle_count, interface_started
                if not interface_started and t in ('<', '>'):
                    angle_count += 1 if t == '<' else -1
                elif angle_count > 0:
                    pass
                elif t == '{':
                    interface_started = True
                    brace_count += 1
                elif t == '}' and interface_started:
                    brace_count -= 1
                    if brace_count == 0:
                        self.next(self._state_global)
                        return True
                return False

            self.next(skip_interface)
            return

        # Track abstract modifier inside class bodies
        if token == 'abstract' and self.as_object:
            self._in_abstract_context = True
            return

        # Track static and async modifiers
        if token == 'static':
            self._static_seen = True
            self._prev_token = token
            return
        if token == 'async':
            self._async_seen = True
            self._prev_token = token
            return
        if token == 'new':
            # Track 'new' keyword to avoid treating constructors as functions
            self._prev_token = token
            return

        if self.as_object:
            # Support for getter/setter: look for 'get' or 'set' before method name
            if self._getter_setter_prefix:
                prefix = self._getter_setter_prefix
                self._getter_setter_prefix = None
                if token[0].isalnum() or token[0] in '_$#"\'':
                    # Next token is the property name
                    self.last_tokens = f"{prefix} {token}"
                    return
                # No name follows: "get" or "set" was the name itself, of a
                # method, get() {}, or of a property, { get, set: 1 }
                self.last_tokens = prefix
            elif token in ('get', 'set'):
                self._getter_setter_prefix = token
                return
            in_value = self._in_prop_value or self._in_field_value
            if token == '[' and not in_value:
                self._collect_computed_name()
                return
            if token == ':' and self.in_class and self.typed:
                # field: Type
                self._consume_type_annotation()
                return
            if token == ':':
                # Only set function_name for valid identifiers
                name = self.last_tokens
                if name and (name[0].isalpha() or name[0] in ('_', '$', '#')):
                    self.function_name = name
                self._in_prop_value = True
                return
            elif not in_value and (token == '<' or (
                    token.startswith('<') and token.endswith('>') and len(token) > 1)):
                # Generic type params on method: sortByKey<T>(...) {
                # Handles both multi-token <T, U> and single-token <T> from TSX tokenizer.
                if token == '<':
                    self._consume_generic_type_params()
                return
            elif token == '(':
                if getattr(token, 'arrow', None) and not self.started_function:
                    # The parameters of an arrow function. It has the name
                    # of its field or property, field = (...) => {} and
                    # prop: (...) => {}, also after its type parameters,
                    # and none anywhere else in a value,
                    # prop: a ? b : (...) => {}
                    if not (self.last_tokens in ('=', '>') or (
                            self._in_prop_value
                            and self.last_tokens == self.function_name)):
                        self.function_name = ''
                    self._function(self.function_name)
                    self.next(self._function, token)
                    return
                # Check if this is a method call (previous token was . or new)
                if self._prev_token == '.' or self._prev_token == 'new':
                    # Method call inside object — use sub_state so
                    # the matching ')' doesn't escape the object reader.
                    self.sub_state(self.__class__(self.context))
                    self._prev_token = token
                    return
                # In property value (after ':'), identifier( is a function call
                # unless it's the prop name itself: prop: (...) => {} is arrow fn
                if self._in_prop_value and (
                        not self.function_name
                        or self.last_tokens != self.function_name):
                    self.sub_state(self.__class__(self.context))
                    self._prev_token = token
                    return
                if getattr(token, 'arrow', None) is False and (
                        self.last_tokens == '=' or self._in_prop_value
                        or self._in_field_value):
                    # A parenthesized value, field = (...) or prop: (...),
                    # is not the parameter list of an arrow function.
                    self.sub_state(self.__class__(self.context))
                    self._prev_token = token
                    return
                if not self.started_function:
                    # When last_tokens is '=' we're in a field assignment
                    # pattern (field = () => {}), so use function_name which
                    # was set by the '=' handler to the field name.
                    if self.last_tokens == '=' and self.function_name:
                        self._function(self.function_name)
                    else:
                        self._function(self.last_tokens)
                self.next(self._function, token)
                return
            # If we've seen async/static and this is an identifier, it's likely a method name
            elif (self._async_seen or self._static_seen) and token not in ('*', 'function', '=>'):
                if token == '=':
                    # End of static/async field name — clear modifiers so
                    # the value expression and subsequent members parse
                    # normally.  e.g. `static propTypes = { ... };`
                    self._static_seen = False
                    self._async_seen = False
                    # Fall through to the general '=' handler below
                else:
                    # This is a method name after async/static
                    self.last_tokens = token
                    return

        if token in ('.', '?.'):
            self._state = self._field
            self.last_tokens += token
            self._prev_token = '.'
            return
        if token == 'function':
            if self.started_function and not self.as_object:
                self._pop_function_from_stack()
            self._state = self._function
        elif token in ('if', 'switch', 'for', 'while', 'catch'):
            self.next(self._expecting_condition_and_statement_block)
        elif token in ('else', 'do', 'try', 'final', 'finally'):
            self.next(self._expecting_statement_or_block)
        elif token in ('=>',):
            # "x => ..." has one parameter, the token before the arrow
            name = self.last_token or ''
            self._arrow_parameter = name if (
                name == self.last_tokens and _IDENTIFIER.match(name)) else None
            self._start_arrow_function()
            self._state = self._arrow_function
        elif token == '=':
            # Only set function_name for valid identifiers
            name = self.last_tokens
            if name and (name[0].isalpha() or name[0] in ('_', '$', '#')):
                self.function_name = name
            self._in_field_value = self.as_object
        elif token == "(":
            arrow = getattr(token, 'arrow', None)
            if arrow and not self.started_function:
                # The parameters of an arrow function: it takes the name it
                # is assigned to, if any.
                #   const fn = (...) => {}
                #   list.map((...) => {})
                if self.last_tokens not in ('=', '>'):
                    self.function_name = ''
                self._function(self.function_name)
                self.next(self._function, token)
            elif self._prev_token == '.' or self._prev_token == 'new':
                # This is a method call or constructor, not a function definition
                self.sub_state(
                    self.__class__(self.context))
            elif self.function_name:
                # Distinguish arrow-function definition from function call:
                #   const fn = (...): T => {}  <- _prev_token is '=' or 'async'
                #   const fn = someFunc(...)   <- _prev_token is an identifier
                #   const x = (a + b) * c      <- no arrow after the ')'
                # In the second case, ( follows an identifier that differs
                # from function_name, so it's a call — not a definition.
                if (self.last_tokens != self.function_name
                        and self._prev_token not in ('=', 'async', '>')):
                    self.function_name = ''
                    self.sub_state(self.__class__(self.context))
                elif arrow is False:
                    self.sub_state(self.__class__(self.context))
                else:
                    if not self.started_function:
                        self._function(self.function_name)
                    self.next(self._function, token)
            else:
                self.sub_state(
                    self.__class__(self.context))
        elif token == '{':
            if self.started_function and not self._expression_body:
                self.sub_state(
                    self.__class__(self.context),
                    self._pop_function_from_stack)
            elif self.last_tokens == ':' and self._after_label:
                # case x: { ... } is a block of statements, not an object
                self.sub_state(self.__class__(self.context))
            else:
                self.read_object()
        elif token == '[':
            # An array, an index or a pattern: read up to its own ']', so
            # that the functions and the objects inside it are found.
            inside_brackets = self.__class__(self.context)
            inside_brackets._closed_by = ']'
            self.sub_state(inside_brackets)
        elif token in ('}', ')', self._closed_by):
            self.statemachine_return()
        elif token == ',':
            # The body of an arrow function without braces ends here
            self._pop_function_from_stack()
        elif token == ';' or (self.context.newline and not (
                token in _CONTINUED_BY or self.last_token in _CONTINUED_AFTER)):
            if token == ';':
                self._plain_colons = []
                self._class_seen = False
            self.function_name = ''
            self._pop_function_from_stack()
            # Reset modifiers on newline/semicolon
            self._static_seen = False
            self._async_seen = False
            self._in_abstract_context = False
            self._in_prop_value = False
            self._in_field_value = False
            self._prev_token = ''

        if not self.as_object and self.typed:
            if token == ':':
                self._consume_type_annotation()
                self._prev_token = token
                return
        if self.as_object and token == ',':
            self._in_prop_value = False
            self._in_field_value = False
        self.last_tokens = token
        # Don't overwrite _prev_token if it's 'new' or '.' (preserve for next token)
        if self._prev_token not in ('new', '.'):
            self._prev_token = token

    def read_object(self):
        def callback():
            self.next(self._state_global)

        object_reader = self.__class__(self.context)
        object_reader.as_object = True
        object_reader.in_class, self._class_seen = self._class_seen, False
        # Pass along the modifier flags
        object_reader._static_seen = self._static_seen
        object_reader._async_seen = self._async_seen
        self.sub_state(object_reader, callback)
        # Reset modifiers after entering object
        self._static_seen = False
        self._async_seen = False

    def _expecting_condition_and_statement_block(self, token):
        def callback():
            self.next(self._expecting_statement_or_block)

        if token == "await":
            return

        if token != '(':
            # catch { ... } has no condition
            self.next(self._expecting_statement_or_block, token)
            return

        self.sub_state(
            self.__class__(self.context), callback)

    def _expecting_statement_or_block(self, token):
        def callback():
            self.next(self._state_global)
        if token == "{":
            self.sub_state(
                self.__class__(self.context), callback)
        else:
            self.next(self._state_global, token)

    def _push_function_to_stack(self):
        if self._in_abstract_context:
            return
        self.started_function = True
        self._expression_body = False
        self.context.push_new_function(self.function_name or '(anonymous)')

    def _pop_function_from_stack(self):
        if self.started_function:
            ended = self.context.current_function
            # An arrow function without braces can be ended by the first
            # token of a later line, which is not its own.
            by_next_line = (self._expression_body and self.context.newline
                            and self._token is not None)
            self.context.end_of_function()
            if by_next_line:
                self._give_back_last_token(ended)
        self.started_function = None
        self._expression_body = False
        self._in_prop_value = False
        self._in_field_value = False

    def _give_back_last_token(self, ended):
        enclosing = self.context.current_function
        ended.end_line = self._last_line
        counters = ['nloc', 'token_count']
        if self._token in TypeScriptReader._control_flow_keywords:
            counters.append('cyclomatic_complexity')
        for counter in counters:
            setattr(ended, counter, getattr(ended, counter) - 1)
            setattr(enclosing, counter, getattr(enclosing, counter) + 1)

    def _start_arrow_function(self):
        # At the arrow, so that the function starts at the line of the arrow
        # also when its body is on the next one.
        if not self.started_function:
            self._push_function_to_stack()
            if self.started_function and self._arrow_parameter:
                self.context.parameter(self._arrow_parameter)

    def _arrow_function(self, token):
        # Clear function_name so expression-body ( doesn't re-enter _function
        self.function_name = ''
        # Clear modifiers so the body's opening { isn't captured by the
        # async/static handler in the class body path.
        self._async_seen = False
        self._static_seen = False
        # Without a "{" right after the arrow the body is an expression, and
        # a "{" in it opens an object.
        self._expression_body = token != '{'
        self.next(self._state_global, token)

    def _function(self, token):
        if token == '*':
            return
        if token == '<':
            # Generic type params: function name<T>(...) — consume <...>
            # so function_name (already set) is preserved.
            self._consume_generic_type_params(self._function)
            return
        if token.startswith('<') and token.endswith('>') and len(token) > 1:
            # Single-token generic from TSX tokenizer (e.g., <T>, <Props>)
            return
        if token != '(':
            # Only set function_name for valid identifiers
            if token and (token[0].isalpha() or token[0] in ('_', '$', '#')):
                self.function_name = token
            else:
                self.function_name = ''
            # Reset modifiers after setting function name
            self._static_seen = False
            self._async_seen = False
        else:
            if not self.started_function:
                self._push_function_to_stack()
            self._generic_depth_in_dec = 0
            self._nesting_in_dec = 0
            self._state = self._dec
            self._dec(token)

    def _field(self, token):
        if token in ('[', '('):
            # obj?.[index] and obj?.(argument)
            self.next(self._state_global, token)
            return
        self.last_tokens += token
        self._state = self._state_global

    def _dec(self, token):
        if token in ('(', '[', '{'):
            # A default value, a destructuring pattern or a type can open
            # brackets inside the list.
            self._nesting_in_dec += 1
            if token != '(':
                return
        elif token in (']', '}'):
            if self._nesting_in_dec > 1:
                self._nesting_in_dec -= 1
            return
        elif token == ')':
            self._nesting_in_dec -= 1
            if self._nesting_in_dec <= 0:
                self._state = self._expecting_func_opening_bracket
        else:
            # Filter out TypeScript type keywords and operators from parameter count
            if token == ',':
                # Ignore commas inside generic type brackets, Map<K, V>, and
                # inside the brackets of a pattern, a value or a type
                if (not getattr(self, '_generic_depth_in_dec', 0)
                        and self._nesting_in_dec == 1):
                    self.context.parameter(',')
            elif token == '<':
                self._generic_depth_in_dec = getattr(
                    self, '_generic_depth_in_dec', 0) + 1
            elif token == '>':
                depth = getattr(self, '_generic_depth_in_dec', 0)
                if depth > 0:
                    self._generic_depth_in_dec = depth - 1
            elif token in _TS_TYPE_KEYWORDS:
                pass
            elif token in ('*', '+', '-', '/', '%', '=', '.'):
                pass
            elif not getattr(self, '_generic_depth_in_dec', 0):
                if _IDENTIFIER.match(token):
                    self.context.parameter(token.replace('?', ''))
            return
        self.context.add_to_long_function_name(" " + token)

    def _expecting_func_opening_bracket(self, token):
        # Do not reset started_function for arrow functions (=>)
        if token == ':':
            self._consume_type_annotation()
        elif token == ';' and self.as_object and self._in_abstract_context:
            # Abstract method declaration ends with ';' — no body
            if self.started_function:
                self._pop_function_from_stack()
            self._in_abstract_context = False
            self.next(self._state_global)
        elif token != '{' and token != '=>':
            if self.started_function:
                # Arrow function not confirmed (no => or { after params).
                # Use forgive to cleanly un-push the optimistic function
                # so it doesn't appear in output or corrupt the stack.
                self.context.forgive = True
                self.context.end_of_function()
            self.started_function = None
        self.next(self._state_global, token)

    def _collect_computed_name(self):
        # Collect tokens between [ and ]
        tokens = []

        def collect(token):
            if token == ']':
                # Try to join tokens and camelCase if possible
                name = ''.join(tokens)
                # Remove quotes and pluses for simple cases
                name = name.replace("'", '').replace('"', '').replace('+', '').replace(' ', '')
                # Lowercase first char, uppercase next word's first char
                name = self._to_camel_case(name)
                self.last_tokens = name
                self.next(self._state_global)
                return True
            tokens.append(token)
            return False
        self.next(collect)

    def _to_camel_case(self, s):
        # Simple camelCase conversion for test case
        if not s:
            return s
        parts = s.split()
        if not parts:
            return s
        return parts[0][0].lower() + parts[0][1:] + ''.join(p.capitalize() for p in parts[1:])

    def _consume_generic_type_params(self, then=None):
        """Consume <...> generic type parameters (e.g., method<T>(...))
        so the method name in last_tokens is preserved."""
        depth = 1
        then = then or self._state_global

        def consume(token):
            nonlocal depth
            if token == '<':
                depth += 1
            elif token == '>':
                depth -= 1
                if depth == 0:
                    self.next(then)
        self.next(consume)

    def _consume_type_annotation(self):
        typeStates = TypeScriptTypeAnnotationStates(self.context)

        def callback():
            self._read_again = typeStates.saved_token
        self.sub_state(typeStates, callback)


class TypeScriptTypeAnnotationStates(CodeStateMachine):
    '''
    Reads a type, as it comes after a colon, up to the token after it, which
    is kept in saved_token for the reader of the code. A type is one piece
    for the states of the code: its brackets are not theirs, and a function
    type, (a: A) => B, is not a function.
    '''

    _CLOSING = {'(': ')', '[': ']', '{': '}', '<': '>'}
    # A type must follow these tokens: a "{" after them opens an object type
    # and not the body of a function, and a new line goes on with the type.
    _BEFORE_A_TYPE = frozenset((
        '|', '&', '.', '?', ':', 'is', 'as', 'satisfies', 'keyof', 'typeof',
        'readonly', 'extends', 'asserts', 'infer', 'unique', 'new'))
    _AFTER_THE_TYPE = frozenset(('{', '=', ';', ')', ',', ']', '}', '=>'))

    def __init__(self, context):
        super().__init__(context)
        self.saved_token = None
        self._to_close = []  # The brackets open in the type
        self._type_expected = True
        self._after_parentheses = False

    def _state_global(self, token):
        if self._to_close:
            if token in self._CLOSING:
                self._to_close.append(self._CLOSING[token])
            elif token == self._to_close[-1]:
                self._to_close.pop()
                self._after_parentheses = token == ')'
        elif token in self._CLOSING and (token != '{' or self._type_expected):
            self._to_close.append(self._CLOSING[token])
            self._type_expected = False
        elif token == '=>' and self._after_parentheses:
            # (a: A) => B, a function type: its return type follows
            self._after_parentheses = False
            self._type_expected = True
        elif token in self._AFTER_THE_TYPE or (
                self.context.newline and not self._type_expected
                and token not in ('|', '&')):
            self.saved_token = token
            self.statemachine_return()
        else:
            self._after_parentheses = False
            self._type_expected = token in self._BEFORE_A_TYPE
