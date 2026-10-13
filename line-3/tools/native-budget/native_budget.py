#!/usr/bin/env python3
"""Compare an unsigned EIP-1559 envelope's maximum ETH need with an asserted balance."""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fee-envelope"))
import fee_envelope

UINT256_MAX = 2**256 - 1
MAX_INPUT_CHARS = fee_envelope.MAX_INPUT_CHARS


def wei_amount(text):
    if not isinstance(text, str) or len(text) > 78 or re.fullmatch(r"0|[1-9][0-9]*", text) is None:
        raise ValueError("balance must be canonical nonnegative decimal wei")
    value = int(text)
    if value > UINT256_MAX:
        raise ValueError("balance exceeds uint256")
    return value


def compare(transaction_hex, balance_text):
    balance = wei_amount(balance_text)
    envelope = fee_envelope.summarize(transaction_hex)
    required = int(envelope["valuePlusFeeCeilingWei"])
    return {
        "schema": "native-budget/v1",
        "balanceWei": str(balance),
        "balanceEth": fee_envelope.eth(balance),
        "maximumNativeValueAndFeeWei": str(required),
        "maximumNativeValueAndFeeEth": fee_envelope.eth(required),
        "surplusWei": str(max(balance - required, 0)),
        "shortfallWei": str(max(required - balance, 0)),
        "coversMaximumEnvelope": balance >= required,
        "assumption": "Balance is a caller assertion; no account or chain state was queried.",
        "feeBasis": "gasLimit multiplied by maxFeePerGas; actual gas may be lower.",
        "transaction": envelope,
    }


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--balance-wei", required=True, help="asserted available native ETH in wei")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--demo", action="store_true")
    source.add_argument("--transaction", help="original unsigned type-2 RLP as 0x hex")
    source.add_argument("--stdin", action="store_true", help="read 0x hex from standard input")
    args = parser.parse_args(argv)
    try:
        text = (fee_envelope.tx_decode.demo_transaction() if args.demo else
                sys.stdin.read(MAX_INPUT_CHARS + 1).strip() if args.stdin else args.transaction)
        if args.stdin and len(text) > MAX_INPUT_CHARS:
            raise ValueError("transaction text exceeds the 128 KiB envelope limit")
        report = compare(text, args.balance_wei)
    except (ValueError, UnicodeError) as error:
        print("error: " + str(error), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["coversMaximumEnvelope"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
