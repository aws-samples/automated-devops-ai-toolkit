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

    The task definition JSON should include:
    - Family name
    - Container definitions with name, image, CPU, memory, port mappings, environment variables, command, working directory, and log configuration.

    Make sure to correctly pick up the image, port number, and other details from the Dockerfile to create an accurate task definition file.
'''

cloudformation_generation_fargate_template = '''
    Based on all the details provided:
    ECS cluster details: {ecs_cluster_details}
    Task Definition JSON: {task_definition_json}

    Generate a CloudFormation template for the ECS Fargate and its dependent resources. Ensure the template follows best practices and includes necessary comments for clarity.

    Note:
    1. Do not use any hardcoded resource IDs in the code.
    2. Avoid using data sources unless you need to fetch region, availability zones, and current user details.
    3. Always generate end-to-end code using CloudFormation.
    4. Use task definition content to create ECS task definition resource.
    5. Avoid cyclic dependencies in the code. Specifically, ensure that:
       a. Security groups for the ALB and ECS tasks are defined separately and do not reference each other.
       b. Use the `DependsOn` attribute appropriately to handle dependencies between resources without creating cycles.
       c. Avoid Conditions if not required.
    6. Include all necessary networking components such as custom VPC, subnets, IGW, and security groups.
    7. Ensure to create IAM roles required for the ECS tasks and task execution, including policies for necessary permissions.
    8. Create an Application Load Balancer (ALB) to distribute traffic to the ECS tasks. Configure necessary listeners, target groups, and security groups for the ALB.
    9. User should be able to run the code without being prompted for any additional inputs.
    10. Do not refer to undeclared variables or resources in the code.
    11. Create a standard end-to-end template for one environment and not for multiple environments like staging, dev, pre-prod, etc.
    12. Use security best practices to build policies, roles using least privilege.

    The output should be in YAML format and enclosed in triple backticks with the 'yaml' marker.
'''

# Create ChatPromptTemplate objects from templates
supervisor_prompt = ChatPromptTemplate.from_template(supervisor_template)
ecs_cluster_fargate_prompt = ChatPromptTemplate.from_template(ecs_cluster_fargate_template)
task_definition_prompt = ChatPromptTemplate.from_template(task_definition_template)
cloudformation_generation_fargate_prompt = ChatPromptTemplate.from_template(cloudformation_generation_fargate_template)

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

def read_dockerfile(file_path):
    try:
        with open(file_path, 'r', encoding="utf-8") as file:
            return file.read()
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
            task_definition_json = task_definition_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
            st.info(f"Task definition JSON generated")

            st.info("Generating CloudFormation template...")
            cloudformation_response = cloudformation_generation_fargate_chain.invoke({
                "ecs_cluster_details": ecs_cluster_details,
                "task_definition_json": task_definition_json
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
