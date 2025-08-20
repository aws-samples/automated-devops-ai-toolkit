import logging
import os
import subprocess
import re
import time
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.runnables import RunnablePassthrough, RunnableParallel
from langchain.pydantic_v1 import BaseModel, Field
from langchain_core.tools import tool
from langchain_core.output_parsers import StrOutputParser
from langchain.agents.output_parsers import XMLAgentOutputParser
from langchain import hub
from langchain.agents import AgentExecutor
from core.bedrock_definition import get_model
from langchain_community.callbacks.streamlit import StreamlitCallbackHandler
import streamlit as st

# Define the ExecuteTerraformInput class for tool input
class ExecuteTerraformInput(BaseModel):
    file_path: str = Field(description="The path to the Terraform configuration file.")

# Initialize the Bedrock model
model = get_model()

# Define prompt templates
supervisor_template = '''
    You are an AWS ECS expert. Classify the input requirement and output the setup pattern (either "fargate" or "ec2-autoscaling") without any additional text or explanations.
    Input: {input}
    Output: 
'''

ecs_cluster_fargate_template = '''
    You are a Terraform expert who generates AWS ECS Fargate configuration for multiple environments.
    Initial requirement: {initial_requirement}

    Please provide the following details:
    1. Name of the ECS cluster.
    2. VPC ID to associate the ECS cluster with.
    3. Number of Fargate tasks required.
    4. CPU and memory resources for each task (e.g., 512 vCPU, 1024 MiB memory).
    5. Any specific tags to be applied to the cluster (format: key=value, multiple tags separated by commas).
    6. Additional networking requirements, if any (e.g., subnets, security groups).
'''

ecs_cluster_ec2_autoscaling_template = '''
    You are a Terraform expert who generates AWS ECS EC2 Autoscaling configuration for multiple environments.
    Initial requirement: {initial_requirement}

    Please provide the following details:
    1. Name of the ECS cluster.
    2. VPC ID to associate the ECS cluster with.
    3. Number of EC2 instances needed for autoscaling.
    4. EC2 instance types to be used (e.g., t3.medium).
    5. Autoscaling policy (e.g., target tracking, step scaling, desired capacity).
    6. Any specific tags to be applied to the cluster (format: key=value, multiple tags separated by commas).
    7. Additional networking requirements, if any (e.g., subnets, security groups).
    8. Details for creating an Auto Scaling Group.
'''

task_definition_template = '''
    Generate a task definition in HCL format based on the Dockerfile content provided.
    Dockerfile content: {dockerfile_content}

    IMPORTANT: Extract the following information from the Dockerfile:
    - Base image from FROM instruction (use this as the container image)
    - Exposed ports from EXPOSE instruction (use for containerPort)
    - Working directory from WORKDIR instruction
    - Environment variables from ENV instructions
    - Resource requirements based on application type
    
    DO NOT use hardcoded values like "my-app:latest", "nginx", or port 8080.
    Use the actual information from the Dockerfile provided.
    
    If no EXPOSE instruction is found, analyze the Dockerfile to determine the likely port.
    If no specific image tag is mentioned, use the base image with ":latest" tag.
    
    EXAMPLES of extraction (use actual values from YOUR Dockerfile):
    - If YOUR Dockerfile has FROM node:16 → use image = "node:16"
    - If YOUR Dockerfile has EXPOSE 3000 → use containerPort = 3000
    - If YOUR Dockerfile builds a web-app → use name = "web-app"
    
    Output format (replace placeholders with actual Dockerfile values):
    
    container_definitions = jsonencode([
      {{{{
        name      = "[extract-actual-app-name]"
        image     = "[extract-actual-image-name:tag]"
        cpu       = appropriate-cpu-value
        memory    = appropriate-memory-value
        essential = true
        portMappings = [
          {{{{
            containerPort = [extract-actual-port-number]
            hostPort      = [extract-actual-port-number]
            protocol      = "tcp"
          }}}}
        ]
        environment = [
          # Add any ENV variables from Dockerfile
        ]
        logConfiguration = {{{{
          logDriver = "awslogs"
          options = {{{{
            "awslogs-group"         = "/ecs/[extract-actual-app-name]"
            "awslogs-region"        = "us-east-1"
            "awslogs-stream-prefix" = "ecs"
          }}}}
        }}}}
      }}}}
    ])
'''

