# Sim2Policy Sprint — Implementation Plan

Train a robot locomotion policy with reinforcement learning inside a Nebius Serverless AI Job, checkpoint everything to object storage, and auto-render rollout videos that show the robot going from flailing to walking. Ship it as a template repo anyone can clone and run.

---

## 0. The one architectural decision to make first

There are two viable stacks. Plan to build **Track B first** (it cannot fail), then upgrade to **Track A** (the real GPU story) once the pipeline works end to end.

### Track A — MuJoCo MJX + Brax PPO (the headline)
- Physics simulation itself runs **on the GPU** via MJX (MuJoCo compiled to JAX/XLA), running **thousands of environments in parallel**.
- A quadruped or humanoid locomotion policy trains in **minutes, not hours**, on a single modern GPU.
- Best entry point in 2026: **MuJoCo Playground** (`mujoco_playground`) — DeepMind's batteries-included library of GPU-ready locomotion/manipulation environments with tuned Brax PPO configs. You don't hand-tune anything.
- Risk: JAX + CUDA version alignment inside your container; JAX is unfamiliar territory if you've only used PyTorch.

### Track B — Gymnasium MuJoCo + Stable-Baselines3 PPO (the safety net)
- Classic stack: physics on CPU, policy network training on GPU. PyTorch, dead simple, enormous documentation base.
- HalfCheetah/Ant train to "clearly walking" in 1–3 hours of wall clock with known-good hyperparameters.
- Risk: essentially none — but GPU utilization is modest (MLP policy), so it's a weaker "GPU sim" narrative on its own.

**Hackathon framing if you ship both:** "same serverless job template, two backends — watch the GPU-native simulator train the same task 50× faster." That comparison chart *is* a great demo.

---

## 1. Prerequisites

### Accounts & cloud
- Nebius AI Cloud account with Serverless AI enabled (Jobs are self-service via web console and CLI; pay-as-you-go while running).
- Check quotas before day 1: you need at least one VM-backed GPU slot available (console → Administration → Limits → Quotas), and admin-group membership in your tenant.
- Nebius CLI installed and authenticated locally (`nebius` command).
- An object storage bucket (S3-compatible) for checkpoints, logs, and videos.
- A container registry the job can pull from (Nebius registry or any registry reachable from the platform).
- Credits: budget roughly 10–20 single-GPU hours total for the week (debug runs + 2–3 full training runs + renders). Use short `--timeout` values as a spending guard.

### Local machine
- Docker (with NVIDIA Container Toolkit if you have a local GPU — optional but speeds up debugging a lot).
- Python 3.11+, `uv` or pip.
- ffmpeg (for stitching demo videos locally).

### Knowledge prerequisites (what you actually need to understand)
You do **not** need RL theory depth. You need:
1. The RL loop vocabulary: environment, observation, action, reward, episode, policy. (~1 hour of reading.)
2. What PPO is *operationally*: an on-policy algorithm that alternates "collect N steps of experience in parallel envs" with "gradient-update the policy network." You treat it as a black box with hyperparameters.
3. How Gymnasium environments work: `env.reset()` → loop `env.step(action)` → `terminated/truncated`. (~30 min.)
4. Headless rendering concepts: MuJoCo renders via EGL (GPU, no display) or OSMesa (CPU fallback) — controlled by the `MUJOCO_GL` env var. This is the #1 "works on my machine, fails in the container" trap.

Everything else (network architectures, advantage estimation, entropy coefficients) comes from default configs.

---

## 2. Repo layout (the deliverable)

```
sim2policy/
├── README.md                  # the tutorial — this is half the project's value
├── Dockerfile
├── pyproject.toml
├── configs/
│   ├── halfcheetah_sb3.yaml   # Track B configs
│   ├── ant_sb3.yaml
│   └── go1_mjx.yaml           # Track A config (MuJoCo Playground)
├── src/
│   ├── train_sb3.py           # Track B: SB3 PPO trainer
│   ├── train_mjx.py           # Track A: Brax PPO via mujoco_playground
│   ├── render.py              # checkpoint -> mp4 rollout videos
│   ├── evaluate.py            # seeds, mean reward, success threshold
│   └── storage.py             # S3 sync helpers (boto3, endpoint-configurable)
├── jobs/
│   ├── submit.sh              # wraps `nebius ai job create ...`
│   └── README.md              # job parameters explained
├── Makefile                   # make build / push / train ENV=... / render / report
└── assets/                    # committed sample outputs: curves PNG, GIF teaser
```

