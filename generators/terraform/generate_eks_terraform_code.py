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
    You are an AWS EKS expert. Classify the input requirement and output the setup pattern (either "fargate" or "ec2-nodegroup") without any additional text or explanations.
    Input: {input}
    Output: 
'''

eks_cluster_fargate_template = '''
    You are a Terraform expert who generates AWS EKS Fargate configuration.
    Initial requirement: {initial_requirement}

    Please provide the following details:
    1. Name of the EKS cluster.
    2. Kubernetes version (e.g., 1.28).
    3. VPC configuration requirements.
    4. Fargate profile configuration (namespaces, selectors).
    5. Any specific tags to be applied to the cluster.
    6. Additional networking requirements (subnets, security groups).
'''

eks_cluster_ec2_template = '''
    You are a Terraform expert who generates AWS EKS EC2 node group configuration.
    Initial requirement: {initial_requirement}

    Please provide the following details:
    1. Name of the EKS cluster.
    2. Kubernetes version (e.g., 1.28).
    3. Node group configuration (instance types, scaling settings).
    4. EC2 instance types to be used (e.g., t3.medium).
    5. Scaling configuration (min, max, desired capacity).
    6. Any specific tags to be applied to the cluster.
    7. Additional networking requirements (subnets, security groups).
'''

kubernetes_manifest_template = '''
    Generate Kubernetes manifests based on the Dockerfile content provided.
    Dockerfile content: {dockerfile_content}

    IMPORTANT: Extract the following information from the Dockerfile:
    - Base image from FROM instruction (use this as the container image)
    - Exposed ports from EXPOSE instruction (use for containerPort and service port)
    - Working directory from WORKDIR instruction
    - Environment variables from ENV instructions
    - Resource requirements based on application type
    
    DO NOT use hardcoded values like "nginx", "my-app:latest", or port 80/8080.
    Use the actual information from the Dockerfile provided.

    EXAMPLES of extraction (use actual values from YOUR Dockerfile):
    - If YOUR Dockerfile has FROM node:16 → use image: node:16
    - If YOUR Dockerfile has EXPOSE 3000 → use containerPort: 3000
    - If YOUR Dockerfile builds a web-app → use name: web-app

    Generate the following Kubernetes resources with extracted values:
    - Deployment with container specifications (use extracted image and ports)
    - Service to expose the application (use extracted ports)
    - ConfigMap if needed for configuration (use extracted ENV variables)
    - Ingress for external access (use extracted service port)

    Extract and use the actual image name, ports, environment variables, and configuration from the provided Dockerfile content.
'''

terraform_generation_fargate_template = '''
    Based on all the details provided:
    EKS cluster details: {eks_cluster_details}
    Kubernetes Manifests: {kubernetes_manifests}

    Generate reusable Terraform configurations for EKS Fargate and its dependent resources.

    CRITICAL REQUIREMENTS:
    1. DO NOT use external modules (no "module" blocks)
    2. Generate all resources inline using standard Terraform AWS provider resources
    3. DO NOT reference undefined modules like "alb_ingress" or external module sources
    4. Use only standard AWS provider resources: aws_eks_cluster, aws_eks_fargate_profile, aws_vpc, etc.
    5. Extract container image, ports, and names from the Kubernetes manifests
    6. Include all necessary resources: VPC, subnets, security groups, IAM roles, EKS cluster, Fargate profiles
    7. For ALB, use aws_lb, aws_lb_listener, aws_lb_target_group resources directly
    8. All resources must be self-contained without external module dependencies

    MANDATORY RESOURCES (required for working EKS Fargate):
    - VPC with public subnets and internet gateway
    - EKS Cluster with Fargate profiles
    - IAM roles for cluster and Fargate profiles
    - Security Groups for EKS
    - OIDC provider for service accounts
    - CloudWatch Logs Group
    
    OPTIONAL RESOURCES (create only if user specifically requests load balancing):
    - Application Load Balancer and Target Group (only if user mentions ALB/load balancer/ingress)
    - ALB Ingress Controller setup (only if ALB is requested)
    - Ingress resources (only if load balancing is requested)

    Requirements:
    1. Create EKS cluster with Fargate profiles
    2. Include VPC, subnets, IGW, and security groups
    3. Create IAM roles for cluster and Fargate profiles
    4. Configure OIDC provider for service accounts
    5. Generate Kubernetes manifests as Terraform resources
    6. Follow security best practices
    7. Avoid hardcoded values and cyclic dependencies
    8. If no load balancer/ingress is mentioned, create basic Kubernetes Service of type ClusterIP
    9. DO NOT use deprecated template provider or template_file data source
    10. Use templatefile() function or locals instead of template_file
    11. Only use aws and kubernetes providers - no template, null, or other deprecated providers
    12. CRITICAL: DO NOT use variables - embed all values directly in resources
    13. CRITICAL: DO NOT prompt for user input - generate complete standalone Terraform code
    14. CRITICAL: DO NOT use heredoc syntax or templatefile() for Kubernetes manifests
    15. CRITICAL: Use jsonencode() or direct HCL syntax for all configurations

    The output should be in code format and enclosed in triple backticks with the 'hcl' marker.
    
    MANDATORY OUTPUT FORMAT:
    ```hcl
    [Your Terraform code here]
    ```
    
    DO NOT return plain text without code block markers.
