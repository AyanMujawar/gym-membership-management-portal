variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-south-1"
}

variable "aws_profile" {
  description = "Named AWS CLI profile holding this project's credentials"
  type        = string
  default     = "gym-new"
}

variable "aws_account_id" {
  description = "The only AWS account this configuration may be applied to (a safety guard)"
  type        = string
  default     = "237226121384"
}

variable "instance_type" {
  description = "EC2 instance type (t3.small = 2 GB RAM; t3.micro's 1 GB ran out of memory during deploys)"
  type        = string
  default     = "t3.small"
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key that will be allowed to log into the VM"
  type        = string
  default     = "~/.ssh/gym-portal-key.pub"
}

variable "root_volume_size" {
  description = "Size in GB of the server's disk"
  type        = number
  default     = 20
}

variable "ssh_allowed_cidr" {
  description = "Who may reach SSH. Open to all because the CI runners and the demo laptop have changing addresses; login is key-only"
  type        = string
  default     = "0.0.0.0/0"
}

variable "open_legacy_api_port" {
  description = "Open port 5000 for the old FA1 version, which called the API directly. Off: the FA2 version only needs ports 22, 80 and 3000"
  type        = bool
  default     = false
}
