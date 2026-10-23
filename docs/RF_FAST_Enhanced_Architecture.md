# RF-FAST Enhanced: Integrating WiFi CSI Deep Learning into the RF-FAST Framework

**Addendum to the RF-FAST Research Framework**
*Analysis of Chen et al. (2024) and Architectural Update*

---

## Part 1: Critical Analysis of Chen et al. (2024)

### What the Paper Actually Contributes

Chen et al. present a practical WiFi CSI-based fall detection system using an ESP32S3 microcontroller as the receiver and a commodity home router as the transmitter. The system collects CSI amplitude matrices at 100 Hz, standardises them to a (300 × 52) shape via linear interpolation, and feeds them into a modified pretrained ResNet18 for activity classification. Binary classification (fall vs non-fall) achieves 93.97% accuracy, outperforming SVM (88.79%) and random forest (87.93%) on the same dataset.

Three contributions are technically substantive. First, the **hardware approach** — an ESP32S3 with an external antenna receiving CSI from a standard home router — produces a complete passive WiFi sensing node for under $15 AUD. This is the most cost-effective CSI acquisition setup published to date, and the device is widely available. Second, the **image-based representation**: treating the (time × subcarrier) CSI matrix as a single-channel grayscale image and applying a pretrained image classification CNN is an elegant and reproducible design choice. The pretrained ResNet18 weights provide a useful initialisation despite the domain mismatch between ImageNet and CSI data. Third, the **t-SNE finding** is clinically important and under-discussed in the paper itself: activities involving vertical body displacement (sitting down, standing up) cluster near fall events in feature space, while horizontal-motion activities (walking, jumping forward) cluster separately. This tells us that WiFi CSI at 2.4 GHz is primarily encoding the vertical component of body motion — which is exactly the relevant dimension for fall detection and postural instability assessment in stroke survivors.

### What the Paper Does Not Adequately Address

Several limitations are significant and must be corrected for in RF-FAST. The participant population — ten volunteers with a mean age of 23.6 years, mean BMI 23.4 — is the antithesis of the FAST trial population (mean age 75, multiple comorbidities, 70% hemiplegic). It is entirely unclear whether the CSI signatures of a healthy 23-year-old falling forwards in a conference room resemble those of a 75-year-old stroke survivor with hemiplegia losing balance near a bathroom sink. This is the single most critical limitation for direct transfer to RF-FAST.

The data splitting strategy — random 75/25 train/test allocation — inflates accuracy estimates because consecutive windows from the same session will appear in both training and test sets, leaking temporal autocorrelation. A correct approach for a small, multi-volunteer dataset is leave-one-subject-out cross-validation, which would produce lower but more honest accuracy figures.

The paper treats fall detection as a single-environment binary event classification task. RF-FAST requires something fundamentally different: continuous, longitudinal monitoring in an ecologically valid home environment where the task is not event detection from a 3-second clip but trajectory characterisation over weeks.

Finally, the paper discards phase information entirely due to single-antenna phase noise on the ESP32. This is pragmatic but sacrifices potentially useful information. The USRP N210, with its more stable oscillator and phase-coherent design, does not share this constraint and can exploit phase alongside amplitude.

---

## Part 2: Mapping Chen et al. Contributions to RF-FAST Enhancement

### 2.1 ESP32S3 as a Multi-Room Passive CSI Layer

This is the most immediately impactful contribution for RF-FAST. The original framework identified single-room coverage as its most critical deployment limitation. The ESP32S3 solution directly addresses this.

The architecture updates as follows. The USRP N210 remains as the primary active FMCW radar in the main living area — this is where the highest-quality, most information-rich sensing occurs, covering the FAST exercise and mobility activities. A network of two to four ESP32S3 nodes, each costing under $15, is deployed in the remaining rooms: bedroom, bathroom, kitchen, and hallway. These nodes receive CSI from the existing home WiFi router (no new transmitter hardware required) and stream processed features to the edge hub. Together, the system achieves whole-home coverage at modest additional cost.

