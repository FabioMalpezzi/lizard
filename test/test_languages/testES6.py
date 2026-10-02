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


class Test_ES6_arrow_function_lines(unittest.TestCase):

    def test_arrow_function_with_its_body_on_the_next_line(self):
        code = (
            "const counters = event =>\n"
            "  list.filter(key => event[key]).join(' ');\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual(
            [('(anonymous)', 2, 2, 1), ('counters', 1, 2, 1), ('after', 3, 3, 1)],
            function_summary(get_js_function_list(code)))

    def test_anonymous_arrow_function_with_its_body_on_the_next_line(self):
        code = (
            "const rows = list.map(item =>\n"
            "  item.name + item.value);\n"
        )
        self.assertEqual([('(anonymous)', 1, 2, 1)],
                         function_summary(get_js_function_list(code)))


class Test_ES6_object_in_the_body_of_an_arrow_function(unittest.TestCase):

    def test_object_literals_in_an_expression_body(self):
        code = (
            "function layout(vertical) {\n"
            "  const box = f => vertical ? {x: f.a, y: f.b} : {x: f.b, y: f.a};\n"
            "  return box;\n"
            "}\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual(
            [('box', 2, 2, 2), ('layout', 1, 4, 1), ('after', 5, 5, 1)],
            function_summary(get_js_function_list(code)))

    def test_block_body_is_still_a_body(self):
        code = (
            "const f = x => {\n"
            "  if (x) { return {a: 1}; }\n"
            "  return {a: 2};\n"
            "};\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual([('f', 1, 4, 2), ('after', 5, 5, 1)],
                         function_summary(get_js_function_list(code)))


class Test_ES6_arrow_function_ends_at_a_comma(unittest.TestCase):
    """An arrow function without braces ends at the comma after its body."""

    def names_and_parameters(self, code):
        return [(f.name, f.parameter_count) for f in get_js_function_list(code)]

    def test_arrow_functions_as_properties(self):
        code = "const o = { a: (x) => x, b: () => 1, c() { return 1; } };"
        self.assertEqual([('a', 1), ('b', 0), ('c', 0)],
                         self.names_and_parameters(code))

    def test_arrow_functions_as_arguments(self):
        code = "sort(list, a => a.id, (b, c) => b + c);"
        self.assertEqual([('(anonymous)', 1), ('(anonymous)', 2)],
                         self.names_and_parameters(code))

    def test_arrow_functions_in_an_array(self):
        code = "const steps = [x => x + 1, y => y * 2];"
        self.assertEqual([('(anonymous)', 1), ('(anonymous)', 1)],
                         self.names_and_parameters(code))

    def test_arrow_functions_in_one_declaration(self):
        code = "const inc = x => x + 1, dec = x => x - 1;"
        self.assertEqual([('inc', 1), ('dec', 1)],
                         self.names_and_parameters(code))

    def test_complexity_goes_to_its_own_arrow_function(self):
        code = "const o = { a: x => x ? 1 : 2, b: y => y && 1 };"
        self.assertEqual(
            [('a', 2), ('b', 2)],
            [(f.name, f.cyclomatic_complexity) for f in get_js_function_list(code)])


class Test_ES6_arrow_function_after_a_member_access(unittest.TestCase):

    def names_and_parameters(self, code):
        return [(f.name, f.parameter_count) for f in get_js_function_list(code)]

    def test_arrow_property_without_parameters(self):
        code = "const o = {status: r.status, json: () => JSON.parse(text)};"
        self.assertEqual([('json', 0)], self.names_and_parameters(code))

    def test_arrow_property_with_parameters(self):
        code = "const o = {status: r.status, add: (a, b) => a + b};"
        self.assertEqual([('add', 2)], self.names_and_parameters(code))

    def test_arrow_function_assigned_to_a_member(self):
        code = "a.b = (x, y) => { return x; };"
        self.assertEqual([('a.b', 2)], self.names_and_parameters(code))

    def test_arrow_function_without_parentheses_after_a_property(self):
        code = "const o = {status: r.status, id: x => x};"
        self.assertEqual([('id', 1)], self.names_and_parameters(code))


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

    def test_parameters_starting_with_underscore_or_dollar(self):
        functions = get_js_function_list("function r(text, _a, $b, _) { return text; }")
        self.assertEqual(4, functions[0].parameter_count)

    def test_underscore_as_first_parameter_of_an_arrow_function(self):
        functions = get_js_function_list("list.forEach((_, key) => selected.add(key));")
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


