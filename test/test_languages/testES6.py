import unittest
from lizard import  analyze_file, FileAnalyzer, get_extensions
from lizard_languages import JavaScriptReader


def get_js_function_list(source_code):
    return analyze_file.analyze_source_code("a.js", source_code).function_list

class Test_tokenizing_ES6(unittest.TestCase):

    def check_tokens(self, expect, source):
        tokens = list(JavaScriptReader.generate_tokens(source))
        self.assertEqual(expect, tokens)

    def test_dollar_var(self):
        self.check_tokens(["`", "`abc\ndef`", "`"], """`abc\ndef`""")

    def test_tokenizing_string_with_formatter(self):
        self.check_tokens(['"${1}a"'], r'"${1}a"')

class Test_parser_for_JavaScript_ES6(unittest.TestCase):

    def test_simple_function(self):
        functions = get_js_function_list("x=>x")
        self.assertEqual("(anonymous)", functions[0].name)

    def test_two_functions(self):
        functions = get_js_function_list("""
            x=>x
            x=>x
        """)
        self.assertEqual(2, len(functions))

    def test_two_functions_with_semicolon(self):
        functions = get_js_function_list("""x=>x; x=>x;""")
        self.assertEqual(2, len(functions))

    def test_function_with_block(self):
        functions = get_js_function_list("""
            x=>{return 0;}
        """)
        self.assertEqual(1, len(functions))
        self.assertEqual("(anonymous)", functions[0].name)

    def test_complexity(self):
        functions = get_js_function_list("""
            x=>a && b
        """)
        self.assertEqual(2, functions[0].cyclomatic_complexity)

    def test_nested(self):
        functions = get_js_function_list("""
            function a(){x=>a;}
        """)
        self.assertEqual(2, len(functions))
        self.assertEqual('a', functions[1].name)

    def test_nested2(self):
        functions = get_js_function_list("""
            function a(){m.map(x=>a) && b}
        """)
        self.assertEqual('(anonymous)', functions[0].name)
        self.assertEqual(1, functions[0].cyclomatic_complexity)
        self.assertEqual(2, functions[1].cyclomatic_complexity)

    def test_nested3(self):
        functions = get_js_function_list("""
            function a(){x=>a}
        """)
        self.assertEqual(2, len(functions))
        self.assertEqual('a', functions[1].name)

    def test_nested_complexity(self):
        functions = get_js_function_list("""
            x=>{
                a&&b;
                b&&c;
                }
        """)
        self.assertEqual(3, functions[0].cyclomatic_complexity)

    def test_arraw_function_name(self):
        functions = get_js_function_list("""
            const x=a=>1
        """)
        self.assertEqual('x', functions[0].name)

    def test_arraw_function_with_multiple_param(self):
        functions = get_js_function_list("""
            const x=(a, b=3, {...x, y})=>1
        """)
        self.assertEqual('x', functions[0].name)

    def test_arrow_function_return_object(self):
        functions = get_js_function_list("""
            pairs = evens.map(v => ({ even: v, odd: v + 1 }))
        """)
        self.assertEqual(1, len(functions))

    def test_class(self):
        functions = get_js_function_list("""
            class A {
            f(){}
            m(){}
            }
        """)
        self.assertEqual(['f', 'm'], [f.name for f in functions])

    def test_class_with_prop_as_function(self):
        functions = get_js_function_list("""
            class A {
            f(){}
            m(){}
            g:(x,y)=>x+1
            h:function(){}
            get i(){return 1;}
            }
        """)
        self.assertEqual(['f', 'm', 'g', 'h', 'get i'], [f.name for f in functions])

    def test_generator_function(self):
        functions = get_js_function_list("""
            function* range() {yield 1}
        """)
        self.assertEqual(1, len(functions))
        self.assertEqual('range', functions[0].name)

    def test_generator_function_assign_to_name(self):
        functions = get_js_function_list("""
            range = function* () {yield 1}
        """)
        self.assertEqual(1, len(functions))
        self.assertEqual('range', functions[0].name)

    def test_statement_block(self):
        functions = get_js_function_list("""
            function a(e) {
                if (id == 'current') {
                    a() {}
                } else {
                    a() {}
                }
                do{ a() {} }while(x);
                switch(x){ a() {} }
                for(x){ a() {} }
                for await (x){ a() {} }
                while(x){ a() {} }
                try{
                    a(){}
                } catch (x) {
                    a() {}
                } final {
                    a() {}
                }
            }

        """)
        self.assertEqual(1, len(functions))
        self.assertEqual('a', functions[0].name)

    # TBD: Method Properties


