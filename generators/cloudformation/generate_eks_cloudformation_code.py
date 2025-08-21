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
    You are an AWS EKS expert. Classify the input requirement and output the setup pattern (either "fargate" or "ec2-nodegroup") without any additional text or explanations.
    Input: {input}
    Output: 
'''

eks_cluster_fargate_template = '''
    You are a CloudFormation expert who generates AWS EKS Fargate configuration.
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
    You are a CloudFormation expert who generates AWS EKS EC2 node group configuration.
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

    CRITICAL REQUIREMENTS - MUST EXTRACT FROM DOCKERFILE:
    1. MANDATORY: Extract base image from FROM instruction (e.g., FROM node:16 → use image: node:16)
    2. MANDATORY: Extract port from EXPOSE instruction (e.g., EXPOSE 3000 → use containerPort: 3000)
    3. MANDATORY: Extract app name from image or working directory
    4. MANDATORY: Extract environment variables from ENV instructions
    
    FORBIDDEN - DO NOT USE THESE DEFAULT VALUES:
    - nginx (extract actual image from Dockerfile)
    - my-app:latest (extract actual image from Dockerfile)
    - port 80/8080 (extract actual EXPOSE port from Dockerfile)
    - generic names like "app" (extract meaningful name from Dockerfile)

    EXTRACTION EXAMPLES (follow this pattern exactly):
    - Dockerfile: FROM python:3.9 → Kubernetes: image: python:3.9
    - Dockerfile: EXPOSE 5000 → Kubernetes: containerPort: 5000
    - Dockerfile: FROM node:16-alpine → Kubernetes: image: node:16-alpine
    - Dockerfile: EXPOSE 3000 → Kubernetes: containerPort: 3000

    Generate Kubernetes resources with EXTRACTED values only:
    - Deployment with container specifications (MUST use extracted image and ports)
    - Service to expose the application (MUST use extracted ports)
    - ConfigMap if needed (MUST use extracted ENV variables)
    - Ingress for external access (MUST use extracted service port)

    VALIDATION: Before generating, verify you have extracted:
    ✓ Actual image name from FROM instruction
    ✓ Actual port number from EXPOSE instruction
    ✓ Actual environment variables from ENV instructions
'''

cloudformation_generation_fargate_template = '''
    Based on all the details provided:
    EKS cluster details: {eks_cluster_details}
    Kubernetes Manifests: {kubernetes_manifests}

    Generate a CloudFormation template for EKS Fargate using NATIVE AWS CloudFormation resource types.

    CRITICAL REQUIREMENTS - MUST FOLLOW EXACTLY:
    1. This is for EKS (Kubernetes), NOT ECS
    2. Use ONLY native AWS CloudFormation resource types (AWS::EKS::Cluster, AWS::EKS::FargateProfile)
    3. DO NOT use custom resource types like AWSQS::EKS::Cluster or Custom::FargateProfile
    4. DO NOT use AWS::ECS::Service, AWS::ECS::TaskDefinition, or any ECS resources
    5. DO NOT create Parameters section with defaults
    6. Use extracted values from Kubernetes manifests directly
    7. EXAMPLES of extraction (use actual values from YOUR manifests):
       - If YOUR manifest has image: node:16 → use node:16 directly
       - If YOUR manifest has containerPort: 3000 → use 3000 directly
       - If YOUR manifest has name: web-app → use web-app directly

    MANDATORY RESOURCES (required for working EKS Fargate):
    - AWS::EC2::VPC with public subnets and internet gateway
    - AWS::EKS::Cluster (native CloudFormation type)
    - AWS::EKS::FargateProfile (native CloudFormation type)
    - AWS::IAM::Role for cluster service role
    - AWS::IAM::Role for Fargate pod execution role
    - AWS::EC2::SecurityGroup for EKS cluster
    - AWS::Logs::LogGroup for cluster logging
    
    OPTIONAL RESOURCES (create only if user specifically requests load balancing):
    - AWS::ElasticLoadBalancingV2::LoadBalancer (only if user mentions ALB/load balancer/ingress)
    - AWS::ElasticLoadBalancingV2::TargetGroup (only if ALB is requested)
    - AWS::ElasticLoadBalancingV2::Listener (only if ALB is requested)

    FORBIDDEN - DO NOT INCLUDE:
    - Custom resource types (AWSQS::*, Custom::*)
    - Default values like nginx, app, or port 80

    REQUIRED NATIVE EKS RESOURCES:
    - AWS::EKS::Cluster (NOT AWSQS::EKS::Cluster)
    - AWS::EKS::FargateProfile (NOT Custom::FargateProfile)
    - AWS::IAM::Role (for cluster and Fargate execution)
    - AWS::EC2::VPC, AWS::EC2::Subnet, AWS::EC2::InternetGateway
    - AWS::EC2::SecurityGroup
    - AWS::Logs::LogGroup

    Extract container values from Kubernetes manifests and use directly in template.
    The output should be in YAML format and enclosed in triple backticks with the 'yaml' marker.
