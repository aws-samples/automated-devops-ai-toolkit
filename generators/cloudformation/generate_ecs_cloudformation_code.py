import os
import re
import time
import streamlit as st
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain_core.output_parsers import StrOutputParser
from langchain.schema import AIMessage
from core.bedrock_definition import get_model

# Initialize the Bedrock model
model = get_model()

# Define prompt templates
supervisor_template = '''
    You are an AWS ECS expert. Classify the input requirement and output the setup pattern (either "fargate" or "ec2-autoscaling") without any additional text or explanations.
    Input: {input}
    Output: 
'''

ecs_cluster_fargate_template = '''
    You are a CloudFormation expert who generates AWS ECS Fargate configuration for multiple environments.
    Initial requirement: {initial_requirement}

    Please provide the following details:
    1. Name of the ECS cluster.
    2. VPC ID to associate the ECS cluster with.
    3. Number of Fargate tasks required.
    4. CPU and memory resources for each task (e.g., 512 vCPU, 1024 MiB memory).
    5. Any specific tags to be applied to the cluster (format: key=value, multiple tags separated by commas).
    6. Additional networking requirements, if any (e.g., subnets, security groups).
'''

task_definition_template = '''
    Generate a task definition JSON based on the Dockerfile content provided.
    Dockerfile content: {dockerfile_content}

    CRITICAL: Extract these exact values from the Dockerfile:
    1. FROM instruction → container image (e.g., "python:3.9", "node:16", "nginx:alpine")
    2. EXPOSE instruction → containerPort (e.g., 3000, 5000, 8080)
    3. Application name → derive from image or working directory
    
    Output MUST be valid JSON with extracted values:
    {{
      "family": "extracted-app-name",
      "containerDefinitions": [
        {{
          "name": "extracted-app-name",
          "image": "extracted-image-from-dockerfile",
          "cpu": 256,
          "memory": 512,
          "essential": true,
          "portMappings": [
            {{
              "containerPort": extracted-port-from-dockerfile,
              "protocol": "tcp"
            }}
          ],
          "logConfiguration": {{
            "logDriver": "awslogs",
            "options": {{
              "awslogs-group": "/ecs/extracted-app-name",
              "awslogs-region": "us-east-1",
              "awslogs-stream-prefix": "ecs"
            }}
          }}
        }}
      ]
    }}
    
    Replace "extracted-*" with actual values from the Dockerfile. DO NOT use "nginx", "app", or port 80 unless they are actually in the Dockerfile.
'''

cloudformation_generation_fargate_template = '''
    Based on all the details provided:
    ECS cluster details: {ecs_cluster_details}
    Task Definition JSON: {task_definition_json}

    Generate a CloudFormation template for the ECS Fargate and its dependent resources. 

    CRITICAL REQUIREMENTS - MUST FOLLOW EXACTLY:
    1. Parse the Task Definition JSON to extract the actual container image, port, and name
    2. DO NOT create a Parameters section with defaults
    3. DO NOT use !Ref for ContainerImage, ContainerName, or ContainerPort
    4. Use the extracted values DIRECTLY in the Resources section
    5. CRITICAL: Include AWS::ECS::TaskDefinition resource with ContainerDefinitions
    6. CRITICAL: ECS Service MUST reference the TaskDefinition with TaskDefinition: !Ref
    7. CRITICAL: Use dynamic availability zones with !GetAZs instead of hardcoded zones
    8. EXAMPLES of extraction (use actual values from YOUR task definition JSON):
       - If YOUR JSON has "image": "node:16" → write Image: node:16 directly
       - If YOUR JSON has "containerPort": 3000 → write ContainerPort: 3000 directly
       - If YOUR JSON has "name": "web-app" → write Name: web-app directly

    FORBIDDEN - DO NOT INCLUDE:
    - Parameters section
    - !Ref ContainerImage, !Ref ContainerName, !Ref ContainerPort
    - Default values like nginx, app, or port 80
    - Hardcoded availability zones like us-east-1a

    REQUIRED COMPLETE TEMPLATE - MANDATORY ECS RESOURCES:
    Generate a COMPLETE CloudFormation template with essential ECS resources.
    
    MANDATORY RESOURCES (required for working ECS Fargate):
    - AWSTemplateFormatVersion and Description
    - VPC with public subnets using !GetAZs for availability zones
    - Internet Gateway and Route Tables
    - ECS Cluster 
    - AWS::ECS::TaskDefinition with ContainerDefinitions array
    - ECS Service with TaskDefinition: !Ref and NetworkConfiguration
    - Security Groups for ECS tasks (specific ports, not -1)
    - IAM roles for task execution (AmazonECSTaskExecutionRolePolicy)
    - CloudWatch Logs Group
    - Outputs section with key resource references
    
    OPTIONAL RESOURCES (create only if user specifically requests load balancing):
    - Application Load Balancer and Target Group (only if user mentions ALB/load balancer)
    - ALB Security Groups (only if ALB is created)
    - LoadBalancer configuration in ECS Service (only if ALB is created)
    
    TEMPLATE STRUCTURE EXAMPLE:
    AWSTemplateFormatVersion: '2010-09-09'
    Description: 'ECS Fargate application'
    Resources:
      VPC:
        Type: AWS::EC2::VPC
      PublicSubnet1:
        AvailabilityZone: !Select [0, !GetAZs '']
      ECSTaskDefinition:
        Type: AWS::ECS::TaskDefinition
        Properties:
          ContainerDefinitions:
            - Name: [extracted-name]
              Image: [extracted-image]
              PortMappings:
                - ContainerPort: [extracted-port]
      ECSService:
        Type: AWS::ECS::Service
        Properties:
          TaskDefinition: !Ref ECSTaskDefinition
    
    If no load balancer is mentioned, create ECS Service without LoadBalancers configuration.
    Extract container values from Task Definition JSON and use directly in template.
    The output should be in YAML format and enclosed in triple backticks with the 'yaml' marker.
    
    MANDATORY OUTPUT FORMAT:
    ```yaml
    [Your CloudFormation template here]
    ```
    
    DO NOT return plain text without code block markers.
'''

