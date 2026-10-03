'''
Language parser for C, C++ -like languages.
'''

import re
import itertools
from .code_reader import CodeStateMachine, CodeReader

# Tokenizer fragment for C++ empty-delimiter raw strings R"(...)" (optional u8/u/U/L
# prefix). Stops at the first ')"'. Custom delimiters use the normal string rule.
# See #451, #478; subgroup-free per CodeReader.generate_tokens.
_CPP_RAW_STRING_TOKEN = r"|(?:u8|u|U|L)?R\"\((?:[^)]|\)(?!\"))*\)\""


class CCppCommentsMixin(object):  # pylint: disable=R0903

    @staticmethod
    def get_comment_from_token(token):
        if token.startswith("/*") or token.startswith("//"):
            return token[2:]


# pylint: disable=R0903
class CLikeReader(CodeReader, CCppCommentsMixin):
    ''' This is the reader for C, C++ and Java. '''

    ext = ["c", "cpp", "cc", "cxx", "h", "hpp"]
    language_names = ['cpp', 'c']
    macro_pattern = re.compile(r"#\s*(\w+)\s*(.*)", re.M | re.S)

    def __init__(self, context):
        super(CLikeReader, self).__init__(context)
        self.parallel_states = (
                CLikeStates(context),
                CLikeNestingStackStates(context),
                CppRValueRefStates(context))

    @staticmethod
    def generate_tokens(source_code, addition='', token_class=None):
        addition = _CPP_RAW_STRING_TOKEN + \
                  r"|(?:\d*\.\d+(?:[eE][-+]?\d+)?)" + \
                  r"|(?:\d+\.(?:\d+)?(?:[eE][-+]?\d+)?)" + \
                  addition
        return CodeReader.generate_tokens(source_code, addition, token_class)

    def preprocess(self, tokens):
        tilde = False
        for token, skipped in _ConditionalBranches(tokens, self.macro_pattern):
            if skipped and not token.startswith('#'):
                for _ in range(token.count('\n')):
                    yield '\n'
            elif token == '~':
                tilde = True
            elif tilde:
                tilde = False
                yield "~" + token
            elif not token.isspace() or token == '\n':
                macro = self.macro_pattern.match(token)
                if macro:
                    if macro.group(1) in ('if', 'ifdef', 'elif'):
                        self.context.add_condition()
                    elif macro.group(1) == 'include' and not skipped:
                        yield "#include"
                        yield macro.group(2) or "\"\""
                    for _ in macro.group(2).split('\n')[1:]:
                        yield '\n'
                else:
                    yield token


class _ConditionalBranches(object):
    """Follows #if, #else and #endif and tells, for each token, whether it
    is in a branch that cannot be read after the ones before it.

    When the branches of a conditional each open a brace or a parenthesis
    that is closed once after the #endif, as in

        #ifdef A
          if (x > 3) {
        #else
          if (x > 5) {
        #endif

    reading them all leaves a bracket open for the rest of the file. Of
    the branches of a conditional that leave the brackets unbalanced only
    the first is read, or the second when the first is "#if 0". Balanced
    branches are all read, as before: they cannot open or close anything
    for the code that follows, whatever the other branches do.

    Whether a branch is balanced is known at its end, so a conditional is
    read up to its #endif before its tokens are passed on.
    """

    _brackets = {'{': (1, 0), '}': (-1, 0), '(': (0, 1), ')': (0, -1)}
    _if_0 = re.compile(r"#\s*if\s+0\s*(?://.*|/\*.*)?$", re.S)

    def __init__(self, tokens, macro_pattern):
        self._tokens = iter(tokens)
        self._macro_pattern = macro_pattern

    def __iter__(self):
        for token in self._tokens:
            if self._directive(token) in ('if', 'ifdef', 'ifndef'):
                for item in self._conditional(token)[0]:
                    yield item
            else:
                yield token, False

    def _directive(self, token):
        if token.startswith('#'):
            macro = self._macro_pattern.match(token)
            if macro:
                return macro.group(1)
        return None

    def _conditional(self, opening):
        """Returns the tokens from "opening" to its #endif, each with
        True if it is skipped, and the brackets left open by them."""
        items = [(opening, False)]
        left_open = (0, 0)
        dead = self._if_0.match(opening)
        while True:
            branch, unbalance, closing = self._branch()
            if unbalance == (0, 0):
                items.extend(branch)
            elif dead or left_open != (0, 0):
                items.extend((token, True) for token, _ in branch)
            else:
                items.extend(branch)
                left_open = unbalance
            dead = False
            if closing is None:
                break
            items.append((closing, False))
            if self._directive(closing) == 'endif':
                break
        return items, left_open

    def _branch(self):
        """Returns the tokens up to the next #else, #elif or #endif of
        this conditional, the brackets they leave open and that
        directive, or None at the end of the file."""
        items = []
        braces = parentheses = 0
        for token in self._tokens:
            directive = self._directive(token)
            if directive in ('if', 'ifdef', 'ifndef'):
                nested, unbalance = self._conditional(token)
                items.extend(nested)
            elif directive in ('else', 'elif', 'endif'):
                return items, (braces, parentheses), token
            else:
                items.append((token, False))
                unbalance = self._brackets.get(token, (0, 0))
            braces += unbalance[0]
            parentheses += unbalance[1]
        return items, (braces, parentheses), None


