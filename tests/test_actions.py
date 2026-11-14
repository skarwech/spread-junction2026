"""Action builders and the pre-flight validator, checked against the server's own contract (openapi.json)."""
import copy
import json
import random
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

from desk import actions as A

ROOT = Path(__file__).resolve().parents[1]
OPENAPI = json.loads((ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
_registry = Registry().with_resource("urn:openapi", Resource.opaque(OPENAPI))
SCHEMA = Draft202012Validator({"$ref": "urn:openapi#/components/schemas/Action"}, registry=_registry)


def schema_ok(action) -> bool:
    return SCHEMA.is_valid(action)


def base_actions() -> list[dict]:
    window = A.window(600, 1200)
    stops = [A.stop("r1", 0, "pickup", window=window, with_plates=True, with_charging=False), A.stop("r1", 0, "delivery")]
    schedule = [A.fee_step(600, 5000), A.fee_step(660, 5500)]
    return [
        A.quote("r1", {"next_day": 12000, "same_day": 15000}),
        A.post(stops, experienced=True, manual_licence=False, schedule=schedule),
        A.offer("g1", "d1", 4800),
        A.reprice("g1", schedule),
        A.withdraw("g1"),
        A.release("g1"),
    ]


@pytest.mark.parametrize("action", base_actions(), ids=lambda a: a["type"])
def test_every_builder_output_is_accepted_by_the_server_schema(action):
    assert schema_ok(action)
    assert A.errors(action) == []


def test_builders_refuse_what_the_server_would_refuse():
    with pytest.raises(A.InvalidAction):
        A.quote("r1", {})  # RULES.md:47: a quote needs at least one price
    with pytest.raises(A.InvalidAction):
        A.quote("r1", {"next_day": 0})
    with pytest.raises(A.InvalidAction):
        A.post([A.stop("r1", 0, "pickup")], experienced=False, manual_licence=False, schedule=[A.fee_step(0, 1)])
    with pytest.raises(A.InvalidAction):
        A.reprice("g1", [A.fee_step(10, 5000), A.fee_step(20, 4000)])  # RULES.md:64: fees never fall
    with pytest.raises(A.InvalidAction):
        A.reprice("g1", [A.fee_step(20, 5000), A.fee_step(10, 6000)])  # steps in time order
    with pytest.raises(A.InvalidAction):
        A.reprice("g1", [A.fee_step(i, 100 + i) for i in range(49)])
    with pytest.raises(A.InvalidAction):
        A.offer("g1", "d1", True)  # a bool is not a fee
    with pytest.raises(A.InvalidAction):
        A.offer("g1", "d1", 4800.0)  # cents are whole numbers, sent as integers


def test_world_rules_are_reported_separately_from_schema_errors():
    falling = {"type": "reprice", "gigId": "g1", "schedule": [{"at": 10, "feeCents": 5000}, {"at": 20, "feeCents": 4000}]}
    assert schema_ok(falling)
    assert A.schema_errors(falling) == []
    assert A.rule_errors(falling) and A.errors(falling)


def test_batch_limits():
    good = base_actions()
    assert A.batch_errors(good) == []
    assert A.batch_errors([]) == ["a batch needs 1 to 50 actions"]
    assert A.batch_errors(good * 9) == ["a batch needs 1 to 50 actions"]
    bad = good + [{"type": "quote", "requestId": "", "prices": {"next_day": 1}}]
    assert A.batch_errors(bad)[0].startswith("[6].requestId")


# ---- the validator against the schema, on mutations of valid actions ------------------------------------

WRONG_VALUES = [None, "", "x" * 65, "x", -1, 0, 1, 2, 9007199254740991, 9007199254740992, 1.5, 3.0, True, False, [], {}, {"from": 1}]


def mutations(rng: random.Random, action: dict) -> dict:
    """One random structural change to a valid action: a field removed, retyped or added, at any depth."""
    a = copy.deepcopy(action)
    paths = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                paths.append(path + [k])
                walk(v, path + [k])
        elif isinstance(node, list):
            for i, v in enumerate(node):
                paths.append(path + [i])
                walk(v, path + [i])
    walk(a, [])
    path = rng.choice(paths)
    parent = a
    for p in path[:-1]:
        parent = parent[p]
    key, move = path[-1], rng.random()
    if move < 0.15 and isinstance(parent, dict):
        del parent[key]
    elif move < 0.25 and isinstance(parent, list):
        parent.pop(key) if rng.random() < 0.5 else parent.extend(copy.deepcopy(parent) * rng.choice([1, 30]))
    elif move < 0.35 and isinstance(parent, dict):
        parent[rng.choice(["extra", "same_day", "next_day", "within_3_days", "two_days"])] = rng.choice(WRONG_VALUES)
    else:
        parent[key] = rng.choice(WRONG_VALUES + ["pickup", "delivery", "quote", "post"])
    return a


def test_validator_is_never_looser_than_the_server_schema_and_differs_only_on_whole_floats():
    rng = random.Random(20261113)
    cases = [mutations(rng, rng.choice(base_actions())) for _ in range(5000)]
    accepted_by_us_rejected_by_server = [c for c in cases if not A.schema_errors(c) and not schema_ok(c)]
    rejected_by_us_only = [c for c in cases if A.schema_errors(c) and schema_ok(c)]
    assert accepted_by_us_rejected_by_server == []  # soundness: never send what the server refuses
    # we are stricter in one documented way: an integral float such as 3.0 (the schema calls it an integer)
    assert all("3.0" in json.dumps(c) or "float" in " ".join(A.schema_errors(c)) for c in rejected_by_us_only)
    agree = sum((not A.schema_errors(c)) == schema_ok(c) for c in cases)
    assert agree / len(cases) > 0.97
    assert 300 < sum(schema_ok(c) for c in cases) < 4700  # the fuzz exercises both sides
