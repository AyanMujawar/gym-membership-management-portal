# Prints the VM's public IP after "terraform apply" finishes, so it can be
# pasted straight into ansible/inventory.ini
output "public_ip" {
  description = "Public IP address of the deployed EC2 instance"
  value       = aws_instance.gym_portal_vm.public_ip
}
