import unittest

from .testHelpers import get_cpp_function_list_with_extension, \
    get_python_function_list_with_extension
from lizard import FileAnalyzer, get_extensions
from lizard_ext.lizardns import LizardExtension as NestedStructure


def process_cpp(source):
    return get_cpp_function_list_with_extension(source, NestedStructure())


def process_python(source):
    return get_python_function_list_with_extension(source, NestedStructure())


class TestCppNestedStructures(unittest.TestCase):

    def test_no_structures(self):
        result = process_cpp("int fun(){}")
        self.assertEqual(0, result[0].max_nested_structures)

    def test_if_structure(self):
        result = process_cpp("int fun(){if(a){xx;}}")
        self.assertEqual(1, result[0].max_nested_structures)

    def test_ternary_operator(self):
        """The ternary operator is not a structure."""
        result = process_cpp("int fun(){return (a)?b:c;}")
        self.assertEqual(0, result[0].max_nested_structures)

    def test_forever_loop(self):
        result = process_cpp("int fun(){for(;;){dosomething();}}")
        self.assertEqual(1, result[0].max_nested_structures)

    def test_terminator_in_parentheses(self):
        result = process_cpp("int fun(){for(int a;;){ if (a) return b;}}")
        self.assertEqual(2, result[0].max_nested_structures)

    def test_and_condition_in_if_structure(self):
        result = process_cpp("int fun(){if(a&&b){xx;}}")
        self.assertEqual(1, result[0].max_nested_structures)

    def test_else_if(self):
        result = process_cpp("""
        x c() {
          if (a && b)
            baz();
          else if (c)
            foo();
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_non_r_value_ref_in_body(self):
        result = process_cpp("""
        x c() {
          if (a && b) {
            baz();
          } else {
            foo();
          }
        }
        x a() {
          c = a && b;
        }
        """)
        self.assertEqual(1, result[0].max_nested_structures)
        self.assertEqual(0, result[1].max_nested_structures)

    def test_nested_if_structures(self):
        result = process_cpp("""
        x a() {
          if (a && b)
            if (a != 0)
               a = b;
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_nested_if_structures_in_2_functions(self):
        result = process_cpp("""
        x c() {
          if (a && b) {
            if(a != 0) {
                a = b;
            }
          }
        }
        x a() {
          if (a && b)
            if (a != 0)
               a = b;
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)
        self.assertEqual(2, result[1].max_nested_structures)

    def test_nested_loop_mixed_brackets(self):
        result = process_cpp("""
        x c() {
          if (a && b) {
            if (a != 0)
              a = b;
          }
        }
        x a() {
          if (a && b)
            if (a != 0) {
               a = b;
            }
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)
        self.assertEqual(2, result[1].max_nested_structures)

    def test_equal_metric_structures(self):
        result = process_cpp("""
        x c() {
          if (a && b) {
            if(a != 0){
                a = b;
            } else b = a;
          }
          if (a && b){
            if(a != 0)
                a = b;
            else
                b = a;
          }
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_while(self):
        result = process_cpp("""
        x c() {
          while (a && b) {
            if(a != 0){
                a = b;
            }
            while (s) continue;
          }
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_do(self):
        result = process_cpp("""
        x c() {
          do {
            if(a != 0){
                a = b;
            } else {
                b = a;
            }
          } while (a && b);
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_try_catch(self):
        result = process_cpp("""
        x c() {
          try {
            if (a != 0) {
                foo();
            } else {
                bar();
            }
          } catch (auto& err) {}
        }
        x a() {
          try {
            foo();
          } catch (auto& err) {
            if (a != 0) {
                bar();
            } else {
                baz();
            }
          }
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)
        self.assertEqual(2, result[1].max_nested_structures)

    def test_braceless_nested_if_try_structures(self):
        result = process_cpp("""
        x c() {
          if (a)
            try {
              throw 42;
            } catch(...) {
              if (b) return 42;
            }
        }
        """)
        self.assertEqual(3, result[0].max_nested_structures)

    def test_non_block_if(self):
        result = process_cpp("""
        x c() {
          if (a)
            if(b) {
              {}
              if (c) { if (e) f; }
            }
        }
        """)
        self.assertEqual(4, result[0].max_nested_structures)

    def test_braceless_nested_if_and_for(self):
        result = process_cpp("""
        x c() {
          if (a)
              for (;;)
                if(b) c;
        }
        """)
        self.assertEqual(3, result[0].max_nested_structures)

    def test_braceless_nested_for_try_structures(self):
        result = process_cpp("""
        x c() {
          for (;;)
            try {
              throw 42;
            } catch(...) {
              if (b) return 42;
            }
        }
        """)
        self.assertEqual(3, result[0].max_nested_structures)

    def test_switch_case(self):
        """Switch-Case is one control structure."""
        result = process_cpp("""
        x c() {
          switch (a) {
            case 1:
              if (b && c) break;
            case 0:
            default:
              return;
          }
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_scope(self):
        result = process_cpp("""
        x c() {
          {{{{{{for (a : c) {
            {{{{if(a != 0) {{{{
                a = b;
            }}}}}}}}
          }}}}}}}
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_gotcha_if_else(self):
        """The last 'else' is associated with the innermost 'if'."""
        result = process_cpp("""
        x c() {
          if (a)
            if (b)
              call();
          else  // Deceiving indentation!
              for (auto c : d)  // #3 control structure is here!
                call(c);
        }
        """)
        self.assertEqual(3, result[0].max_nested_structures)

    def test_non_structure_braces(self):
        """Extra braces for initializer lists may confuse the nesting level."""
        result = process_cpp("""
        x c() {
          if (a) return {{}};  // Initializer list with a braceless structure.
          if (b)
            if (c)
              if (d) return 42;
        }
        """)
        self.assertEqual(3, result[0].max_nested_structures)

    def test_braceless_consecutive_if_structures(self):
        """Braceless structures one after another."""
        result = process_cpp("""
        x c() {
          if (a)
            if (b)
                foobar();
          if (c)
            if (d)
                baz();
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_braceless_consecutive_for_if_structures(self):
        """Braceless structures one after another."""
        result = process_cpp("""
        x c() {
          for (;;)
            for (;;)
                foobar();
          if (c)
            if (d)
                baz();
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_braceless_consecutive_if_structures_with_return(self):
        """Braceless structures one after another."""
        result = process_cpp("""
        x c() {
          if (a)
            if (b)
                return true;
          if (c)
            if (d)
                return false;
        }
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_braceless_nested_if_else_structures(self):
        result = process_cpp("""
        x c() {
          if (a)
            if (b) {
              return b;
            } else {
              if (b) return 42;
            }
        }
        """)
        self.assertEqual(3, result[0].max_nested_structures)

    def xtest_braceless_nested_if_else_if_structures(self):
        result = process_cpp("""
        x c() {
          if (a)
            if (b) {
              return b;
            } else if (c) {
              if (b) return 42;
            }
        }
        """)
        self.assertEqual(3, result[0].max_nested_structures)

    @unittest.skip("Unspecified. Not Implemented. Convoluted.")
    def test_struct_inside_declaration(self):
        """Extra complexity class/struct should be ignored."""
        result = process_cpp("""
        x c() {
          for (struct {int s; int foo() { while(c) return s; }} a{42};;) break;
        }
        """)
        self.assertEqual(1, result[0].max_nested_structures)

    @unittest.skip("Unspecified. Not Implemented. Convoluted.")
    def test_struct_inside_definition(self):
        """Extra complexity class/struct should be ignored."""
        result = process_cpp("""
        x c() {
          for (;;) {
            struct {int s; int foo() { while(c) return s; }} a{42};
          }
        }
        """)
        self.assertEqual(1, result[0].max_nested_structures)

    def test_raw_string_literal_with_braces(self):
        """Raw string literals containing braces should not cause IndexError."""
        result = process_cpp(r'''
        int main() {
            const char* json = R"({
  "name": "Ada Lovelace",
  "id": 101,
  "languages": ["C++", "Python", "Assembly"],
  "active": true,
  "profile": {
    "bio": "Mathematician & pioneer",
    "links": {
      "website": "https://example.com/ada",
      "github": "https://github.com/ada"
    }
  }
})";
            for (int i = 1; i <= 3; ++i) {
                for (int j = 1; j <= 3; ++j) {
                    return i + j;
                }
            }
            return 0;
        }
        ''')
        self.assertEqual(2, result[0].max_nested_structures)

    def test_raw_string_literal_with_delimiter(self):
        """Raw string literals with delimiters should be handled correctly."""
        result = process_cpp(r'''
        int fun() {
            const char* s = R"delim(some {content} with )delim";
            if (true) {
                return 1;
            }
            return 0;
        }
        ''')
        self.assertEqual(1, result[0].max_nested_structures)

    def test_raw_string_literal_simple(self):
        """Simple raw string literals should not interfere with complexity counting."""
        result = process_cpp(r'''
        int fun() {
            const char* s = R"(hello world)";
            if (a) {
                if (b) {
                    return c;
                }
            }
            return 0;
        }
        ''')
        self.assertEqual(2, result[0].max_nested_structures)


class X: #TestPythonNestedStructures(unittest.TestCase):

    def test_no_structures(self):
        result = process_python("def fun():\n pass")
        self.assertEqual(0, result[0].max_nested_structures)

    def test_if_structure(self):
        result = process_python("def fun():\n if a:\n  return")
        self.assertEqual(1, result[0].max_nested_structures)

    def test_for_structure(self):
        result = process_python("def fun():\n for a in b:\n  foo()")
        self.assertEqual(1, result[0].max_nested_structures)

    def test_condition_in_if_structure(self):
        result = process_python("def fun():\n if a and b:\n  return")
        self.assertEqual(1, result[0].max_nested_structures)

    def test_elif(self):
        result = process_python("""
        def c():
          if a:
            baz()
          elif c:
            foo()
        """)
        self.assertEqual(1, result[0].max_nested_structures)

    def test_nested_if_structures(self):
        result = process_python("""
        def c():
          if a:
            if b:
              baz()
          else:
            foo()
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_equal_metric_structures(self):
        result = process_python("""
        def c():
          if a:
            if b:
              baz()
          else:
            foo()

          for a in b:
            if c:
              bar()
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_while(self):
        result = process_python("""
        def c():
          while a:
            baz()
        """)
        self.assertEqual(1, result[0].max_nested_structures)

    def test_try_catch(self):
        result = process_python("""
        def c():
          try:
            f.open()
          catch Exception as err:
            print(err)
          finally:
            f.close()
        """)
        self.assertEqual(1, result[0].max_nested_structures)

    def test_two_functions(self):
        result = process_python("""
        def c():
          try:
            if a:
              foo()
          catch Exception as err:
            print(err)

        def d():
          for a in b:
            for x in y:
              if i:
                return j
        """)
        self.assertEqual(2, result[0].max_nested_structures)
        self.assertEqual(3, result[1].max_nested_structures)

    def test_nested_functions(self):
        result = process_python("""
        def c():
            def d():
                for a in b:
                    for x in y:
                        if i:
                            return j
            try:
                if a:
                    foo()
            catch Exception as err:
                print(err)

        """)
        self.assertEqual(3, result[0].max_nested_structures)
        self.assertEqual(2, result[1].max_nested_structures)

    def test_with_structure(self):
        result = process_python("""
        def c():
            with open(f) as input_file:
                foo(f)
        """)
        self.assertEqual(1, result[0].max_nested_structures)

    def test_for_else(self):
        result = process_python("""
        def c():
            for i in range(10):
                break
            else:
                for j in range(i):
                    print(j)
        """)
        self.assertEqual(2, result[0].max_nested_structures)

    def test_while_else(self):
        result = process_python("""
        def c(i):
            while i < 10:
                break
            else:
                for j in range(i):
                    print(j)
        """)
        self.assertEqual(2, result[0].max_nested_structures)

class TestNestedStructuresOfTheNextFile(unittest.TestCase):

    NESTED = """
    int nested(int a) {
      for (;;) {
        if (a) {
          while (a) {
            a--;
          }
        }
      }
    }
    """

    def setUp(self):
        self.analyzer = FileAnalyzer(get_extensions([NestedStructure()]))

    def nested_structures(self, filename, code):
        functions = self.analyzer.analyze_source_code(filename, code).function_list
        return [(f.name, f.max_nested_structures) for f in functions]

    def test_file_after_a_file_that_ends_inside_the_head_of_a_structure(self):
        self.nested_structures("a.c", "int broken(int a) { if (a > MACRO(1 ) { return 1; } }")
        self.assertEqual([('nested', 3)], self.nested_structures("b.c", self.NESTED))

    def test_file_after_a_file_that_ends_inside_a_block(self):
        self.nested_structures("a.c", "int broken(int a) { if (a) { while (a) { for (;;) {")
        self.assertEqual([('nested', 3)], self.nested_structures("b.c", self.NESTED))


class TestGoNestedStructures(unittest.TestCase):

    def nested_structures(self, code):
        analyzer = FileAnalyzer(get_extensions([NestedStructure()]))
        functions = analyzer.analyze_source_code("a.go", code).function_list
        return [(f.name, f.max_nested_structures) for f in functions]

    def test_for_with_three_clauses(self):
        self.assertEqual([('sum', 2)], self.nested_structures("""
            func sum(n int) int {
                total := 0
                for i := 0; i < n; i++ {
                    if i%2 == 0 {
                        total += i
                    }
                }
                return total
            }
            """))

    def test_if_with_an_initial_statement(self):
        self.assertEqual([('first', 2)], self.nested_structures("""
            func first(m map[string]int) int {
                if v, ok := m["a"]; ok {
                    for v > 10 {
                        v--
                    }
                    return v
                }
                return 0
            }
            """))

    def test_switch_with_an_initial_statement(self):
        self.assertEqual([('kind', 2)], self.nested_structures("""
            func kind(a int) int {
                switch b := a * 2; {
                case b > 10:
                    if a > 7 {
                        return 2
                    }
                }
                return 0
            }
            """))

    def test_select_is_a_structure(self):
        self.assertEqual([('drain', 2)], self.nested_structures("""
            func drain(data <-chan int, done <-chan bool) int {
                total := 0
                for {
                    select {
                    case v := <-data:
                        total += v
                    case <-done:
                        return total
                    }
                }
            }
            """))

    def test_structures_after_a_for_with_three_clauses(self):
        self.assertEqual([('twice', 1)], self.nested_structures("""
            func twice(n int) int {
                total := 0
                for i := 0; i < n; i++ {
                    total += i
                }
                if total > 10 {
                    total = 10
                } else {
                    total = 0
                }
                return total
            }
            """))

    def test_for_over_a_composite_literal(self):
        self.assertEqual([('table', 2), ('sizes', 2)], self.nested_structures("""
            func table(t *testing.T) {
                for _, tt := range []struct {
                    name string
                    ok   bool
                }{
                    {"a", true},
                    {"b", false},
                } {
                    if tt.ok {
                        t.Log(tt.name)
                    }
                }
            }

            func sizes(m map[string][]pkg.Size) int {
                for _, n := range []int{1, 2} {
                    for _, s := range m[key(n)] {
                        return s.n
                    }
                }
                return 0
            }
            """))

    def test_do_and_try_are_names(self):
        self.assertEqual([('do', 0), ('run', 1)], self.nested_structures("""
            func do(b int) {}

            func run(c *Client) int {
                if c.try() {
                    return c.do(1)
                }
                return 0
            }
            """))


class TestRustNestedStructures(unittest.TestCase):

    def nested_structures(self, code):
        analyzer = FileAnalyzer(get_extensions([NestedStructure()]))
        functions = analyzer.analyze_source_code("a.rs", code).function_list
        return [(f.name, f.max_nested_structures) for f in functions]

    def test_match_is_a_structure_and_its_arms_are_not(self):
        self.assertEqual([('name', 1)], self.nested_structures("""
            fn name(x: i32) -> &'static str {
                match x {
                    1 => "one",
                    2 | 3 => "few",
                    _ => "many",
                }
            }
            """))

    def test_loop_is_a_structure(self):
        self.assertEqual([('count', 3)], self.nested_structures("""
            fn count(n: i32) -> i32 {
                let mut total = 0;
                'outer: loop {
                    for i in 0..n {
                        if total > 100 {
                            break 'outer;
                        }
                        total += i + 1;
                    }
                }
                total
            }
            """))

    def test_structure_inside_a_match_arm(self):
        self.assertEqual([('pick', 2)], self.nested_structures("""
            fn pick(x: Option<i32>) -> i32 {
                match x {
                    Some(v) => {
                        if v > 0 { v } else { 0 }
                    }
                    None => 0,
                }
            }
            """))