This sensor heterogeneity is architecturally important: the USRP provides high-bandwidth, controlled-waveform, micro-Doppler-capable sensing; the ESP32 nodes provide low-cost, opportunistic, room-level activity classification. Each modality has appropriate responsibilities in the inference pipeline.

### 2.2 ResNet18 CSI Classification as a Parallel Inference Stream

The modified ResNet18 architecture — single-channel input convolutional layer, pretrained backbone, task-specific classification head — is directly adoptable as the classification head for each ESP32S3 node's data stream. For RF-FAST, the model is not trained from scratch on Chen et al.'s dataset but rather fine-tuned using three stages.

In the first stage, the ResNet18 backbone is initialised with Chen et al.'s weights (or directly from ImageNet pretrained weights, which performed similarly). In the second stage, the model is fine-tuned on an intermediate dataset of older adults performing the relevant activities — sit-to-stand, walking, lying down, bathroom entry — with emphasis on the vertical-motion classes that the t-SNE analysis identified as most discriminative for fall detection. In the third stage, the model is further personalised using each stroke survivor's own early monitoring data, adapting to their specific CSI signature profile. This three-stage fine-tuning strategy is appropriate for small target-domain datasets and is well-established in transfer learning literature.

The same ResNet18 architecture, with a different input specification, is also applied to the USRP FMCW range-Doppler spectrograms. Here, the input is a (128 × 256) matrix (Doppler bins × range bins), still treated as a single-channel image. This creates a symmetric dual-stream CNN architecture — one stream per sensing modality — that can be jointly trained or independently deployed.

### 2.3 The (Time × Subcarrier) Representation for RF-FAST Feature Design

The (300 × 52) CSI matrix representation — time samples as rows, OFDM subcarriers as columns — is a design choice with direct parallels in FMCW processing. In RF-FAST's USRP pipeline, the analogous representation is a (128 chirps × 256 range-bins) range-Doppler map accumulated over a coherent processing interval, or equivalently a (time × Doppler-frequency) micro-Doppler spectrogram across a 3-second window. Treating both as single-channel images and processing them with the same CNN architecture creates a modality-agnostic pipeline that simplifies code maintenance and enables cross-modal transfer learning.

The linear interpolation resampling strategy from Chen et al. is also adopted for RF-FAST's sensor fusion challenge: wearable accelerometers (100 Hz), ESP32S3 CSI (variable ~80–100 Hz actual reception), and USRP frames (10 frames/second) operate at different rates. A common resampled representation at 100 Hz, with linear interpolation for the USRP-derived features, provides a unified time axis for multimodal fusion.

### 2.4 Binary Versus Multi-Class Design Principle

The Chen et al. finding — that binary classification (94%) substantially outperforms 5-class classification (84%) — has a direct design implication for RF-FAST. Rather than building a single multi-task model that simultaneously classifies activities, detects falls, and assesses gait quality, the updated RF-FAST pipeline uses a cascade of specialised binary classifiers.

The first classifier answers: is the subject currently in a fall/emergency event? This operates on 3-second windows with a 0.5-second slide, at the highest priority. The second classifier answers: is the subject performing a LiFE exercise? This operates on 10-second windows for adherence monitoring. The third classifier answers: is the subject's gait pattern within their personal normal range? This operates on 30-second aggregated feature windows. The cascade design ensures that the most clinically urgent task (fall detection) receives the highest specificity classifier and the fastest inference path.

### 2.5 The t-SNE Vertical-Motion Insight — Clinical Re-interpretation

The t-SNE visualisation in Chen et al. deserves more attention than the paper gives it. The clustering of sit-down and stand-up actions near fall events — and the separation of horizontal-motion activities (walking, jumping) — reflects a fundamental physical fact: WiFi CSI at 2.4 GHz with a 1.25m transmitter-receiver separation is most sensitive to vertical displacement of the body's centre of mass. This is because vertical motion perpendicular to the direct Tx-Rx path produces the largest Fresnel zone perturbations.

