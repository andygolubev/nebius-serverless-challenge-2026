SHELL := /bin/bash
ENV ?= smoke_sb3
RUN_ID ?= dev
CONFIG := configs/$(ENV).yaml
IMAGE ?= sim2policy:sb3
AWS_REGION ?= eu-west-2
AWS_STACK ?= sim2policy-debug-g6
AWS_DEBUG_KEY ?= /tmp/$(AWS_STACK).pem
AWS_SSH_LOCATION ?= $(shell curl -fsS https://checkip.amazonaws.com 2>/dev/null)/32

API_HOST ?= 127.0.0.1
API_PORT ?= 8000
BACKEND ?= mock

.PHONY: setup check test lock build-sb3 build-mjx push smoke train evaluate render report api cloud-dry-run cloud-train aws-debug-validate aws-debug-deploy aws-debug-key aws-debug-ssh aws-debug-stop aws-debug-delete clean
setup:
	uv sync --extra dev --extra api
check:
	uv run ruff check src tests
	uv run mypy src
test:
	uv run pytest
lock:
	uv lock
build-sb3:
	docker build --provenance=false --target sb3 --build-arg SOURCE_REVISION=$$(git rev-parse HEAD) -t $(IMAGE) .
build-mjx:
	docker build --provenance=false --target mjx --build-arg SOURCE_REVISION=$$(git rev-parse HEAD) -t $(IMAGE) .
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
report:
	uv run python -m sim2policy.report_cli curve --config $(CONFIG) --run-root runs/$(RUN_ID)
api:
	SIM2POLICY_API_BACKEND=$(BACKEND) SIM2POLICY_API_HOST=$(API_HOST) SIM2POLICY_API_PORT=$(API_PORT) uv run sim2policy-api
cloud-dry-run:
	DRY_RUN=1 IMAGE=$(IMAGE) CONFIG=$(CONFIG) RUN_ID=$(RUN_ID) jobs/submit.sh
cloud-train:
	IMAGE=$(IMAGE) CONFIG=$(CONFIG) RUN_ID=$(RUN_ID) jobs/submit.sh
aws-debug-validate:
	aws cloudformation validate-template --region $(AWS_REGION) --template-body file://infra/aws-debug-g6.yaml
aws-debug-deploy:
	aws cloudformation deploy --region $(AWS_REGION) --stack-name $(AWS_STACK) --template-file infra/aws-debug-g6.yaml --capabilities CAPABILITY_IAM --parameter-overrides SSHLocation=$(AWS_SSH_LOCATION) InstanceType=g6.2xlarge
aws-debug-key:
	aws ssm get-parameter --region $(AWS_REGION) --name "$$(aws cloudformation describe-stacks --region $(AWS_REGION) --stack-name $(AWS_STACK) --query "Stacks[0].Outputs[?OutputKey=='PrivateKeySsmParameter'].OutputValue | [0]" --output text)" --with-decryption --query Parameter.Value --output text > $(AWS_DEBUG_KEY)
	chmod 600 $(AWS_DEBUG_KEY)
aws-debug-ssh:
	ssh -i $(AWS_DEBUG_KEY) ubuntu@"$$(aws cloudformation describe-stacks --region $(AWS_REGION) --stack-name $(AWS_STACK) --query "Stacks[0].Outputs[?OutputKey=='InstancePublicIp'].OutputValue | [0]" --output text)"
aws-debug-stop:
	aws ec2 stop-instances --region $(AWS_REGION) --instance-ids "$$(aws cloudformation describe-stacks --region $(AWS_REGION) --stack-name $(AWS_STACK) --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]" --output text)"
aws-debug-delete:
	aws cloudformation delete-stack --region $(AWS_REGION) --stack-name $(AWS_STACK)
clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache runs/$(RUN_ID)
