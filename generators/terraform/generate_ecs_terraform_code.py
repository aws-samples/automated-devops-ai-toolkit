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
    Generate a task definition JSON based on the Dockerfile content provided.
    Dockerfile content: {dockerfile_content}

    The task definition JSON should include:
    - Family name
    - Container definitions with name, image, CPU, memory, port mappings, environment variables, command, working directory, and log configuration.

    Make sure to correctly pick up the image, port number, and other details from the Dockerfile to create an accurate task definition file.
'''

terraform_generation_fargate_template = '''
    Based on all the details provided:
    ECS cluster details: {ecs_cluster_details}
    Task Definition JSON: {task_definition_json}

    Generate reusable Terraform configurations for the ECS Fargate and its dependent resources. Ensure the configuration follows best practices and includes necessary comments for clarity.

    Note:
    1. Do not use any hardcoded resource IDs in the code.
    2. Avoid using data sources unless you need to fetch region, availability zones, and current user details.
    3. Always generate end-to-end code using Terraform.
    4. Use task definition content to create ECS task definition resource.
    5. Avoid cyclic dependencies in the code. Specifically, ensure that:
       a. Security groups for the ALB and ECS tasks are defined separately and do not reference each other.
       b. Use the `depends_on` attribute appropriately to handle dependencies between resources without creating cycles.
    6. Include all necessary networking components such as custom VPC, subnets, IGW, and security groups.
    7. Ensure to create IAM roles required for the ECS tasks and task execution, including policies for necessary permissions.
    8. Create an Application Load Balancer (ALB) to distribute traffic to the ECS tasks. Configure necessary listeners, target groups, and security groups for the ALB.
    9. User should be able to run the code without being prompted for any additional inputs.
    10. Do not refer to undeclared variables or resources in the code.

    The output should be in code format and enclosed in triple backticks with the 'hcl' marker.
'''

terraform_generation_ec2_autoscaling_template = '''
    Based on all the details provided:
    ECS cluster details: {ecs_cluster_details}
    Task Definition JSON: {task_definition_json}

    Generate reusable Terraform configurations for the ECS EC2 Autoscaling and its dependent resources, including the Auto Scaling Group (ASG). Ensure the configuration follows best practices and includes necessary comments for clarity.

    Note:
    1. Do not use any hardcoded resource IDs in the code.
    2. Avoid using data sources unless you need to fetch region, availability zones, and current user details.
    3. Always generate end-to-end code using Terraform.
    4. Use task definition content to create ECS task definition resource.
    5. Avoid cyclic dependencies in the code. Specifically, ensure that:
       a. Security groups for the ALB and ECS tasks are defined separately and do not reference each other.
       b. Use the `depends_on` attribute appropriately to handle dependencies between resources without creating cycles.
    6. Include all necessary networking components such as custom VPC, subnets, IGW, NATGW, and security groups.
    7. Ensure to create IAM roles required for the ECS tasks and task execution, including policies for necessary permissions.
    8. Create an Application Load Balancer (ALB) to distribute traffic to the ECS tasks. Configure necessary listeners, target groups, and security groups for the ALB.
    9. Include Auto Scaling Group (ASG) configuration for the EC2 instances.
    10. User should be able to run the code without being prompted for any additional inputs.
    11. Do not refer to undeclared variables or resources in the code.

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
    with open(file_path, 'r', encoding="utf-8") as file:
        return file.read()

def extract_json_from_response(response):
    match = re.search(r'```json\s+(.*?)\s+```', response, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        raise ValueError("Failed to extract JSON content: markers not found")

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
        result = subprocess.run(
            ['terraform', 'init'],
            cwd=os.path.dirname(file_path),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logging.info(f"Terraform init output: {result.stdout}")

        result = subprocess.run(
            ['terraform', 'plan'],
            cwd=os.path.dirname(file_path),
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

        st.info("Generating task definition JSON...")
        task_definition_response = task_definition_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
        st.info(f"Task definition response: {task_definition_response}")

        if not task_definition_response:
            raise ValueError("Task definition generation failed. Response is empty.")

        task_definition_json = extract_json_from_response(task_definition_response)

        st.info("Generating Terraform configuration...")
        terraform_response = terraform_generation_fargate_chain.invoke({
            "ecs_cluster_details": ecs_cluster_details,
            "task_definition_json": task_definition_json,
        })["response"]
    elif "ec2-autoscaling" in classification_result_line.lower():
        st.info("Generating ECS EC2 Autoscaling configuration...")
        ecs_cluster_details = ecs_cluster_ec2_autoscaling_chain.invoke({"initial_requirement": initial_requirement})["response"]
        st.info(f"ECS EC2 Autoscaling configuration generated: {ecs_cluster_details}")

        st.info("Reading Dockerfile content...")
        dockerfile_content = read_dockerfile(dockerfile_path)
        st.info(f"Dockerfile content: {dockerfile_content}")

        st.info("Generating task definition JSON...")
        task_definition_response = task_definition_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
        st.info(f"Task definition response: {task_definition_response}")

        if not task_definition_response:
            raise ValueError("Task definition generation failed. Response is empty.")

        task_definition_json = extract_json_from_response(task_definition_response)

        st.info("Generating Terraform configuration...")
        terraform_response = terraform_generation_ec2_autoscaling_chain.invoke({
            "ecs_cluster_details": ecs_cluster_details,
            "task_definition_json": task_definition_json,
        })["response"]
    else:
        st.error("Unable to classify input. Please provide more details.")
        return "Unable to classify input. Please provide more details."

    terraform_code = extract_terraform_code_from_output(terraform_response)
    
    end_time = time.time()
    st.info(f"Time taken for generating Terraform code: {end_time - start_time:.2f} seconds")

    return terraform_code

def extract_terraform_code_from_output(output):
    # Extract the Terraform code block within the triple backticks and `hcl` marker
    terraform_code_blocks = re.findall(r'```hcl\s*(.*?)\s*```', output, re.DOTALL)
    
    if terraform_code_blocks:
        return "\n\n".join(terraform_code_blocks).strip()
    else:
        logging.error("Failed to extract Terraform code: markers not found")
        return None

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