'''

cloudformation_generation_ec2_template = '''
    Based on all the details provided:
    EKS cluster details: {eks_cluster_details}
    Kubernetes Manifests: {kubernetes_manifests}

    Generate a CloudFormation template for EKS with EC2 node groups using NATIVE AWS CloudFormation resource types.

    CRITICAL REQUIREMENTS - MUST FOLLOW EXACTLY:
    1. This is for EKS (Kubernetes), NOT ECS
    2. Use ONLY native AWS CloudFormation resource types (AWS::EKS::Cluster, AWS::EKS::Nodegroup)
    3. DO NOT use custom resource types like AWSQS::EKS::Cluster or Custom::NodeGroup
    4. DO NOT use AWS::ECS::Service, AWS::ECS::TaskDefinition, or any ECS resources
    5. DO NOT create Parameters section with defaults
    6. Use extracted values from Kubernetes manifests directly
    7. EXAMPLES of extraction (use actual values from YOUR manifests):
       - If YOUR manifest has image: node:16 → use node:16 directly
       - If YOUR manifest has containerPort: 3000 → use 3000 directly
       - If YOUR manifest has name: web-app → use web-app directly

    MANDATORY RESOURCES (required for working EKS with EC2):
    - AWS::EC2::VPC with public/private subnets, IGW, and NAT Gateway
    - AWS::EKS::Cluster (native CloudFormation type)
    - AWS::EKS::Nodegroup (native CloudFormation type)
    - AWS::IAM::Role for cluster service role
    - AWS::IAM::Role for node group instance role
    - AWS::EC2::SecurityGroup for EKS cluster
    - AWS::Logs::LogGroup for cluster logging
    
    OPTIONAL RESOURCES (create only if user specifically requests load balancing):
    - AWS::ElasticLoadBalancingV2::LoadBalancer (only if user mentions ALB/load balancer/ingress)
    - AWS::ElasticLoadBalancingV2::TargetGroup (only if ALB is requested)
    - AWS::ElasticLoadBalancingV2::Listener (only if ALB is requested)

    FORBIDDEN - DO NOT INCLUDE:
    - Custom resource types (AWSQS::*, Custom::*)
    - Default values like nginx, app, or port 80

    REQUIRED NATIVE EKS RESOURCES:
    - AWS::EKS::Cluster (NOT AWSQS::EKS::Cluster)
    - AWS::EKS::Nodegroup (NOT Custom::NodeGroup)
    - AWS::IAM::Role (for cluster and node group)
    - AWS::EC2::VPC, AWS::EC2::Subnet, AWS::EC2::InternetGateway, AWS::EC2::NatGateway
    - AWS::EC2::SecurityGroup
    - AWS::Logs::LogGroup

    Extract container values from Kubernetes manifests and use directly in template.
    The output should be in YAML format and enclosed in triple backticks with the 'yaml' marker.
