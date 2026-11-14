"""World-model runners for `pwa gen --runner <name>` (adapters/<name>/run.py).

Each run.py accepts run_agent.py's argv, imports the upstream harness
(adapters.common.upstream.import_run_agent), applies
adapters.common.agent_api.patch (agent provider headers), optionally replaces
run_agent.SanaWMEngine, and calls run_agent.main().

Engine contract (same as upstream SanaWMEngine):
    __init__(self, args)
    generate(image_path, prompt, action, output_dir, name, num_frames, intrinsics_path=None) -> Path  # mp4

Inference-time methods compose as wrappers around generate(), e.g.

    class AnchorMemory:
        def __init__(self, base): self.base = base
        def generate(self, image_path, prompt, action, *a, **kw):
            image_path = self.pick_anchor(image_path, action)   # re-anchor / memory retrieval
            mp4 = self.base.generate(image_path, prompt, action, *a, **kw)
            self.update_memory(mp4)                            # state tracking
            return mp4

    Base = run_agent.SanaWMEngine
    run_agent.SanaWMEngine = lambda args: AnchorMemory(Base(args))

Create adapters/<name>/run.py for each variant so `pwa gen` records which one ran.
"""
