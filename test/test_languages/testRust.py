import unittest
from lizard import analyze_file, FileAnalyzer, get_extensions


def get_rust_fileinfo(source_code):
    return analyze_file.analyze_source_code("a.rs", source_code)


def get_rust_function_list(source_code):
    return get_rust_fileinfo(source_code).function_list


class TestRust(unittest.TestCase):

    def test_main(self):
        result = get_rust_function_list('''
        fn main() {
            println!("Hello, world!");
        }
        ''')
        self.assertEqual(1, len(result))
        self.assertEqual('main', result[0].name)

    def test_return(self):
        result = get_rust_function_list('''
        fn plus_one(x: i32) -> i32 {
            x + 1;
        }
        ''')
        self.assertEqual(1, len(result))
        self.assertEqual('plus_one', result[0].name)

    def test_if(self):
        result = get_rust_function_list('''
        fn main() {
            match a() {}
        }
        ''')
        self.assertEqual(1, len(result))
        self.assertEqual(2, result[0].cyclomatic_complexity)

    def test_generic(self):
        result = get_rust_function_list('''
        fn largest<T>(list: &[T]) -> T {
            let mut largest = list[0];

            for &item in list.iter() {
                if item > largest {
                    largest = item;
                }
            }

            largest
        }

        fn main() {
            match a() {}
        }
        ''')
        self.assertEqual(2, len(result))
        self.assertEqual('largest', result[0].name)
        self.assertEqual(3, result[0].cyclomatic_complexity)

    def test_generic_with_where(self):
        result = get_rust_function_list('''
        fn some_function<T, U>(t: T, u: U) -> i32
            where T: Display + Clone,
                  U: Clone + Debug {
                  }
        ''')
        self.assertEqual(1, len(result))
        self.assertEqual(2, result[0].cyclomatic_complexity)

    def test_nested_functions(self):
        result = get_rust_function_list('''
        fn main() {
            let x = 4;

            fn equal_to_x(z: i32) -> bool { z == x }

            let y = 4;

            assert!(equal_to_x(y));
        }
        ''')
        self.assertEqual(2, len(result))

    def test_lifetime(self):
        result = get_rust_function_list('''
        pub fn func<'a>(a: &'a i64)
        {
            _ = a
        }
        ''')

        self.assertEqual(1, len(result))

    def test_case_as_identifier(self):
        """
        Test that 'case' used as an identifier doesn't add to CCN.
        Rust doesn't have 'case' keyword (uses match expressions with arms).
        """
        code = '''
        fn handle_case_variable(case: i32) -> i32 {
            let case_value = case;
            match case_value {
                1 => println!("one"),
                2 => println!("two"),
                _ => println!("other"),
            }
            case
        }
        '''
        result = get_rust_function_list(code)
        self.assertEqual(1, len(result))
        
        # Expected: 2 = base(1) + match(1)
        # 'case' as identifier should not add to CCN
        self.assertEqual(2, result[0].cyclomatic_complexity,
                        "'case' as identifier doesn't add to CCN")

    def test_match_expression_complexity(self):
        """
        Test that Rust match expressions are counted correctly.
        Rust uses match arms (with =>), not case statements.
        """
        code = '''
        fn categorize(value: i32) -> &'static str {
            match value {
                1 | 2 | 3 => "small",
                4 | 5 => "medium",
                6..=10 => "large",
                _ => "other",
            }
        }
        '''
        result = get_rust_function_list(code)
        self.assertEqual(1, len(result))
        
        # Should be 2: base(1) + match(1) = 2
        # The || in match arms (1 | 2) is pattern matching, not logical operator
        self.assertEqual(2, result[0].cyclomatic_complexity)

    def test_parameter_of_function_type(self):
        result = get_rust_function_list('''
        fn first(list: &[i32], less: impl Fn(i32, i32) -> bool) -> i32 {
            list[0]
        }
        ''')
        self.assertEqual(2, result[0].parameter_count)

    def test_char_literal_of_one_letter(self):
        result = get_rust_function_list('''
        fn is_a(c: char) -> u8 {
            if c == 'a' {
                return 1;
            }
            2
        }

        fn is_b(c: char) -> u8 {
            if c == 'b' { 3 } else { 4 }
        }
        ''')
        self.assertEqual(['is_a', 'is_b'], [f.name for f in result])
        self.assertEqual(7, result[0].end_line)
        self.assertEqual(2, result[1].cyclomatic_complexity)

    def test_lifetime_is_not_a_char_literal(self):
        result = get_rust_function_list('''
        fn pick<'a>(a: &'a str, b: &'a str) -> &'a str {
            'outer: loop {
                break 'outer;
            }
            if a.len() > b.len() { a } else { b }
        }
        ''')
        self.assertEqual(['pick'], [f.name for f in result])
        self.assertEqual(2, result[0].parameter_count)
        self.assertEqual(7, result[0].end_line)

    def test_nested_block_comment(self):
        result = get_rust_function_list('''
        fn positive(a: i32) -> i32 {
            /* a comment /* nested */ with a brace } */
            if a > 0 {
                return a;
            }
            0
        }

        fn after(a: i32) -> i32 {
            a
        }
        ''')
        self.assertEqual(['positive', 'after'], [f.name for f in result])
        self.assertEqual(2, result[0].cyclomatic_complexity)
        self.assertEqual(8, result[0].end_line)
        self.assertEqual(6, result[0].nloc)

    def test_nested_block_comment_on_many_lines(self):
        result = get_rust_function_list('''
        fn one() -> i32 {
            /* outer
               /* inner { */
               still a comment: if x { "
            */
            1
        }
        ''')
        self.assertEqual(['one'], [f.name for f in result])
        self.assertEqual(1, result[0].cyclomatic_complexity)
        self.assertEqual(8, result[0].end_line)
        self.assertEqual(3, result[0].nloc)

    def test_loop_is_counted(self):
        result = get_rust_function_list('''
        fn count(n: i32) -> i32 {
            let mut total = 0;
            loop {
                if total > n {
                    break;
                }
                total += 1;
            }
            total
        }
        ''')
        self.assertEqual(3, result[0].cyclomatic_complexity)

    def test_closure_without_parameters_is_not_a_logical_operator(self):
        result = get_rust_function_list('''
        fn lazy(value: Option<i32>) -> i32 {
            let zero = || 0;
            let moved = move || 1;
            run(|| 2, || 3);
            value.unwrap_or_else(|| 0)
        }
        ''')
        self.assertEqual(1, result[0].cyclomatic_complexity)

    def test_logical_or_is_still_counted(self):
        result = get_rust_function_list('''
        fn either(a: bool, b: Vec<bool>, c: Option<bool>) -> bool {
            a || b[0] || f(a) || c? || "x".is_empty() || a
        }
        ''')
        self.assertEqual(7, result[0].cyclomatic_complexity)
