import os
import git
from typing import List, Optional
from langchain.prompts import PromptTemplate, ChatPromptTemplate
from core.bedrock_definition import get_model
from langchain_core.output_parsers import JsonOutputParser
from core.custom_logging import logger

def clone_repo(git_url: str, directory: str, token: Optional[str] = None) -> str:
    """
    Clones a Git repository to the specified directory.

    Args:
        git_url (str): The Git URL of the repository.
        directory (str): The directory where the repository should be cloned.
        token (Optional[str]): The Git token for private repositories.

    Returns:
        str: The path to the cloned repository.
    """
    if token:
        if "https://" in git_url:
            git_url = git_url.replace("https://", f"https://{token}@")
        elif "git@" in git_url:
            git_url = git_url.replace("git@", f"git@{token}:")
        else:
            raise ValueError(f"Unsupported Git URL format: {git_url}")
    
    repo_path = os.path.join(directory, os.path.basename(git_url).replace('.git', ''))
    
    try:
        if os.path.exists(repo_path):
            logger.info(f"Repository already exists at '{repo_path}'. Pulling latest changes.")
            repo = git.Repo(repo_path)
            repo.git.pull()
        else:
            logger.info(f"Cloning repository '{git_url}' to '{repo_path}'")
            git.Repo.clone_from(git_url, repo_path)
    except Exception as e:
        logger.info(f"Failed to clone repository: {e}")
        raise Exception(f"Repository cloning failed: {e}") from e
    
    return repo_path

def list_files(directory: str) -> List[str]:
    """
    Lists all files in the given directory.

    Args:
        directory (str): The absolute path to the directory.

    Returns:
        List[str]: A list of file names in the directory.

    Raises:
        FileNotFoundError: If the specified directory does not exist.
        NotADirectoryError: If the specified path is not a directory.
        PermissionError: If the user does not have permission to access the directory.
    """
    file_list = []

    try:
        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)
                if os.path.isfile(file_path):
                    file_list.append(file_path)
    except FileNotFoundError:
        logger.info(f"The directory '{directory}' does not exist.")
    except NotADirectoryError:
        logger.info(f"The path '{directory}' is not a directory.")
    except PermissionError:
        logger.info(f"You do not have permission to access '{directory}'.")
    except Exception as e:
        logger.info(f"An unexpected error occurred: {e}")

    return file_list

def identify_project_details(git_url: str, directory: str, token: Optional[str] = None) -> Optional[str]:
    """
    Identifies the project name based on the files in the given Git repository.

    Args:
        git_url (str): The Git URL of the repository.
        directory (str): The directory where the repository should be cloned.
        token (Optional[str]): The Git token for private repositories.

    Returns:
        Optional[str]: The identified project name, or None if the project name cannot be determined.
    """
    try:
        project_path = clone_repo(git_url, directory, token)
        files = list_files(project_path)
    except Exception as e:
        logger.info(f"Error processing repository: {e}")
        return None

    # Define the prompt template
    project_identification_prompt_template = """
    You are an expert in evaluating the list of file paths provided and respond with an appropriate information about programming language, dependencies object path used in the project. Do recursive and deep dive search for pom.xml or go.mod and note down the path:
    {files}

    Please provide the response in straight forward way without any detailed explanation. For example: if the files contain pom.xml response should be as follows. Also the dependency object value should contain the relative path to the dependency object from the location of project execution.
    
    {{
        "project_type":"Java",
        "dependency_object" : "pom.xml",
    }}
    
    """

    # Create the prompt template object 
    file_evaluation_prompt = ChatPromptTemplate.from_template(project_identification_prompt_template)
    llm_chain = file_evaluation_prompt | get_model() | JsonOutputParser()
    file_list_str = "\n".join(files)
    logger.debug(file_list_str)
    response = llm_chain.invoke(file_list_str)
    response['files_list'] = file_list_str
    logger.info(response)
    logger.debug(response.get("project_type"))
    logger.debug(response.get("dependency_object"))
    return response
