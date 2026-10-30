from spectra.core.geometry import Candidate, ios, iou, merge_candidates, segment_intersects_box, tile_grid


def test_tile_grid_covers_page_without_padding():
    tiles = tile_grid(6622, 4677, 640, 160)
    assert len(tiles) == 14 * 10
    assert max(t.x + t.size for t in tiles) == 6622
    assert max(t.y + t.size for t in tiles) == 4677
    assert min(t.x for t in tiles) == 0
    # every pixel column is covered
    covered = set()
    for t in tiles:
        covered.update(range(t.x, t.x + t.size))
    assert covered == set(range(6622))


def test_ios_is_one_for_truncated_copy():
    whole = (0, 0, 10, 10)
    part = (0, 0, 4, 10)
    assert ios(whole, part) == 1.0
    assert iou(whole, part) == 0.4


def test_merge_joins_symbol_split_by_tile_edge_and_keeps_neighbours():
    cands = [
        Candidate((100, 100, 120, 110), "valve", 0.9),  # whole, from tile A
        Candidate((110, 100, 120, 110), "valve", 0.6, truncated=True),  # cut by tile B's edge
        Candidate((125, 100, 145, 110), "valve", 0.8),  # a real neighbour
        Candidate((101, 100, 121, 110), "flange", 0.5),  # other class at the same spot
    ]
    out = merge_candidates(cands)
    assert [c.box for c in out] == [(100, 100, 120, 110), (125, 100, 145, 110)]
    assert out[0].alternatives == {"flange": 0.5}


def test_segment_box_intersection():
    assert segment_intersects_box((0, 5), (20, 5), (5, 0, 10, 10))
    assert not segment_intersects_box((0, 20), (20, 20), (5, 0, 10, 10))
