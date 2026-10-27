"""Test settings shared by every test file.

The real game sprite sheets used by some tests (tests/samples/*.png) are not in the public repository, because they
belong to their games' owners. A test that needs one of them (directly or through a fixture) is skipped, with the
reason shown, when the sheet is missing."""
import inspect
from pathlib import Path

import pytest

SAMPLES = Path(__file__).parent / "samples"
SHEETS = ("barbarian", "commando", "samurai", "sonic_2", "streets_of_rage_2", "turrican_2")


def _sources(item) -> str:
    texts = []
    try:
        texts.append(inspect.getsource(item.function))
    except (OSError, TypeError):
        pass
    for defs in item._fixtureinfo.name2fixturedefs.values():
        for d in defs:
            try:
                texts.append(inspect.getsource(d.func))
            except (OSError, TypeError):
                pass
    return "\n".join(texts)


def pytest_collection_modifyitems(config, items):
    missing = [s for s in SHEETS if not (SAMPLES / f"{s}.png").exists()]
    if not missing:
        return
    for item in items:
        text = _sources(item)
        gone = [s for s in missing if f'"{s}' in text or f"'{s}" in text]
        if gone:
            item.add_marker(pytest.mark.skip(reason=f"needs sample sheet {gone[0]}.png, which is not in the public "
                                                    "repository"))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """A test that reaches a missing sample sheet through a helper function is reported as skipped, not failed."""
    outcome = yield
    rep = outcome.get_result()
    exc = call.excinfo
    if rep.failed and exc is not None and exc.errisinstance(FileNotFoundError) and \
            any(f"{s}.png" in str(exc.value) for s in SHEETS):
        rep.outcome = "skipped"
        rep.longrepr = (str(item.fspath), item.location[1] or 0,
                        "Skipped: needs a sample sheet that is not in the public repository")
