"""CPU-only checks for feedforward KV-backlash camera reversal compensation."""
from __future__ import annotations
import math
from types import SimpleNamespace
import numpy as np
import pytest
from adapters.lingbot_world2 import backlash_cal as BC, player_hint as H, poses as P, run as R, session as S
from adapters.lingbot_world2.flag_stats import FlagStats

_yaw = lambda c2w: float(math.atan2(*(c2w[:3, :3] @ np.array([0.0, 0.0, 1.0]))[[0, 2]]))

def test_cli_env_parsing_and_validation():
    cfg, rest = BC.parse(["--seed", "7"], {})
    assert not cfg.enabled and (cfg.boost, cfg.tau_frames, cfg.min_run_frames, rest) == (0.22, 16.0, 8, ["--seed", "7"])
    assert BC.parse(["--lingbot-backlash-cal", "--lingbot-backlash-boost=0.3"], {})[0] == BC.BacklashConfig(True, 0.3, 16.0, 8)
    assert BC.parse(["--lingbot-backlash-boost", "0"], {"LINGBOT_BACKLASH_CAL": "1", "LINGBOT_BACKLASH_TAU": "12"})[0] == BC.BacklashConfig(True, 0.0, 12.0, 8)
    for argv, env in ((["--lingbot-backlash-boost", "-0.1"], {}), (["--lingbot-backlash-boost=-0.01"], {}),
                      (["--lingbot-backlash-boost"], {}), ([], {"LINGBOT_BACKLASH_BOOST": "-1"}),
                      ([], {"LINGBOT_BACKLASH_TAU": "0"}), ([], {"LINGBOT_BACKLASH_TAU": "-4"}), ([], {"LINGBOT_BACKLASH_MIN_RUN": "0"})):
        with pytest.raises(SystemExit):
            BC.parse(argv, env)
    with pytest.raises(SystemExit, match="requires session mode"):
        R.configure(["--lingbot-backlash-cal", "--lingbot-stateless"], {})

def test_tracker_decay_dataset_vs_closed_loop_and_jitter():
    P.reset({})
    cfg = BC.BacklashConfig(enabled=True, boost=0.22, tau_frames=16.0, min_run_frames=8)
    uni, jit, indep = BC.BacklashTracker(cfg), BC.BacklashTracker(cfg), BC.BacklashTracker(cfg)
    assert [uni.step("l") for _ in range(32)] == [(1.0, 1.0)] * 32 and (uni.reversals, uni.boosted_frames) == (0, 0)
    assert all(jit.step(k) == (1.0, 1.0) for k in ["j"] * 7 + ["l"] * 7 + ["j"] * 4 + ["l"] * 4) and jit.reversals == 0
    assert [indep.step("j") for _ in range(8)] and indep.step("none") == (1.0, 1.0) and indep.step("l+i") == (pytest.approx(1.22), 1.0)
    ds_bl, cl_bl = BC.BacklashTracker(cfg), BC.BacklashTracker(cfg)
    ds, cl = S.PoseTrack(backlash=ds_bl), S.PoseTrack(backlash=cl_bl)
    ds.advance(P.parse_action("j-32,l-32,none-12"))
    cl.advance(["j"] * 28)
    before_l = cl.last.copy()
    cl.advance(["l"] * 32)
    assert (ds_bl.reversals, ds_bl.boosted_frames) == (cl_bl.reversals, cl_bl.boosted_frames) == (1, 32)
    ds_l_rot, cl_l_rot = S.se3_inverse(ds.latents[8]) @ ds.latents[16], S.se3_inverse(before_l) @ cl.last
    assert np.allclose(ds_l_rot, cl_l_rot, atol=1e-12)
    extra = P.YAW * sum(cfg.boost * math.exp(-k / cfg.tau_frames) for k in range(32))
    assert _yaw(cl_l_rot) - 32 * P.YAW == pytest.approx(extra, rel=1e-6) and 0.8 * cfg.boost * cfg.tau_frames * P.YAW < extra
    plain, eased = S.PoseTrack(), S.PoseTrack(backlash=BC.BacklashTracker(cfg))
    plain.advance(["j"] * 28 + ["l"] * 32)
    assert eased.advance(["j"] * 28, ease_turns=True).shape == (8, 4, 4) and eased.advance(["l"] * 32, ease_turns=True).shape == (8, 4, 4)
    assert _yaw(eased.last) > _yaw(plain.last) and np.array_equal(S.PoseTrack().advance(["j"] * 28), S.PoseTrack(backlash=None).advance(["j"] * 28))
    assert H.replay(["LEFT", "RIGHT"], {"LEFT": "j", "RIGHT": "l"}.get, 33, True, True)["heading"] == pytest.approx(0.0)

def test_flag_stats_and_gen_arms_isolation(monkeypatch, capsys):
    for k in [k for k in R.os.environ if k.startswith("LINGBOT_")]:
        monkeypatch.delenv(k)
    off, on = FlagStats(False, "goal", False, False), FlagStats(False, "goal", False, False, backlash_cal=True)
    assert "backlash" not in off.line(off.finish_task("GC033")) and "backlash" not in off.total_line()
    on.backlash_step(1, 32)
    assert on.finish_task("GC033")["backlash_reversals"] == 1 and "backlash_reversals=1 backlash_frames=32" in on.total_line()
    monkeypatch.setattr(R, "import_run_agent", lambda **kw: SimpleNamespace(run_task=lambda *a: None, main=lambda: 0))
    monkeypatch.setattr(R.agent_api, "patch", lambda *a: "test")
    assert R.main(["run.py", "--lingbot-backlash-cal", "--lingbot-backlash-boost=0.25"]) == 0 and R.BACKLASH.boost == 0.25 and R.STATS.backlash_cal
    assert R.main(["run.py"]) == 0 and not R.BACKLASH.enabled and not R.STATS.backlash_cal
    assert "backlash" not in capsys.readouterr().out.splitlines()[-1]
