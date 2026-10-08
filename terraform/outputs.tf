# The server's fixed public address: the website is at http://<ip>, Grafana at http://<ip>:3000.
# Put it in ansible/inventory.ini (or the SERVER_IP secret used by the CI/CD pipeline).
output "public_ip" {
  description = "Elastic IP address of the deployed EC2 instance"
  value       = aws_eip.gym_portal_ip.public_ip
}
