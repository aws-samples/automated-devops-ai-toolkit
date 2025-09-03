import os
import git
import re
from typing import List, Optional
from langchain.prompts import PromptTemplate, ChatPromptTemplate
from core.bedrock_definition import get_model
from langchain_core.output_parsers import JsonOutputParser
from core.custom_logging import logger

SAFE_CLONE_ROOT = "./safe_temp_repos"

def _sanitize_path_component(path_component: str) -> str:
    """Sanitize path component to prevent attacks while preserving functionality."""
    if '..' in path_component or path_component.startswith('/') or '\\' in path_component:
        raise ValueError(f"Invalid path component: {path_component}")
    if not re.match(r'^[a-zA-Z0-9._-]+$', path_component):
        raise ValueError(f"Path component contains invalid characters: {path_component}")
    return path_component

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
    # Validate and normalize the directory path
    safe_root_abs = os.path.abspath(SAFE_CLONE_ROOT)
    user_dir_abs = os.path.abspath(os.path.join(safe_root_abs, directory))
    if not user_dir_abs.startswith(safe_root_abs):
        raise ValueError(f"Invalid clone directory: {directory}")

    if token:
        if "https://" in git_url:
            git_url = git_url.replace("https://", f"https://{token}@")
        elif "git@" in git_url:
            git_url = git_url.replace("git@", f"git@{token}:")
        else:
            raise ValueError(f"Unsupported Git URL format: {git_url}")
    
    # Sanitize repository name from URL
    repo_name = os.path.basename(git_url).replace('.git', '')
    repo_name = _sanitize_path_component(repo_name)
    repo_path = os.path.join(user_dir_abs, repo_name)
    
    # Final validation of constructed repository path
    repo_path_abs = os.path.abspath(repo_path)
    if not repo_path_abs.startswith(safe_root_abs):
        raise ValueError(f"Invalid repository path: {repo_path}")
    
    try:
        if os.path.exists(repo_path_abs):
            logger.info(f"Repository already exists at '{repo_path_abs}'. Pulling latest changes.")
            repo = git.Repo(repo_path_abs)
            repo.git.pull()
        else:
            logger.info(f"Cloning repository '{git_url}' to '{repo_path_abs}'")
            git.Repo.clone_from(git_url, repo_path_abs)
    except Exception as e:
        logger.info(f"Failed to clone repository: {e}")
        raise Exception(f"Repository cloning failed: {e}") from e
    
    return repo_path_abs

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
    # Validate and normalize the directory path
    safe_root_abs = os.path.abspath(SAFE_CLONE_ROOT)
    dir_abs = os.path.abspath(directory)
    if not dir_abs.startswith(safe_root_abs):
        logger.warning(f"Attempted access to directory outside safe root: {directory}")
        raise PermissionError(f"Access to directory '{directory}' is not allowed.")

    file_list = []

    try:
        for root, dirs, files in os.walk(dir_abs):
            # Validate each root path during traversal
            root_abs = os.path.abspath(root)
            if not root_abs.startswith(safe_root_abs):
                logger.warning(f"Skipping invalid path during traversal: {root}")
                continue
                
            for file in files:
                try:
                    # Sanitize filename for security
                    _sanitize_path_component(file)
                    file_path = os.path.join(root, file)
                    if os.path.isfile(file_path):
                        file_list.append(file_path)
                except ValueError:
                    logger.warning(f"Skipping file with invalid name: {file}")
                    continue
                    
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
    You are an expert in evaluating file paths to identify project types. Analyze the files and return ONLY valid JSON with no additional text.

    Files: {files}

    Identification rules (priority order):
    - If pom.xml exists: project_type="java", dependency_object=path to pom.xml
    - If build.gradle exists: project_type="java", dependency_object=path to build.gradle  
    - If go.mod exists: project_type="go", dependency_object=path to go.mod
    - If Cargo.toml exists: project_type="rust", dependency_object=path to Cargo.toml
    - If package.json exists: project_type="node", dependency_object=path to package.json
    - If requirements.txt exists: project_type="python", dependency_object=path to requirements.txt
    - If setup.py exists: project_type="python", dependency_object=path to setup.py
    - If pyproject.toml exists: project_type="python", dependency_object=path to pyproject.toml
    - If Dockerfile exists but no other files: project_type="docker", dependency_object=path to Dockerfile
    - If .csproj exists: project_type="dotnet", dependency_object=path to .csproj file
    - If composer.json exists: project_type="php", dependency_object=path to composer.json

    Return only this JSON format:
    {{"project_type":"<language>","dependency_object":"<full_path_to_dependency_file>"}}
    """

    # Create the prompt template object 
    file_evaluation_prompt = ChatPromptTemplate.from_template(project_identification_prompt_template)
    llm_chain = file_evaluation_prompt | get_model()
    file_list_str = "\n".join(files)
    logger.debug(file_list_str)
    
    try:
        raw_response = llm_chain.invoke({"files": file_list_str})
        # Extract JSON from response if wrapped in text
        import json
        import re
        
        response_text = raw_response.content if hasattr(raw_response, 'content') else str(raw_response)
        json_match = re.search(r'\{[^}]*\}', response_text)
        
        if json_match:
            response = json.loads(json_match.group())
        else:
            raise ValueError("No JSON found in response")
            
        response['files_list'] = file_list_str
        logger.info(response)
        logger.debug(response.get("project_type"))
        logger.debug(response.get("dependency_object"))
        return response
    except Exception as e:
        logger.error(f"JSON parsing failed: {e}")
        return None