For RF-FAST, this has a specific clinical implication. The most dangerous moments for post-stroke survivors are sit-to-stand transfers and nocturnal rising from bed — both of which involve significant vertical displacement. The CSI sensitivity profile is therefore well-matched to the highest-risk activities in this population. However, it also means that postural sway during standing (a key balance measure in FAST) and lateral stepping (a LiFE exercise) may be poorly captured by the ESP32 CSI nodes compared to the FMCW radar, which has explicit Doppler frequency resolution in all directions. This motivates the complementary sensing design: FMCW for lateral/rotational motion, CSI for vertical transitions.

---

## Part 3: Updated End-to-End System Architecture — RF-FAST Enhanced

### Architecture Overview

The updated system has five sensing inputs, three processing tiers, two AI inference tracks that merge into a unified risk assessment, and a blockchain-secured clinical interface. The architecture is designed for a single-occupancy or primary-occupant home.

```
╔══════════════════════════════════════════════════════════════════════════╗
║                     RF-FAST ENHANCED — SENSING LAYER                    ║
╠══════════════╦══════════════════════════╦═══════════════════════════════╣
║  ACTIVE SDR  ║   PASSIVE WIFI CSI       ║     IoT WEARABLES/ENV         ║
║              ║                          ║                               ║
║  USRP N210   ║  ESP32S3 Node 1 (Bedroom)║  Wrist IMU (100 Hz, BLE)     ║
║  FMCW Radar  ║  ESP32S3 Node 2 (Bathroom║  PIR sensors (4 rooms)        ║
║  2.4 GHz     ║  ESP32S3 Node 3 (Kitchen)║  Door/pressure sensors        ║
║  Main Room   ║  Home Router (Tx, shared)║  Heart rate (BLE)             ║
║  20 MHz BW   ║  2.4 GHz, 52 subcarriers ║                               ║
╚══════════════╩══════════════════════════╩═══════════════════════════════╝
         │                    │                          │
         ▼                    ▼                          ▼
╔══════════════════════════════════════════════════════════════════════════╗
║                        EDGE HUB (Raspberry Pi 4B)                       ║
║                                                                          ║
║  • GigE interface to USRP N210 (UHD driver, GNU Radio runtime)          ║
║  • WiFi interface to ESP32S3 nodes (MQTT over local WiFi)               ║
║  • BLE gateway for wearable sensors                                     ║
║  • NTP sync across all sensor streams                                   ║
╚══════════════════════════════════════════════════════════════════════════╝
         │
         ▼
╔══════════════════════════════════════════════════════════════════════════╗
║                  EDGE PROCESSING SERVER (Dell Pro Max T2)               ║
║                                                                          ║
║  ┌─────────────────────────┐   ┌──────────────────────────────────────┐ ║
║  │  FMCW SIGNAL PROCESSOR  │   │   CSI SIGNAL PROCESSOR               │ ║
║  │  (GNU Radio + Python)   │   │   (Python, per ESP32S3 node)         │ ║
║  │                         │   │                                      │ ║
║  │  Raw IQ → Dechirp →    │   │  Raw CSI amplitude matrix →          │ ║
║  │  Beat FFT → Range-      │   │  Linear interpolation resampling →   │ ║
║  │  Doppler Map →          │   │  Standardise to (300 × 52) →         │ ║
║  │  CFAR Detection →       │   │  Bandpass filter (motion freqs) →    │ ║
║  │  Micro-Doppler Spectro- │   │  Amplitude normalisation             │ ║
║  │  gram (128 × 256)       │   │                                      │ ║
║  └────────────┬────────────┘   └─────────────────┬────────────────────┘ ║
║               │                                  │                      ║
║               ▼                                  ▼                      ║
║  ┌─────────────────────────┐   ┌──────────────────────────────────────┐ ║
║  │  FMCW FEATURE EXTRACTOR │   │   CSI FEATURE EXTRACTOR              │ ║
║  │                         │   │                                      │ ║
║  │  • Cadence (steps/min)  │   │  • Vertical motion energy ratio      │ ║
║  │  • Stride symmetry      │   │  • Transition event detection        │ ║
║  │  • Sway amplitude       │   │  • Room occupancy state              │ ║
║  │  • Torso/limb ratio     │   │  • Activity duration                 │ ║
║  │  • Step regularity      │   │  • CSI variance (motion proxy)       │ ║
║  │  • Micro-Doppler entropy│   │                                      │ ║
║  └────────────┬────────────┘   └─────────────────┬────────────────────┘ ║
║               │                                  │                      ║
╚═══════════════╪══════════════════════════════════╪══════════════════════╝
                │                                  │
                ▼                                  ▼
╔══════════════════════════════════════════════════════════════════════════╗
║                      AI/ML INFERENCE LAYER                               ║
║                                                                          ║
║  STREAM A: FMCW Track               STREAM B: CSI Track                 ║
║  ┌──────────────────────┐           ┌──────────────────────────────────┐ ║
║  │ Micro-Doppler CNN    │           │ Modified ResNet18 (per room node)│ ║
║  │ Input: (128×256)     │           │ Input: (300×52) CSI amplitude    │ ║
║  │ 4-layer conv stack   │           │ Pretrained backbone +            │ ║
║  │ → Gait quality score │           │ stroke-specific fine-tuning      │ ║
║  │ → Exercise classifier│           │ → Binary: Fall / No-fall         │ ║
║  │ → Cadence features   │           │ → Transition event type          │ ║
║  └──────────┬───────────┘           └──────────────┬───────────────────┘ ║
║             │                                      │                     ║
║             └───────────────┬───────────────────────┘                    ║
║                             ▼                                            ║
║              ┌──────────────────────────────┐                           ║
║              │   MULTIMODAL FUSION MODULE   │                           ║
║              │                              │                           ║
║              │  + Wearable feature vector   │                           ║
║              │  + Environmental context     │                           ║
║              │  + Room occupancy state      │                           ║
║              │                              │                           ║
║              │  Fusion: Attention-weighted  │                           ║
║              │  concatenation → MLP head    │                           ║
║              └──────────────┬───────────────┘                           ║
║                             │                                            ║
║             ┌───────────────┼─────────────────┐                         ║
║             ▼               ▼                 ▼                         ║
║  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐  ║
║  │ FALL/NEAR-   │  │  EXERCISE    │  │  7-DAY RISK TRAJECTORY       │  ║
║  │ FALL DETECTOR│  │  ADHERENCE   │  │  Personalised Autoencoder    │  ║
║  │ Binary CNN   │  │  CLASSIFIER  │  │  → Anomaly score             │  ║
║  │ 3s window    │  │  10s window  │  │  → Trend direction           │  ║
║  │ 0.5s slide   │  │              │  │  → FAST booster trigger      │  ║
║  └──────────────┘  └──────────────┘  └──────────────────────────────┘  ║
║                                                                          ║
║  FEDERATED LEARNING: Local gradient computation, no raw data egress     ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║                    BLOCKCHAIN AUDIT LAYER                                ║
║              (Hyperledger Fabric, local permissioned node)              ║
║                                                                          ║
║  • Hash(alert, timestamp, participant_id, risk_score) → ledger          ║
║  • Hash(clinician_action, alert_id, timestamp) → ledger                 ║
║  • Tamper-evident audit trail for regulatory compliance                  ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║                    CLINICIAN INTERFACE                                   ║
║                                                                          ║
║  • Daily risk score + trend (7-day sparkline)                           ║
║  • Weekly gait quality summary (cadence, symmetry, sway — FMCW-derived)║
║  • Exercise adherence heatmap (CSI + FMCW combined)                    ║
║  • Room-level activity map (ESP32S3 derived, last 24h)                 ║
║  • SHAP feature attribution for each alert                              ║
║  • FAST booster session trigger with one-click scheduling              ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## Part 4: Updated ML Pipeline — Dual-Stream with Fusion

### Stream A: FMCW Micro-Doppler CNN (USRP N210)

The FMCW stream processes range-Doppler maps from the GNU Radio pipeline into micro-Doppler spectrograms. The model architecture is a compact 4-layer CNN designed for the (128 × 256) input dimension.

```python
# FMCW Micro-Doppler CNN (PyTorch — structural description)