class Test_ES6_values_in_objects_and_arrays(unittest.TestCase):
    """The value of a property or of a field is not a member declaration."""

    def test_array_as_a_property_value(self):
        code = (
            "function a(bytes) {\n"
            "  const signatures = {\n"
            "    '.png': ['image/png', bytes.subarray(0, 8).equals(from([1, 2]))],\n"
            "    '.jpg': ['image/jpeg', bytes.subarray(0, 3).equals(from([3, 4]))],\n"
            "  };\n"
            "  return signatures;\n"
            "}\n"
            "function b() { return 1; }\n"
        )
        self.assertEqual([('a', 1, 7, 1), ('b', 8, 8, 1)],
                         function_summary(get_js_function_list(code)))

    def test_array_of_objects_as_a_property_value(self):
        code = (
            "function a() {\n"
            "  return { name: 'x', list: [{ id: 1, tags: ['a', 'b'] }, { id: 2 }] };\n"
            "}\n"
            "function b() { return 1; }\n"
        )
        self.assertEqual([('a', 1, 3, 1), ('b', 4, 4, 1)],
                         function_summary(get_js_function_list(code)))

    def test_less_than_in_a_property_value(self):
        code = (
            "function a(date) {\n"
            "  return {\n"
            "    date,\n"
            "    recent: date ? now() - parse(date) < 30 : false,\n"
            "  };\n"
            "}\n"
            "function b() { return 1; }\n"
        )
        self.assertEqual([('a', 1, 6, 2), ('b', 7, 7, 1)],
                         function_summary(get_js_function_list(code)))

    def test_array_as_a_class_field_value(self):
        code = (
            "class K {\n"
            "  x = [f(1), g(2)];\n"
            "  m() { return 1; }\n"
            "}\n"
        )
        self.assertEqual([('m', 3, 3, 1)],
                         function_summary(get_js_function_list(code)))

    def test_less_than_in_a_class_field_value(self):
        code = (
            "class K {\n"
            "  x = a < b;\n"
            "  m1() { return 1; }\n"
            "  m2() { return 2; }\n"
            "}\n"
        )
        self.assertEqual([('m1', 3, 3, 1), ('m2', 4, 4, 1)],
                         function_summary(get_js_function_list(code)))

    def test_functions_in_an_array(self):
        code = (
            "const handlers = [\n"
            "  function () { return 1; },\n"
            "  (a) => { return a; },\n"
            "];\n"
            "function b() { return 1; }\n"
        )
        self.assertEqual(
            [('(anonymous)', 2, 2, 1), ('(anonymous)', 3, 3, 1), ('b', 5, 5, 1)],
            function_summary(get_js_function_list(code)))

    def test_arrow_function_returning_an_array_on_many_lines(self):
        code = (
            "const f = x => [\n"
            "  x,\n"
            "  x + 1,\n"
            "];\n"
            "function b() { return 1; }\n"
        )
        self.assertEqual([('f', 1, 4, 1), ('b', 5, 5, 1)],
                         function_summary(get_js_function_list(code)))

    def test_optional_index_access(self):
        code = (
            "function a(s, list) {\n"
            "  const first = find(s)?.[1];\n"
            "  return [first, list?.[0]];\n"
            "}\n"
            "function b() { return 1; }\n"
        )
        self.assertEqual([('a', 1, 4), ('b', 5, 5)],
                         [(f.name, f.start_line, f.end_line)
                          for f in get_js_function_list(code)])

    def test_square_bracket_without_its_pair(self):
        code = (
            "function a(c, r) {\n"
            "  const s = new Set(r.flatMap(x => c ? [f(x), g(x)] : [f(x)]));\n"
            "  return s;\n"
            "}\n"
            "function b() { return 1; }\n"
        )
        self.assertEqual([('a', 1, 4), ('b', 5, 5)],
                         [(f.name, f.start_line, f.end_line)
                          for f in get_js_function_list(code) if f.name != '(anonymous)'])

    def test_computed_member_names_are_still_read(self):
        code = (
            "const o = {\n"
            "  [key]: [1, 2],\n"
            "  ['a' + 'b']() { return 1; },\n"
            "  plain() { return 2; },\n"
            "};\n"
        )
        self.assertEqual(['ab', 'plain'],
                         [f.name for f in get_js_function_list(code)])


