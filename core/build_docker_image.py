import logging
import docker
from docker.errors import BuildError, APIError
from pathlib import Path
from core.custom_logging import logger
from generators.docker.generate_docker_file import fix_docker_build_issue

logger = logging.getLogger(__name__)
# Define a set of allowed image names and tags
ALLOWED_IMAGES = {
    "image1": ["latest", "v1", "v2"],
    "image2": ["latest", "stable"],
    # Add more allowed images and tags as needed
}

def run_container(client, image_tag):
    """
    Run a container with the given image tag and return the container object.
    """
    return client.containers.run(
        image_tag,
        detach=True,
        security_opt=["no-new-privileges"],
        cap_drop=["ALL"],
        read_only=True
    )

def build_docker_image(dockerfile_path: str, image_name: str, tag: str,fix_count: int=0):
    """
    Builds a Docker image from the Dockerfile in the specified project directory.

    Args:
        dockerfile_path (str): The path to the Dockerfile
        image_name (str): The name of the Docker image to be built.
        tag (str): The tag for the Docker image.
        fix_count (int): Counter for build attempts.

    Returns:
        None
    """
    try:
         # Validate image name and tag
     #   if image_name not in ALLOWED_IMAGES or tag not in ALLOWED_IMAGES[image_name]:
     #       raise ValueError(f"Invalid image name or tag: {image_name}:{tag}")
        fix_count+=1
        logger.info(f"Before docker build env '{image_name}:{tag}'...")
        client = docker.from_env()
        dockerfile_content=""
        logger.info(f"Building Docker image '{image_name}:{tag}'...")
        with open(dockerfile_path, "r", encoding="utf-8") as f:
            dockerfile_content = f.read()
        updated_tag=f"{image_name}:{tag}"
        # Build the Docker image
        client.images.build(
            path=str(Path(dockerfile_path).parent),
            dockerfile=str('Dockerfile'),
            tag=updated_tag,
            buildargs={
                "provenance" : "false"
            },
            rm=True
        )
        logger.info(f"Docker image '{image_name}:{tag}' built successfully.")
        logger.info(f"Running docker image '{image_name}:{tag}'.")
        # Use the separate function to run the container
        container_object = run_container(client, updated_tag)
        logger.info(f"Container '{container_object.id}' created from the image.")
        logger.info(f"Stopping Container '{container_object.id}'.")
        container_object.stop()
        logger.info(f"Removing Container '{container_object.id}'.")
        container_object.remove()
    except docker.errors.BuildError as e:
        logger.info(f"Error building Docker image: {e}")
        if fix_count > 10:
            logger.info("Fixing the Dockerfile build issue failed after multiple attempts. Please check the Dockerfile and try again.")
            return
        fix_docker_build_issue(e,dockerfile_content,dockerfile_path)
        build_docker_image(dockerfile_path, image_name, tag,fix_count)
    except docker.errors.APIError as e:
        logger.info(f"Unexpected error: {e}")
        if fix_count > 10:
            logger.info("Fixing the Dockerfile build issue failed after multiple attempts. Please check the Dockerfile and try again.")
            return
        fix_docker_build_issue(e,dockerfile_content,dockerfile_path)
        build_docker_image(dockerfile_path, image_name, tag,fix_count)
    except Exception as e:
        logger.info(f"An unexpected error occurred: {e}")
