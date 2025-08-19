import logging
import subprocess
import os
from pathlib import Path
from core.custom_logging import logger
from generators.docker.generate_docker_file import fix_docker_build_issue

logger = logging.getLogger(__name__)

def run_container(image_tag):
    """
    Run a container with the given image tag using Finch.
    """
    try:
        result = subprocess.run([
            "finch", "run", "-d",
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
            "--read-only",
            image_tag
        ], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to run container: {e.stderr}")

def build_docker_image(dockerfile_path: str, image_name: str, tag: str, fix_count: int=0):
    """
    Builds a Docker image using Finch from the Dockerfile in the specified project directory.

    Args:
        dockerfile_path (str): The path to the Dockerfile
        image_name (str): The name of the Docker image to be built.
        tag (str): The tag for the Docker image.
        fix_count (int): Counter for build attempts.

    Returns:
        None
    """
    try:
        fix_count += 1
        logger.info(f"Building Docker image '{image_name}:{tag}' using Finch...")
        
        dockerfile_content = ""
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            dockerfile_content = f.read()
        
        updated_tag = f"{image_name}:{tag}"
        build_path = str(Path(dockerfile_path).parent)
        
        # Build the Docker image using Finch
        result = subprocess.run([
            "finch", "build",
            "-t", updated_tag,
            "-f", dockerfile_path,
            build_path
        ], capture_output=True, text=True, check=True)
        
        logger.info(f"Docker image '{image_name}:{tag}' built successfully with Finch.")
        logger.info(f"Running docker image '{image_name}:{tag}'.")
        
        # Run the container
        container_id = run_container(updated_tag)
        logger.info(f"Container '{container_id}' created from the image.")
        
        # Stop and remove container
        subprocess.run(["finch", "stop", container_id], check=True)
        subprocess.run(["finch", "rm", container_id], check=True)
        logger.info(f"Container '{container_id}' stopped and removed.")
        
    except subprocess.CalledProcessError as e:
        logger.info(f"Error building Docker image with Finch: {e.stderr}")
        if fix_count > 10:
            logger.info("Fixing the Dockerfile build issue failed after multiple attempts.")
            return
        fix_docker_build_issue(str(e.stderr), dockerfile_content, dockerfile_path)
        build_docker_image(dockerfile_path, image_name, tag, fix_count)
    except Exception as e:
        logger.info(f"An unexpected error occurred: {e}")