class FMCWGaitNet(nn.Module):
    """
    Input:  (B, 1, 128, 256) — (batch, channel, doppler_bins, range_bins)
    Output: gait_features (B, 64), activity_logits (B, N_classes)
    """
    def __init__(self, n_classes=5):
        super().__init__()
        self.encoder = nn.Sequential(
            # Block 1: capture coarse Doppler structure
            nn.Conv2d(1, 32, kernel_size=(7,7), padding=3),
            nn.BatchNorm2d(32), nn.ReLU(),
            nn.MaxPool2d(2),                    # → (32, 64, 128)

            # Block 2: stride asymmetry features (cross-limb Doppler)
            nn.Conv2d(32, 64, kernel_size=(5,5), padding=2),
            nn.BatchNorm2d(64), nn.ReLU(),
            nn.MaxPool2d(2),                    # → (64, 32, 64)

            # Block 3: micro-Doppler fine structure
            nn.Conv2d(64, 128, kernel_size=(3,3), padding=1),
            nn.BatchNorm2d(128), nn.ReLU(),
            nn.MaxPool2d(2),                    # → (128, 16, 32)

            # Block 4: temporal periodicity (cadence)
            nn.Conv2d(128, 64, kernel_size=(3,3), padding=1),
            nn.BatchNorm2d(64), nn.ReLU(),
            nn.AdaptiveAvgPool2d((4, 4))        # → (64, 4, 4) = 1024
        )
        self.gait_head = nn.Linear(1024, 64)    # 64-dim gait embedding
        self.class_head = nn.Linear(64, n_classes)

    def forward(self, x):
        features = self.encoder(x).flatten(1)
        gait_emb = F.relu(self.gait_head(features))
        logits   = self.class_head(gait_emb)
        return gait_emb, logits