'''

# Create ChatPromptTemplate objects
supervisor_prompt = ChatPromptTemplate.from_template(supervisor_template)
eks_cluster_fargate_prompt = ChatPromptTemplate.from_template(eks_cluster_fargate_template)
eks_cluster_ec2_prompt = ChatPromptTemplate.from_template(eks_cluster_ec2_template)
kubernetes_manifest_prompt = ChatPromptTemplate.from_template(kubernetes_manifest_template)
cloudformation_generation_fargate_prompt = ChatPromptTemplate.from_template(cloudformation_generation_fargate_template)
cloudformation_generation_ec2_prompt = ChatPromptTemplate.from_template(cloudformation_generation_ec2_template)

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

cloudformation_generation_fargate_chain = (
    RunnableParallel({"kubernetes_manifests": kubernetes_manifest_chain, "eks_cluster_details": RunnablePassthrough()})
    .assign(response=cloudformation_generation_fargate_prompt | model | StrOutputParser())
    .pick(["response"])
)

cloudformation_generation_ec2_chain = (
    RunnableParallel({"kubernetes_manifests": kubernetes_manifest_chain, "eks_cluster_details": RunnablePassthrough()})
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

def extract_yaml_from_response(response):
    """Extract YAML content from AI response"""
    import re
    
    # Try to find YAML in code blocks
    yaml_match = re.search(r'```yaml\s*(.*?)\s*```', response, re.DOTALL)
    if yaml_match:
        return yaml_match.group(1).strip()
    
    # Try to find YAML without code blocks
    yaml_match = re.search(r'apiVersion:.*', response, re.DOTALL)
    if yaml_match:
        return yaml_match.group(0).strip()
    
    # If no YAML found, return the response as is
    return response.strip()

def extract_kubernetes_values(kubernetes_manifests, dockerfile_content=None):
    """Extract key values from Kubernetes manifests with Dockerfile fallback"""
    try:
        if isinstance(kubernetes_manifests, str):
            import re
            
            # Extract image
            image_match = re.search(r'image:\s*([^\s\n]+)', kubernetes_manifests)
            image = image_match.group(1) if image_match else None
            
            # Extract port
            port_match = re.search(r'containerPort:\s*(\d+)', kubernetes_manifests)
            port = int(port_match.group(1)) if port_match else None
            
            # Extract name
            name_match = re.search(r'name:\s*([^\s\n]+)', kubernetes_manifests)
            name = name_match.group(1) if name_match else None
            
            # If extraction failed, parse Dockerfile directly
            if not image or not port:
                dockerfile_values = extract_from_dockerfile(dockerfile_content)
                image = image or dockerfile_values.get('image', 'my-app:latest')
                port = port or dockerfile_values.get('port', 8080)
                name = name or dockerfile_values.get('name', 'app')
            
            return {
                'image': image,
                'port': port,
                'name': name
            }
    except Exception as e:
        logger.warning(f"Failed to extract from Kubernetes manifests: {e}")
    
    # Final fallback: parse Dockerfile directly
    if dockerfile_content:
        return extract_from_dockerfile(dockerfile_content)
    
    return {'image': 'my-app:latest', 'port': 8080, 'name': 'app'}

def extract_from_dockerfile(dockerfile_content):
    """Extract values directly from Dockerfile content"""
    if not dockerfile_content:
        return {'image': 'my-app:latest', 'port': 8080, 'name': 'app'}
    
    import re
    
    # Extract base image from FROM instruction
    from_match = re.search(r'FROM\s+([^\s\n]+)', dockerfile_content, re.IGNORECASE)
    image = from_match.group(1) if from_match else 'my-app:latest'
    
    # Extract port from EXPOSE instruction
    expose_match = re.search(r'EXPOSE\s+(\d+)', dockerfile_content, re.IGNORECASE)
    port = int(expose_match.group(1)) if expose_match else 8080
    
    # Generate app name from image
    name = image.split(':')[0].split('/')[-1] if image != 'my-app:latest' else 'app'
    
    return {
        'image': image,
        'port': port,
        'name': name
    }

def generate_eks_cloudformation_template(initial_requirement, dockerfile_path):
    try:
        start_time = time.time()
        
        if not initial_requirement or not dockerfile_path:
            raise ValueError("Initial requirement and Dockerfile path are required.")
        
        st.info("Classifying EKS deployment type...")
        classification_result = supervisor_chain.invoke({"input": initial_requirement})["response"]
        st.info(f"Classification result: {classification_result}")

        if "fargate" in classification_result.lower():
            st.info("Generating EKS Fargate configuration...")
            eks_cluster_details = eks_cluster_fargate_chain.invoke({"initial_requirement": initial_requirement})["response"]
            
            st.info("Reading Dockerfile content...")
            dockerfile_content = read_dockerfile(dockerfile_path)
            
            st.info("Generating Kubernetes manifests...")
            kubernetes_manifests_response = kubernetes_manifest_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
            
            # Extract values from Kubernetes manifests for CloudFormation
            kubernetes_values = extract_kubernetes_values(kubernetes_manifests_response, dockerfile_content)
            st.info(f"Extracted values: {kubernetes_values}")
            
            # Enhanced manifests with extracted values
            enhanced_manifests = f"Kubernetes Manifests with extracted values: Image={kubernetes_values['image']}, Port={kubernetes_values['port']}, Name={kubernetes_values['name']}. Original: {kubernetes_manifests_response}"
            
            st.info("Generating EKS Fargate CloudFormation template...")
            cloudformation_response = cloudformation_generation_fargate_chain.invoke({
                "eks_cluster_details": eks_cluster_details,
                "kubernetes_manifests": enhanced_manifests
            })["response"]
            
        elif "ec2-nodegroup" in classification_result.lower():
            st.info("Generating EKS EC2 node group configuration...")
            eks_cluster_details = eks_cluster_ec2_chain.invoke({"initial_requirement": initial_requirement})["response"]
            
            st.info("Reading Dockerfile content...")
            dockerfile_content = read_dockerfile(dockerfile_path)
            
            st.info("Generating Kubernetes manifests...")
            kubernetes_manifests_response = kubernetes_manifest_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
            
            # Extract values from Kubernetes manifests for CloudFormation
            kubernetes_values = extract_kubernetes_values(kubernetes_manifests_response, dockerfile_content)
            st.info(f"Extracted values: {kubernetes_values}")
            
            # Enhanced manifests with extracted values
            enhanced_manifests = f"Kubernetes Manifests with extracted values: Image={kubernetes_values['image']}, Port={kubernetes_values['port']}, Name={kubernetes_values['name']}. Original: {kubernetes_manifests_response}"
            
            st.info("Generating EKS EC2 CloudFormation template...")
            cloudformation_response = cloudformation_generation_ec2_chain.invoke({
                "eks_cluster_details": eks_cluster_details,
                "kubernetes_manifests": enhanced_manifests
            })["response"]
        else:
            st.error(f"Unsupported EKS deployment type: {classification_result}")
            raise ValueError(f"Unsupported EKS deployment type: {classification_result}")

        cloudformation_template = extract_yaml_from_response(cloudformation_response)
        
        if cloudformation_template:
            st.info("EKS CloudFormation template generated successfully")
        else:
            st.error("Failed to generate EKS CloudFormation template")
            raise ValueError("Failed to generate EKS CloudFormation template")

        end_time = time.time()
        st.info(f"Time taken for generating EKS CloudFormation template: {end_time - start_time} seconds")

        return cloudformation_template
    except Exception as e:
        st.error(f"Error in generate_eks_cloudformation_template: {str(e)}")
        raise

def regenerate_eks_cloudformation_template_if_error(template_body, stack_name):
    PROMPT = """
        You are a CloudFormation expert specializing in EKS. Analyze the following CloudFormation template:

        {template_body}

        If there are any errors or improvements to be made, provide a corrected version of the entire template. 
        If no changes are needed, simply return the original template.

        The output must be in YAML format, enclosed in triple backticks with the 'yaml' marker. 
        Do not include any additional text or explanations outside the code block.
    """
    question_prompt = PromptTemplate.from_template(template=PROMPT)
    query = question_prompt.format(template_body=template_body)
    
    st.info("Analyzing and potentially fixing EKS CloudFormation template...")
    response = model.invoke(query)
    response = extract_content_from_ai_message(response)
    
    fixed_template = extract_yaml_from_response(response)
    
    if fixed_template:
        st.info("EKS CloudFormation template analysis complete")
        return fixed_template
    else:
        st.info("No changes made to the EKS CloudFormation template")
        return template_body

def get_fixed_eks_cloudformation_template(user_input, dockerfile_path):
    try:
        start_time = time.time()
        
        if not user_input or not dockerfile_path:
            raise ValueError("User input and Dockerfile path are required")
        
        # Generate the initial template
        cloudformation_template = generate_eks_cloudformation_template(user_input, dockerfile_path)
        
        if cloudformation_template is None:
            raise ValueError("Failed to generate initial EKS CloudFormation template")

        # Write the initial template to a file
        initial_template_path = "iac/initial_eks_cloudformation_template.yaml"
        write_output_to_file(cloudformation_template, initial_template_path)
        st.info(f"Initial EKS CloudFormation template written to {initial_template_path}")

        # Generate a unique stack name
        stack_name = f"eks-stack-{int(time.time())}"

        # Attempt to fix the template if there are any errors
        fixed_template = regenerate_eks_cloudformation_template_if_error(cloudformation_template, stack_name)
        
        if fixed_template:
            # Write the fixed template to a file
            fixed_template_path = "iac/fixed_eks_cloudformation_template.yaml"
            write_output_to_file(fixed_template, fixed_template_path)
            st.info(f"Fixed EKS CloudFormation template written to {fixed_template_path}")
        else:
            st.warning("Failed to fix EKS CloudFormation template. Using the initial template.")
            fixed_template = cloudformation_template

        end_time = time.time()
        st.info(f"Total time taken: {end_time - start_time} seconds")

        return fixed_template
    except Exception as e:
        st.error(f"Error in get_fixed_eks_cloudformation_template: {str(e)}")
        return None
