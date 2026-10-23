"""G3 classifier v2: compact 4-conv-block CNN on spectrogram patches.

CLAUDE.md §6/§7: "compact CNN on spectrogram patches (the FMCWGaitNet sketch
in the framework docs, 4 conv blocks -- not full ResNet18; dataset is too
small)". Architecture adapted from docs/RF_FAST_Enhanced_Architecture.md's
FMCWGaitNet: same 4-block philosophy, kernel-size progression (coarse ->
fine structure), channel progression, and 1024-dim flattened embedding --
only the input's second spatial axis changes from range bins to time frames,
since this project has no FMCW range axis (docs/errata.md).

Input: (B, 1, 60, 154) -- (batch, channel, time_frames, doppler_bins),
matching models/build_spectrogram_dataset.py's patch shape.
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


class FMCWGaitNetCW(nn.Module):
    """CW-Doppler-only adaptation of the framework's FMCWGaitNet sketch."""

    def __init__(self, n_classes):
        super().__init__()
        self.encoder = nn.Sequential(
            # Block 1: coarse Doppler structure
            nn.Conv2d(1, 32, kernel_size=7, padding=3),
            nn.BatchNorm2d(32), nn.ReLU(),
            nn.MaxPool2d(2),

            # Block 2: stride asymmetry / cross-limb Doppler
            nn.Conv2d(32, 64, kernel_size=5, padding=2),
            nn.BatchNorm2d(64), nn.ReLU(),
            nn.MaxPool2d(2),

            # Block 3: micro-Doppler fine structure
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128), nn.ReLU(),
            nn.MaxPool2d(2),

            # Block 4: temporal periodicity (cadence) -> fixed-size embedding
            nn.Conv2d(128, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64), nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 4)),
        )
        self.dropout = nn.Dropout(0.3)  # small dataset (CLAUDE.md §6): guard against overfitting
        self.gait_head = nn.Linear(1024, 64)
        self.class_head = nn.Linear(64, n_classes)

    def forward(self, x):
        features = self.encoder(x).flatten(1)
        gait_emb = F.relu(self.gait_head(self.dropout(features)))
        logits = self.class_head(gait_emb)
        return logits