```

### Stream B: Modified ResNet18 CSI Classifier (ESP32S3 Nodes)

Following Chen et al. exactly for the backbone, with three modifications for RF-FAST: a stroke-specific activity label set, a personalised fine-tuning stage, and a confidence output alongside the classification label.

```python
# Modified ResNet18 for RF-FAST CSI (PyTorch)

import torchvision.models as models

class CSIFallNet(nn.Module):
    """
    Input:  (B, 1, 300, 52) — (batch, channel, time_samples, subcarriers)
            Resampled via linear interpolation to standardised 300 packets.
            Amplitude only (no phase — consistent with Chen et al.).
    Output: fall_prob (B,), activity_logits (B, N_classes)
    
    Label set for RF-FAST (post-stroke specific):
      0: Stationary/sitting
      1: Walking (preferred speed)
      2: LiFE exercise (balance/strength)
      3: Sit-to-stand / stand-to-sit transition   ← HIGH RISK
      4: Fall event                               ← EMERGENCY
    """
    def __init__(self, n_classes=5):
        super().__init__()
        resnet = models.resnet18(pretrained=True)
        # Adapt first conv for single-channel input (Chen et al. approach)
        resnet.conv1 = nn.Conv2d(
            1, 64, kernel_size=7, stride=2, padding=3, bias=False
        )
        # Copy weights from pretrained (average across RGB channels)
        with torch.no_grad():
            resnet.conv1.weight = nn.Parameter(
                resnet.conv1.weight.sum(dim=1, keepdim=True)
            )
        self.backbone  = nn.Sequential(*list(resnet.children())[:-1])
        self.fall_head = nn.Linear(512, 1)          # binary: fall prob
        self.act_head  = nn.Linear(512, n_classes)  # activity class

    def forward(self, x):
        feat       = self.backbone(x).squeeze(-1).squeeze(-1)  # (B, 512)
        fall_prob  = torch.sigmoid(self.fall_head(feat))       # (B, 1)
        act_logits = self.act_head(feat)                       # (B, N)
        return fall_prob, act_logits
```

**Fine-tuning stages for RF-FAST:**

```
Stage 1 — Domain pre-adaptation (weeks 1-4 of Phase 1):
  Freeze: backbone layers 1-3
  Train:  backbone layer 4 + both heads
  Data:   Chen et al. dataset + publicly available CSI datasets
          (NTU-Fi HAR, UT-HAR) filtered for relevant activities
  Goal:   Adapt to "vertical motion sensitivity" regime