---

## 3. Step-by-step build

### Step 1 — Local skeleton (Track B), no cloud yet
Goal: PPO training a HalfCheetah locally for 5 minutes, producing a checkpoint and a video. Prove the whole loop on your laptop first.

```python
# src/train_sb3.py (core)
import gymnasium as gym
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.callbacks import CheckpointCallback

def main(env_id="HalfCheetah-v5", total_steps=2_000_000, n_envs=16, run_dir="runs/dev"):
    venv = make_vec_env(env_id, n_envs=n_envs)          # parallel CPU envs
    model = PPO("MlpPolicy", venv, device="cuda",
                tensorboard_log=f"{run_dir}/tb", verbose=1)
    ckpt = CheckpointCallback(save_freq=50_000 // n_envs,
                              save_path=f"{run_dir}/checkpoints")
    model.learn(total_timesteps=total_steps, callback=ckpt)
    model.save(f"{run_dir}/final")
```

Key choices:
- **Environments:** `HalfCheetah-v5` (fastest to converge, debug env), `Ant-v5` (looks like a robot), `Humanoid-v5` (most striking, slowest — save for Track A or a long final run).
- **Hyperparameters:** don't invent them. Copy the tuned PPO configs from **RL Baselines3 Zoo** for each env — this single decision removes most convergence risk.

### Step 2 — Rendering pipeline
The videos are your demo. Make rendering a first-class script, not an afterthought.

```python
# src/render.py (core idea)
import gymnasium as gym, imageio
from stable_baselines3 import PPO

def rollout_video(ckpt_path, env_id, out_mp4, steps=500):
    env = gym.make(env_id, render_mode="rgb_array")
    model = PPO.load(ckpt_path)
    obs, _ = env.reset(seed=0)
    frames = []
    for _ in range(steps):
        action, _ = model.predict(obs, deterministic=True)
        obs, _, term, trunc, _ = env.step(action)
        frames.append(env.render())
        if term or trunc:
            obs, _ = env.reset()
    imageio.mimsave(out_mp4, frames, fps=30)
```

Render at **three checkpoints — untrained, ~25% trained, final** — and stitch them side by side with ffmpeg. That progression montage is the single most persuasive artifact in the whole submission.

### Step 3 — Containerize with headless rendering
This is where DevOps skill pays off and where most people get stuck.

```dockerfile
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3-pip ffmpeg \
    libegl1 libgl1 libglvnd0 libosmesa6 \
    && rm -rf /var/lib/apt/lists/*
ENV MUJOCO_GL=egl            # GPU headless rendering; fallback: osmesa
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml .
RUN pip install gymnasium[mujoco] stable-baselines3 tensorboard imageio[ffmpeg] boto3 pyyaml
COPY src/ src/
ENTRYPOINT ["python3", "-m"]
```

Test locally before any cloud submission:
```bash
docker run --gpus all -e MUJOCO_GL=egl sim2policy \
  src.render --smoke-test    # renders 10 frames from a random policy
```
If EGL fails on the cloud GPU image, flip `MUJOCO_GL=osmesa` (CPU rendering — slower, but only used for the render step). Build this fallback into `render.py` as a retry.

### Step 4 — Object storage integration
Jobs are ephemeral; everything of value must leave the container. Two options: mount object storage into the job (supported in job configuration), or sync explicitly with boto3 against the S3-compatible endpoint. **Do the explicit boto3 sync** — it's more portable for people cloning your template on other clouds, which strengthens the "learnable example" story.

Sync (a) TensorBoard event files every N minutes via a background thread or SB3 callback, (b) checkpoints on save, (c) videos at end. Bucket layout:
```
s3://sim2policy/<run_id>/{checkpoints,tensorboard,videos,report}/
```
This also gives you **resumability**: on startup, `train_sb3.py` checks for the latest checkpoint in the run prefix and resumes — your insurance against a job timeout mid-run.

