"""Straight-line synthetic orchestration, with opaque application-owned behavior."""

from trial_app.runtime import load_market as _market
from trial_app.runtime import load_protocol as _protocol
from trial_app.runtime import run_benchmark as _benchmark


def load_market(path):
    return _market(path=path)


def load_protocol(path):
    return _protocol(path=path)


def run_benchmark(dataset, protocol, candidate):
    return _benchmark(dataset=dataset, protocol=protocol, candidate=candidate)


def workflow(market_path, protocol_path, candidate):
    dataset = load_market(path=market_path)
    protocol = load_protocol(path=protocol_path)
    result = run_benchmark(dataset=dataset, protocol=protocol, candidate=candidate)
    return result
