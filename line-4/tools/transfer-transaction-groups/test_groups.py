"""Offline regressions; synthetic mutations are tests, never chain evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location("transaction_groups_test", HERE / "groups.py")
groups = importlib.util.module_from_spec(spec)
spec.loader.exec_module(groups)


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.capture = groups.reader.read_capture(
            HERE.parent / "transfer-crosscheck" / "publicnode.json")

    def rebuild(self, capture):
        events, duplicates = groups.window.validate_logs(
            capture["raw_logs"], capture["decimals"], capture["token_address"],
            capture["from_block"], capture["to_block"])
        capture.update(transfers=events, transfer_count=len(events), duplicate_count=duplicates)
        return capture

    def test_real_transaction_and_intermediate_endpoint(self):
        result = groups.report(self.capture)
        self.assertEqual(result["observed_transaction_count"], 1)
        tx = result["transactions"][0]
        self.assertEqual(tx["transaction_hash"], self.capture["transfers"][0]["transaction_hash"])
        self.assertEqual(tx["transaction_index"], 238)
        self.assertEqual(tx["log_indexes"], [642, 644, 645])
        self.assertEqual(tx["endpoint_count"], 4)
        self.assertEqual(sum(int(f["net_raw"]) for f in tx["endpoints"]), 0)
        relay = next(f for f in tx["endpoints"]
                     if f["address"] == self.capture["transfers"][1]["to"])
        self.assertEqual(relay["touching_count"], 2)
        self.assertEqual(relay["net_raw"], "0")
        self.assertEqual(tx["event_total_raw"], "266646694671317841507957")

    def test_raw_order_and_duplicate_logs_do_not_change_groups(self):
        before = groups.report(self.capture)
        changed = copy.deepcopy(self.capture)
        changed["raw_logs"].reverse()
        changed["raw_logs"].append(copy.deepcopy(changed["raw_logs"][0]))
        after = groups.report(self.rebuild(changed))
        self.assertEqual(before["transactions"], after["transactions"])
        self.assertEqual(after["duplicate_log_count"], 1)
        self.assertEqual(after["transfer_count"], 3)

    def test_empty_window_has_no_transactions(self):
        self.capture["raw_logs"] = []
        report = groups.report(self.rebuild(self.capture))
        self.assertEqual(report["transactions"], [])
        self.assertEqual(report["observed_transaction_count"], 0)

    def test_one_hash_with_different_index_is_refused(self):
        self.capture["raw_logs"][1]["transactionIndex"] = "0xef"
        with self.assertRaisesRegex(groups.window.RpcError, "conflicting mined positions"):
            groups.report(self.rebuild(self.capture))

    def test_different_hash_in_same_position_is_refused(self):
        self.capture["raw_logs"][1]["transactionHash"] = "0x" + "ab" * 32
        with self.assertRaisesRegex(groups.window.RpcError, "one mined position"):
            groups.report(self.rebuild(self.capture))

    def test_transaction_index_must_follow_block_log_order(self):
        for index, log in enumerate(self.capture["raw_logs"]):
            log["transactionHash"] = "0x" + format(index + 1, "064x")
            log["transactionIndex"] = hex(10 - index)
        with self.assertRaisesRegex(groups.window.RpcError, "decrease"):
            groups.report(self.rebuild(self.capture))

    def test_multiple_transactions_have_chain_order(self):
        for index, log in enumerate(self.capture["raw_logs"]):
            log["transactionHash"] = "0x" + format(index + 1, "064x")
            log["transactionIndex"] = hex(10 + index)
        report = groups.report(self.rebuild(self.capture))
        self.assertEqual(report["observed_transaction_count"], 3)
        self.assertEqual([t["transaction_index"] for t in report["transactions"]], [10, 11, 12])

    def test_one_hash_across_blocks_is_refused(self):
        log = self.capture["raw_logs"][0]
        log["blockNumber"] = hex(self.capture["from_block"])
        log["blockHash"] = self.capture["from_block_anchor"]["hash"]
        with self.assertRaisesRegex(groups.window.RpcError, "conflicting mined positions"):
            groups.report(self.rebuild(self.capture))

    def test_transaction_positions_restart_in_each_block(self):
        log = self.capture["raw_logs"][0]
        log["blockNumber"] = hex(self.capture["from_block"])
        log["blockHash"] = self.capture["from_block_anchor"]["hash"]
        log["transactionHash"] = "0x" + "ab" * 32
        # Same transaction index as the later block is a different position.
        report = groups.report(self.rebuild(self.capture))
        self.assertEqual(report["observed_transaction_count"], 2)
        self.assertEqual([t["block"] for t in report["transactions"]],
                         [self.capture["from_block"], self.capture["to_block"]])
        self.assertEqual([t["transaction_index"] for t in report["transactions"]], [238, 238])

    def test_self_transfer_and_zero_value_touch_once(self):
        log = self.capture["raw_logs"][0]
        log["topics"][2] = log["topics"][1]
        log["data"] = "0x" + "00" * 32
        self.capture["raw_logs"] = [log]
        tx = groups.report(self.rebuild(self.capture))["transactions"][0]
        self.assertEqual(tx["endpoint_count"], 1)
        self.assertEqual(tx["endpoints"][0]["touching_count"], 1)
        self.assertEqual(tx["endpoints"][0]["net_raw"], "0")

    def test_uint256_amounts_use_integer_math(self):
        for log in self.capture["raw_logs"]:
            log["data"] = "0x" + "ff" * 32
        tx = groups.report(self.rebuild(self.capture))["transactions"][0]
        self.assertEqual(tx["event_total_raw"], str(3 * (2**256 - 1)))
        self.assertEqual(sum(int(f["net_raw"]) for f in tx["endpoints"]), 0)

    def test_zero_decimals_and_imd_identity(self):
        self.capture["decimals"] = 0
        self.capture["token"] = "IMD"
        self.capture["token_address"] = groups.window.TOKENS["imd"]
        for log in self.capture["raw_logs"]:
            log["address"] = self.capture["token_address"]
        report = groups.report(self.rebuild(self.capture))
        self.assertEqual(report["token"], "IMD")
        tx = report["transactions"][0]
        self.assertEqual(tx["event_total"], tx["event_total_raw"])

    def test_forged_decoded_summary_is_refused(self):
        self.capture["transfers"][0]["raw_value"] = "1"
        with self.assertRaisesRegex(groups.window.RpcError, "summary disagrees"):
            groups.report(self.capture)

    def test_removed_raw_log_is_refused(self):
        self.capture["raw_logs"][0]["removed"] = True
        with self.assertRaises(groups.window.RpcError):
            groups.report(self.capture)

    def test_demo_cli_and_workspace_file_boundaries(self):
        run = subprocess.run([sys.executable, "-B", str(HERE / "groups.py"), "--demo"],
                             cwd=ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["observed_transaction_count"], 1)
        scratch = ROOT / "test" / "scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            target = Path(folder) / "capture.json"
            target.write_text(json.dumps(self.capture))
            link = Path(folder) / "link.json"
            link.symlink_to(target)
            for path in (link, str(target.parent / ".." / target.parent.name / target.name)):
                with self.subTest(path=str(path)):
                    bad = subprocess.run([sys.executable, "-B", str(HERE / "groups.py"),
                                          "--capture", str(path)], cwd=ROOT,
                                         capture_output=True, text=True, timeout=10)
                    self.assertEqual(bad.returncode, 2)
                    self.assertEqual(bad.stdout, "")


if __name__ == "__main__":
    unittest.main()