terraform_generation_fargate_template = '''
    Based on all the details provided:
    ECS cluster details: {ecs_cluster_details}
    Task Definition HCL: {task_definition_json}

    Generate reusable Terraform configurations for ECS Fargate with essential resources.

    MANDATORY RESOURCES (required for working ECS Fargate):
    - VPC with public subnets and internet gateway
    - ECS Cluster
    - Task Definition with extracted container values
    - ECS Service with network configuration
    - Security Groups for ECS tasks
    - IAM roles for task execution
    - CloudWatch Logs Group
    
    OPTIONAL RESOURCES (create only if user specifically requests load balancing):
    - Application Load Balancer and Target Group (only if user mentions ALB/load balancer)
    - ALB Security Groups (only if ALB is created)
    - Load balancer configuration in ECS Service (only if ALB is created)

    Requirements:
    1. Do not use any hardcoded resource IDs in the code.
    2. Include required data sources like aws_availability_zones and aws_caller_identity.
    3. Always generate end-to-end code using Terraform.
    4. Use the provided HCL container_definitions directly in aws_ecs_task_definition resource.
    5. Avoid cyclic dependencies in the code.
    6. Include all necessary networking components such as custom VPC, subnets, IGW, and security groups.
    7. Ensure to create IAM roles required for the ECS tasks and task execution, including policies for necessary permissions.
    8. If no load balancer is mentioned, create ECS Service without load_balancer configuration.
    9. DO NOT use deprecated template provider or template_file data source
    10. Use templatefile() function or locals for user data instead of template_file
    11. Only use aws provider - no template, null, or other deprecated providers
    12. DO NOT use variables - embed all values directly in resources
    13. DO NOT prompt for user input - generate complete standalone Terraform code
    14. Use extracted container values directly in container_definitions, not as variables
    9. User should be able to run the code without being prompted for any additional inputs.
    10. Do not refer to undeclared variables or resources in the code.
    11. Include data sources for availability zones: data "aws_availability_zones" "available" {{}}
    12. Use the provided container_definitions HCL directly without modification.

    The output should be in code format and enclosed in triple backticks with the 'hcl' marker.
'''

terraform_generation_ec2_autoscaling_template = '''
    Based on all the details provided:
    ECS cluster details: {ecs_cluster_details}
    Task Definition HCL: {task_definition_json}

    Generate reusable Terraform configurations for ECS EC2 Autoscaling with essential resources.

    MANDATORY RESOURCES (required for working ECS with EC2):
    - VPC with public/private subnets and NAT gateway
    - ECS Cluster
    - Auto Scaling Group and Launch Template for EC2 instances
    - Task Definition with extracted container values
    - ECS Service
    - Security Groups for ECS tasks
    - IAM roles for task execution and EC2 instances
    - CloudWatch Logs Group
    
    OPTIONAL RESOURCES (create only if user specifically requests load balancing):
    - Application Load Balancer and Target Group (only if user mentions ALB/load balancer)
    - ALB Security Groups (only if ALB is created)
    - Load balancer configuration in ECS Service (only if ALB is created)

    Requirements:
    1. Do not use any hardcoded resource IDs in the code.
    2. Include required data sources like aws_availability_zones and aws_caller_identity.
    3. Always generate end-to-end code using Terraform.
    4. Use the provided HCL container_definitions directly in aws_ecs_task_definition resource.
    5. Avoid cyclic dependencies in the code.
    6. Include all necessary networking components such as custom VPC, subnets, IGW, NATGW, and security groups.
    7. Ensure to create IAM roles required for the ECS tasks and task execution, including policies for necessary permissions.
    8. If no load balancer is mentioned, create ECS Service without load_balancer configuration.
    9. Include Auto Scaling Group (ASG) configuration for the EC2 instances.
    10. User should be able to run the code without being prompted for any additional inputs.
    11. DO NOT use deprecated template provider or template_file data source
    12. Use templatefile() function or locals for user data instead of template_file
    13. Only use aws provider - no template, null, or other deprecated providers
    14. DO NOT use variables - embed all values directly in resources
    15. DO NOT prompt for user input - generate complete standalone Terraform code
    16. Use extracted container values directly in container_definitions, not as variables
    11. Do not refer to undeclared variables or resources in the code.
    12. Include data sources for availability zones: data "aws_availability_zones" "available" {{}}
    13. Use the provided container_definitions HCL directly without modification.

    The output should be in code format and enclosed in triple backticks with the 'hcl' marker.
'''

# Create ChatPromptTemplate objects from templates
supervisor_prompt = ChatPromptTemplate.from_template(supervisor_template)
ecs_cluster_fargate_prompt = ChatPromptTemplate.from_template(ecs_cluster_fargate_template)
ecs_cluster_ec2_autoscaling_prompt = ChatPromptTemplate.from_template(ecs_cluster_ec2_autoscaling_template)
task_definition_prompt = ChatPromptTemplate.from_template(task_definition_template)
terraform_generation_fargate_prompt = ChatPromptTemplate.from_template(terraform_generation_fargate_template)
terraform_generation_ec2_autoscaling_prompt = ChatPromptTemplate.from_template(terraform_generation_ec2_autoscaling_template)

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

