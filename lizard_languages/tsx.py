'''
Language parser for TSX/JSX

Uses TypeScriptStates (from typescript.py) for function detection.
Only overrides tokenization to handle JSX-specific syntax (<Component>, {expressions}).
'''

from .code_reader import CodeReader
from .js_style_regex_expression import js_style_literal_tokens
from .typescript import TypeScriptReader, TEMPLATE_LITERAL, QUESTION_MARK_TOKENS
from .typescript import JSTokenizer, Tokenizer, mark_parentheses


class TSXReader(TypeScriptReader):
    # pylint: disable=R0903

    ext = ['tsx', 'jsx']
    language_names = ['tsx', 'jsx']

    @staticmethod
    def generate_tokens(source_code, addition='', token_class=None):
        return mark_parentheses(
            TSXReader._generate_tsx_tokens(source_code, addition, token_class))

    @staticmethod
    def _generate_tsx_tokens(source_code, addition, token_class):
        # Add support for TypeScript type annotations in JSX
        addition = addition + \
            r"|(?:<[A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9]*)*>)" + \
            r"|(?:<\/[A-Za-z][\w.:-]*>)" + \
            r"|(?:<\/?>)" + \
            r"|(?:#\w+)" + \
            r"|(?:\$\w+)" + \
            QUESTION_MARK_TOKENS + \
            r"|(?:<\/\w+>)" + \
            r"|(?:=>)" + \
            r"|" + TEMPLATE_LITERAL
        js_tokenizer = TSXTokenizer()

        def read(source):
            position = 0
            while position is not None:
                start, position = position, None
                for token in js_style_literal_tokens(
                        CodeReader.generate_tokens, source[start:], addition,
                        token_class):
                    prefix = '//' if token.startswith('//') else token[:1]
                    if (prefix in _NOT_IN_TEXT and len(token) > len(prefix)
                            and js_tokenizer.reads_text()):
                        # In the text of a tag "//" does not start a
                        # comment, "#" a line of the preprocessor, "/" a
                        # regular expression or a quote a string: what
                        # follows is read again as text.
                        #   <p>Visit https://example.com today</p>
                        #   <p>PR #{pr.number}, it's in /config</p>
                        for tok in js_tokenizer(prefix):
                            yield tok
                        position = start + len(prefix)
                        break
                    for tok in js_tokenizer(token):
                        yield tok
                    start += len(token)

        for tok in read(source_code):
            if tok.startswith('`') and tok.endswith('`') and len(tok) > 1:
                for part in TypeScriptReader._split_template_literal(
                        tok, addition, token_class, False):
                    yield part
            else:
                yield tok
        # A tag that is still open at the end of the file
        for tok in js_tokenizer.left_over():
            yield tok


# The characters that start a token longer than themselves, which in the text
# of a tag are text
_NOT_IN_TEXT = frozenset(('//', '/', '#', "'", '"', '`'))

# After one of these words a "<" opens a tag, as after an operator; after any
# other word, a ")" or a "]" it is a comparison or opens type arguments.
_BEFORE_A_TAG = frozenset((
    'return', 'default', 'case', 'yield', 'await', 'do', 'else', 'in', 'of'))


def _is_opening_tag(token):
    return (token.startswith('<') and token.endswith('>')
            and not token.startswith('</') and not token.endswith('/>'))


class TSXTokenizer(JSTokenizer):
    def __init__(self):
        super().__init__()
        self.previous = ''  # The last token that is not white space

    def process_token(self, token):
        previous = self.previous
        if not token.isspace():
            self.previous = token
        can_be_tag = previous in _BEFORE_A_TAG or not (
            previous[-1:].isalnum() or previous[-1:] in ('_', '$', ')', ']'))
        if token == "<" and can_be_tag:
            self.sub_tokenizer = XMLTagWithAttrTokenizer()
            return

        if _is_opening_tag(token) and can_be_tag:
            # <div> or <>, a tag without attributes: its text follows
            self.sub_tokenizer = XMLTagWithAttrTokenizer(token)
            return

        if token == "=>":
            # Special handling for arrow functions
            yield token
            return

        for tok in super().process_token(token):
            yield tok


