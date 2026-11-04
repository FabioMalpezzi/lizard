import unittest

from .testHelpers import get_cpp_function_list_with_extension
from lizard import FileAnalyzer, get_extensions
from lizard_ext.lizardns import LizardExtension as NestedStructure


def process_cpp(source):
    return get_cpp_function_list_with_extension(source, NestedStructure())


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
