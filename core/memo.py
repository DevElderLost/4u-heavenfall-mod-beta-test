"""Hand-written memos in one place: `remember` is for caches that `functools` cannot hold (keyed by `id()` of an
object, or kept per object or per folder scan) and the hook through which the test recorder watches them.

`set_observer(observer)` installs `observer(store, key, make) -> value`, which then decides what `remember` returns
(it may call `make` itself, or serve a stored value); `set_observer(None)` removes it. Tiny and dependency-free.
"""
_observer = None


def set_observer(observer) -> None:
    """Install the observer `observer(store, key, make) -> value`, or None to remove it."""
    global _observer
    _observer = observer


def remember(store: dict, key, make):
    """`store[key]` when present, else `store[key] = make()` (an installed observer decides instead)."""
    if _observer is not None:
        return _observer(store, key, make)
    if key not in store:
        store[key] = make()
    return store[key]
