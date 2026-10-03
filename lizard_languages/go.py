'''
Language parser for Go lang
'''

from .code_reader import CodeReader, CodeStateMachine
from .clike import CCppCommentsMixin
from .golike import GoLikeStates


class GoReader(CodeReader, CCppCommentsMixin):
    # pylint: disable=R0903

    ext = ['go']
    language_names = ['go']

    def __init__(self, context):
        super(GoReader, self).__init__(context)
        self.parallel_states = [GoStates(context)]

    @staticmethod
    def generate_tokens(source_code, addition='', token_class=None):
        addition = addition + r"|`[^`]*`"  # Add support for backtick-quoted strings
        addition = addition + r"|<-"  # The receive operator is one token
        return CodeReader.generate_tokens(source_code, addition, token_class)

    def __call__(self, tokens, reader):
        self.context = reader.context
        for token in tokens:
            # Skip counting ? in backtick-quoted strings
            if token.startswith('`') and token.endswith('`'):
                for state in self.parallel_states:
                    state(token)
                yield token
                continue

            # For non-backtick tokens, process normally
            for state in self.parallel_states:
                state(token)
            yield token
        for state in self.parallel_states:
            state.statemachine_before_return()
        self.eof()


class GoStates(GoLikeStates):  # pylint: disable=R0903
    TOKENS_AFTER_NO_BODY = ('}', ';', '=')
    BODY_STARTS_ON_SIGNATURE_LINE = True
    PARAMETER_BRACKETS = {'[': ']', '{': '}'}

    def __init__(self, context):
        super(GoStates, self).__init__(context)
        self._line_of_last_token = None

    def _state_global(self, token):
        line, self._line_of_last_token = (
            self._line_of_last_token, self.context.current_line)
        if token == 'type' and self.last_token == '(':
            return  # "switch v := x.(type) {" declares no type
        if token == 'func' and self.last_token in (']', ')') and (
                line == self.context.current_line):
            # A function type after a type: the elements of
            # "[]func(){a, b}", the result of "[]func() func(){a, b}".
            return
        super(GoStates, self)._state_global(token)

    def _after_type_name(self, token):
        if token == '[':
            # "type Set[T any] interface {": type parameters before the type
            self.next(self._type_brackets, token)
        elif token != '=':
            super(GoStates, self)._after_type_name(token)

    @CodeStateMachine.read_inside_brackets_then("[]", "_after_type_name")
    def _type_brackets(self, _):
        pass