### Step 5 — First serverless job
The CLI shape (from the Nebius quickstart — verify current flags against the docs when you start):

```bash
nebius ai job create \
  --name sim2policy-halfcheetah \
  --image <registry>/sim2policy:latest \
  --container-command python3 \
  --args "-m src.train_sb3 --config configs/halfcheetah_sb3.yaml --run-id hc-001" \
  --platform gpu-l40s-a \
  --preset 1gpu-8vcpu-32gb \
  --timeout 4h \
  --subnet-id <subnet_ID>
```

Sequence of cloud runs (don't skip the small ones):
1. The official **nvidia-smi quickstart job** — verifies account, quota, subnet, GPU visibility.
2. Your image, `--args "-c nvidia-smi"` style smoke run — verifies registry pull + CUDA in *your* container.
3. 10-minute training run — verifies storage sync, TensorBoard files appearing in the bucket.
4. Full HalfCheetah run (~1–2 h).

Wrap submission in `jobs/submit.sh` taking `ENV`, `RUN_ID`, `TIMEOUT` so the README can say: `make train ENV=ant RUN_ID=demo1`.

### Step 6 — Track A upgrade (MJX via MuJoCo Playground)
Add `train_mjx.py` using `mujoco_playground` locomotion environments (e.g., Go1 quadruped or humanoid) with their bundled Brax PPO training functions. Key container changes: install `jax[cuda12]`, `mujoco-mjx`, `playground`; pin versions and test the JAX↔CUDA pairing locally in Docker before submitting. Reuse the same storage/render/report plumbing.

What you gain: the training run finishes in **minutes** with the GPU pegged at high utilization (thousands of parallel sims), and you can show a live job going from launch to a walking quadruped video inside a demo slot. Capture `nvidia-smi dmon` output during both tracks for the utilization comparison chart.

### Step 7 — Evaluation harness
`evaluate.py` loads a checkpoint and runs **20 deterministic episodes across 5 seeds**, reporting mean ± std episode reward and a binary success criterion per env (e.g., HalfCheetah: mean reward > 4000; Ant: > 4000; quadruped: forward velocity sustained without falling). Emit `report/metrics.json` plus a markdown summary with:
- reward curve PNG (exported from TensorBoard)
- wall-clock to success threshold
- GPU type, utilization, and **cost per trained policy** (runtime × on-demand rate)
- Track A vs Track B comparison table (if both done)

### Step 8 — README tutorial + demo assets
The README is a deliverable, not documentation. Structure: what RL is in 10 lines → architecture diagram → "run it in 15 minutes" quickstart → config reference → how to add your own environment → cost table → troubleshooting (EGL, JAX/CUDA, quota errors). Record a 60–90 s screen capture: submit job → TensorBoard curve climbing → final video playing.

---

## 4. Day-by-day schedule

| Day | Goal | Exit criterion |
|---|---|---|
| 0 (eve) | Nebius account, CLI, quota check, bucket, run official nvidia-smi quickstart job | Quickstart job succeeds |
| 1 | Local Track B skeleton: train 5 min on HalfCheetah, render a video | mp4 of a (bad) policy exists |
| 2 | Dockerfile + headless rendering + registry push; smoke job on Nebius | Your container renders frames in a cloud job |
| 3 | Storage sync + resumability; full HalfCheetah run in the cloud | Checkpoints + TB logs land in bucket; reward curve climbing |
| 4 | Track A: MJX/Playground container variant; quadruped run | GPU-parallel training completes; video rendered |
| 5 | Ant (and optionally Humanoid via Track A); eval harness; cost/utilization data | metrics.json + comparison table for ≥2 envs |
| 6 | Template polish: Makefile, configs, README tutorial, progression montage | A stranger could clone and run it from README alone |
| 7 | Buffer + submission writeup + demo recording | Submitted |

Rule of thumb: if Track A isn't working by **end of day 4, cut it** and spend the time making Track B's montage, metrics, and README excellent. A polished safe project beats a broken ambitious one in hackathon judging every time.

---

## 5. Artifacts produced (submission checklist)

1. **Public Git repo** — Dockerfile, both trainers, render/eval scripts, job submission wrapper, configs, Makefile, tutorial README.
2. **Container image** in a registry (referenced in README).
3. **Trained policy checkpoints** for 2–3 environments (committed or linked from storage).
4. **Rollout videos**: untrained / mid / final per environment + one stitched progression montage.
5. **TensorBoard logs** + exported reward-curve PNGs.
6. **Benchmark report**: wall-clock to success, GPU utilization, cost per trained policy, Track A vs B comparison.
7. **60–90 s demo recording** of the full loop.
8. **Submission writeup**: pain → solution → metrics → how to reproduce in 15 minutes.

---

## 6. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| EGL rendering fails in cloud container | Medium | `MUJOCO_GL=osmesa` fallback baked into render.py; rendering is decoupled from training so training is never blocked |
| JAX/CUDA version mismatch (Track A) | Medium | Pin versions, test in Docker locally first; hard cutoff end of day 4 |
| RL doesn't converge | Low if you use Zoo hyperparams | Copy RL Baselines3 Zoo configs verbatim; HalfCheetah is very forgiving |
| Job timeout kills a long run | Medium | Checkpoint-resume from object storage; generous `--timeout` on final runs |
| Registry pull failure / subnet misconfig | Medium | Day 2 smoke job exists precisely to surface this early |
| Credit burn | Low | Short timeouts on debug runs; Track A runs are minutes long anyway |
| Humanoid too slow on Track B | High | Humanoid only via Track A; Ant is the Track B showpiece |

---

## 7. Learning resources (ordered for your situation)

### Minimum viable understanding (~half a day, do before Day 1)
1. **Hugging Face Deep RL Course** — Unit 1 (intro/vocabulary) and Unit 8 (PPO). Practical, SB3-based, no math wall: https://huggingface.co/learn/deep-rl-course/unit0/introduction
2. **Gymnasium docs** — basic usage + MuJoCo environments pages: https://gymnasium.farama.org
3. **Stable-Baselines3 docs** — PPO page + examples + callbacks: https://stable-baselines3.readthedocs.io

### When you hit specifics
4. **RL Baselines3 Zoo** (tuned hyperparameters — copy, don't tune): https://github.com/DLR-RM/rl-baselines3-zoo
5. **MuJoCo docs** — rendering/EGL section for the headless container work: https://mujoco.readthedocs.io
6. **MJX documentation** (GPU-accelerated MuJoCo): https://mujoco.readthedocs.io/en/stable/mjx.html
7. **MuJoCo Playground** (Track A environments + training recipes): https://playground.mujoco.org and https://github.com/google-deepmind/mujoco_playground
8. **Brax** (the JAX PPO implementation Playground uses): https://github.com/google/brax
9. **Nebius Serverless AI Jobs quickstart** (CLI flags, quotas, subnet setup): https://docs.nebius.com/serverless/quickstart/jobs and overview: https://nebius.com/services/serverless

### Deeper background (optional, post-hackathon)
10. **OpenAI Spinning Up** — the canonical conceptual RL intro: https://spinningup.openai.com
11. **"The 37 Implementation Details of PPO"** — why PPO implementations differ; superb engineering read: https://iclr-blog-track.github.io/2022/03/25/ppo-implementation-details/
12. **CleanRL** — single-file PPO implementations to read end to end: https://docs.cleanrl.dev
13. **PPO paper** (Schulman et al., 2017): https://arxiv.org/abs/1707.06347
14. **MuJoCo Menagerie** — high-quality robot models if you want a realistic robot beyond Gymnasium's built-ins: https://github.com/google-deepmind/mujoco_menagerie

---

## 8. Demo script for judges (3 minutes)

1. (20 s) Pain: "Training a robot policy normally means days of CUDA/sim setup before step one. This repo is `git clone` → walking robot in one serverless job."
2. (30 s) Launch a Track A job live from the terminal (`make train ENV=go1`).
3. (40 s) While it runs: show the architecture slide and the Track A vs Track B GPU-utilization/cost comparison.
4. (40 s) Show TensorBoard of the live run — reward curve climbing in real time (only possible because Track A trains in minutes).
5. (40 s) The money shot: progression montage — flailing → stumbling → walking.
6. (10 s) Metrics card: "Quadruped policy: X minutes, $Y, reproducible with one command."