class CppRValueRefStates(CodeStateMachine):
    # pylint: disable=R0903

    def _state_global(self, token):
        if token == "&&":
            self.next(self._r_value_ref)
        elif token == "typedef":
            self.next(self._typedef)

    @CodeStateMachine.read_until_then('=;{})')
    def _r_value_ref(self, token, _):
        if token == "=":
            self.context.add_condition(-1)
        self.next(self._state_global)

    @CodeStateMachine.read_until_then(';')
    def _typedef(self, _, tokens):
        self.context.add_condition(-tokens.count("&&"))
        self.next(self._state_global)


# pylint: disable=R0903
class CLikeNestingStackStates(CodeStateMachine):
    """Machinery to track nesting levels of tokens.

    The main indicators of nesting are braces: '{' and '}'.
    However, the code is complicated due to braceless structures,
    which are control-flow structures in C-like languages.
    Moreover, using braces as nesting level indicators leads to a big caveat;
    C++ initializer lists, uniform initialization,
    and any other constructs with braces add extra nesting level.

    Another complication comes from nested classes inside function bodies
    and control-flow declarations/bodies.
    The handling of these complex cases is unspecified and can be ignored.
    """

    __namespace_separators = ['<', ":", "final", "[", "extends", 'implements']

    def _state_global(self, token):
        """Dual-purpose state for global and structure bodies."""
        if token == "template":
            self._state = self._template_declaration
        elif token == ".":
            self._state = self._dot
        elif token in ("struct", "class", "namespace", "union"):
            self._state = self._read_namespace
        elif token == "{":
            self.context.add_bare_nesting()
        elif token == '}':
            self.context.pop_nesting()

    def _dot(self, _):
        self._state = self._state_global

    def _read_namespace(self, token):
        """Processes declarations right after namespace/class keywords."""
        if token == "[":
            self._state = self._read_attribute
        else:
            self._state = self._read_namespace_name
        self._state(token)

    @CodeStateMachine.read_until_then(')({;')
    def _read_namespace_name(self, token, saved):
        """Processes namespace/class/struct names from declarations."""
        self._state = self._state_global
        if token == "{":
            self.context.add_namespace(''.join(itertools.takewhile(
                lambda x: x not in self.__namespace_separators, saved)))

    @CodeStateMachine.read_inside_brackets_then("<>", "_state_global")
    def _template_declaration(self, _):
        """Ignores template parameters."""
        pass

    @CodeStateMachine.read_inside_brackets_then("[]", "_read_namespace")
    def _read_attribute(self, _):
        """Ignores C++11 attributes inside [[ ]]."""
        pass