Stage 2 — Population fine-tuning (Phase 2):
  Freeze: backbone layers 1-2
  Train:  backbone layers 3-4 + heads
  Data:   Phase 2 data from older adults (50-80 years) with
          post-stroke movement patterns
  Goal:   Learn post-stroke CSI signatures

Stage 3 — Participant personalisation (first 2 weeks of Phase 3 home monitoring):
  Freeze: backbone (all layers)
  Train:  classification heads only (few-shot, ~50 samples per class)
  Data:   Individual participant's own CSI data from calibration period
  Goal:   Personal baseline adaptation
```

### Fusion Module: Attention-Weighted Multimodal Integration

```python
class MultimodalFusionModule(nn.Module):
    """
    Fuses FMCW gait embedding, CSI embeddings (multiple rooms),
    wearable features, and environmental context.
    
    Inputs:
      fmcw_emb:   (B, 64)   — from FMCWGaitNet
      csi_embs:   (B, R, 64) — R room CSI embeddings (active rooms only)
      wear_feat:  (B, 16)   — wearable feature vector (cadence, HRV, jerk)
      env_feat:   (B, 8)    — room occupancy + time-of-day + door states
    
    Output:
      fused_emb:  (B, 128)  — fused representation for downstream heads
    """
    def __init__(self, n_rooms=3):
        super().__init__()
        # Cross-modal attention: FMCW attends over CSI room embeddings
        self.cross_attn = nn.MultiheadAttention(
            embed_dim=64, num_heads=4, batch_first=True
        )
        # Modality weighting (learned, soft)
        self.modality_gate = nn.Sequential(
            nn.Linear(64 + 64 + 16 + 8, 32),
            nn.ReLU(),
            nn.Linear(32, 4),   # 4 modality weights
            nn.Softmax(dim=-1)
        )
        self.projection = nn.Linear(64 + 64 + 16 + 8, 128)

    def forward(self, fmcw_emb, csi_embs, wear_feat, env_feat):
        # Aggregate room CSI embeddings via attention
        # Query: FMCW embedding; Keys/Values: CSI room embeddings
        fmcw_q   = fmcw_emb.unsqueeze(1)                   # (B, 1, 64)
        csi_agg, _ = self.cross_attn(fmcw_q, csi_embs, csi_embs)
        csi_agg  = csi_agg.squeeze(1)                       # (B, 64)
        
        concat   = torch.cat([fmcw_emb, csi_agg, wear_feat, env_feat], dim=-1)
        fused    = F.relu(self.projection(concat))          # (B, 128)
        return fused
```

### Cascade Classifier Design

```
PRIORITY 1 — Fall/Near-Fall Detector (3s window, 0.5s slide)
  Input:  fused_emb (B, 128)
  Head:   MLP(128 → 64 → 1) + sigmoid
  Trigger threshold: p_fall > 0.85
  Action on trigger: immediate alert → clinician dashboard
                     blockchain audit entry

PRIORITY 2 — Exercise Adherence Classifier (10s window, 5s slide)
  Input:  fused_emb (B, 128) + activity context
  Head:   MLP(128 → 64 → N_exercises) 
  Classes: {no_exercise, tandem_walk, lateral_step, heel_raise,
            sit_to_stand_reps, other_movement}
  Output: hourly exercise log → adherence score (0-24)
  Note:   replaces self-report Exercise Adherence Rating Scale (EARS)