ecs_cluster_ec2_autoscaling_chain = (
    RunnableParallel({"initial_requirement": RunnablePassthrough()})
    .assign(response=ecs_cluster_ec2_autoscaling_prompt | model | StrOutputParser())
    .pick(["response"])
)

task_definition_chain = (
    RunnableParallel({"dockerfile_content": RunnablePassthrough()})
    .assign(response=task_definition_prompt | model | StrOutputParser())
    .pick(["response"])
)

terraform_generation_fargate_chain = (
    RunnableParallel({"task_definition_json": task_definition_chain, "ecs_cluster_details": RunnablePassthrough()})
    .assign(response=terraform_generation_fargate_prompt | model | StrOutputParser())
    .pick(["response"])
)

terraform_generation_ec2_autoscaling_chain = (
    RunnableParallel({"task_definition_json": task_definition_chain, "ecs_cluster_details": RunnablePassthrough()})
    .assign(response=terraform_generation_ec2_autoscaling_prompt | model | StrOutputParser())
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
    except Exception as e:
        st.error(f"Error reading Dockerfile: {e}")
        raise

# Removed extract_json_from_response function as we now use HCL directly

@tool("ReadFiles", args_schema=ExecuteTerraformInput, return_direct=False)
def read_files(file_path):
    """
    Read the content of the Terraform configuration file.
    Args:
        file_path (str): The path to the Terraform configuration file.
    Returns:
        str: The content of the Terraform configuration file.
    """
    if os.path.isfile(file_path):
        with open(file_path, 'r', encoding="utf-8") as file:
            return file.read()
    elif os.path.isdir(file_path):
        content = ""
        for f in os.listdir(file_path):
            if f.endswith(".tf"):
                p = os.path.join(file_path, f)
                content += open(p, 'r', encoding="utf-8").read()
        return content
    else:
        return f"Invalid path: {file_path}"

@tool("ExecuteTerraform", args_schema=ExecuteTerraformInput, return_direct=False)
def execute_terraform(file_path):
    """
    Execute Terraform commands to initialize and plan the Terraform configuration.
    Args:
        file_path (str): The path to the Terraform configuration file.
    Returns:
        str: The output of the Terraform plan command.
    """
    try:
        # Ensure we have a valid directory path
        if not file_path:
            working_dir = "iac"
        else:
            working_dir = os.path.dirname(file_path) or "iac"
        
        # Create directory if it doesn't exist
        os.makedirs(working_dir, exist_ok=True)
        
        result = subprocess.run(
            ['terraform', 'init'],
            cwd=working_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logging.info(f"Terraform init output: {result.stdout}")

        result = subprocess.run(
            ['terraform', 'plan'],
            cwd=working_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logging.info(f"Terraform plan output: {result.stdout}")
        return result.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing Terraform: {e.stderr}")
        return f"Error executing Terraform: {e.stderr}"

def generate_terraform_code(initial_requirement, dockerfile_path):
    start_time = time.time()
    st.info("Classifying input requirement...")
    classification_result = supervisor_chain.invoke({"input": initial_requirement})["response"]
    st.info(f"Classification result: {classification_result}")

    classification_result_line = classification_result.split('\n')[0]

    if "fargate" in classification_result_line.lower():
        st.info("Generating ECS Fargate configuration...")
        ecs_cluster_details = ecs_cluster_fargate_chain.invoke({"initial_requirement": initial_requirement})["response"]
        st.info(f"ECS Fargate configuration generated: {ecs_cluster_details}")

        st.info("Reading Dockerfile content...")
        dockerfile_content = read_dockerfile(dockerfile_path)
        st.info(f"Dockerfile content: {dockerfile_content}")

        st.info("Generating task definition HCL...")
        task_definition_response = task_definition_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
        st.info(f"Task definition response: {task_definition_response}")

        if not task_definition_response:
            raise ValueError("Task definition generation failed. Response is empty.")

        task_definition_hcl = task_definition_response.strip()

        st.info("Generating Terraform configuration...")
        terraform_response = terraform_generation_fargate_chain.invoke({
            "ecs_cluster_details": ecs_cluster_details,
            "task_definition_json": task_definition_hcl,
        })["response"]
    elif "ec2-autoscaling" in classification_result_line.lower():
        st.info("Generating ECS EC2 Autoscaling configuration...")
        ecs_cluster_details = ecs_cluster_ec2_autoscaling_chain.invoke({"initial_requirement": initial_requirement})["response"]
        st.info(f"ECS EC2 Autoscaling configuration generated: {ecs_cluster_details}")

        st.info("Reading Dockerfile content...")
        dockerfile_content = read_dockerfile(dockerfile_path)
        st.info(f"Dockerfile content: {dockerfile_content}")

        st.info("Generating task definition HCL...")
        task_definition_response = task_definition_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
        st.info(f"Task definition response: {task_definition_response}")

        if not task_definition_response:
            raise ValueError("Task definition generation failed. Response is empty.")

        task_definition_hcl = task_definition_response.strip()

        st.info("Generating Terraform configuration...")
        terraform_response = terraform_generation_ec2_autoscaling_chain.invoke({
            "ecs_cluster_details": ecs_cluster_details,
            "task_definition_json": task_definition_hcl,
        })["response"]
    else:
        st.error("Unable to classify input. Please provide more details.")
        return "Unable to classify input. Please provide more details."

    terraform_code = extract_terraform_code_from_output(terraform_response)
    
    end_time = time.time()
    st.info(f"Time taken for generating Terraform code: {end_time - start_time:.2f} seconds")

    return terraform_code

def extract_terraform_code_from_output(output):
    # Try multiple patterns to extract Terraform code
    patterns = [
        r'```hcl\s*(.*?)\s*```',      # ```hcl
        r'```terraform\s*(.*?)\s*```', # ```terraform  
        r'```tf\s*(.*?)\s*```',       # ```tf
        r'```\s*(.*?)\s*```'          # Generic ```
    ]
    
    for pattern in patterns:
        terraform_code_blocks = re.findall(pattern, output, re.DOTALL)
        if terraform_code_blocks:
            return "\n\n".join(terraform_code_blocks).strip()
    
    # If no code blocks found, return the output as-is (might be plain text)
    logging.warning("No code block markers found, returning raw output")
    return output.strip()

def get_fixed_terraform_code(user_input, dockerfile_path):
    terraform_code = generate_terraform_code(user_input, dockerfile_path)
    initial_terraform_file_path = "iac/main.tf"

    os.makedirs(os.path.dirname(initial_terraform_file_path), exist_ok=True)

    with open(initial_terraform_file_path, 'w', encoding="utf-8") as file:
        file.write(terraform_code)

    fixed_output = regenerate_terraform_code_if_error(initial_terraform_file_path)
    return fixed_output

def regenerate_terraform_code_if_error(initial_terraform_file_path):
    PROMPT = """
        You are a Terraform expert.
        1. Use the ReadFiles tool to access the Terraform code from {file_path}.
        2. Use the ExecuteTerraform tool to obtain the Terraform plan output.

        Analyze the Terraform plan output:
        - If there are no errors, provide the final output in code format, enclosed in triple backticks with the 'hcl' marker, and exit.
        - If errors are found, fix the issues in the Terraform code.

        Ensure the corrected Terraform code includes all necessary resources, comments, and changes. The output must be in code format, enclosed in triple backticks with the 'hcl' marker. Do not include any additional text or explanations.
    """
    question_prompt = PromptTemplate.from_template(template=PROMPT)
    query = question_prompt.format(file_path=initial_terraform_file_path)
    agent = terraform_plan_agent()
    
    st_callback = StreamlitCallbackHandler(st.container())
    agent_output = agent.invoke({"input": query}, {"callbacks": [st_callback]})
    terraform_code = extract_terraform_code_from_output(agent_output['output'])
    
    return terraform_code

def terraform_plan_agent():
    model = get_model()
    prompt = hub.pull("hwchase17/xml-agent-convo")
    tools = [read_files, execute_terraform]
    
    agent = (
            {
                "input": lambda x: x["input"],
                "agent_scratchpad": lambda x: convert_intermediate_steps(
                    x["intermediate_steps"]
                ),
                "tool_names": lambda x: convert_tools(tools),
            }
            | prompt.partial(tools=convert_tools(tools))
            | model.bind(stop=["</tool_input>", "</final_answer>"])
            | XMLAgentOutputParser()
    )

    agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True, return_intermediate_steps=True)
    return agent_executor

def convert_tools(tools):
    return "\n".join([f"{tool.name}: {tool.description}" for tool in tools])

def convert_intermediate_steps(intermediate_steps):
    log = ""
    for action, observation in intermediate_steps:
        log += (
            f"<tool>{action.tool}</tool><tool_input>{action.tool_input}"
            f"</tool_input><observation>{observation}</observation>"
        )
    return log
