'''
Language parser for Rust lang
'''

from .code_reader import CodeReader, CodeStateMachine
from .clike import CCppCommentsMixin
from .golike import GoLikeStates


class RustReader(CodeReader, CCppCommentsMixin):
    # pylint: disable=R0903

    ext = ['rs']
    language_names = ['rust']

    # Separated condition categories
    _control_flow_keywords = {'if', 'for', 'while', 'loop', 'catch', 'where'}
    _logical_operators = {'&&', '||'}
    _case_keywords = set()  # Rust match arms are counted via `=>` in RustStates
    # Note: '?' in Rust is the error propagation operator, not ternary
    _ternary_operators = {'?'}

    def __init__(self, context):
        super().__init__(context)
        self.parallel_states = [RustStates(context),
                                RustClosureStates(context)]

    @staticmethod
    def generate_tokens(source_code, addition='', token_class=None):
        addition = r"|(?:'\w+\b)"  # lifetimes, labels
        return CodeReader.generate_tokens(source_code, addition, token_class)


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


class RustClosureStates(CodeStateMachine):  # pylint: disable=R0903
    '''"||" is the logical operator after an operand, and the empty
    parameter list of a closure anywhere else: "run(|| 0)", "move || 1".'''

    _keywords_before_closure = ('move', 'return', 'in', 'async', 'static',
                                'break', 'else')

    def _state_global(self, token):
        if token == '||' and not self._after_operand():
            self.context.add_condition(-1)

    def _after_operand(self):
        last = self.last_token
        if last is None or last in self._keywords_before_closure:
            return False
        return last[-1].isalnum() or last[-1] in '_)]}?"\''