class Test_ES6_members_named_get_or_set(unittest.TestCase):
    """get and set start an accessor only before its name."""

    def test_methods_named_get_and_set(self):
        code = (
            "class A {\n"
            "  get(key) { return this.map[key]; }\n"
            "  set(key, value) { this.map[key] = value; }\n"
            "  other() { return 2; }\n"
            "  get size() { return 1; }\n"
            "}\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual(
            [('get', 1), ('set', 2), ('other', 0), ('get size', 0), ('after', 0)],
            [(f.name, f.parameter_count) for f in get_js_function_list(code)])

    def test_shorthand_properties_named_get_and_set(self):
        code = (
            "function f(base, get, set) {\n"
            "  return { base, get, set };\n"
            "}\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual([('f', 1, 3, 1), ('after', 4, 4, 1)],
                         function_summary(get_js_function_list(code)))

    def test_properties_named_get_and_set(self):
        code = (
            "function g(set) {\n"
            "  const o = { get: () => { return 1; }, set };\n"
            "  return o;\n"
            "}\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual(
            [('get', 2, 2, 1), ('g', 1, 4, 1), ('after', 5, 5, 1)],
            function_summary(get_js_function_list(code)))


class Test_ES6_blocks_of_statements(unittest.TestCase):
    """A block of statements is not read as an object."""

    def names(self, code):
        return [(f.name, f.start_line, f.end_line)
                for f in get_js_function_list(code)]

    def test_block_after_a_case_label(self):
        code = (
            "function a(n, x) {\n"
            "  switch (n) {\n"
            "    case 1: {\n"
            "      const label = x\n"
            "        ? `<b ${x.on ? 1 : 2} title=\"${x.t ? f(1) : f(2)}\">`\n"
            "        : '';\n"
            "      return label;\n"
            "    }\n"
            "    default: {\n"
            "      const k = x\n"
            "        ? [f(1), f(2)]\n"
            "        : (x < 3);\n"
            "      return k;\n"
            "    }\n"
            "  }\n"
            "}\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual([('a', 1, 16), ('after', 17, 17)], self.names(code))

    def test_block_after_catch_without_a_binding(self):
        code = (
            "function b(f) {\n"
            "  try {\n"
            "    f();\n"
            "  } catch {\n"
            "    const k = f\n"
            "      ? `${f(1)} ${f(2)}`\n"
            "      : '';\n"
            "  }\n"
            "}\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual([('b', 1, 9), ('after', 10, 10)], self.names(code))

    def test_block_after_finally(self):
        code = (
            "function b(f) {\n"
            "  try {\n"
            "    f();\n"
            "  } finally {\n"
            "    const k = f\n"
            "      ? `${f(1)} ${f(2)}`\n"
            "      : '';\n"
            "  }\n"
            "}\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual([('b', 1, 9), ('after', 10, 10)], self.names(code))


class Test_es6_class_field_without_a_semicolon(unittest.TestCase):

    def summary(self, code, filename):
        return [(f.name, f.start_line, f.end_line) for f in
                analyze_file.analyze_source_code(filename, code).function_list]

    def check(self, code, expected):
        for filename in ("a.js", "a.ts", "a.tsx"):
            self.assertEqual(expected, self.summary(code, filename), filename)

    def test_field_then_a_method_with_a_modifier(self):
        for modifier, name in (("async ", "load"), ("static ", "load"),
                               ("get ", "get load"), ("set ", "set load"),
                               ("*", "load")):
            code = (
                "class A {\n"
                "  count = 0\n"
                "  " + modifier + "load(v) {\n"
                "    return 1;\n"
                "  }\n"
                "  two() {\n"
                "    return 2;\n"
                "  }\n"
                "}\n"
            )
            self.check(code, [(name, 3, 5), ('two', 6, 8)])

    def test_arrow_function_field_then_an_async_method(self):
        code = (
            "class A {\n"
            "  handler = () => 1\n"
            "  async load() {\n"
            "    return 1;\n"
            "  }\n"
            "  two() {\n"
            "    return 2;\n"
            "  }\n"
            "}\n"
            "function after(a) { return a; }\n"
        )
        for filename in ("a.js", "a.ts", "a.tsx"):
            self.assertEqual(
                [('handler', 2), ('load', 3), ('two', 6), ('after', 10)],
                [(name, start) for name, start, _ in
                 self.summary(code, filename)], filename)

    def test_async_arrow_function_on_the_line_after_its_name(self):
        code = (
            "const handler =\n"
            "  async () => {\n"
            "    return 1;\n"
            "  };\n"
            "const obj = {\n"
            "  run:\n"
            "    async (x) => { return x; },\n"
            "};\n"
        )
        self.check(code, [('handler', 2, 4), ('run', 7, 7)])


class Test_es6_spread_of_a_parenthesized_expression(unittest.TestCase):

    def test_function_in_a_spread_object(self):
        code = (
            "const props = {\n"
            "  ...(cond && { f: () => { return 1; } }),\n"
            "  ...(other ? { g(x) { return x; } } : {}),\n"
            "  h: 2,\n"
            "};\n"
            "function after(a) { return a; }\n"
        )
        for filename in ("a.js", "a.ts", "a.tsx"):
            functions = analyze_file.analyze_source_code(
                filename, code).function_list
            self.assertEqual(
                [('f', 2, 2, 1, 0), ('g', 3, 3, 1, 1), ('after', 6, 6, 1, 1)],
                [(f.name, f.start_line, f.end_line, f.cyclomatic_complexity,
                  f.parameter_count) for f in functions], filename)


class Test_ES6_expression_on_many_lines(unittest.TestCase):
    """A new line does not end an expression that goes on."""

    def test_arrow_function_body_on_the_next_lines(self):
        code = (
            "const pick = (a, b) =>\n"
            "  a && b\n"
            "    ? a\n"
            "    : b || 0;\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual([('pick', 1, 4, 4), ('after', 5, 5, 1)],
                         function_summary(get_js_function_list(code)))

    def test_arrow_function_body_that_ends_a_line_with_an_operator(self):
        code = (
            "const counters = event =>\n"
            "  ['a', 'b'].filter(key => event[key] != null).join(' ') ||\n"
            "  unknown();\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual(
            [('(anonymous)', 2, 2, 1), ('counters', 1, 3, 2), ('after', 4, 4, 1)],
            function_summary(get_js_function_list(code)))

    def test_arrow_function_body_with_lines_that_start_with_a_plus(self):
        code = (
            "const row = item => '<td>' + item.name\n"
            "  + (item.on ? 'on' : 'off')\n"
            "  + '</td>';\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual([('row', 1, 3, 2), ('after', 4, 4, 1)],
                         function_summary(get_js_function_list(code)))

    def test_statements_without_semicolons_still_end_at_the_line(self):
        code = (
            "const inc = x => x + 1\n"
            "const dec = x => x - 1\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual(['inc', 'dec', 'after'],
                         [f.name for f in get_js_function_list(code)])

    def test_property_value_on_many_lines(self):
        code = (
            "const o = {\n"
            "  a: cond\n"
            "    ? (x) => { return 1; }\n"
            "    : (y, z) => { return 2; },\n"
            "  b() { return 3; },\n"
            "};\n"
        )
        self.assertEqual(
            [('(anonymous)', 1), ('(anonymous)', 2), ('b', 0)],
            [(f.name, f.parameter_count) for f in get_js_function_list(code)])


class Test_ES6_arrow_function_ended_by_the_next_line(unittest.TestCase):
    """The token that ends an arrow function without braces is not its own."""

    def test_statements_without_semicolons(self):
        code = (
            "const inc = x => x + 1\n"
            "const dec = x => x - 1\n"
            "if (a) { b() }\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual([('inc', 1, 1, 1), ('dec', 2, 2, 1), ('after', 4, 4, 1)],
                         function_summary(get_js_function_list(code)))

    def test_lines_and_tokens_are_the_same_with_and_without_a_semicolon(self):
        with_semicolon = get_js_function_list("const inc = x => x + 1;\nlet a\n")[0]
        without = get_js_function_list("const inc = x => x + 1\nlet a\n")[0]
        self.assertEqual(1, without.nloc)
        self.assertEqual(with_semicolon.nloc, without.nloc)
        self.assertEqual(with_semicolon.token_count - 1, without.token_count)

    def test_last_property_of_an_object(self):
        code = (
            "const rules = {\n"
            "  find: text => text.match(/a/g)\n"
            "}\n"
            "function after() { return 1; }\n"
        )
        self.assertEqual([('find', 2, 2, 1), ('after', 4, 4, 1)],
                         function_summary(get_js_function_list(code)))

    def test_body_on_the_last_line_of_the_file(self):
        functions = get_js_function_list("const inc = x =>\n  x + 1")
        self.assertEqual([('inc', 1, 2, 1)], function_summary(functions))
        self.assertEqual(2, functions[0].nloc)

    def test_last_argument_of_a_call(self):
        code = (
            "run(\n"
            "  x => x + 1\n"
            ")\n"
        )
        functions = get_js_function_list(code)
        self.assertEqual([('(anonymous)', 2, 2, 1)], function_summary(functions))
        self.assertEqual(1, functions[0].nloc)