PRIORITY 3 — Gait Quality Monitor (30s window, personal baseline)
  Input:  FMCW feature vector (cadence, symmetry, sway, entropy)
  Model:  Personalised Autoencoder (trained on participant's week-1 data)
  Output: reconstruction_error → z-score vs personal baseline
  Trigger: z-score > 2.0 for ≥3 consecutive 30s windows → elevated risk flag
  
PRIORITY 4 — 7-Day Mobility Decline Predictor
  Input:  Daily aggregated features (7-day rolling window)
  Model:  Gradient Boosted Trees (XGBoost) on 12 daily summary features
  Output: P(clinician mobility score decline > 0.1 m/s in next 7 days)
  Features: [mean cadence, cadence CV, mean sway, symmetry trend slope,
             exercise sessions per day, nocturnal movement count,
             sit-to-stand count, CSI transition event count × 4 rooms,
             wearable step count, HRV RMSSD mean, time-since-stroke,
             FAST intervention week]
```

---

## Part 5: Data Processing Pipeline — Standardised Protocol

### USRP N210 Data Ingestion

```
GNU Radio → Raw IQ (complex64, 20 MS/s)
  ↓ Dechirp (multiply with delayed TX reference)
  ↓ Low-pass filter (cutoff: B·Tmax/c, where Tmax = max range)
  ↓ Range FFT (N=512, Hann window) → beat spectrum per chirp
  ↓ Stack N_chirps=128 chirps → (128 × 512) range-time matrix
  ↓ Doppler FFT across chirps (N=128, Hann window)
  → Range-Doppler Map (128 × 512 complex, 10 maps/second)
  ↓ Extract 3s window → stack 30 maps → (30 × 128 × 512) 
  ↓ Doppler-Time spectrogram (sum over range dimension, 15m/s ± 50 bins)
  → Micro-Doppler spectrogram (128 Doppler × 300 time) as input to CNN
  
Parallel: extract scalar features from each map:
  • Peak Doppler frequency (cadence estimate)
  • Doppler bandwidth (activity intensity)
  • Range centroid (position stability — sway proxy)
  • Number of detected targets (CFAR threshold = 12 dB SINR)
```

### ESP32S3 CSI Data Ingestion (Chen et al. protocol, adapted)

```
ESP32S3 Ping → Router CSI response at ~100 Hz
  ↓ Buffer to 3-second window (target: 300 packets)
  ↓ Linear interpolation to exactly (300 × 52) if packet count ≠ 300
    (handles 60-120 packets/s actual reception rate variability)
  ↓ Amplitude extraction only: |h_k| for k=1..52 subcarriers
  ↓ Per-subcarrier z-score normalisation (remove static multipath)
  ↓ Median filter (window=5) along time axis (remove spike noise)
  → CSI amplitude matrix (300 × 52) as input to ResNet18
  
Parallel: extract scalar features:
  • Mean amplitude variance (overall motion energy)
  • Frequency of high-variance events (transition count proxy)
  • Subcarrier-weighted vertical motion index
    (sum |h_k|·w_k where w_k = subcarrier sensitivity to vertical motion,
     estimated from calibration data)
```

### Sensor Fusion Timestamps

```python
# NTP-aligned multi-stream buffer (pseudo-code)

class SensorFusionBuffer:
    """
    All streams timestamped via NTP (≤50ms synchronisation error).
    Fused feature vector assembled at 2 Hz (0.5s cadence).
    """
    WINDOW_SEC  = 30    # integration window for gait features
    STEP_SEC    = 0.5   # output cadence

    def assemble_feature_vector(self, t_now):
        # FMCW: 10 maps/sec × 30s = 300 maps → compute gait features
        fmcw_maps   = self.fmcw_buffer.get(t_now - 30, t_now)
        fmcw_feats  = self.fmcw_extractor(fmcw_maps)       # (64,)

        # CSI: per-room, most recent 3s window → activity class + fall prob
        csi_outputs = {}
        for room, node in self.csi_nodes.items():
            if node.is_occupied():
                mat = node.buffer.get_latest_3s()           # (300, 52)
                csi_outputs[room] = self.csi_model(mat)    # (fall_p, act)

        # Wearable: 30s window → scalar features
        wear_feats = self.wearable.get_features(t_now - 30, t_now)  # (16,)

        # Environmental context
        env_context = self.env_sensors.get_state(t_now)             # (8,)

        return FusedVector(fmcw_feats, csi_outputs, wear_feats, env_context)
```

---

## Part 6: Updated Experimental Design Modifications

### Additions to Phase 1 (Lab Feasibility)

Phase 1 must now include an explicit **ESP32S3 characterisation protocol** run alongside the USRP FMCW protocol. For each activity (walking, sit-to-stand, tandem stance, simulated fall), both sensing modalities capture simultaneously, enabling a paired comparison of their sensitivity to each activity type. The t-SNE analysis from Chen et al. is reproduced on the Phase 1 data to confirm that the vertical-motion sensitivity holds for the post-stroke gait population, or to quantify how it differs. This comparison is itself publishable.

### Additions to Phase 2 (Home-Simulation)

Three ESP32S3 nodes are deployed in the simulated home room — one in each of the sub-spaces designated as "bedroom," "bathroom," and "kitchen" within the test space. The USRP covers the main living area. This tests the multi-node coordination protocol, the MQTT data ingestion pipeline, and the room-transition detection logic (when a participant moves from one ESP32S3's coverage zone to another).

### Additions to Phase 3 (Home Monitoring)

Home installation now requires: one USRP N210 (living room, wall-mounted antenna), two to three ESP32S3 nodes with external antennas (bedroom nightstand, bathroom counter at safe height, kitchen), and the BLE wearable. Installation time target: under 90 minutes per home, with no structural modifications. The ESP32 nodes require only a power outlet and connection to the existing home WiFi — no IT configuration by participants.

---

## Part 7: Revised Publication Strategy

The Chen et al. integration creates an additional, distinct publication opportunity.

**New Paper: "Multimodal RF Sensing for Post-Stroke Fall Prevention: Combining FMCW Radar and WiFi CSI for Whole-Home Gait Monitoring"**

This paper directly contrasts the two sensing modalities — USRP FMCW vs ESP32S3 CSI — on the Phase 1/2 dataset, reporting per-activity sensitivity and specificity for each modality separately and in fusion. It positions the USRP as the "ground truth" micro-Doppler reference and the ESP32S3 as the scalable deployment alternative, with the fusion system achieving performance between the two. The target journal is *IEEE Journal of Biomedical and Health Informatics* (Q1), which has published several CSI-based health sensing papers and welcomes comparative hardware studies.

This paper also provides a direct response to the limitations of Chen et al. — specifically, it validates (or refutes) whether the ResNet18 CSI approach generalises to an older post-stroke population, which is a meaningful scientific contribution to the WiFi sensing field independent of the RF-FAST clinical framing.

---

## Part 8: Critical Limitations Added by Chen et al. Integration

The multi-node architecture introduces three new failure modes that the original RF-FAST framework did not face.

Inter-node interference is the most technically demanding challenge. Multiple ESP32S3 nodes using the same 2.4 GHz channel as the home router — and now also competing with the USRP N210's active FMCW transmission — create a congested RF environment. The USRP's FMCW waveform, if transmitting at 2.4 GHz, will corrupt the CSI measurements on the ESP32 nodes in the same room. Mitigation: the USRP and ESP32 nodes must operate in different frequency sub-bands. The USRP can use the 2.4 GHz band's upper edge (channel 11, 2.462 GHz), while the home router and ESP32 nodes use channels 1 or 6. Alternatively, the USRP is moved to the 5.8 GHz ISM band (requiring a 5.8 GHz-capable daughterboard — the UBX-40 supports this), entirely separating the active and passive sensing bands. This is the recommended approach and should be budgeted for in Phase 2.

Data heterogeneity across rooms is a subtler problem. The CSI signatures for the same activity will differ between the living room node, the bedroom node, and the bathroom node because the multipath environments are different. Models trained on bedroom data will not transfer directly to bathroom data. The personalised fine-tuning stage must be conducted separately per node per participant — tripling the fine-tuning data requirement and compute time.

Privacy risk escalation warrants attention. Three ESP32S3 nodes covering a bathroom, bedroom, and kitchen together create a far more comprehensive surveillance capability than a single USRP in the living room. Even with amplitude-only data, the nocturnal bedroom and bathroom monitoring creates data that participants may reasonably consider more intimate than living-room movement patterns. The consent process must be updated to address each room's sensing coverage explicitly, with an individual opt-out per node.

---

*This addendum updates the RF-FAST Research Framework (v1) to integrate contributions from: Chen T, Li X, Li H, Zhu G. "Deep learning-based fall detection using commodity Wi-Fi." Journal of Information and Intelligence 2(2024):355–364.*
