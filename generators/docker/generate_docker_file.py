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
    Can you please update the content with appropriate fix and provide me correct dockerfile without any explanation. For example, the output should be straight forward as follows
    "FROM python:latest\n\n# Creating Application Source Code Directory\nRUN mkdir -p /usr/src/app"
"""

get_info_for_docker_file_prompt = """
    You are a developer AI assistant who has knowledge in all programming languages. Can you help in identifying the contents required for a docker file with the following information. Always use latest images for base image like `FROM python:latest`
    project_type: {project_type}
    project_dependency_object_content: {dependency_object_content}
    project_files: {files}
    
    output should be simple and crystal clear without any explanation about it like 

        "base_image": "python:latest",
        "run_instructions": "yum update -y",
        "copy_instructions": "COPY . /app/",
        "install_instructions": "RUN pip install -r requirements.txt",
        "expose_port": "EXPOSE 8080",
        "run_as_user": "USER app",
        "entry_point": "ENTRYPOINT [\"python\"]"
"""

docker_file_generation_prompt_template = """
        You are a Dockerfile generation AI assistant. Your task is to generate a Dockerfile by following the best practices based on the provided details and instructions.
        Project Type: {project_type}
        Dockerfile content information: {docker_file_content_info}
        
        1. Always prefer to use base image of the dockerfile based on project type specified
        2. After base image information, Add instructions with RUN to update and upgrade image to fix any security patches or bugs. Like yum update -y or apt update -y, etc..
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
        logger.info(response["str"])
        st.info("Updated Dockerfile content after fixing build issue:")
        st.code(response["str"])
        create_dockerfile(dockerfile_path, response["str"])
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
        dockerfile_prompt_info_prompt = PromptTemplate(template=get_info_for_docker_file_prompt, input_variables=["project_type", "dependency_object_content", "files"])
        llm_chain = dockerfile_prompt_info_prompt | model | {"str": StrOutputParser()}
        
        logger.info("Dependency object content:")
        logger.debug(dependency_object_content)
        
        docker_file_content_info = llm_chain.invoke({"project_type": project_type, "dependency_object_content": dependency_object_content, "files": project_files_list})
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
