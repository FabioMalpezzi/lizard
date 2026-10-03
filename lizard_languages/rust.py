'''
Language parser for Rust lang
'''

from .code_reader import CodeReader
from .clike import CCppCommentsMixin
from .golike import GoLikeStates


class RustReader(CodeReader, CCppCommentsMixin):
    # pylint: disable=R0903

    ext = ['rs']
    language_names = ['rust']

    # Separated condition categories
    _control_flow_keywords = {'if', 'for', 'while', 'catch', 'where'}
    _logical_operators = {'&&', '||'}
    _case_keywords = set()  # Rust match arms are counted via `=>` in RustStates
    # Note: '?' in Rust is the error propagation operator, not ternary
    _ternary_operators = {'?'}

    def __init__(self, context):
        super().__init__(context)
        self.parallel_states = [RustStates(context)]

    @staticmethod
    def generate_tokens(source_code, addition='', token_class=None):
        # lifetimes, labels; with a closing quote it is a char literal: 'a'
        addition = r"|(?:'\w+\b(?!'))"
        # raw strings r"..", r#".."#, with up to three "#", and r#name
        addition += r'|b?r"[^"]*"' + ''.join(
            r'|b?r%s"(?:[^"]|"(?!%s))*"%s' % (hashes, hashes, hashes)
            for hashes in ('###', '##', '#')) + r"|r\#\w+"
        addition += r"|\.\.\.|\.\.=|\.\."  # ranges: one token each
        addition += r"|\d\w*\.\d\w*(?:[eE][-+]?\d\w*)?"  # 1.5, 2.0e-3, 1.0f64
        while source_code:
            offset = 0
            rest = ''
            for token in CodeReader.generate_tokens(
                    source_code, addition, token_class):
                if token.startswith('/*'):
                    end = _end_of_block_comment(source_code, offset)
                    if end != offset + len(token):
                        # Block comments nest in Rust: the common pattern
                        # stopped at the first "*/". Give the whole comment
                        # and read again from its real end.
                        yield source_code[offset:end]
                        rest = source_code[end:]
                        break
                elif token.startswith('#') and len(token) > 1:
                    # The common tokenizer reads "#" and the rest of the
                    # line as a C macro. In Rust "#" starts an attribute,
                    # or is a token of a macro: read again what follows.
                    yield '#'
                    rest = source_code[offset + 1:]
                    break
                offset += len(token)
                yield token
            source_code = rest


def _end_of_block_comment(source_code, start):
    depth = 0
    index = start
    while index < len(source_code):
        if source_code.startswith('/*', index):
            depth += 1
            index += 2
        elif source_code.startswith('*/', index):
            depth -= 1
            index += 2
            if depth == 0:
                return index
        else:
            index += 1
    return len(source_code)


class RustStates(GoLikeStates):  # pylint: disable=R0903
    FUNC_KEYWORD = 'fn'

    def __init__(self, context, in_match_arms=False):
        super().__init__(context)
        self._in_match_arms = in_match_arms
        self._seen_match_arm = False
        self._match_subject_nesting = 0

    def _state_global(self, token):
        if token == '=>':
            if self._in_match_arms:
                if self._seen_match_arm:
                    self.context.add_condition()
                self._seen_match_arm = True
            return
        if token == 'match':
            self._match_subject_nesting = 0
            self._state = self._match_subject
            return
        super()._state_global(token)

    def _match_subject(self, token):
        if token in '([':
            self._match_subject_nesting += 1
            return
        if token in ')]':
            if self._match_subject_nesting:
                self._match_subject_nesting -= 1
            return
        if token != '{' or self._match_subject_nesting:
            return
        self.sub_state(
            RustStates(self.context, in_match_arms=True),
            self._end_match)

    def _end_match(self):
        self.next(self._state_global)
