"""
Dependency-free tests for sim.player_gen.assign_ceiling_label (no pytest needed).

Run from backend/:   python tests/test_ceiling_label.py
Exits non-zero on failure.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sim.player_gen import assign_ceiling_label, assign_label, CEILING_JITTER  # noqa: E402

_failures = []


def check(cond, msg):
    if not cond:
        _failures.append(msg)
        print(f"  FAIL: {msg}")
    else:
        print(f"  ok:   {msg}")


VALID = {'High Upside', 'Some Upside', 'Near Ceiling'}


def test_always_valid_grade():
    print("test_always_valid_grade:")
    for pid in range(200):
        for comp in (35, 55, 66, 74, 84):
            for pot in (comp, comp + 8, comp + 20, 99):
                g = assign_ceiling_label(comp, pot, pid)
                if g not in VALID:
                    _failures.append(f"bad grade {g!r} for comp={comp} pot={pot}")
                    break
    check(not _failures, "every (comp, pot, id) yields a valid grade")


def test_deterministic():
    print("test_deterministic:")
    pid = uuid.uuid4()
    a = assign_ceiling_label(60, 78, pid)
    b = assign_ceiling_label(60, 78, pid)
    check(a == b, f"same id is stable across calls ({a})")


def test_finished_product_reads_near_ceiling():
    print("test_finished_product_reads_near_ceiling:")
    # composite == potential: no headroom, no jitter can invent upside (jitter only
    # pushes the *perceived* ceiling, and a tier gain needs real distance).
    near = all(assign_ceiling_label(70, 70, pid) == 'Near Ceiling' for pid in range(100))
    check(near, "composite == potential is always 'Near Ceiling'")


def test_big_gap_reads_high_upside():
    print("test_big_gap_reads_high_upside:")
    # 45 (Weak) -> 90 (Elite) is 4 tiers; even worst-case jitter can't drop it below
    # a 2-tier delta, so it must read 'High Upside' for every player.
    allhigh = all(assign_ceiling_label(45, 90, pid) == 'High Upside' for pid in range(200))
    check(allhigh, "a 4-tier gap is always 'High Upside' regardless of jitter")


def test_jitter_only_near_boundary():
    print("test_jitter_only_near_boundary:")
    # A player whose potential sits deep inside a tier (>CEILING_JITTER from both
    # edges) cannot be flipped by jitter — the grade is unanimous across ids.
    # composite 66 (Average), potential 78 (Above Avg, 73–82: 5pt from lower edge > 3).
    grades = {assign_ceiling_label(66, 78, pid) for pid in range(300)}
    check(grades == {'Some Upside'},
          f"potential clear of tier edges is unanimous (got {grades})")


def test_boundary_player_gets_fuzz():
    print("test_boundary_player_gets_fuzz:")
    # potential 73 sits exactly on the Above Avg edge; -jitter drops it into Average.
    # composite 66 (Average). So the grade should split between 'Some Upside' (tier
    # gained) and 'Near Ceiling' (jittered back down) — proving the fuzz is real.
    grades = {assign_ceiling_label(66, 73, pid) for pid in range(300)}
    check(len(grades) > 1, f"a player on a tier edge sees fuzz (got {grades})")


if __name__ == '__main__':
    for t in (
        test_always_valid_grade,
        test_deterministic,
        test_finished_product_reads_near_ceiling,
        test_big_gap_reads_high_upside,
        test_jitter_only_near_boundary,
        test_boundary_player_gets_fuzz,
    ):
        t()

    print("\n" + "=" * 50)
    if _failures:
        print(f"{len(_failures)} FAILURE(S):")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("ALL TESTS PASSED")
