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
