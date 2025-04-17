resource "aws_security_group" "alb" {
  name_prefix = "${var.project_name}-alb-sg"
  description = "Security group for Application Load Balancer"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["43.252.205.113/32"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-alb-sg"
    Environment = var.environment
  }
}

# Security Groups
resource "aws_security_group" "ec2" {
  name_prefix = "${var.project_name}-ec2-sg"
  description = "Security group for Streamlit EC2 instance"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 8501
    to_port         = 8501
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-ec2-sg"
    Environment = var.environment
  }
}

# EC2 Instance
resource "aws_instance" "this" {
  depends_on                  = [aws_iam_role_policy_attachment.ssm_policy]
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = var.ec2_subnet_id
  vpc_security_group_ids      = [aws_security_group.ec2.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.ec2_profile.name
  root_block_device {
    volume_size           = 40
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  user_data                   = <<-EOF
              #!/bin/bash
              sudo su
              cd /opt/
              python3 -m ensurepip --upgrade
              yum install git -y
              git clone https://github.com/aws-samples/automated-devops-ai-toolkit.git
              cd automated-devops-ai-toolkit
              python3 -m venv .venv
              source .venv/bin/activate
              mkdir -p /opt/cache
              export PIP_CACHE_DIR=/opt/cache
              pip3 install -r requirements.txt
              streamlit run app.py 
              EOF
  user_data_replace_on_change = true
  tags = {
    Name        = "${var.project_name}-server"
    Environment = var.environment
  }
}

# Application Load Balancer
resource "aws_lb" "this" {
  name               = "${var.project_name}-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = var.alb_subnet_ids
  tags = {
    Name        = "${var.project_name}-alb"
    Environment = var.environment
  }
}

# Target Group
resource "aws_lb_target_group" "streamlit" {
  name     = "${var.project_name}-tg"
  port     = 8501
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    timeout             = 5
    path                = "/"
    port                = "8501"
    unhealthy_threshold = 2
  }

  tags = {
    Name        = "${var.project_name}-tg"
    Environment = var.environment
  }
}

# Target Group Attachment
resource "aws_lb_target_group_attachment" "streamlit" {
  target_group_arn = aws_lb_target_group.streamlit.arn
  target_id        = aws_instance.this.id
  port             = 8501
}

# Listener
resource "aws_lb_listener" "front_end" {
  load_balancer_arn = aws_lb.this.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.streamlit.arn
  }
}
