# Version matrix

`uv.lock` is the source of truth. The initial lock resolved on 2026-06-29 with Python 3.12,
Gymnasium 1.3.0, Stable-Baselines3 2.9.0, PyTorch 2.12.1, MuJoCo 3.10.0, JAX 0.10.2,
Brax 0.14.2, and Playground 0.2.0. The Linux/NVIDIA image uses CUDA 12.9.1.

The shared package/tests were verified locally. The SB3 and MJX rows remain candidates until the
Linux GPU smoke commands pass; update this file with driver/GPU and exact smoke results rather than
calling an unexecuted matrix “tested.” SB3 deliberately does not depend on JAX or Playground.

