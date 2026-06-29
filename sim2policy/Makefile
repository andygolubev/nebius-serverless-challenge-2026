SHELL := /bin/bash
ENV ?= smoke_sb3
RUN_ID ?= dev
CONFIG := configs/$(ENV).yaml
IMAGE ?= sim2policy:sb3

.PHONY: setup check test lock build-sb3 build-mjx push smoke train evaluate render cloud-dry-run cloud-train clean
setup:
	uv sync --extra dev
check:
	uv run ruff check src tests
	uv run mypy src
test:
	uv run pytest
lock:
	uv lock
build-sb3:
	docker build --target sb3 --build-arg SOURCE_REVISION=$$(git rev-parse HEAD) -t $(IMAGE) .
build-mjx:
	docker build --target mjx --build-arg SOURCE_REVISION=$$(git rev-parse HEAD) -t $(IMAGE) .
push:
	docker push $(IMAGE)
smoke:
	uv run python -m sim2policy.render --config $(CONFIG) --output runs/$(RUN_ID)/videos/smoke.mp4 --smoke-test
train:
	uv run python -m sim2policy.train_sb3 --config $(CONFIG) --run-id $(RUN_ID)
evaluate:
	uv run python -m sim2policy.evaluate --config $(CONFIG) --run-id $(RUN_ID) --checkpoint $(CHECKPOINT)
render:
	uv run python -m sim2policy.render --config $(CONFIG) --run-id $(RUN_ID) --checkpoint $(CHECKPOINT) --output runs/$(RUN_ID)/videos/rollout.mp4
cloud-dry-run:
	DRY_RUN=1 IMAGE=$(IMAGE) CONFIG=$(CONFIG) RUN_ID=$(RUN_ID) jobs/submit.sh
cloud-train:
	IMAGE=$(IMAGE) CONFIG=$(CONFIG) RUN_ID=$(RUN_ID) jobs/submit.sh
clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache runs/$(RUN_ID)

