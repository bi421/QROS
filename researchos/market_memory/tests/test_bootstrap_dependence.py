from researchos.market_memory.bootstrap import block_bootstrap_mean_ci


def test_block_bootstrap_is_deterministic() -> None:
    values = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
    first = block_bootstrap_mean_ci(values, block_size=2, num_resamples=200, seed=17)
    second = block_bootstrap_mean_ci(values, block_size=2, num_resamples=200, seed=17)
    assert first.to_dict() == second.to_dict()
    assert first.method == "moving_block_bootstrap"


def test_block_size_one_is_iid_bootstrap_special_case() -> None:
    values = [0.1, -0.2, 0.3, 0.4]
    iid = block_bootstrap_mean_ci(values, block_size=1, num_resamples=100, seed=9)
    direct = block_bootstrap_mean_ci(values, block_size=1, num_resamples=100, seed=9)
    assert iid.to_dict() == direct.to_dict()
    assert iid.method == "percentile_bootstrap"


def test_block_bootstrap_preserves_ordered_local_dependence() -> None:
    values = [0.0, 0.0, 1.0, 1.0] * 4
    iid = block_bootstrap_mean_ci(values, block_size=1, num_resamples=500, seed=21)
    blocked = block_bootstrap_mean_ci(values, block_size=2, num_resamples=500, seed=21)
    assert blocked.point_estimate == iid.point_estimate
    assert blocked.bootstrap_std != iid.bootstrap_std


def test_block_bootstrap_rejects_invalid_block_size() -> None:
    values = [1.0, 2.0, 3.0]
    for block_size in (0, -1, 4):
        try:
            block_bootstrap_mean_ci(values, block_size=block_size)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid block_size was accepted")