class Test_ES6_unparenthesized_arrow_params(unittest.TestCase):
    """Tests class field arrows with unparenthesized single parameter."""

    def test_async_unparenthesized_arrow(self):
        """field = async x => {} should detect field and not break subsequent methods"""
        code = '''
        class Foo {
            before() { return 1; }
            handler = async x => { return x; };
            after() { return 2; }
        }
        '''
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        self.assertIn("before", names)
        self.assertIn("after", names)

    def test_unparenthesized_arrow_no_async(self):
        """field = x => {} should detect field and not break subsequent methods"""
        code = '''
        class Foo {
            before() { return 1; }
            transform = x => x * 2;
            after() { return 2; }
        }
        '''
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        self.assertIn("before", names)
        self.assertIn("after", names)

    def test_async_unparenthesized_arrow_complex_body(self):
        """async field arrow with complex body should not corrupt parser state"""
        code = '''
        class Service {
            extractRules() { return {}; }
            runExternal = async recordIds => {
                if (recordIds.length > 0) {
                    await this.doSomething();
                }
                return true;
            };
            runReset(record) {
                if (typeof this.reset === "function") { this.reset(record); }
            }
            get tableClass() { return "test"; }
            deleteRecord(isDeleted, itemIndex) {
                try { this.records.splice(itemIndex, 1); } catch (err) { console.error(err); }
            }
        }
        '''
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        self.assertIn("extractRules", names)
        self.assertIn("runReset", names)
        self.assertIn("get tableClass", names)
        self.assertIn("deleteRecord", names)
        self.assertNotIn("if", names)


class Test_ES6_dot_field_assignment(unittest.TestCase):
    """Tests that field = OBJ.PROP does not break subsequent method detection."""

    def test_dot_field_assignment(self):
        """field = A.B; should not swallow the next method"""
        code = 'class C { x = A.B; m1() {} m2() {} }'
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        self.assertIn("m1", names)
        self.assertIn("m2", names)

    def test_chained_dot_field_assignment(self):
        """field = A.B.C; should not swallow the next method"""
        code = 'class C { x = A.B.C; m1() {} m2() {} }'
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        self.assertIn("m1", names)
        self.assertIn("m2", names)

    def test_multiple_dot_field_assignments(self):
        """Multiple field = OBJ.PROP should not swallow methods"""
        code = '''
        class C {
            x = A.B;
            y = C.D;
            m1() { return 1; }
            m2() { return 2; }
        }
        '''
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        self.assertIn("m1", names)
        self.assertIn("m2", names)


class Test_ES6_destructuring_params(unittest.TestCase):
    """Tests arrow functions with destructuring parameters."""

    def test_object_destructuring(self):
        functions = get_js_function_list("const process = ({name, age}) => name + age;")
        self.assertEqual(["process"], [f.name for f in functions])

    def test_array_destructuring(self):
        functions = get_js_function_list("const first = ([head, ...tail]) => head;")
        self.assertEqual(["first"], [f.name for f in functions])

    def test_nested_destructuring(self):
        code = '''
        const extract = ({user: {name, address: {city}}}) => {
            return name + " from " + city;
        }
        '''
        functions = get_js_function_list(code)
        self.assertEqual(["extract"], [f.name for f in functions])

    def test_default_values_in_destructuring(self):
        code = '''
        const configure = ({host = "localhost", port = 3000, debug = false}) => {
            return {host, port, debug};
        }
        '''
        functions = get_js_function_list(code)
        self.assertEqual(["configure"], [f.name for f in functions])


