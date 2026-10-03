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

    def test_result_type_with_braces(self):
        result = get_go_function_list('''
            func set(names []string) map[string]struct{} {
                seen := map[string]struct{}{}
                for _, name := range names {
                    if name != "" {
                        seen[name] = struct{}{}
                    }
                }
                return seen
            }
            func after(a int) int {
                return a
            }
                ''')
        self.assertEqual(["set", "after"], [f.name for f in result])
        self.assertEqual(3, result[0].cyclomatic_complexity)
        self.assertEqual(2, result[0].start_line)
        self.assertEqual(10, result[0].end_line)

    def test_result_type_with_a_struct_with_fields(self):
        result = get_go_function_list('''
            func pair(a int) struct{ x, y int } {
                if a > 0 {
                    return struct{ x, y int }{a, a}
                }
                return struct{ x, y int }{0, 0}
            }
                ''')
        self.assertEqual(["pair"], [f.name for f in result])
        self.assertEqual(2, result[0].cyclomatic_complexity)
        self.assertEqual(7, result[0].end_line)

    def test_function_type_in_a_struct_type_inside_a_function(self):
        result = get_go_function_list('''
            func table(t *testing.T) {
                for _, test := range []struct {
                    name    string
                    consume func(a int, b chan struct{})
                    closed  bool
                }{
                    {name: "a"},
                } {
                    if test.closed {
                        t.Log(test.name)
                    }
                }
            }

            func after() {}
                ''')
        self.assertEqual(["table", "after"], [f.name for f in result])
        self.assertEqual(3, result[0].cyclomatic_complexity)
        self.assertEqual(14, result[0].end_line)

    def test_variable_of_function_type(self):
        result = get_go_function_list('''
            func outer(a int) int {
                var check func(int) bool
                check = isPositive
                if check(a) {
                    return a
                }
                return 0
            }
                ''')
        self.assertEqual(["outer"], [f.name for f in result])
        self.assertEqual(2, result[0].cyclomatic_complexity)

    def test_function_without_a_name_at_the_top_level(self):
        result = get_go_function_list('''
            var hook = func(a int, b string) (int, error) {
                return a, nil
            }

            var servers = map[string]newServer{
                "plain": func(t *testing.T, h Handler) *Server {
                    return NewServer(h)
                },
            }

            var isBusy = func(err error) bool { return false }
                ''')
        self.assertEqual(["", "", ""], [f.name for f in result])
        self.assertEqual([(2, 4), (7, 9), (12, 12)],
                         [(f.start_line, f.end_line) for f in result])
        self.assertEqual([2, 2, 1], [f.parameter_count for f in result])

    def test_function_type_followed_by_a_method(self):
        result = get_go_function_list('''
            var hook func(res *Response, err error)

            func (c *Client) do(req *Request) (res *Response, err error) {
                if hook != nil {
                    defer hook(res, err)
                }
                return c.send(req)
            }
                ''')
        self.assertEqual(["do"], [f.name for f in result])
        self.assertEqual(2, result[0].cyclomatic_complexity)
        self.assertEqual(1, result[0].parameter_count)

    def test_condition_after_a_variable_of_function_type(self):
        result = get_go_function_list('''
            func serve(c Conn, opts *Opts) {
                var newf func(*serverConn)
                if inTests {
                    newf = opts.hook
                }
                run(c, opts, newf)
            }
                ''')
        self.assertEqual(["serve"], [f.name for f in result])
        self.assertEqual(2, result[0].cyclomatic_complexity)
        self.assertEqual(7, result[0].nloc)
        self.assertEqual(36, result[0].token_count)
