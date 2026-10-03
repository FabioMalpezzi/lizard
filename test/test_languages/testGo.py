import unittest
import inspect
from lizard import analyze_file, FileAnalyzer, get_extensions


def get_go_function_list(source_code):
    return analyze_file.analyze_source_code(
        "a.go", source_code).function_list


class Test_parser_for_Go(unittest.TestCase):

    def test_empty(self):
        functions = get_go_function_list("")
        self.assertEqual(0, len(functions))

    def test_no_function(self):
        result = get_go_function_list('''
        for name, ok := range names; ok {
                print("Hello, \\(name)!")
            }
                ''')
        self.assertEqual(0, len(result))

    def test_one_function(self):
        result = get_go_function_list('''
            func sayGoodbye() { }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("sayGoodbye", result[0].name)
        self.assertEqual(0, result[0].parameter_count)
        self.assertEqual(1, result[0].cyclomatic_complexity)

    def test_one_with_parameter(self):
        result = get_go_function_list('''
            func sayGoodbye(personName string, alreadyGreeted chan bool) { }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("sayGoodbye", result[0].name)
        self.assertEqual(2, result[0].parameter_count)

    def test_one_function_with_return_value(self):
        result = get_go_function_list('''
            func sayGoodbye() string { }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("sayGoodbye", result[0].name)

    def test_one_function_with_two_return_values(self):
        result = get_go_function_list('''
            func sayGoodbye(p int) (string, error) { }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("sayGoodbye", result[0].name)
        self.assertEqual(1, result[0].parameter_count)

    def test_one_function_defined_on_a_struct(self):
        result = get_go_function_list('''
            func (s Stru) sayGoodbye(){ }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("sayGoodbye", result[0].name)
        self.assertEqual("(s Stru)sayGoodbye", result[0].long_name)

    def test_one_function_with_complexity(self):
        result = get_go_function_list('''
            func sayGoodbye() { if ++diceRoll == 7 { diceRoll = 1 }}
                ''')
        self.assertEqual(2, result[0].cyclomatic_complexity)

    def test_one_function_with_return_empty_interface(self):
        result = get_go_function_list('''
            func sayGoodbye() interface{} {
                if ++diceRoll == 7 { diceRoll = 1 }
            }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("sayGoodbye", result[0].name)
        self.assertEqual(3, result[0].length)

    def test_nest_function(self):
        result = get_go_function_list('''
            func sayGoodbye() {
                f1 := func() {}
                f2 := func(n int) {}
                f3 := func() int {
                    return 0
                }
            }
                ''')
        self.assertEqual(4, len(result))

        self.assertEqual("", result[0].name)
        self.assertEqual("", result[0].long_name)
        self.assertEqual(1, result[0].length)

        self.assertEqual("", result[1].name)
        self.assertEqual(" n int", result[1].long_name)
        self.assertEqual(1, result[1].length)
        self.assertEqual(['n int'], result[1].full_parameters)

        self.assertEqual("", result[2].name)
        self.assertEqual("", result[2].long_name)
        self.assertEqual(3, result[2].length)

        self.assertEqual("sayGoodbye", result[3].name)
        self.assertEqual(7, result[3].length)

    def test_interface(self):
        result = get_go_function_list('''
			type geometry interface{
					 area()  float64
					 perim()  float64
			 }
            func sayGoodbye() { }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("sayGoodbye", result[0].name)

    def test_interface_followed_by_a_class(self):
        result = get_go_function_list('''
			type geometry interface{
					 area()  float64
					 perim()  float64
			 }
            class c { }
                ''')
        self.assertEqual(0, len(result))

    def test_struct_with_func_followed_by_function_with_receiver(self):
        result = get_go_function_list('''
            type Geometry struct {
                isEqual func(float64, float64) error
            }

            func (g *Geometry) sayGoodbye() { }
                ''')

        self.assertEqual(1, len(result))
        self.assertEqual("sayGoodbye", result[0].name)

    def test_interface_with_func_followed_by_function_with_receiver(self):
        result = get_go_function_list('''
            type MyComparator struct{}

            type Comparator interface {
                Handle(func(int) string)
            }

            func (m MyComparator) Handle(f func(int) string) {}
                ''')

        self.assertEqual(1, len(result))
        self.assertEqual("Handle", result[0].name)

    def test_sql_query_with_question_marks(self):
        result = get_go_function_list('''
            func getQuery(dbIndex uint32, tbIndex uint32) string {
                query := fmt.Sprintf(`INSERT INTO online_docs_%d.online_docs_notify_%d
                (a, b, c, d, e, f, g, h, i, j)
                VALUES (?, ?, ?, ?, ?, ?, ?, FROM_UNIXTIME(?), ?, %d)`,
                dbIndex, tbIndex, notifyStatusNew)
                return query
            }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("getQuery", result[0].name)
        self.assertEqual(1, result[0].cyclomatic_complexity)

    def test_generic_function_with_type_param(self):
        result = get_go_function_list('''
            func Map[T any](x T) T { return x }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("Map", result[0].name)
        self.assertEqual(1, result[0].parameter_count)

    def test_generic_function_with_multiple_type_params(self):
        result = get_go_function_list('''
            func Reduce[T any, U any](xs []T, acc U) U { return acc }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("Reduce", result[0].name)
        self.assertEqual(2, result[0].parameter_count)

    def test_generic_function_with_nested_slice_constraint(self):
        result = get_go_function_list('''
            func Clone[S ~[]E, E any](s S) S { return s }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("Clone", result[0].name)
        self.assertEqual(1, result[0].parameter_count)

    def test_generic_method_with_receiver(self):
        result = get_go_function_list('''
            func (r *Box) Get[T any](x T) T { return x }
                ''')
        self.assertEqual(1, len(result))
        self.assertEqual("Get", result[0].name)
        self.assertEqual(1, result[0].parameter_count)

    def test_receive_operator_is_one_token(self):
        result = get_go_function_list('''
            func next(c <-chan int) int { return <-c }
                ''')
        self.assertEqual(14, result[0].token_count)

    def test_shift_and_bit_clear_operators_are_one_token(self):
        result = get_go_function_list('''
            func mask(a uint, n uint) uint {
                a <<= 1
                return (a << n) >> 2 &^ 1
            }
                ''')
        self.assertEqual(25, result[0].token_count)

    def test_catch_and_while_are_names(self):
        result = get_go_function_list('''
            func check(t *testing.T, while bool) {
                catch := func() {
                    recover()
                }
                defer catch()
                t.Log(while)
            }
                ''')
        self.assertEqual(["", "check"], [f.name for f in result])
        self.assertEqual(1, result[1].cyclomatic_complexity)

    def test_compound_assignments_are_one_token(self):
        result = get_go_function_list('''
            func scale(a int) int {
                a *= 2
                a /= 3
                a %= 5
                return a
            }
                ''')
        self.assertEqual(20, result[0].token_count)

    def test_float_literal_is_one_token(self):
        result = get_go_function_list('''
            func half() float64 {
                return 1.5
            }
            func sum(v []float64) (float64, complex128) {
                z := 0x1p-2 + 1e3 + .5 + 1_0.2_5 + 2i + 1e-3 + 2.5e+3i
                return z + v[0].Real(), 1.
            }
                ''')
        self.assertEqual(9, result[0].token_count)
        self.assertEqual(43, result[1].token_count)

    def test_pointer_to_pointer_is_two_tokens(self):
        result = get_go_function_list('''
            func deref(p **int) int {
                return **p
            }
                ''')
        self.assertEqual(15, result[0].token_count)
