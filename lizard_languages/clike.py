'''
Language parser for C, C++ -like languages.
'''

import re
import itertools
from .code_reader import CodeStateMachine, CodeReader
from .clike_states import CLikeStates

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

    ext = ["c", "cpp", "cc", "cxx", "h", "hh", "hpp"]
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
    _TYPE_KEYWORDS = ("struct", "class", "namespace", "union")

    def _state_global(self, token):
        """Dual-purpose state for global and structure bodies."""
        if token == "template":
            self._state = self._template_declaration
        elif token == ".":
            self._state = self._dot
        elif token in self._TYPE_KEYWORDS:
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