class Test_ES6_default_params(unittest.TestCase):
    """Tests arrow functions with default parameters."""

    def test_default_params(self):
        code = 'const greet = (name = "world", greeting = "Hello") => greeting + " " + name;'
        functions = get_js_function_list(code)
        self.assertEqual(["greet"], [f.name for f in functions])

    def test_default_param_function(self):
        code = '''
        function createEl(tag = "div", content = "") {
            const el = document.createElement(tag);
            el.textContent = content;
            return el;
        }
        '''
        functions = get_js_function_list(code)
        self.assertEqual(["createEl"], [f.name for f in functions])


class Test_ES6_class_field_arrows(unittest.TestCase):
    """Tests class field arrow functions."""

    def test_class_arrow_fields(self):
        """Arrow functions as class fields should use the field name"""
        code = '''
        class Btn {
            handleClick = () => { this.setState({clicked: true}); };
            handleHover = (e) => { console.log(e); };
            render() { return null; }
        }
        '''
        functions = get_js_function_list(code)
        self.assertEqual(
            ["handleClick", "handleHover", "render"],
            [f.name for f in functions])

    def test_class_field_then_method(self):
        """Regular class method after arrow field should be detected"""
        code = '''
        class Timer {
            tick = () => { this.count++; };
            reset() { this.count = 0; }
            getCount() { return this.count; }
        }
        '''
        functions = get_js_function_list(code)
        self.assertEqual(
            ["tick", "reset", "getCount"],
            [f.name for f in functions])

    def test_field_arrow_with_params(self):
        """Field arrow with parameters should use the field name"""
        code = '''
        class EventBus {
            emit = (event, data) => { this.listeners[event](data); };
            on = (event, cb) => { this.listeners[event] = cb; };
        }
        '''
        functions = get_js_function_list(code)
        self.assertEqual(
            ["emit", "on"],
            [f.name for f in functions])

    def test_field_arrow_block_body(self):
        """Field arrow with block body and complexity"""
        code = '''
        class Validator {
            validate = (value) => {
                if (!value) return false;
                if (value.length < 3) return false;
                return true;
            };
        }
        '''
        functions = get_js_function_list(code)
        self.assertEqual(["validate"], [f.name for f in functions])
        self.assertGreater(functions[0].cyclomatic_complexity, 1)


class Test_ES6_optional_chaining_no_fp(unittest.TestCase):
    """Tests that optional chaining does not produce false positives."""

    def test_optional_chain_call(self):
        """obj?.method() should not produce FP for method"""
        code = '''
        function safe(obj) {
            return obj?.method();
        }
        '''
        functions = get_js_function_list(code)
        self.assertEqual(["safe"], [f.name for f in functions])

    def test_nullish_coalescing(self):
        """Nullish coalescing should not produce FP"""
        code = '''
        function getVal(cfg) {
            const val = cfg?.setting ?? "default";
            return val;
        }
        '''
        functions = get_js_function_list(code)
        self.assertEqual(["getVal"], [f.name for f in functions])


class Test_ES6_private_class_fields(unittest.TestCase):
    """Tests private class field methods."""

    def test_private_field_methods(self):
        code = '''
        class Counter {
            #count = 0;
            increment() { this.#count++; }
            getCount() { return this.#count; }
        }
        '''
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        self.assertIn("increment", names)
        self.assertIn("getCount", names)


class Test_ES6_computed_property_methods(unittest.TestCase):
    """Tests computed property name methods."""

    def test_computed_key_methods(self):
        code = '''
        const key = "method";
        const obj = {
            [key]() { return 1; },
            ["static" + "Key"]() { return 2; }
        };
        '''
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        self.assertIn("key", names)
        self.assertIn("staticKey", names)

    def test_symbol_iterator(self):
        code = '''
        class Iterable {
            [Symbol.iterator]() {
                let i = 0;
                return { next: () => ({value: i++, done: i > 10}) };
            }
        }
        '''
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        self.assertIn("symbol.iterator", names)


