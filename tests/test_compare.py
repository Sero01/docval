import json

from eval.compare import regressions


def result(f1, header, valpass):
    return {"aggregates": {"txn_f1": f1, "header_field_accuracy": header,
                           "validation_pass_rate": valpass}}


def test_no_regression_when_equal_or_better():
    assert regressions(result(0.9, 0.9, 0.9), result(0.9, 0.85, 0.9)) == []


def test_drop_beyond_tolerance_is_flagged():
    regs = regressions(result(0.80, 0.9, 0.9), result(0.90, 0.9, 0.9),
                       tolerance=0.01)
    assert regs and "txn_f1" in regs[0]
