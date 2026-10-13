# Unsigned native balance budget

`native_budget.py` compares an unsigned type-2 transaction's maximum ETH
requirement (native value plus `gasLimit × maxFeePerGas`) with a balance in wei
that the caller supplies. It reports exact surplus or shortfall and exits 1
when the asserted balance does not cover that ceiling. All calculations use
integer wei. The tool reads no account state, wallet, key, environment variable,
or network; it does not sign or send. A balance assertion can be stale or wrong,
and actual gas cost may be lower than the fee-cap ceiling. ZTO and IMD calls
still require ETH for Ethereum gas.

## Try it

```sh
python3 -B line-3/tools/native-budget/native_budget.py --balance-wei 200000000000000 --demo
```

Tried locally: this printed a 0.0002 ETH asserted balance against the
synthetic unsigned ZTO `totalSupply()` example's exact 0.0002 ETH maximum fee
need, reporting zero shortfall and coverage. This is an offline calculation,
not a live balance or chain observation. Requires only Python's standard
library and the committed sibling `fee-envelope` and decoder modules.
