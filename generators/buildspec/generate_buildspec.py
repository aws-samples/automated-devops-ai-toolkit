import os
import re
import time
import streamlit as st
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core.bedrock_definition import get_model
from langchain.schema import AIMessage

# Initialize the Bedrock model
model = get_model()

# Define the instruction template
instruction_template = '''
1. You are an AWS CodeBuild expert. 
2. Generate a buildspec.yaml file for building, tagging, and pushing a Docker image to Amazon ECR based on the provided Dockerfile content and ECR repository details including clone steps as pre-requisite.

Dockerfile content: {dockerfile_content}
ECR Repository Name: {ecr_repository_name}
ECR Repository URI: {ecr_repository_uri}

3. The buildspec.yaml file must adhere to the Dockerfile content and ECR details. Include all necessary phases and commands, following AWS best practices for security and efficiency.
4. Use only the latest of prescribed image runtime versions {runtime_version} - dotnet, golang, ruby, python, php, nodejs, java
'''

# Define the buildspec template
buildspec_template = '''
version: 0.2

phases:
  install:
    runtime-versions:
      {runtime_version}
    commands:
{install_commands}

  pre_build:
    commands:
      - echo "Logging in to Amazon ECR..."
      - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin {ecr_repository_uri}
      - REPOSITORY_URI={ecr_repository_uri}
      - IMAGE_TAG=$CODEBUILD_RESOLVED_SOURCE_VERSION

  build:
    commands:
{build_commands}
      - echo "Building Docker image..."
      - docker build -t $REPOSITORY_URI:$IMAGE_TAG .

  post_build:
    commands:
      - echo "Pushing the Docker image to ECR..."
      - docker push $REPOSITORY_URI:$IMAGE_TAG

Ensure that the generated buildspec.yaml includes all necessary phases and commands, and follows AWS best practices for security and efficiency.

The output must be in YAML format, enclosed in triple backticks with the 'yaml' marker. 
Do not include any additional text or explanations outside the code block.
'''

# Combine instruction and buildspec templates
combined_template = instruction_template + "\n" + buildspec_template

# Create a ChatPromptTemplate object from the combined template
buildspec_prompt = ChatPromptTemplate.from_template(combined_template)

def extract_yaml_from_response(response):
    match = re.search(r'```yaml\s*([\s\S]*?)\s*```', response, re.DOTALL)
    if match:
        return match.group(1).strip()
    else:
        st.error("Failed to extract YAML content: markers not found")
        raise ValueError("Failed to extract YAML content: markers not found")

def parse_dockerfile_details(dockerfile_content):
    from_line = next((line for line in dockerfile_content.split('\n') if line.startswith('FROM')), None)
    if from_line:
        image_parts = from_line.split(':')
        image_name = image_parts[0].split('/')[-1].lower()
        image_version = image_parts[1] if len(image_parts) > 1 else 'latest'

        if 'java' in image_name or 'openjdk' in image_name or 'jdk' in image_name:
            java_version = re.search(r'\d+', image_version).group()
            runtime_version = f"java: corretto{java_version}"
            install_commands = "      - apt-get update\n      - apt-get install -y maven"
            build_commands = "      - echo \"Building Java project with Maven...\"\n      - mvn package"
        elif image_name.startswith('node'):
            runtime_version = f"nodejs: {image_version}"
            install_commands = "      - apt-get update\n      - apt-get install -y npm"
            build_commands = "      - echo \"Building Node.js project with npm...\"\n      - npm install\n      - npm run build"
        elif image_name.startswith('python'):
            runtime_version = f"python: {image_version}"
            install_commands = "      - apt-get update\n      - apt-get install -y python3-pip"
            build_commands = "      - echo \"Building Python project...\"\n      - pip3 install -r requirements.txt\n      - python3 app.py"
        elif image_name.startswith('golang'):
            runtime_version = f"golang: {image_version}"
            install_commands = "      - apt-get update\n      - apt-get install -y golang"
            build_commands = "      - echo \"Building Go project...\"\n      - go build main.go"
        else:
            runtime_version = ""
            install_commands = "      - echo \"No specific install commands for this image type\""
            build_commands = "      - echo \"No specific build commands for this image type\""

        return runtime_version, install_commands, build_commands
    else:
        return "", "", ""

def extract_content_from_ai_message(message):
    if isinstance(message, AIMessage):
        return message.content
    elif isinstance(message, str):
        return message
    else:
        st.error(f"Unexpected message type: {type(message)}")
        raise ValueError(f"Unexpected message type: {type(message)}")

def generate_buildspec(dockerfile_path, ecr_repository_name, ecr_repository_uri):
    try:
        start_time = time.time()

        # Read the Dockerfile content
        with open(dockerfile_path, 'r', encoding="utf-8") as file:
            dockerfile_content = file.read()
        st.info(f"Dockerfile content read successfully")

        # Parse the Dockerfile content to get the runtime version and commands
        runtime_version, install_commands, build_commands = parse_dockerfile_details(dockerfile_content)

        # Invoke the language model to generate the buildspec.yaml
        response = buildspec_prompt.format_prompt(
            dockerfile_content=dockerfile_content,
            ecr_repository_name=ecr_repository_name,
            ecr_repository_uri=ecr_repository_uri,
            runtime_version=runtime_version,
            install_commands=install_commands,
            build_commands=build_commands
        ).to_string()

        # Invoke the model and extract the content from the AIMessage
        ai_response = model.invoke(response)
        response_content = extract_content_from_ai_message(ai_response)

        # Extract YAML content from the response
        buildspec_yaml = extract_yaml_from_response(response_content)

        if buildspec_yaml:
            st.info("BuildSpec YAML generated successfully")
            
            # Write the buildspec.yaml to a file
            buildspec_path = "iac/buildspec.yaml"
            write_output_to_file(buildspec_yaml, buildspec_path)
            st.info(f"BuildSpec YAML written to {buildspec_path}")
        else:
            st.error("Failed to generate BuildSpec YAML")
            raise ValueError("Failed to generate BuildSpec YAML")

        end_time = time.time()
        st.info(f"Time taken for generating BuildSpec YAML: {end_time - start_time} seconds")

        return buildspec_yaml
    except Exception as e:
        st.error(f"Error in generate_buildspec: {str(e)}")
        return None

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

# Main execution (if needed)
if __name__ == "__main__":
    # Add any main execution code here
    pass