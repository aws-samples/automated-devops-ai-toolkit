from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from core.bedrock_definition import get_model
from core.custom_logging import logger
from pathlib import Path
import os
import streamlit as st
from typing import Tuple

fix_dockerfile_build_issue_prompt = """
    You are an expert in fixing issues in Dockerfile that raise during docker build. I am getting the following error {docker_build_error} when building docker image with the following Dockerfile content 
    {dockerfile_content}
    
    CRITICAL RULES:
    1. Return ONLY valid Dockerfile instructions
    2. Do NOT include any markdown formatting (```, ```dockerfile)
    3. Do NOT include any explanatory text or comments about the fix
    4. Do NOT include >>> or any other formatting artifacts
    5. Do NOT include quotes around the entire response
    6. Start directly with FROM instruction
    7. Each line must be a valid Dockerfile instruction
    
    COMMON FIXES FOR PACKAGE MANAGER ERRORS:
    - If error contains "apt-get" and base image is Alpine: Replace with "apk update && apk add"
    - If error contains "yum" and base image is Debian/Ubuntu: Replace with "apt-get update && apt-get install -y"
    - If error contains "apk" and base image is not Alpine: Replace with appropriate package manager
    - For Java projects: Ensure Maven is installed with correct package manager for the base image
    
    PACKAGE MANAGER BY BASE IMAGE:
    - openjdk:*-slim, debian, ubuntu → apt-get update && apt-get install -y
    - openjdk:*-alpine, alpine → apk update && apk add
    - amazonlinux, centos, rhel → yum update -y && yum install -y
    
    LANGUAGE-SPECIFIC ARTIFACT FIXES:
    - JAVA: If JAR not found, extract from pom.xml/build.gradle:
      * Maven: artifactId-version.jar (e.g., sample-0.0.1-SNAPSHOT.jar)
      * Gradle: Extract from build.gradle archiveBaseName and version
    - GO: If binary not found, use module name from go.mod:
      * Extract module name: "module github.com/user/myapp" → binary: myapp
      * Use: RUN go build -o /app/myapp ./cmd/main.go
    - NODE.JS: Extract app name from package.json:
      * Use "name" field from package.json for app identification
      * Entry point from "main" or "scripts.start"
    - PYTHON: Extract app name from setup.py or pyproject.toml if exists:
      * Use requirements.txt for dependencies
      * Entry point typically app.py or main.py
    - RUST: Extract from Cargo.toml:
      * Use [package] name field for binary name
      * Binary location: target/release/binary-name
    
    Fix the error and return only the corrected Dockerfile content.
"""

get_info_for_docker_file_prompt = """
    You are a developer AI assistant who has knowledge in all programming languages. Extract build information from dependency files.
    project_type: {project_type}
    project_dependency_object_content: {dependency_object_content}
    project_files: {project_files_list}
    
    LANGUAGE-SPECIFIC EXTRACTION RULES:
    
    JAVA (pom.xml/build.gradle):
    - Extract artifactId and version from pom.xml: artifactId-version.jar
    - For Gradle: extract archiveBaseName and version from build.gradle
    
    GO (go.mod):
    - Extract module name: "module github.com/user/myapp" → binary: "myapp"
    - Main file typically in cmd/ or root directory
    
    NODE.JS (package.json):
    - Extract "name" field for app name
    - Extract "main" field for entry point (default: index.js)
    - Extract "scripts.start" for run command
    
    PYTHON (requirements.txt/setup.py):
    - App name from setup.py name field or directory name
    - Entry point typically app.py, main.py, or from setup.py
    
    RUST (Cargo.toml):
    - Extract [package] name for binary name
    - Binary path: target/release/name
    
    Output format (simple key-value pairs):
    base_image: language:latest
    app_name: extracted-app-name
    binary_name: extracted-binary-name
    entry_point: extracted-entry-point
    expose_port: EXPOSE 8080
    build_artifact: path/to/artifact
"""

