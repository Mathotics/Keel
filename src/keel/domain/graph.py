from collections.abc import Mapping, Sequence

Adjacency = Mapping[int, Sequence[int]]


def would_create_cycle(adjacency: Adjacency, source: int, target: int) -> bool:
    """True when adding source → target would close a cycle.

    That happens when the proposed target can already reach the proposed
    source along existing edges. A self-link is a cycle of one.
    """
    return _can_reach(adjacency, start=target, goal=source)


def _can_reach(adjacency: Adjacency, start: int, goal: int) -> bool:
    stack = [start]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if node == goal:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, ()))
    return False