class XMLTagWithAttrTokenizer(Tokenizer):
    def __init__(self, opening_tag=None):
        super(XMLTagWithAttrTokenizer, self).__init__()
        self.tag = opening_tag and opening_tag[1:-1]
        self.state = self._start_of_body if opening_tag else self._global_state
        self.cache = [opening_tag or '<']
        self._attr_expr_active = False

    def __call__(self, token):
        if self.sub_tokenizer:
            for tok in self.sub_tokenizer(token):
                yield tok
            if self.sub_tokenizer._ended:
                self.sub_tokenizer = None
                if self._attr_expr_active:
                    # The TSXTokenizer consumed the closing '}' of a JSX
                    # attribute expression.  Inject ';' so the state machine
                    # properly closes any expression-body arrow function
                    # that was opened inside the attribute (e.g.
                    # onClick={() => handler()}).
                    self._attr_expr_active = False
                    yield ';'
            return
        for tok in self.process_token(token):
            yield tok

    def process_token(self, token):
        self.cache.append(token)
        if not token.isspace():
            result = self.state(token)
            if result is not None:
                if isinstance(result, list):
                    for tok in result:
                        yield tok
                else:
                    return result
        return ()

    def abort(self):
        self.stop()
        return self.cache

    def reads_text(self):
        if self.sub_tokenizer:
            return self.sub_tokenizer.reads_text()
        return self.state in (self._start_of_body, self._body)

    def left_over(self):
        return self.cache + super().left_over()

    def flush(self):
        tmp, self.cache = self.cache, []
        text = ''.join(tmp)
        # White space is given as it was read, with every new line as a
        # token: a longer token of white space would not be counted.
        return tmp if text.isspace() or not text else [text]

    def _global_state(self, token):
        if not isidentifier(token):
            return self.abort()
        self.tag = token
        self.state = self._after_tag

    def _after_tag(self, token):
        if token == '>':
            self.state = self._start_of_body
        elif token == "/":
            self.state = self._expecting_self_closing
        elif token in ('.', '-', ':') and self.cache[-2] == self.tag:
            # Menu.Item, my-item, svg:rect: the name of the tag goes on
            self.state = self._global_state
        elif token == '{':
            # {...props}
            return self._expression()
        elif isidentifier(token):
            self.state = self._expecting_equal_sign
        else:
            return self.abort()

    def _expecting_self_closing(self, token):
        if token == ">":
            self.stop()
            return self.flush()
        return self.abort()

    def _expecting_equal_sign(self, token):
        if token == '=':
            self.state = self._expecting_value
        elif token in ('-', ':'):
            # aria-label, xlink:href: the name of the attribute goes on
            self.state = self._attribute_name
        else:
            # An attribute without a value: disabled, checked
            self.state = self._after_tag
            return self._after_tag(token)

    def _attribute_name(self, token):
        if not (isidentifier(token) or token.isdigit()):
            return self.abort()
        self.state = self._expecting_equal_sign

    def _expecting_value(self, token):
        if token[0] in "'\"":
            self.state = self._after_tag
        elif token == "{":
            return self._expression()

    def _expression(self):
        # TSXTokenizer handles brace-depth tracking and stops at the
        # matching '}'.  Transition straight to _after_tag so the next
        # attribute (or '>') is processed correctly once the sub-
        # tokenizer finishes.  What was read of the tag is given first, so
        # that the code of the expression is at its own lines.
        self.state = self._after_tag
        self.sub_tokenizer = TSXTokenizer()
        self._attr_expr_active = True
        return self.flush()

    def _start_of_body(self, token):
        # Abort if the first token can't be JSX body content — likely type
        # parameters or type arguments: <T extends A>(x: T) => x, <T> = ...
        if token in ('=', '=>', ';', ')', ',') or (
                token == '(' and self.tag[:1].isupper()):
            return self.abort()
        self.state = self._body
        return self._body(token)

    def _body(self, token):
        # What is not a tag or an expression is text, not code: its words,
        # brackets and quotes are not tokens.
        if token == '=>':
            return self.abort()

        if token == "<":
            self.sub_tokenizer = XMLTagWithAttrTokenizer()
            self.cache.pop()
            return self.flush()

        if _is_opening_tag(token):
            # A tag without attributes inside this one: the closing tag
            # that follows is its own
            self.sub_tokenizer = XMLTagWithAttrTokenizer(token)
            self.cache.pop()
            return self.flush()

        if token.startswith("</"):
            self.stop()
            return self.flush()

        if token == '{':
            # The braces around an expression are not tokens: the closing
            # one is taken by the tokenizer of the expression, and the
            # opening one alone would be a brace of the code.
            self.sub_tokenizer = TSXTokenizer()
            self.cache.pop()
            return self.flush()


def isidentifier(token):
    try:
        return token.isidentifier()
    except AttributeError:
        return token.encode(encoding='UTF-8')[0].isalpha()