docker_file_generation_prompt_template = """
        You are a Dockerfile generation AI assistant. Your task is to generate a Dockerfile by following the best practices based on the provided details and instructions.
        Project Type: {project_type}
        Dockerfile content information: {docker_file_content_info}
        
        1. Always prefer to use base image of the dockerfile based on project type specified
        2. CRITICAL: Match package manager to base image OS:
           - For Debian/Ubuntu-based images (debian, ubuntu, python, node, openjdk with -slim): use "apt-get update && apt-get install -y"
           - For RHEL/CentOS-based images (centos, rhel, amazonlinux): use "yum update -y && yum install -y"
           - For Alpine-based images (alpine, node:alpine, openjdk:alpine): use "apk update && apk add"
        3. Don't use wrapper binaries for project that need compilation like use mvn instead of mvnw. Also make sure you use only official binaries instead of binaries that are listed from third party services.
        4. Try to identify the list of all the dependencies required for the project along with their versions from the Dependency Object Content details provided in the prompt.
        5. Try to add instructions to clean any files that are not required for running the application. For example for building a go binary all go modules are needed. But after the binary was built, there is no need to keep the dependency files. But on the other hand, if it is a python project all the dependencies should be present as it uses those files during runtime.
        6. Make sure to add instructions to copy all the required files from the dependency object content to the docker container. Like COPY . /app/ or COPY src/ /app/ or ADD . /app or ADD src /app. These instructions should be present before the compilation of the source code instructions provided like RUN mvn clean package or RUN go build
        7. Make sure to add instructions to install all the required dependencies for the application. Like RUN mvn clean package or go build. Always make sure this should be present after the COPY or ADD instruction of the source code. Don't use wrapper binaries like .mvnw
        7. Make sure to add instructions to expose the port required for the application to run. Like EXPOSE 8080 or EXPOSE 5000 and please add it to top of the instructions after FROM and before COPY
        8. Make sure to add instructions to specify the entry point for the application. Like ENTRYPOINT ["python"] or ENTRYPOINT ["./app"]
        10. Make sure to add instructions to define the working directory for the application. Like WORKDIR /app
        11. Make sure to add instructions to define the environment variables for the application. Like ENV PORT=8080 or ENV DB_HOST=localhost
        12. In the end create a user, assign appropriate permissions to that user on all the application files after installing the required dependencies and generating the binary. For example RUN useradd appuser && chown -R appuser:appuser /app
        13. Add instruction to run the docker image under that specific user. Like USER appuser
        14. Make sure we have appropriate entrypoint or CMD at the end of all instructions in the dockerfile
        15. Also consider underlying OS platform information while building dockerfile
        16. Make sure to use the latest version of the base latest debian image
        17. Don't use dependency:go-offline mode in dockerfile and take dependencies from the dependency object content provided in the prompt
        18. In CMD or entry point specify the entry point paths correct instead of using wildcards by evaluating the dependency objects configuration.
        19. For Java projects, always use JDK base images (like openjdk:11-jdk-slim) not JRE images, as compilation requires JDK
        20. For Java projects, use multi-stage builds: build stage with JDK for compilation, runtime stage with JRE for execution
        21. CRITICAL LANGUAGE-SPECIFIC ARTIFACT HANDLING:
            
            JAVA:
            - Maven: Extract artifactId and version from pom.xml → artifactId-version.jar
            - Gradle: Extract from build.gradle → archiveBaseName-version.jar
            - Use exact JAR name in COPY target/actual-jar-name.jar
            
            GO:
            - Extract module name from go.mod: "module github.com/user/myapp" → binary: myapp
            - Use: RUN go build -o /app/binary-name ./cmd/main.go or RUN go build -o /app/binary-name
            - Entry point: ENTRYPOINT ["/app/binary-name"]
            
            NODE.JS:
            - Extract app name from package.json "name" field
            - Entry point from "main" field or "scripts.start"
            - Use: ENTRYPOINT ["node", "main-file"]
            
            PYTHON:
            - Entry point typically app.py, main.py, or from setup.py
            - Use: ENTRYPOINT ["python", "entry-file"]
            
            RUST:
            - Extract binary name from Cargo.toml [package] name
            - Binary path: target/release/name
            - Use: COPY target/release/binary-name /app/
            
        22. DO NOT use hardcoded names - extract actual names from dependency files
        
        EXAMPLES OF CORRECT PACKAGE MANAGER USAGE:
        - FROM openjdk:11-jdk-slim → RUN apt-get update && apt-get install -y maven
        - FROM openjdk:11-jdk-alpine → RUN apk update && apk add maven
        - FROM amazonlinux:2 → RUN yum update -y && yum install -y maven
        
        Also make sure that output should be simple and crystal without any detailed explanation about the instructions in the response. 
         
        "FROM python:latest\n\n# Creating Application Source Code Directory\nRUN mkdir -p /usr/src/app"
"""

def create_dockerfile(file_path: str, file_content: str) -> Tuple[bool, str]:
    """
    Creates a new file with the provided content at the specified file path.

    Args:
        file_path (str): The full path (including the file name) where the file should be created.
        file_content (str): The content to be written to the file.

    Returns:
        Tuple[bool, str]: A tuple containing:
            - bool: True if the file was created successfully, False otherwise.
            - str: A message indicating the result of the file creation operation.
    """
    try:
        parent_folder = os.path.dirname(file_path)
        Path(parent_folder).mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding="utf-8") as file:
            file.write(file_content)
        return True, f"File '{file_path}' created successfully."
    except (IOError, OSError) as e:
        return False, f"Error creating file '{file_path}': {str(e)}"

