import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_budget
from fee_envelope import tx_decode


class NativeBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tx = tx_decode.demo_transaction()
        self.required = 200_000_000_000_000

    def test_exact_coverage_and_one_wei_shortfall(self):
        self.assertTrue(native_budget.compare(self.tx, str(self.required))["coversMaximumEnvelope"])
        report = native_budget.compare(self.tx, str(self.required - 1))
        self.assertFalse(report["coversMaximumEnvelope"])
        self.assertEqual(report["shortfallWei"], "1")

    def test_value_is_included_and_surplus_exact(self):
        fields, end = tx_decode.rlp_item(bytes.fromhex(self.tx[2:]), 1)
        self.assertEqual(end, len(bytes.fromhex(self.tx[2:])))
        fields[6] = (17).to_bytes(1, "big")
        value_tx = "0x02" + tx_decode.rlp_encode(fields).hex()
        report = native_budget.compare(value_tx, str(self.required + 22))
        self.assertEqual(report["maximumNativeValueAndFeeWei"], str(self.required + 17))
        self.assertEqual(report["surplusWei"], "5")

    def test_balance_canonical_and_bounded(self):
        for value in ("01", "-1", "1.0", str(2**256)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                native_budget.wei_amount(value)


if __name__ == "__main__":
    unittest.main()
