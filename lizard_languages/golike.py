'''
Language parser for Go lang
'''

from .code_reader import CodeStateMachine


class GoLikeStates(CodeStateMachine):  # pylint: disable=R0903

    FUNC_KEYWORD = 'func'
    # A function type ("var check func(int) bool") and a declaration
    # ("fn area(&self) -> f64;") have no body. A language sets here the
    # tokens that, outside the brackets of the result type, show that no
    # body follows; without them the next brace of the file is the body.
    TOKENS_AFTER_NO_BODY = ()
    # In Go the brace of the body is on the line where the signature ends.
    BODY_STARTS_ON_SIGNATURE_LINE = False

    def __init__(self, context):
        super(GoLikeStates, self).__init__(context)
        self._result_brackets = 0
        self._signature_line = None
        self._first_parentheses = []

    def _state_global(self, token):
        if token == self.FUNC_KEYWORD:
            self._state = self._function_name
            self._result_brackets = 0
            self._signature_line = None
            self._first_parentheses = []
            self.context.push_new_function('')
        elif token == 'type':
            self._state = self._type_definition
        elif token in '{':
            self.sub_state(self.statemachine_clone())
        elif token in '}':
            self.statemachine_return()

    def _type_definition(self, token):
        self._state = self._after_type_name

    def _after_type_name(self, token):
        if token == 'struct':
            self._state = self._struct_definition
        elif token == 'interface':
            self._state = self._interface_definition
        else:
            self._state = self._state_global

    @CodeStateMachine.read_inside_brackets_then("{}", "_state_global")
    def _struct_definition(self, tokens):
        pass

    @CodeStateMachine.read_inside_brackets_then("{}", "_state_global")
    def _interface_definition(self, tokens):
        pass

    def _function_name(self, token):
        if token != '`':
            if token == '(':
                if self.TOKENS_AFTER_NO_BODY and self._first_parentheses:
                    # Parentheses again: the results of a function without
                    # a name, as in "= func(a int) (int, error) {".
                    return self._function_without_name(token)
                if len(self.context.stacked_functions) > 0\
                        and self.context.stacked_functions[-1].name != '*global*':
                    return self.next(self._function_dec, token)
                else:
                    return self.next(self._member_function, token)
            if self.TOKENS_AFTER_NO_BODY and self._first_parentheses and (
                    token == self.FUNC_KEYWORD or
                    self._starts_another_line()):
                # A function type without a result, as in
                # "var hook func(a int)", and then something else.
                self._forget_function()
                return self.next(self._state_global, token)
            if self.TOKENS_AFTER_NO_BODY and not (
                    token[0].isalpha() or token[0] == '_'):
                # Not a name: a function without a name or a function type,
                # as in "= func(a int) *T {" and "[]func(int)".
                return self._function_without_name(token)
            if token == '{':
                return self.next(self._expect_function_impl, token)
            self.context.add_to_function_name(token)
            self._state = self._expect_function_dec

    def _function_without_name(self, token):
        """The first parentheses were read as the receiver of a method, and
        what followed as its name: they are the parameters and the result
        type of a function without a name, or of a function type."""
        function = self.context.current_function
        function.name = function.long_name = ''
        depth = 0
        for saved in self._first_parentheses:
            if saved == '(':
                depth += 1
            if depth == 1 and saved not in '()':
                self.context.parameter(saved)
            elif depth > 1:
                self.context.add_to_long_function_name(" " + saved)
            if saved == ')':
                depth -= 1
        self._first_parentheses = []
        self.next(self._expect_function_impl, token)

    def _expect_function_dec(self, token):
        if token == '(':
            self._first_parentheses = []
            self.next(self._function_dec, token)
        elif token in ('<', '['):
            # Skip type-parameter lists: Rust/Kotlin/Swift `foo<T>(...)`,
            # Go/Scala `foo[T](...)` / `foo[T any](...)`.
            self.next(self._skip_type_parameters, token)
        elif self.TOKENS_AFTER_NO_BODY:
            # No parameters after the name: it was the result type of a
            # function without a name, as in "= func(a int) bool {", or of
            # a function type, as in "var check func(int) bool".
            self._function_without_name(token)
        else:
            self._state = self._state_global

    def _skip_type_parameters(self, token):
        if self.br_count == 0:
            self._type_param_open = token
            self._type_param_close = '>' if token == '<' else ']'
        self.br_count += {
            self._type_param_open: 1,
            self._type_param_close: -1,
        }.get(token, 0)
        if self.br_count == 0:
            self.next(self._expect_function_dec)

    @CodeStateMachine.read_inside_brackets_then("()", '_function_name')
    def _member_function(self, tokens):
        self._signature_line = self.context.current_line
        self._first_parentheses.append(tokens)
        self.context.add_to_long_function_name(tokens)

    @CodeStateMachine.read_inside_brackets_then("()", '_expect_function_impl')
    def _function_dec(self, token):
        self._signature_line = self.context.current_line
        if token not in '()':
            self.context.parameter(token)

    def _starts_another_line(self):
        line, self._signature_line = self._signature_line, self.context.current_line
        return (self.BODY_STARTS_ON_SIGNATURE_LINE and
                line is not None and line != self.context.current_line)

    def _has_no_body(self, token):
        if not self.TOKENS_AFTER_NO_BODY:
            return False
        another_line = self._starts_another_line()
        if token in ('(', '[', '<'):
            self._result_brackets += 1
        elif token in (')', ']', '>'):
            self._result_brackets -= 1
            return self._result_brackets < 0
        elif self._result_brackets == 0:
            return token in self.TOKENS_AFTER_NO_BODY or another_line
        return False

    def _forget_function(self):
        """What was counted for a function that has no body belongs to
        the function around it."""
        without_body = self.context.current_function
        if self.context.stacked_functions:
            around = self.context.stacked_functions.pop()
            around.token_count += without_body.token_count - 1
            around.nloc += without_body.nloc - 1
            around.cyclomatic_complexity += without_body.cyclomatic_complexity - 1
            around.end_line = without_body.end_line
            self.context.current_function = around

    def _expect_function_impl(self, token):
        if self._has_no_body(token):
            self._forget_function()
            self.next(self._state_global, token)
        elif token == '{':
            if self.last_token in ('interface', 'struct'):
                # A result type written with braces, as in Go
                # "func f() map[string]struct{} {": not the body.
                self.next(self._result_type_braces, token)
            else:
                self.next(self._function_impl, token)

    @CodeStateMachine.read_inside_brackets_then("{}", "_expect_function_impl")
    def _result_type_braces(self, _):
        self._signature_line = self.context.current_line

    def _function_impl(self, _):
        def callback():
            self._state = self._state_global
            self.context.end_of_function()
        self.sub_state(self.statemachine_clone(), callback)
