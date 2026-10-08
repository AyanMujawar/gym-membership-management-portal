terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile

  # Terraform refuses to run if the credentials belong to any other AWS account
  allowed_account_ids = [var.aws_account_id]

  # Every resource created here is labelled, so it is always clear what belongs to this project
  default_tags {
    tags = {
      Project = "gym-portal"
    }
  }
}

# Automatically finds the latest Ubuntu 22.04 image in whichever region we deploy to,
# instead of hardcoding an AMI ID that's only valid in one specific region
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical (the official publisher of Ubuntu images)

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# Registers our local public key with AWS so we can SSH in - no manual key pair
# creation needed in the console
resource "aws_key_pair" "deployer" {
  key_name   = "gym-portal-key"
  public_key = file(var.ssh_public_key_path)
}

# The firewall. Only what people genuinely need is open: SSH (key-only, used by Ansible and CI),
# the website, and Grafana. Prometheus, Alertmanager and the API itself are not reachable from outside:
# nginx forwards /api internally, and the monitoring UIs are bound to the server's own loopback.
resource "aws_security_group" "allow_web_ssh" {
  name = "gym-portal-allow-web-ssh"
  # AWS cannot change a security group's description in place (it would replace the group), so this wording is kept
  description = "Allow SSH, HTTP, and backend API traffic"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.ssh_allowed_cidr]
  }

  ingress {
    description = "Website (nginx)"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Grafana dashboards"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Only needed by the old FA1 version, whose frontend called the API on port 5000 directly.
  # Set open_legacy_api_port = false once the FA2 version is the only one in use.
  dynamic "ingress" {
    for_each = var.open_legacy_api_port ? [1] : []
    content {
      description = "Legacy backend API (FA1 fallback only)"
      from_port   = 5000
      to_port     = 5000
      protocol    = "tcp"
      cidr_blocks = ["0.0.0.0/0"]
    }
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# The actual virtual machine that will run our Docker containers
resource "aws_instance" "gym_portal_vm" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type
  key_name               = aws_key_pair.deployer.key_name
  vpc_security_group_ids = [aws_security_group.allow_web_ssh.id]

  # Room for the application images plus the monitoring stack and its data
  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
  }

  # Require session tokens for the instance metadata service (blocks a class of credential-theft attacks)
  metadata_options {
    http_tokens = "required"
  }

  tags = {
    Name = "gym-portal-vm"
  }
}

# A fixed public address. Without it the IP changes whenever the server is stopped and started,
# which would break the CI/CD pipeline's deploy target and the demo links.
resource "aws_eip" "gym_portal_ip" {
  domain   = "vpc"
  instance = aws_instance.gym_portal_vm.id

  tags = {
    Name = "gym-portal-ip"
  }
}
