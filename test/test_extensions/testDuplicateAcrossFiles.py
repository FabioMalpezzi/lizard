import unittest
from unittest.mock import patch
from lizard_ext.lizardduplicate import LizardExtension as DuplicateDetector
from lizard import analyze_files, get_extensions
from .duplicate_c_function_builder import CFunctionBuilder


class TestDuplicateExtensionAcrossFiles(unittest.TestCase):

    def setUp(self):
        self.detector = DuplicateDetector()
        self.builder = CFunctionBuilder()

    @patch('lizard_core.file_analyzer.auto_read')
    def detect(self, source_files, auto_read):
        auto_read.side_effect = lambda filename: source_files[filename]
        extensions = get_extensions([self.detector])
        list(analyze_files(sorted(source_files.keys()), exts=extensions))
        return list(self.detector.get_duplicates(30))

    def test_basic_duplicate(self):
        duplicates = self.detect({
                'f1.cpp': self.builder
                    .six_line_function()
                    .build(),
                'f2.cpp': self.builder
                    .five_line_function()
                    .six_line_function()
                .build()
                })
        self.assertEqual(1, len(duplicates))
        self.assertEqual("f1.cpp", duplicates[0][0].file_name)
        self.assertEqual("f2.cpp", duplicates[0][1].file_name)
        self.assertEqual(1, duplicates[0][0].start_line)
        self.assertEqual(6, duplicates[0][0].end_line)
        self.assertEqual(6, duplicates[0][1].start_line)
        self.assertEqual(11, duplicates[0][1].end_line)
        self.assertAlmostEqual(0.666666666, self.detector.duplicate_rate())

    def test_more_duplicate(self):
        duplicates = self.detect({
                'f1.cpp': self.builder
                    .six_line_function()
                    .build(),
                'f2.cpp': self.builder
                    .six_line_function()
                    .build(),
                'f3.cpp': self.builder
                    .six_line_function()
                    .build()
                })
        self.assertEqual(1, len(duplicates))

    LONG_FUNCTION = '''double %s(const double *q, const double *p, int n, double rate) {
  double total = 0.0;
  for (int i = 0; i < n; i++) {
    if (q[i] > 0 && p[i] > 0) {
      double part = q[i] * p[i];
      double tax = part * rate;
      total += part + tax;
    } else if (q[i] < 0) {
      total += 0;
    }
  }
  double rounded = total * 100 / 100;
  if (rounded < 0) {
    return 0;
  }
  return rounded;
}
'''

    def test_duplicate_of_a_whole_file_ends_at_its_last_line(self):
        duplicates = self.detect({
                'f1.cpp': self.LONG_FUNCTION % 'total_of_rows',
                'f2.cpp': self.LONG_FUNCTION % 'sum_of_orders',
                })
        self.assertEqual(1, len(duplicates))
        self.assertEqual(
            [('f1.cpp', 1, 17), ('f2.cpp', 1, 17)],
            [(s.file_name, s.start_line, s.end_line) for s in duplicates[0]])

    def test_duplicate_rate_of_two_copies_is_not_above_one(self):
        self.detect({
                'f1.cpp': self.LONG_FUNCTION % 'total_of_rows',
                'f2.cpp': self.LONG_FUNCTION % 'sum_of_orders',
                })
        self.assertEqual(1, self.detector.duplicate_rate())

    def test_duplicate_ends_at_the_same_line_with_other_files_before(self):
        duplicates = self.detect({
                'f0.cpp': self.builder.different_six_line_function().build(),
                'f1.cpp': self.LONG_FUNCTION % 'total_of_rows',
                'f2.cpp': self.LONG_FUNCTION % 'sum_of_orders',
                })
        self.assertEqual(
            [[('f1.cpp', 1, 17), ('f2.cpp', 1, 17)]],
            [[(s.file_name, s.start_line, s.end_line) for s in d]
             for d in duplicates])