'''

terraform_generation_ec2_template = '''
    Based on all the details provided:
    EKS cluster details: {eks_cluster_details}
    Kubernetes Manifests: {kubernetes_manifests}

    Generate reusable Terraform configurations for EKS with EC2 node groups and dependent resources.

    CRITICAL REQUIREMENTS:
    1. DO NOT use external modules (no "module" blocks)
    2. Generate all resources inline using standard Terraform AWS provider resources
    3. DO NOT reference undefined modules like "alb_ingress" or external module sources
    4. Use only standard AWS provider resources: aws_eks_cluster, aws_eks_node_group, aws_vpc, etc.
    5. Extract container image, ports, and names from the Kubernetes manifests
    6. Include all necessary resources: VPC, subnets, security groups, IAM roles, EKS cluster, node groups
    7. For ALB, use aws_lb, aws_lb_listener, aws_lb_target_group resources directly
    8. All resources must be self-contained without external module dependencies

    MANDATORY RESOURCES (required for working EKS with EC2):
    - VPC with public/private subnets, IGW, and NAT Gateway
    - EKS Cluster with EC2 node groups
    - IAM roles for cluster and node groups
    - Security Groups for EKS
    - OIDC provider for service accounts
    - CloudWatch Logs Group
    
    OPTIONAL RESOURCES (create only if user specifically requests load balancing):
    - Application Load Balancer and Target Group (only if user mentions ALB/load balancer/ingress)
    - ALB Ingress Controller setup (only if ALB is requested)
    - Ingress resources (only if load balancing is requested)

    Requirements:
    1. Create EKS cluster with EC2 node groups
    2. Include VPC, subnets, IGW, NAT Gateway, and security groups
    3. Create IAM roles for cluster and node groups
    4. Configure OIDC provider for service accounts
    5. Generate Kubernetes manifests as Terraform resources
    6. Follow security best practices
    7. Avoid hardcoded values and cyclic dependencies
    8. If no load balancer/ingress is mentioned, create basic Kubernetes Service of type ClusterIP
    9. DO NOT use deprecated template provider or template_file data source
    10. Use templatefile() function or locals instead of template_file
    11. Only use aws and kubernetes providers - no template, null, or other deprecated providers
    8. Avoid hardcoded values and cyclic dependencies
    9. CRITICAL: DO NOT use variables - embed all values directly in resources
    10. CRITICAL: DO NOT prompt for user input - generate complete standalone Terraform code
    11. CRITICAL: DO NOT use heredoc syntax or templatefile() for configurations
    12. CRITICAL: Use jsonencode() or direct HCL syntax for all configurations

    The output should be in code format and enclosed in triple backticks with the 'hcl' marker.
    
    MANDATORY OUTPUT FORMAT:
    ```hcl
    [Your Terraform code here]
    ```
    
    DO NOT return plain text without code block markers.