cloudformation_generation_ec2_template = '''
    Based on all the details provided:
    ECS cluster details: {ecs_cluster_details}
    Task Definition JSON: {task_definition_json}

    Generate a CloudFormation template for ECS with EC2 Auto Scaling and its dependent resources.

    CRITICAL REQUIREMENTS - MUST FOLLOW EXACTLY:
    1. Parse the Task Definition JSON to extract the actual container image, port, and name
    2. DO NOT create a Parameters section with defaults
    3. DO NOT use !Ref for ContainerImage, ContainerName, or ContainerPort
    4. Use the extracted values DIRECTLY in the Resources section
    5. CRITICAL: Include AWS::ECS::TaskDefinition resource with ContainerDefinitions
    6. CRITICAL: ECS Service MUST reference the TaskDefinition with TaskDefinition: !Ref
    7. CRITICAL: Use dynamic availability zones with !GetAZs instead of hardcoded zones
    8. EXAMPLES of extraction (use actual values from YOUR task definition JSON):
       - If YOUR JSON has "image": "node:16" → write Image: node:16 directly
       - If YOUR JSON has "containerPort": 3000 → write ContainerPort: 3000 directly
       - If YOUR JSON has "name": "web-app" → write Name: web-app directly

    FORBIDDEN - DO NOT INCLUDE:
    - Parameters section
    - !Ref ContainerImage, !Ref ContainerName, !Ref ContainerPort
    - Default values like nginx, app, or port 80
    - Hardcoded availability zones like us-east-1a

    REQUIRED COMPLETE TEMPLATE - MANDATORY ECS RESOURCES:
    Generate a COMPLETE CloudFormation template with essential ECS resources.
    
    MANDATORY RESOURCES (required for working ECS with EC2):
    - AWSTemplateFormatVersion and Description
    - VPC with public/private subnets using !GetAZs for availability zones
    - Internet Gateway, NAT Gateway, and Route Tables
    - ECS Cluster with EC2 capacity provider
    - AWS::ECS::TaskDefinition with ContainerDefinitions array
    - ECS Service with TaskDefinition: !Ref
    - Auto Scaling Group and Launch Template for EC2 instances
    - Security Groups for ECS tasks and EC2 instances
    - IAM roles for task execution and EC2 instances
    - CloudWatch Logs Group
    - Outputs section with key resource references
    
    OPTIONAL RESOURCES (create only if user specifically requests load balancing):
    - Application Load Balancer and Target Group (only if user mentions ALB/load balancer)
    - ALB Security Groups (only if ALB is created)
    - LoadBalancer configuration in ECS Service (only if ALB is created)
    
    If no load balancer is mentioned, create ECS Service without LoadBalancers configuration.
    Extract container values from Task Definition JSON and use directly in template.
    The output should be in YAML format and enclosed in triple backticks with the 'yaml' marker.
    
    MANDATORY OUTPUT FORMAT:
    ```yaml
    [Your CloudFormation template here]
    ```
    
    DO NOT return plain text without code block markers.
'''
       - If YOUR JSON has "image": "node:16" → write Image: node:16 directly
       - If YOUR JSON has "containerPort": 3000 → write ContainerPort: 3000 directly
       - If YOUR JSON has "name": "web-app" → write Name: web-app directly

    FORBIDDEN - DO NOT INCLUDE:
    - Parameters section
    - !Ref ContainerImage, !Ref ContainerName, !Ref ContainerPort
    - Default values like nginx, app, or port 80

    REQUIRED COMPLETE TEMPLATE - MANDATORY ECS RESOURCES:
    Generate a COMPLETE CloudFormation template with essential ECS resources.
    
    MANDATORY RESOURCES (required for working ECS with EC2):
    - VPC with public/private subnets and NAT gateway
    - ECS Cluster
    - Auto Scaling Group and Launch Template for EC2 instances
    - Task Definition with extracted container values, ExecutionRole, TaskRole
    - ECS Service
    - Security Groups for ECS tasks
    - IAM roles for task execution and EC2 instances
    - CloudWatch Logs Group
    
    OPTIONAL RESOURCES (create only if user specifically requests load balancing):
    - Application Load Balancer and Target Group (only if user mentions ALB/load balancer)
    - ALB Security Groups (only if ALB is created)
    - LoadBalancer configuration in ECS Service (only if ALB is created)
    
    If no load balancer is mentioned, create ECS Service without LoadBalancers configuration.
    Extract container values from Task Definition JSON and use directly in template.
    The output should be in YAML format and enclosed in triple backticks with the 'yaml' marker.