class Test_ES6_for_loops_with_functions(unittest.TestCase):
    """Tests function detection inside for loops."""

    def test_for_of_body(self):
        code = '''
        function processAll(items) {
            for (const item of items) {
                if (item.active) { handle(item); }
            }
        }
        '''
        functions = get_js_function_list(code)
        self.assertEqual(["processAll"], [f.name for f in functions])

    def test_forEach_callback(self):
        code = '''
        function logAll(items) {
            items.forEach((item) => {
                console.log(item.name);
            });
        }
        '''
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        self.assertIn("logAll", names)
        self.assertIn("(anonymous)", names)


class Test_ES6_multiple_arrow_patterns(unittest.TestCase):
    """Tests various arrow function declaration patterns."""

    def test_arrow_returning_object(self):
        """Arrow returning object literal in parens"""
        code = "const make = (x) => ({value: x, label: String(x)});"
        functions = get_js_function_list(code)
        self.assertEqual(["make"], [f.name for f in functions])

    def test_chained_arrow_filter_map(self):
        """Filter + map chain with arrow callbacks"""
        code = '''
        const result = items
            .filter(x => x > 0)
            .map(x => x * 2);
        '''
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        anon_count = sum(1 for n in names if n == "(anonymous)")
        self.assertEqual(2, anon_count)

    def test_nested_arrows(self):
        """Curried function pattern — outer arrow detected"""
        code = '''
        const add = (a) => (b) => a + b;
        '''
        functions = get_js_function_list(code)
        names = [f.name for f in functions]
        self.assertIn("add", names)
        # Expression-body arrow: inner (b) => a + b is the body expression,
        # only the outer arrow is detected as a function
        self.assertEqual(1, len(functions))

    def test_arrow_with_block_and_return(self):
        """Arrow with block body and explicit return"""
        code = '''
        const validate = (value) => {
            if (!value) return false;
            if (value.length < 3) return false;
            return true;
        };
        '''
        functions = get_js_function_list(code)
        self.assertEqual(["validate"], [f.name for f in functions])
        self.assertGreater(functions[0].cyclomatic_complexity, 1)


def function_summary(functions):
    return [(f.name, f.start_line, f.end_line, f.cyclomatic_complexity)
            for f in functions]


class Test_ES6_parenthesized_expressions(unittest.TestCase):
    """A parenthesized expression is not the parameter list of a function."""

    def test_conditions_in_a_parenthesized_expression(self):
        code = (
            "function f(a, b) {\n"
            "  const ok = (a && b) || a;\n"
            "  return ok;\n"
            "}\n"
        )
        self.assertEqual([('f', 1, 4, 3)],
                         function_summary(get_js_function_list(code)))

    def test_function_end_after_a_parenthesized_expression_with_calls(self):
        code = (
            "async function a(x) {\n"
            "  const y = (await (await f(x)).json()).z;\n"
            "  if (y) {\n"
            "    return 1;\n"
            "  }\n"
            "  return 0;\n"
            "}\n"
            "function b() { return 1; }\n"
        )
        self.assertEqual([('a', 1, 7, 2), ('b', 8, 8, 1)],
                         function_summary(get_js_function_list(code)))

    def test_function_end_after_a_parenthesized_product(self):
        code = (
            "function m(x) {\n"
            "  const total = (x.a + f(x.b)) * 2;\n"
            "  return total;\n"
            "}\n"
            "function n(x) { return x; }\n"
        )
        self.assertEqual([('m', 1, 4, 1), ('n', 5, 5, 1)],
                         function_summary(get_js_function_list(code)))

    def test_immediately_invoked_arrow_function(self):
        code = (
            "const r = (() => {\n"
            "  if (a) { return 1; }\n"
            "  return 2;\n"
            "})();\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual([('(anonymous)', 1, 4, 2), ('after', 5, 5, 1)],
                         function_summary(get_js_function_list(code)))

    def test_class_field_with_nested_calls(self):
        code = (
            "class K {\n"
            "  x = f(g(1));\n"
            "  m1() { return 1; }\n"
            "  y = (a && b);\n"
            "  m2() { return 2; }\n"
            "}\n"
        )
        self.assertEqual([('m1', 3, 3, 1), ('m2', 5, 5, 1)],
                         function_summary(get_js_function_list(code)))

    def test_class_field_with_an_immediately_invoked_arrow_function(self):
        code = (
            "class K {\n"
            "  y = (() => { if (a) { return 1; } return 2; })();\n"
            "  m() { return 2; }\n"
            "}\n"
        )
        self.assertEqual([('(anonymous)', 2, 2, 2), ('m', 3, 3, 1)],
                         function_summary(get_js_function_list(code)))


