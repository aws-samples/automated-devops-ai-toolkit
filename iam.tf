# Create IAM role
resource "aws_iam_role" "ec2_role" {
  name = "${var.project_name}-ec2-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "${var.project_name}-ec2-role"
    Environment = var.environment
  }
}

# Create IAM instance profile
resource "aws_iam_instance_profile" "ec2_profile" {
  depends_on = [aws_iam_role_policy_attachment.ssm_policy]
  name       = "${var.project_name}-ec2-profile"
  role       = aws_iam_role.ec2_role.name

  tags = {
    Name        = "${var.project_name}-ec2-profile"
    Environment = var.environment
  }
}

# Attach policy to the role (example with SSM policy)
resource "aws_iam_role_policy_attachment" "ssm_policy" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "bedrock_policy" {
  role       = aws_iam_role.ec2_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
}