'''

# Create ChatPromptTemplate objects from templates
supervisor_prompt = ChatPromptTemplate.from_template(supervisor_template)
ecs_cluster_fargate_prompt = ChatPromptTemplate.from_template(ecs_cluster_fargate_template)
task_definition_prompt = ChatPromptTemplate.from_template(task_definition_template)
cloudformation_generation_fargate_prompt = ChatPromptTemplate.from_template(cloudformation_generation_fargate_template)
cloudformation_generation_ec2_prompt = ChatPromptTemplate.from_template(cloudformation_generation_ec2_template)

# Define chains for each process
supervisor_chain = (
    RunnableParallel({"input": RunnablePassthrough()})
    .assign(response=supervisor_prompt | model | StrOutputParser())
    .pick(["response"])
)

ecs_cluster_fargate_chain = (
    RunnableParallel({"initial_requirement": RunnablePassthrough()})
    .assign(response=ecs_cluster_fargate_prompt | model | StrOutputParser())
    .pick(["response"])
)

task_definition_chain = (
    RunnableParallel({"dockerfile_content": RunnablePassthrough()})
    .assign(response=task_definition_prompt | model | StrOutputParser())
    .pick(["response"])
)

cloudformation_generation_fargate_chain = (
    RunnableParallel({"task_definition_json": task_definition_chain, "ecs_cluster_details": RunnablePassthrough()})
    .assign(response=cloudformation_generation_fargate_prompt | model | StrOutputParser())
    .pick(["response"])
)

cloudformation_generation_ec2_chain = (
    RunnableParallel({"task_definition_json": task_definition_chain, "ecs_cluster_details": RunnablePassthrough()})
    .assign(response=cloudformation_generation_ec2_prompt | model | StrOutputParser())
    .pick(["response"])
)

def read_dockerfile(file_path):
    try:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Dockerfile not found at {file_path}")
        
        with open(file_path, 'r', encoding="utf-8") as file:
            content = file.read().strip()
            
        if not content:
            raise ValueError("Dockerfile is empty")
            
        if not content.upper().startswith('FROM'):
            raise ValueError("Invalid Dockerfile: does not start with FROM instruction")
            
        return content
    except FileNotFoundError:
        st.error(f"Dockerfile not found at {file_path}")
        raise
    except IOError as e:
        st.error(f"Error reading Dockerfile: {e}")
        raise

def extract_yaml_from_response(response):
    match = re.search(r'```yaml\s*(.*?)\s*```', response, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        st.error("Failed to extract YAML content: markers not found")
        raise ValueError("Failed to extract YAML content: markers not found")

def write_output_to_file(content, file_path):
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding="utf-8") as file:
            file.write(content)
        st.info(f"Content written to {file_path}")
        return f"Content written to {file_path}"
    except Exception as e:
        st.error(f"Error writing to file {file_path}: {e}")
        raise

def extract_content_from_ai_message(message):
    if isinstance(message, AIMessage):
        return message.content
    elif isinstance(message, str):
        return message
    else:
        st.error(f"Unexpected message type: {type(message)}")
        raise ValueError(f"Unexpected message type: {type(message)}")

def regenerate_cloudformation_template_if_error(template_body, stack_name):
    PROMPT = """
        You are a CloudFormation expert. Analyze the following CloudFormation template:

        {template_body}

        If there are any errors or improvements to be made, provide a corrected version of the entire template. 
        If no changes are needed, simply return the original template.

        The output must be in YAML format, enclosed in triple backticks with the 'yaml' marker. 
        Do not include any additional text or explanations outside the code block.
    """
    question_prompt = PromptTemplate.from_template(template=PROMPT)
    query = question_prompt.format(template_body=template_body)
    
    st.info("Analyzing and potentially fixing CloudFormation template...")
    response = model.invoke(query)
    response = extract_content_from_ai_message(response)
    
    fixed_template = extract_yaml_from_response(response)
    
    if fixed_template:
        st.info("CloudFormation template analysis complete")
        return fixed_template
    else:
        st.info("No changes made to the CloudFormation template")
        return template_body

def extract_json_from_response(response):
    """Extract JSON content from AI response"""
    import re
    import json
    
    # Try to find JSON in code blocks
    json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON without code blocks
    json_match = re.search(r'\{.*\}', response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    
    # If no valid JSON found, return the response as is
    return response

def extract_dockerfile_values(task_definition_json):
    """Extract key values from task definition JSON"""
    try:
        if isinstance(task_definition_json, str):
            task_def = extract_json_from_response(task_definition_json)
        else:
            task_def = task_definition_json
            
        if isinstance(task_def, dict) and 'containerDefinitions' in task_def:
            container = task_def['containerDefinitions'][0]
            return {
                'image': container.get('image', 'my-app:latest'),
                'port': container.get('portMappings', [{}])[0].get('containerPort', 8080),
                'name': container.get('name', 'app')
            }
    except:
        pass
    
    return {'image': 'my-app:latest', 'port': 8080, 'name': 'app'}

def generate_cloudformation_template(initial_requirement, dockerfile_path):
    try:
        start_time = time.time()
        
        if not initial_requirement or not dockerfile_path:
            raise ValueError("Initial requirement and Dockerfile path are required.")
        
        st.info("Classifying input requirement...")
        classification_result = supervisor_chain.invoke({"input": initial_requirement})["response"]
        st.info(f"Classification result: {classification_result}")

        if "fargate" in classification_result.lower():
            st.info("Generating ECS Fargate configuration...")
            ecs_cluster_details = ecs_cluster_fargate_chain.invoke({"initial_requirement": initial_requirement})["response"]
            st.info(f"ECS Fargate configuration generated: {ecs_cluster_details}")

            st.info("Reading Dockerfile content...")
            dockerfile_content = read_dockerfile(dockerfile_path)
            st.info(f"Dockerfile content read successfully")

            st.info("Generating task definition JSON...")
            task_definition_response = task_definition_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
            st.info(f"Task definition JSON generated")
            
            # Extract values from task definition for CloudFormation
            dockerfile_values = extract_dockerfile_values(task_definition_response)
            st.info(f"Extracted values: {dockerfile_values}")
            
            # Enhanced task definition JSON with extracted values
            enhanced_task_def = f"Task Definition with extracted values: Image={dockerfile_values['image']}, Port={dockerfile_values['port']}, Name={dockerfile_values['name']}. Original: {task_definition_response}"

            st.info("Generating CloudFormation template...")
            cloudformation_response = cloudformation_generation_fargate_chain.invoke({
                "ecs_cluster_details": ecs_cluster_details,
                "task_definition_json": enhanced_task_def
            })["response"]
        elif "ec2" in classification_result.lower() or "autoscaling" in classification_result.lower():
            st.info("Generating ECS EC2 autoscaling configuration...")
            ecs_cluster_details = ecs_cluster_fargate_chain.invoke({"initial_requirement": initial_requirement})["response"]
            st.info(f"ECS EC2 configuration generated: {ecs_cluster_details}")

            st.info("Reading Dockerfile content...")
            dockerfile_content = read_dockerfile(dockerfile_path)
            st.info(f"Dockerfile content read successfully")

            st.info("Generating task definition JSON...")
            task_definition_response = task_definition_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
            st.info(f"Task definition JSON generated")
            
            # Extract values from task definition for CloudFormation
            dockerfile_values = extract_dockerfile_values(task_definition_response)
            st.info(f"Extracted values: {dockerfile_values}")
            
            # Enhanced task definition JSON with extracted values
            enhanced_task_def = f"Task Definition with extracted values: Image={dockerfile_values['image']}, Port={dockerfile_values['port']}, Name={dockerfile_values['name']}. Original: {task_definition_response}"

            st.info("Generating CloudFormation template...")
            cloudformation_response = cloudformation_generation_fargate_chain.invoke({
                "ecs_cluster_details": ecs_cluster_details,
                "task_definition_json": enhanced_task_def
            })["response"]
        elif "ec2" in classification_result.lower() or "autoscaling" in classification_result.lower():
            st.info("Generating ECS EC2 autoscaling configuration...")
            ecs_cluster_details = ecs_cluster_fargate_chain.invoke({"initial_requirement": initial_requirement})["response"]
            st.info(f"ECS EC2 configuration generated: {ecs_cluster_details}")

            st.info("Reading Dockerfile content...")
            dockerfile_content = read_dockerfile(dockerfile_path)
            st.info(f"Dockerfile content read successfully")

            st.info("Generating task definition JSON...")
            task_definition_response = task_definition_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
            st.info(f"Task definition JSON generated")
            
            # Extract values from task definition for CloudFormation
            dockerfile_values = extract_dockerfile_values(task_definition_response)
            st.info(f"Extracted values: {dockerfile_values}")
            
            # Enhanced task definition JSON with extracted values
            enhanced_task_def = f"Task Definition with extracted values: Image={dockerfile_values['image']}, Port={dockerfile_values['port']}, Name={dockerfile_values['name']}. Original: {task_definition_response}"

            st.info("Generating CloudFormation template...")
            cloudformation_response = cloudformation_generation_ec2_chain.invoke({
                "ecs_cluster_details": ecs_cluster_details,
                "task_definition_json": enhanced_task_def
            })["response"]
        else:
            st.error(f"Unsupported deployment type: {classification_result}")
            raise ValueError(f"Unsupported deployment type: {classification_result}")

        cloudformation_template = extract_yaml_from_response(cloudformation_response)
        
        if cloudformation_template:
            st.info("CloudFormation template generated successfully")
        else:
            st.error("Failed to generate CloudFormation template")
            raise ValueError("Failed to generate CloudFormation template")

        end_time = time.time()
        st.info(f"Time taken for generating CloudFormation template: {end_time - start_time} seconds")

        return cloudformation_template
    except Exception as e:
        st.error(f"Error in generate_cloudformation_template: {str(e)}")
        raise

def get_fixed_cloudformation_template(user_input, dockerfile_path):
    try:
        start_time = time.time()
        
        if not user_input or not dockerfile_path:
            raise ValueError("User input and Dockerfile path are required")
        
        # Generate the initial template
        cloudformation_template = generate_cloudformation_template(user_input, dockerfile_path)
        
        if cloudformation_template is None:
            raise ValueError("Failed to generate initial CloudFormation template")

        # Write the initial template to a file
        initial_template_path = "iac/initial_cloudformation_template.yaml"
        write_output_to_file(cloudformation_template, initial_template_path)
        st.info(f"Initial CloudFormation template written to {initial_template_path}")

        # Generate a unique stack name
        stack_name = f"ecs-stack-{int(time.time())}"

        # Attempt to fix the template if there are any errors
        fixed_template = regenerate_cloudformation_template_if_error(cloudformation_template, stack_name)
        
        if fixed_template:
            # Write the fixed template to a file
            fixed_template_path = "iac/fixed_cloudformation_template.yaml"
            write_output_to_file(fixed_template, fixed_template_path)
            st.info(f"Fixed CloudFormation template written to {fixed_template_path}")
        else:
            st.warning("Failed to fix CloudFormation template. Using the initial template.")
            fixed_template = cloudformation_template

        end_time = time.time()
        st.info(f"Total time taken: {end_time - start_time} seconds")

        return fixed_template
    except Exception as e:
        st.error(f"Error in get_fixed_cloudformation_template: {str(e)}")
        return None

# Main execution (if needed)
if __name__ == "__main__":
    # Add any main execution code here
    pass
