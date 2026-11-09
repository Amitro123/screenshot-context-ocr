import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from output_checks import hebrew_check, preservation, table_text


def grid(rows):
    return [{'text':text, 'left':str(20+column*200), 'top':str(20+row*50),
             'width':str(len(text)*10), 'height':'20'}
            for row, cells in enumerate(rows) for column, text in enumerate(cells)]


class OutputChecksTests(unittest.TestCase):
    def test_small_or_non_hebrew_sample_is_not_judged(self):
        self.assertFalse(hebrew_check('שלום')['judged'])
        self.assertFalse(hebrew_check('English only')['judged'])
        self.assertFalse(hebrew_check('مرحبا بالعالم')['judged'])

    def test_final_forms_and_reversal(self):
        self.assertTrue(hebrew_check('אךב אםג שלום')['suspicious_midword'])
        self.assertTrue(hebrew_check('םולש ןויסנ ךרד')['possible_reversal'])
        self.assertFalse(hebrew_check('שלום אנשים עובדים')['possible_reversal'])
        self.assertFalse(hebrew_check('שָׁלוֹם אֲנָשִׁים עוֹבְדִים')['suspicious_midword'])

    def test_known_recognition_errors_are_not_certified(self):
        check = hebrew_check('צילום מסך ואתה YAN על המכונה שלך')
        self.assertTrue(check['judged'])
        self.assertFalse(check['possible_reversal'])
        # This heuristic cannot diagnose a Hebrew word recognized as Latin.
        self.assertFalse(check['suspicious_midword'])

    def test_preservation_detects_number_change_and_duplicate_loss(self):
        checks = preservation('27 12 12', '2/ 12')
        self.assertFalse(checks['number_inventory_preserved'])
        self.assertEqual(checks['missing_numbers'], {'27':1, '12':1})
        self.assertFalse(checks['word_inventory_preserved'])
        self.assertEqual(checks['scope'], 'ocr_text_to_output_only')

    def test_simple_table_and_no_invented_header(self):
        rows = [('TEAM','COST'), ('ALPHA','12'), ('BRAVO','27')]
        raw = '\n'.join(' '.join(row) for row in rows)
        text, result = table_text(raw, grid(rows))
        self.assertEqual(text, 'TEAM\tCOST\nALPHA\t12\nBRAVO\t27')
        self.assertEqual(result['status'], 'inferred')
        self.assertFalse(result['structure_verified'])

    def test_rtl_columns_without_reversing_digits(self):
        rows = [('12','עובדים'), ('27','הנהלה'), ('340','עלות')]
        raw = '\n'.join(' '.join(row) for row in rows)
        text, result = table_text(raw, grid(rows), 'rtl')
        self.assertEqual(text, 'עובדים\t12\nהנהלה\t27\nעלות\t340')
        self.assertEqual(result['direction'], 'rtl')

    def test_missing_cell_returns_exact_raw_text(self):
        rows = [('TEAM','COST'), ('ALPHA','12'), ('BRAVO',)]
        raw = 'TEAM COST\nALPHA 12\nBRAVO'
        text, result = table_text(raw, grid(rows))
        self.assertEqual(text, raw)
        self.assertEqual(result['reason'], 'unequal_cell_counts')

    def test_misalignment_refuses_structure(self):
        rows = [('A','B'), ('C','D'), ('E','F')]; words=grid(rows)
        words[-1]['left']='340'
        text, result = table_text('A B C D E F', words)
        self.assertEqual(result['status'], 'fallback')

    def test_tsv_missing_number_refuses_structure(self):
        rows=[('A','12'),('B','27'),('C','340')]
        text,result=table_text('A 12 B 27 C 340 999',grid(rows))
        self.assertEqual(result['reason'], 'content_inventory_mismatch')
        self.assertIn('999',text)

    def test_table_does_not_correct_recognition(self):
        rows=[('A','12'),('B','2/'),('C','340')]
        text,result=table_text('A 12 B 2/ C 340',grid(rows))
        self.assertEqual(result['status'],'inferred')
        self.assertIn('2/',text)
        self.assertFalse(result['structure_verified'])

    def test_malformed_boxes_fall_back(self):
        self.assertEqual(table_text('raw', [{'text':'raw'}])[0], 'raw')
        self.assertEqual(table_text('raw', [])[1]['status'], 'fallback')


if __name__ == '__main__':
    unittest.main()