def fix_docker_build_issue(docker_build_error: str, dockerfile_content: str, dockerfile_path: str) -> bool:
    """
    Fixes issues in Dockerfile that raise during docker build.

    Args:
        docker_build_error (str): The error message raised during Docker build.
        dockerfile_content (str): The content of the Dockerfile.

    Returns:
        bool: True if the Dockerfile was fixed and saved successfully, False otherwise.
    """
    try:
        prompt = PromptTemplate(template=fix_dockerfile_build_issue_prompt, input_variables=["docker_build_error", "dockerfile_content"])
        llm_chain = prompt | get_model() | {"str": StrOutputParser()}
        response = llm_chain.invoke({"docker_build_error": docker_build_error, "dockerfile_content": dockerfile_content})
        
        # Aggressive cleaning of the response
        cleaned_content = response["str"]
        
        # Remove markdown code blocks
        if "```dockerfile" in cleaned_content:
            cleaned_content = cleaned_content.split("```dockerfile")[1].split("```")[0].strip()
        elif "```" in cleaned_content:
            cleaned_content = cleaned_content.split("```")[1].split("```")[0].strip()
        
        # Remove quotes if the entire content is wrapped in quotes
        if cleaned_content.startswith('"') and cleaned_content.endswith('"'):
            cleaned_content = cleaned_content[1:-1]
        
        # Process line by line to remove artifacts
        lines = cleaned_content.split('\n')
        dockerfile_lines = []
        found_from = False
        
        for line in lines:
            # Remove all formatting artifacts
            clean_line = line.replace('>>>', '').replace('<<<', '').strip()
            
            # Skip empty lines and explanatory text
            if not clean_line or clean_line.lower().startswith('here is') or clean_line.lower().startswith('the fixed'):
                continue
                
            if clean_line.startswith('FROM') or found_from:
                found_from = True
                dockerfile_lines.append(clean_line)
        
        cleaned_content = '\n'.join(dockerfile_lines)
        
        logger.info(cleaned_content)
        st.info("Updated Dockerfile content after fixing build issue:")
        st.code(cleaned_content)
        create_dockerfile(dockerfile_path, cleaned_content)
        return True
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        st.error(f"An error occurred while fixing Dockerfile: {e}")
        return False

def generate_docker_file(project_type: str, project_dependency_object: str, project_files_list: str) -> str:
    """
    Generates a Dockerfile based on the provided project type and dependency object.

    Args:
        project_type (str): The type of the project, e.g., "python", "node", "java", etc.
        project_dependency_object (str): Path to the dependency object file, like pom.xml, requirements.txt, etc.
        project_files_list (str): List of project files.

    Returns:
        str: Path to the generated Dockerfile.
    """
    try:
        dependency_object_content = ""
        docker_folder_path_split = "/".join(project_dependency_object.split("/")[:-1])
        dockerfile_path = f"{docker_folder_path_split}/Dockerfile"
        
        if project_dependency_object:
            with open(project_dependency_object, 'r', encoding="utf-8") as file:
                dependency_object_content = file.read()
        else:
            raise ValueError("No appropriate dependency listing object present. Please create an appropriate dependency object like pom.xml, requirements.txt, etc.")
        
        model = get_model()
        dockerfile_prompt_info_prompt = PromptTemplate(template=get_info_for_docker_file_prompt, input_variables=["project_type", "dependency_object_content", "project_files_list"])
        llm_chain = dockerfile_prompt_info_prompt | model | {"str": StrOutputParser()}
        
        logger.info("Dependency object content:")
        logger.debug(dependency_object_content)
        
        docker_file_content_info = llm_chain.invoke({"project_type": project_type, "dependency_object_content": dependency_object_content, "project_files_list": project_files_list})
        logger.info("==============================")
        logger.info(docker_file_content_info)
        logger.info("==============================")
        
        st.info("Dockerfile content information generated by LLM:")
        st.code(docker_file_content_info["str"])
        
        prompt = PromptTemplate(template=docker_file_generation_prompt_template, input_variables=["project_type", "docker_file_content_info"])
        llm_chain = prompt | model | {"str": StrOutputParser()}
        
        response = llm_chain.invoke({"project_type": project_type, "docker_file_content_info": docker_file_content_info["str"]})
        
        logger.info(response["str"])
        st.info("Generated Dockerfile content:")
        st.code(response["str"])
        
        create_dockerfile(dockerfile_path, response["str"])
        logger.info("Generating Dockerfile")
        logger.info("Calling Dockerfile generate")
        return dockerfile_path
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        st.error(f"An error occurred while generating Dockerfile: {e}")
        return ""
