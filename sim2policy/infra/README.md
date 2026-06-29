# AWS g6 debug VM

This directory contains the single CloudFormation template used for the AWS Linux/NVIDIA debugging
path. It creates all cloud resources needed for SSH-based Sim2Policy debugging in one stack:

- VPC, public subnet, route table, internet gateway, and SSH security group
- generated EC2 key pair whose private key is stored by AWS in SSM Parameter Store
- `g6.2xlarge` Ubuntu 24.04 Deep Learning AMI instance
- Elastic IP for stable SSH during the debug session
- EC2 instance role with SSM access and scoped access to the stack-created S3 debug bucket
- encrypted gp3 root volume and a 14-day lifecycle rule for disposable debug artifacts

Deploy to `eu-west-2`:

```bash
cd sim2policy
export AWS_REGION=eu-west-2
export STACK_NAME=sim2policy-debug-g6
export SSH_LOCATION="$(curl -fsS https://checkip.amazonaws.com)/32"

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME" \
  --template-file infra/aws-debug-g6.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides SSHLocation="$SSH_LOCATION" InstanceType=g6.2xlarge
```

Download the generated private key to `/tmp`:

```bash
KEY_PARAM="$(
  aws cloudformation describe-stacks \
    --region "$AWS_REGION" \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='PrivateKeySsmParameter'].OutputValue | [0]" \
    --output text
)"

aws ssm get-parameter \
  --region "$AWS_REGION" \
  --name "$KEY_PARAM" \
  --with-decryption \
  --query Parameter.Value \
  --output text > "/tmp/$STACK_NAME.pem"
chmod 600 "/tmp/$STACK_NAME.pem"
```

SSH:

```bash
PUBLIC_IP="$(
  aws cloudformation describe-stacks \
    --region "$AWS_REGION" \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='InstancePublicIp'].OutputValue | [0]" \
    --output text
)"

ssh -i "/tmp/$STACK_NAME.pem" "ubuntu@$PUBLIC_IP"
```

The VM exports these defaults via `/etc/profile.d/sim2policy-debug.sh`:

```bash
AWS_REGION=eu-west-2
AWS_DEFAULT_REGION=eu-west-2
SIM2POLICY_S3_BUCKET=<stack bucket>
SIM2POLICY_S3_PREFIX=sim2policy
MUJOCO_GL=egl
PYTHONUNBUFFERED=1
```

After SSH, copy or clone the repo into `/home/ubuntu/work`, then run the Linux/GPU smoke gates:

```bash
cd /home/ubuntu/work/nebius-serverless-challenge-2026/sim2policy
uv sync --extra dev --extra sb3
uv run python -m sim2policy.health --backend sb3
uv run python -m sim2policy.render --config configs/smoke_sb3.yaml --output runs/aws-smoke/videos/random.mp4 --smoke-test
uv run python -m sim2policy.train_sb3 --config configs/smoke_sb3.yaml --run-id aws-smoke
```

To avoid surprise spend, stop or delete the stack when done:

```bash
aws ec2 stop-instances --region "$AWS_REGION" --instance-ids "$(
  aws cloudformation describe-stacks \
    --region "$AWS_REGION" \
    --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]" \
    --output text
)"

# or delete all stack-owned resources except the retained non-empty debug bucket
aws cloudformation delete-stack --region "$AWS_REGION" --stack-name "$STACK_NAME"
```
