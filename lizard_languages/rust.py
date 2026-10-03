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
    _control_flow_keywords = {'if', 'for', 'while', 'loop', 'catch', 'match', 'where'}
    _logical_operators = {'&&', '||'}
    _case_keywords = set()  # Rust uses match arms, not case keyword
    # Note: '?' in Rust is the error propagation operator, not ternary
    _ternary_operators = {'?'}

    def __init__(self, context):
        super().__init__(context)
        self.parallel_states = [RustStates(context)]

    @staticmethod
    def generate_tokens(source_code, addition='', token_class=None):
        # lifetimes, labels; with a closing quote it is a char literal: 'a'
        addition = r"|(?:'\w+\b(?!'))"
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
