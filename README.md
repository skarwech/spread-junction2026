# Spread dispatch desk (Junction 2026, Bahn challenge)

A system that does a dispatcher's job for one simulated week: it quotes car dealers, posts gigs for freelance
drivers, and keeps at least 90% of won orders on time. Built step by step, each step with its own evidence page.

## Results (level 8, paired runs on the same weeks)

| | Ranked weeks | Margin |
|---|---|---|
| Kit starter (reference week `spread-1`) | 0/1 | −€72,612.51 |
| This desk, 8 weeks incl. the 4 hardest found | **8/8** (worst 92.5% on time) | **+€74,009** (+€9,251 a week) |
| Test final 1 (live clock) | ranked, 100% on time | every request answered in time |

## The ideas

1. **Price to the week**: quote above list; an adaptive multiplier steers toward 40% of real quotes won,
   never below the typical fee × 1.15, and rises when intake is high (`desk/policy.py`, `Learning`).
2. **Fees to the deadline**: open at 0.9× the typical fee, rise to 2× by the last pickup time − 2 h.
3. **Decline what drivers can't carry**: slack under 6 h or a drive over 5 h gets a 4× list quote.
4. **A desk that can't lose its week**: every call journaled and replayed exactly after a crash
   (`desk/journal.py`, `desk/worldio.py`); a client that never sends a POST twice (`desk/client.py`);
   a live desk with a supervised stream and its own quote thread (`desk/live.py`).

## Run it

```sh
python3 -m venv .venv && .venv/bin/pip install https://spread.bahnexpress.com/kit/spread-0.1.0-py3-none-any.whl pytest jsonschema
printf 'SPREAD_URL=https://spread.bahnexpress.com\nSPREAD_KEY=<team key>\n' > .env   # never committed
.venv/bin/python -m pytest -q tests                                          # 90 tests
.venv/bin/python -m desk.runner --level 8 --seed dev-1 --policy priced --param price_mult=1.5   # a practice week
sh tools/final_mac.sh                                                        # the final (see docs/RUNBOOK.md)
```

## Evidence

- `proof/*.html`: one page per step (G0 reproduction, core, policy, live desk, adaptive price, margin push).
- `evidence/`: the sweeps, restart tests and rehearsals each page is built from (`tools/proof_*.py`).
- `docs/spread_spec.md`: the plan and the decision log (every decision with its seeds and run ids);
  `docs/spec_delta.md`: the plan checked line by line against the challenge's rules.