class Test_ES6_arrow_function_parameters(unittest.TestCase):

    def parameter_counts(self, code):
        return [(f.name, f.parameter_count) for f in get_js_function_list(code)]

    def test_anonymous_arrow_function_as_an_argument(self):
        code = "const r = list.map((x, i) => x + i);"
        self.assertEqual([('(anonymous)', 2)], self.parameter_counts(code))

    def test_anonymous_arrow_function_with_a_block(self):
        code = "const r = list.filter((x) => { return x; });"
        self.assertEqual([('(anonymous)', 1)], self.parameter_counts(code))

    def test_anonymous_arrow_function_without_parameters(self):
        code = "setTimeout(() => { done(); }, 10);"
        self.assertEqual([('(anonymous)', 0)], self.parameter_counts(code))

    def test_arrow_function_without_parentheses(self):
        code = "const f = x => { return x; };"
        self.assertEqual([('f', 1)], self.parameter_counts(code))

    def test_anonymous_arrow_function_without_parentheses(self):
        code = "const r = list.map(x => x * 2);"
        self.assertEqual([('(anonymous)', 1)], self.parameter_counts(code))

    def test_async_arrow_function_without_parentheses(self):
        code = "const f = async x => { return x; };"
        self.assertEqual([('f', 1)], self.parameter_counts(code))

    def test_arrow_function_returning_an_arrow_function_is_one_function(self):
        code = "const curried = (a) => (b) => a + b;"
        self.assertEqual([('curried', 1)], self.parameter_counts(code))

    def test_arrow_function_in_a_ternary(self):
        code = "const f = strict ? (a, b) => a === b : null;"
        self.assertEqual([('(anonymous)', 2)], self.parameter_counts(code))


class Test_ES6_parameter_list(unittest.TestCase):

    def test_destructured_object_is_one_parameter(self):
        functions = get_js_function_list(
            "function d(a = 1, { b, c } = {}, ...rest) { return a; }")
        self.assertEqual(3, functions[0].parameter_count)

    def test_destructured_array_is_one_parameter(self):
        functions = get_js_function_list("function e([a, b], c) { return a; }")
        self.assertEqual(2, functions[0].parameter_count)

    def test_nested_destructuring_is_one_parameter(self):
        functions = get_js_function_list(
            "const extract = ({user: {name, address: {city}}}) => { return name; }")
        self.assertEqual(1, functions[0].parameter_count)

    def test_default_value_with_a_call(self):
        code = (
            "function c(a = g(1, 2), b) {\n"
            "  return a;\n"
            "}\n"
            "function d() { return 1; }\n"
        )
        functions = get_js_function_list(code)
        self.assertEqual([('c', 1, 3, 1), ('d', 4, 4, 1)],
                         function_summary(functions))
        self.assertEqual(2, functions[0].parameter_count)

    def test_default_value_with_an_array(self):
        functions = get_js_function_list("const k = (a, b = [1, 2]) => { return a; };")
        self.assertEqual(2, functions[0].parameter_count)

    def test_method_with_a_default_value_with_a_call(self):
        code = (
            "class K {\n"
            "  m(a = g(1, 2), b) { return a; }\n"
            "  n() { return 1; }\n"
            "}\n"
        )
        functions = get_js_function_list(code)
        self.assertEqual([('m', 2), ('n', 0)],
                         [(f.name, f.parameter_count) for f in functions])
