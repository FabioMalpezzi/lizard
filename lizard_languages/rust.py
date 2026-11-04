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
        # lifetimes, labels; with a closing quote it is a char literal: 'a'
        addition = r"|(?:'\w+\b(?!'))"
        # raw strings r"..", r#".."#, with up to three "#", and r#name
        addition += r'|b?r"[^"]*"' + ''.join(
            r'|b?r%s"(?:[^"]|"(?!%s))*"%s' % (hashes, hashes, hashes)
            for hashes in ('###', '##', '#')) + r"|r\#\w+"
        addition += r"|\.\.\.|\.\.=|\.\."  # ranges: one token each
        addition += r"|\d\w*\.\d\w*(?:[eE][-+]?\d\w*)?"  # 1.5, 2.0e-3, 1.0f64
        addition += r"|\*=|/=|%="
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
    PARAMETER_BRACKETS = {'[': ']', '{': '}', '<': '>'}

    # a "{" after one of these opens a block that is part of an expression
    _BLOCK_KEYWORDS = ('unsafe', 'else', 'loop', 'async', 'move', 'const',
                       '!')
    # each of these is followed by an expression and then by a block
    _KEYWORDS_BEFORE_BLOCK = ('if', 'while', 'for', 'match')

    def __init__(self, context, in_match_arms=False):
        super().__init__(context)
        self._in_match_arms = in_match_arms
        self._seen_match_arm = False
        self._match_subject_nesting = 0
        self._match_subject_blocks = 0
        # Paren depth of each `if` still waiting for its body, innermost last.
        self._if_body_depths = []
        self._else_pending = False
        self._paren_depth = 0
        self._result_brackets = 0

    def _state_global(self, token):
        if token == '=>':
            if self._in_match_arms:
                if self._seen_match_arm:
                    self.context.add_condition()
                self._seen_match_arm = True
            return
        if token == 'match':
            self._match_subject_nesting = 0
            self._match_subject_blocks = 0
            self._state = self._match_subject
            return
        if self._count_let_else(token):
            return
        if token == self.FUNC_KEYWORD:
            self._result_brackets = 0
        super()._state_global(token)

    def _function_name(self, token):
        if token == '(':
            # "fn(i32) -> i32" is the type of a field or a variable: a
            # function pointer, without a name and without a body.
            self._forget_function()
            self.next(self._state_global, token)
        else:
            super()._function_name(token)

    def _expect_function_impl(self, token):
        if token in ('(', '['):
            self._result_brackets += 1
        elif token in (')', ']'):
            self._result_brackets -= 1
        elif token in (';', '}') and not self._result_brackets:
            # A declaration without a body, as in a trait:
            # "fn area(&self) -> f64;"
            self._forget_function()
            self.next(self._state_global, token)
            return
        super()._expect_function_impl(token)

    def _forget_function(self):
        """What was counted for a function that has no body belongs to
        the function around it."""
        without_body = self.context.current_function
        around = self.context.stacked_functions.pop()
        # A new function starts with its first token and line counted.
        around.token_count += without_body.token_count - 1
        around.nloc += without_body.nloc - 1
        around.cyclomatic_complexity += without_body.cyclomatic_complexity - 1
        around.end_line = max(around.end_line, without_body.end_line)
        self.context.current_function = around

    def _count_let_else(self, token):
        """Count `let ... else`. The `else` of an `if` is not another condition.

        Brace bodies are separate state machines, so an `if` and its `else`
        are both seen here with the body omitted. The body is the `{` that
        returns to the parenthesis depth where that `if` began.
        """
        if token != 'else':
            self._else_pending = False
        if token in '([':
            self._paren_depth += 1
        elif token in ')]' and self._paren_depth:
            self._paren_depth -= 1
        if token == 'else':
            if not self._else_pending:
                self.context.add_condition()
            self._else_pending = False
            return True
        if token == 'if':
            self._if_body_depths.append(self._paren_depth)
            return False
        if (token == '{' and self._if_body_depths
                and self._paren_depth == self._if_body_depths[-1]):
            self._if_body_depths.pop()
            self.sub_state(self.statemachine_clone(), self._if_body_closed)
            return True
        return False

    def _if_body_closed(self):
        self._else_pending = True

    def _match_subject(self, token):
        if token in ('(', '['):
            self._match_subject_nesting += 1
        elif token in (')', ']', '}', ';') and not self._match_subject_nesting:
            # No arms: a "match" between the tokens of a macro, as in
            # quote! { f(#(match #args #body),*) }
            self.next(self._state_global, token)
        elif token in (')', ']', '}'):
            self._match_subject_nesting -= 1
        elif token == '{':
            if self._match_subject_nesting or \
                    self.last_token in self._BLOCK_KEYWORDS:
                # a block inside the subject: match unsafe { f() } { .. }
                self._match_subject_nesting += 1
            elif self._match_subject_blocks:
                # the block of an "if" of the subject:
                # match if a { 1 } else { 2 } { .. }
                self._match_subject_blocks -= 1
                self._match_subject_nesting += 1
            else:
                self.sub_state(
                    RustStates(self.context, in_match_arms=True),
                    self._end_match)
        elif token in self._KEYWORDS_BEFORE_BLOCK and \
                not self._match_subject_nesting:
            self._match_subject_blocks += 1

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