# pylint: disable=R0903
class CLikeStates(CodeStateMachine):
    ''' This is the reader for C, C++ and Java. '''
    parameter_bracket_open = '(<'
    parameter_bracket_close = ')>'

    def __init__(self, context):
        super(CLikeStates, self).__init__(context)
        self.bracket_stack = []
        self._saved_tokens = []

    def try_new_function(self, name):
        self.context.try_new_function(name)
        self._state = self._state_function
        if name == 'operator':
            self._state = self._state_operator

    def _state_global(self, token):
        if token[0].isalpha() or token[0] in '_~':
            self.try_new_function(token)
        elif token == '[':
            # Check if this might be a lambda expression (C++ only)
            # Java doesn't have lambda expressions, so skip lambda detection for Java
            if not hasattr(self, 'class_name'):  # JavaStates has class_name attribute
                self._state = self._state_lambda_check

    def _state_function(self, token):
        if token == '(':
            self.next(self._state_dec, token)
        elif token == '::':
            self.context.add_to_function_name(token)
            self.next(self._state_name_with_space)
        elif token == '<':
            self.next(self._state_template_in_name, token)
        else:
            self.next(self._state_global, token)

    @CodeStateMachine.read_inside_brackets_then("<>", "_state_function")
    def _state_template_in_name(self, token):
        self.context.add_to_function_name(token)

    def _state_operator(self, token):
        if token != '(':
            self._state = self._state_operator_next
        self.context.add_to_function_name(' ' + token)

    def _state_operator_next(self, token):
        if token == '(':
            self._state_function(token)
        else:
            self.context.add_to_function_name(' ' + token)

    def _state_name_with_space(self, token):
        self._state = self._state_operator \
            if token == 'operator' else self._state_function
        self.context.add_to_function_name(token)

    @CodeStateMachine.read_inside_brackets_then("()", "_state_dec_to_imp")
    def _state_dec(self, token):
        if token in self.parameter_bracket_open:
            self.bracket_stack.append(token)
        elif token in self.parameter_bracket_close:
            if self.bracket_stack:
                self.bracket_stack.pop()
            else:
                self.next(self._state_global)
        elif len(self.bracket_stack) == 1:
            if token != 'void':  # void is a reserved keyword, meaning no parameters
                self.context.parameter(token)
            return
        self.context.add_to_long_function_name(token)

    def _state_dec_to_imp(self, token):
        if token in ('const', '&', '&&'):
            self.context.add_to_long_function_name(" " + token)
        elif token == 'throw':
            self._state = self._state_throw
        elif token == 'throws':
            self._state = self._state_throws
        elif token == '->':
            self._state = self._state_trailing_return
        elif token == 'noexcept':
            self._state = self._state_noexcept
        elif token == '(':
            long_name = self.context.current_function.long_name
            self.try_new_function(long_name)
            self._state_function(token)
        elif token == '{':
            self.next(self._state_entering_imp, "{")
        elif token == ":":
            self._state = self._state_initialization_list
        elif token == "[":
            self._state = self._state_attribute
            self._state(token)
        elif not (token[0].isalpha() or token[0] == '_'):
            self._state = self._state_global
            self._state(token)
        else:
            self._state = self._state_old_c_params
            self._saved_tokens = [token]

    @CodeStateMachine.read_inside_brackets_then("()")
    def _state_throw(self, _):
        self._state = self._state_dec_to_imp

    @CodeStateMachine.read_until_then(';{')
    def _state_throws(self, token, _):
        self._state = self._state_dec_to_imp
        self._state(token)

    def _state_noexcept(self, token):
        if token == '(':
            self._state = self._state_throw
        else:
            self._state = self._state_dec_to_imp
        self._state(token)

    @CodeStateMachine.read_until_then(';{')
    def _state_trailing_return(self, token, _):
        self._state = self._state_dec_to_imp
        self._state(token)

    def _state_old_c_params(self, token):
        self._saved_tokens.append(token)
        if token == ';':
            self._saved_tokens = []
            self._state = self._state_dec_to_imp
        elif token == '{':
            if len(self._saved_tokens) == 2:
                self._saved_tokens = []
                self._state_dec_to_imp(token)
                return
            self._state = self._state_global
            for tkn in self._saved_tokens:
                self._state(tkn)
        elif token == '(':
            self._state = self._state_global
            for tkn in self._saved_tokens:
                self._state(tkn)

    def _state_initialization_list(self, token):
        self._state = self._state_one_initialization
        if token == '{':
            self.next(self._state_entering_imp, "{")

    @CodeStateMachine.read_until_then('({')
    def _state_one_initialization(self, token, _):
        if token == "(":
            self._state = self._state_initialization_value1
        else:
            self._state = self._state_initialization_value2
        self._state(token)

    @CodeStateMachine.read_inside_brackets_then("()")
    def _state_initialization_value1(self, _):
        self._state = self._state_initialization_list

    @CodeStateMachine.read_inside_brackets_then("{}")
    def _state_initialization_value2(self, _):
        self._state = self._state_initialization_list

    def _state_entering_imp(self, token):
        self.context.confirm_new_function()
        self.next(self._state_imp, token)

    @CodeStateMachine.read_inside_brackets_then("{}")
    def _state_imp(self, _):
        self._state = self._state_global

    @CodeStateMachine.read_inside_brackets_then("[]", "_state_dec_to_imp")
    def _state_attribute(self, _):
        "Ignores function attributes with C++11 syntax, i.e., [[ attribute ]]."
        pass

    def _state_lambda_check(self, token):
        """Check if this is a lambda expression or a function attribute."""
        if token == ']':
            # This is an empty capture list [](params)
            self._state = self._state_lambda_params
        elif token == '[':
            # This is a function attribute [[attribute]]
            self._state = self._state_attribute
        else:
            # This is a lambda with capture list [capture](params)
            self._state = self._state_lambda_capture

    def _state_lambda_params(self, token):
        """Handle lambda parameters and body."""
        if token == '(':
            # Start of parameter list
            self.bracket_stack.append('(')
            self._state = self._state_lambda_param_list
        else:
            # No parameters, check for body or go back to global
            self._state = self._state_lambda_body
            self._state(token)

    def _state_lambda_param_list(self, token):
        """Handle lambda parameter list with proper bracket tracking."""
        if token == '(':
            self.bracket_stack.append('(')
        elif token == ')':
            if self.bracket_stack and self.bracket_stack[-1] == '(':
                self.bracket_stack.pop()
                if not self.bracket_stack:
                    # End of parameter list, check for body
                    self._state = self._state_lambda_body
        elif token in ('<', '['):
            self.bracket_stack.append(token)
        elif token == '>' and self.bracket_stack and self.bracket_stack[-1] == '<':
            self.bracket_stack.pop()
        elif token == ']' and self.bracket_stack and self.bracket_stack[-1] == '[':
            self.bracket_stack.pop()

    def _state_lambda_body(self, token):
        """Handle lambda body and qualifiers."""
        if token == '{':
            # Start of lambda body
            self.bracket_stack.append('{')
            self._state = self._state_lambda_body_skip
        elif token in ('mutable', 'noexcept', 'constexpr', 'consteval'):
            # Lambda qualifiers, stay in this state
            pass
        elif token == '->':
            # Trailing return type, stay in this state until we find '{'
            pass
        elif token in (';', ',', ')'):
            # Lambda declaration ended, return to global
            self._state = self._state_global
            self._state(token)
        else:
            # Other tokens (type names, etc.) - stay in state
            pass

    def _state_lambda_body_skip(self, token):
        """Skip lambda body with proper brace tracking."""
        if token == '{':
            self.bracket_stack.append('{')
        elif token == '}':
            if self.bracket_stack and self.bracket_stack[-1] == '{':
                self.bracket_stack.pop()
                if not self.bracket_stack:
                    # End of lambda body
                    self._state = self._state_global

    def _state_lambda_capture(self, token):
        """Handle lambda capture list."""
        if token == ']':
            # End of capture list, now expect parameters
            self._state = self._state_lambda_params
        # Otherwise, continue in capture list
