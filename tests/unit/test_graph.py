from keel.domain.graph import would_create_cycle


def test_a_new_edge_on_an_empty_graph_is_not_a_cycle() -> None:
    assert not would_create_cycle({}, 1, 2)


def test_reversing_an_edge_closes_a_cycle() -> None:
    assert would_create_cycle({1: [2]}, 2, 1)


def test_a_chain_cannot_loop_back_to_its_start() -> None:
    assert would_create_cycle({1: [2], 2: [3]}, 3, 1)


def test_a_shortcut_along_an_existing_chain_is_not_a_cycle() -> None:
    assert not would_create_cycle({1: [2], 2: [3]}, 1, 3)


def test_an_unrelated_edge_is_not_a_cycle() -> None:
    assert not would_create_cycle({1: [2]}, 3, 4)


def test_a_self_link_is_a_cycle() -> None:
    assert would_create_cycle({}, 1, 1)


def test_a_diamond_that_returns_to_the_source_is_a_cycle() -> None:
    adjacency = {1: [2, 3], 2: [4], 3: [4]}
    assert would_create_cycle(adjacency, 4, 1)


def test_a_visited_node_is_not_walked_twice() -> None:
    adjacency = {1: [2, 3], 2: [3], 3: [2]}
    assert not would_create_cycle(adjacency, 4, 1)
