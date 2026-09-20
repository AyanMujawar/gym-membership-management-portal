terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
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

# Opens the ports our app needs: 22 (SSH, for Ansible), 80 (frontend), 5000 (backend API)
resource "aws_security_group" "allow_web_ssh" {
  name        = "gym-portal-allow-web-ssh"
  description = "Allow SSH, HTTP, and backend API traffic"

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Frontend"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Backend API"
    from_port   = 5000
    to_port     = 5000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
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

  tags = {
    Name = "gym-portal-vm"
  }
}
