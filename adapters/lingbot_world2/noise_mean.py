"""Common random numbers for the per-channel DC component of sampling noise.

For independent standard Gaussian x and anchor a, y=(I-P)x+Pa is also standard
Gaussian when P is an orthogonal mean projection. Only correlations between
blocks change. Spatial/temporal residuals stay fresh; each sampler stage has its
own anchor. Operations work on numpy arrays and torch tensors without imports.
"""


class CoupledMean:
    def __init__(self):
        self.anchors = {}
        self.count = 0

    def apply(self, noise, stage):
        if len(noise.shape) != 4 or any(n <= 0 for n in noise.shape):
            raise ValueError("expected nonempty [channel, time, height, width] noise")
        mean = noise.reshape(noise.shape[0], -1).mean(1).reshape(-1, 1, 1, 1)
        key = (stage, tuple(noise.shape))
        if key not in self.anchors:
            self.anchors[key] = mean
            return noise  # first draw of each stage is bit-identical to the baseline
        self.count += 1
        return noise + (self.anchors[key] - mean)
