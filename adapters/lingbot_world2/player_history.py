"""Opt-in endpoints for older player observations; latest chunk keeps all samples.

Only the imported player module is patched. The verifier's sampler is untouched.
"""


def install(run_agent, on_removed):
    original = run_agent.extract_video_frames_with_timestamps_b64

    def sample(video_path, num_frames=8):
        frames = original(video_path, num_frames)
        # Pinned upstream asks for four samples from older chunks, eight from latest.
        # Subset existing observations to preserve timestamps and JPEG bytes exactly.
        if num_frames == 4 and len(frames) > 2:
            on_removed(len(frames) - 2)
            return [frames[0], frames[-1]]
        return frames

    run_agent.extract_video_frames_with_timestamps_b64 = sample