'''

# Create ChatPromptTemplate objects
supervisor_prompt = ChatPromptTemplate.from_template(supervisor_template)
eks_cluster_fargate_prompt = ChatPromptTemplate.from_template(eks_cluster_fargate_template)
eks_cluster_ec2_prompt = ChatPromptTemplate.from_template(eks_cluster_ec2_template)
kubernetes_manifest_prompt = ChatPromptTemplate.from_template(kubernetes_manifest_template)
terraform_generation_fargate_prompt = ChatPromptTemplate.from_template(terraform_generation_fargate_template)
terraform_generation_ec2_prompt = ChatPromptTemplate.from_template(terraform_generation_ec2_template)

# Define chains
supervisor_chain = (
    RunnableParallel({"input": RunnablePassthrough()})
    .assign(response=supervisor_prompt | model | StrOutputParser())
    .pick(["response"])
)

eks_cluster_fargate_chain = (
    RunnableParallel({"initial_requirement": RunnablePassthrough()})
    .assign(response=eks_cluster_fargate_prompt | model | StrOutputParser())
    .pick(["response"])
)

eks_cluster_ec2_chain = (
    RunnableParallel({"initial_requirement": RunnablePassthrough()})
    .assign(response=eks_cluster_ec2_prompt | model | StrOutputParser())
    .pick(["response"])
)

kubernetes_manifest_chain = (
    RunnableParallel({"dockerfile_content": RunnablePassthrough()})
    .assign(response=kubernetes_manifest_prompt | model | StrOutputParser())
    .pick(["response"])
)

terraform_generation_fargate_chain = (
    RunnableParallel({"kubernetes_manifests": kubernetes_manifest_chain, "eks_cluster_details": RunnablePassthrough()})
    .assign(response=terraform_generation_fargate_prompt | model | StrOutputParser())
    .pick(["response"])
)

terraform_generation_ec2_chain = (
    RunnableParallel({"kubernetes_manifests": kubernetes_manifest_chain, "eks_cluster_details": RunnablePassthrough()})
    .assign(response=terraform_generation_ec2_prompt | model | StrOutputParser())
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

@tool("ReadFiles", args_schema=ExecuteTerraformInput, return_direct=False)
def read_files(file_path):
    """Read Terraform configuration file content."""
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
    """Execute Terraform init and plan commands."""
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
        
        result = subprocess.run(
            ['terraform', 'plan'],
            cwd=working_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"Error executing Terraform: {e.stderr}"

def generate_eks_terraform_code(initial_requirement, dockerfile_path):
    start_time = time.time()
    st.info("Classifying EKS deployment type...")
    classification_result = supervisor_chain.invoke({"input": initial_requirement})["response"]
    st.info(f"Classification result: {classification_result}")

    classification_result_line = classification_result.split('\n')[0]

    if "fargate" in classification_result_line.lower():
        st.info("Generating EKS Fargate configuration...")
        eks_cluster_details = eks_cluster_fargate_chain.invoke({"initial_requirement": initial_requirement})["response"]
        
        st.info("Reading Dockerfile content...")
        dockerfile_content = read_dockerfile(dockerfile_path)
        
        st.info("Generating Kubernetes manifests...")
        kubernetes_manifests = kubernetes_manifest_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
        
        st.info("Generating EKS Fargate Terraform configuration...")
        terraform_response = terraform_generation_fargate_chain.invoke({
            "eks_cluster_details": eks_cluster_details,
            "kubernetes_manifests": kubernetes_manifests,
        })["response"]
        
    elif "ec2-nodegroup" in classification_result_line.lower():
        st.info("Generating EKS EC2 node group configuration...")
        eks_cluster_details = eks_cluster_ec2_chain.invoke({"initial_requirement": initial_requirement})["response"]
        
        st.info("Reading Dockerfile content...")
        dockerfile_content = read_dockerfile(dockerfile_path)
        
        st.info("Generating Kubernetes manifests...")
        kubernetes_manifests = kubernetes_manifest_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
        
        st.info("Generating EKS EC2 Terraform configuration...")
        terraform_response = terraform_generation_ec2_chain.invoke({
            "eks_cluster_details": eks_cluster_details,
            "kubernetes_manifests": kubernetes_manifests,
        })["response"]
    else:
        st.error("Unable to classify EKS deployment type. Please provide more details.")
        return "Unable to classify EKS deployment type."

    terraform_code = extract_terraform_code_from_output(terraform_response)
    
    end_time = time.time()
    st.info(f"Time taken for generating EKS Terraform code: {end_time - start_time:.2f} seconds")

    return terraform_code

def extract_terraform_code_from_output(output):
    patterns = [
        r'```hcl\s*(.*?)\s*```',
        r'```terraform\s*(.*?)\s*```',
        r'```tf\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```'
    ]
    
    for pattern in patterns:
        terraform_code_blocks = re.findall(pattern, output, re.DOTALL)
        if terraform_code_blocks:
            return "\n\n".join(terraform_code_blocks).strip()
    
    # If no code blocks found, try to detect if it's raw Terraform code
    if 'resource "' in output or 'data "' in output or 'provider "' in output:
        logging.warning("No code block markers found, but detected Terraform syntax - using raw output")
        return output.strip()
    
    logging.warning("No code block markers found, checking for generated file")
    
    # Fallback: try to read the generated file
    try:
        with open("iac/eks_main.tf", "r") as f:
            file_content = f.read()
            if file_content.strip():
                logging.info("Using generated file content as fallback")
                return file_content.strip()
    except FileNotFoundError:
        logging.warning("Generated file not found")
    
    logging.warning("Returning raw output as last resort")
    return output.strip()

def get_fixed_eks_terraform_code(user_input, dockerfile_path):
    terraform_code = generate_eks_terraform_code(user_input, dockerfile_path)
    initial_terraform_file_path = "iac/eks_main.tf"

    os.makedirs(os.path.dirname(initial_terraform_file_path), exist_ok=True)

    with open(initial_terraform_file_path, 'w', encoding="utf-8") as file:
        file.write(terraform_code)

    fixed_output = regenerate_terraform_code_if_error(initial_terraform_file_path)
    return fixed_output

def regenerate_terraform_code_if_error(initial_terraform_file_path):
    PROMPT = """
        You are a Terraform expert specializing in EKS.
        1. Use the ReadFiles tool to access the Terraform code from {file_path}.
        2. Use the ExecuteTerraform tool to obtain the Terraform plan output.

        Analyze the Terraform plan output:
        - If there are no errors, provide the final output in code format, enclosed in triple backticks with the 'hcl' marker.
        - If errors are found, fix the issues in the Terraform code.

        Ensure the corrected Terraform code includes all necessary EKS resources, comments, and changes. 
        The output must be in code format, enclosed in triple backticks with the 'hcl' marker.
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
