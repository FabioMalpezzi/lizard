'''
Language parser for JavaScript
'''

from .typescript import TypeScriptReader, TypeScriptStates


class JavaScriptStates(TypeScriptStates):
    typed = False  # No type follows a colon: it is a label or a property


class JavaScriptReader(TypeScriptReader):
    # pylint: disable=R0903

    ext = ['js', 'cjs', 'mjs']
    language_names = ['javascript', 'js']

    def __init__(self, context):
        super(JavaScriptReader, self).__init__(context)
        self.parallel_states = [JavaScriptStates(context)]
