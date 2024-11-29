import streamlit as st
import os
from pathlib import Path
from core.identify_project import identify_project_details
from generators.docker.generate_docker_file import generate_docker_file
from core.build_docker_image import build_docker_image
from core.custom_logging import logger

st.set_page_config(page_title="Dockerfile Generation", layout="wide")
st.header("Dockerfile Generation")

# Initialize session state variables
if 'dockerfile_progress' not in st.session_state:
    st.session_state.dockerfile_progress = 0
if 'dockerfile_status' not in st.session_state:
    st.session_state.dockerfile_status = "Not started"
if 'dockerfile_in_progress' not in st.session_state:
    st.session_state.dockerfile_in_progress = False
if 'docker_file_path' not in st.session_state:
    st.session_state.docker_file_path = None

# Create a container to display logs and LLM output
if 'log_container' not in st.session_state:
    st.session_state.log_container = st.empty()

# Input for Git URL and optional Git token
git_url = st.text_input("Git Repository URL", "")
git_token = st.text_input("Git Token (for private repositories)", "", type="password")
clone_directory = st.text_input("Clone Directory", "./temp_repo")

# Function to generate Dockerfile and image
def generate_dockerfile_and_image(git_url, git_token, clone_directory, status_output, progress_bar):
    try:
        progress_percentage = 0

        with st.spinner("Identifying project details..."):
            project_details = identify_project_details(git_url, clone_directory, git_token)
            project_type = project_details.get("project_type").lower()
            project_files_list = project_details.get("files_list")
            project_dependency_object = project_details.get("dependency_object")
            st.success(f"Project dependency: {project_dependency_object}")

        progress_percentage += 30
        st.session_state.dockerfile_progress = progress_percentage
        progress_bar.progress(progress_percentage)

        docker_file_path = f"{Path(project_dependency_object).parent}/Dockerfile"
        st.session_state.docker_file_path = docker_file_path

        with st.spinner("Checking or generating Dockerfile..."):
            if not os.path.isfile(docker_file_path):
                generate_docker_file(project_type, project_dependency_object, project_files_list)
                st.success("Dockerfile generated.")
            else:
                st.success("Dockerfile already exists.")

        progress_percentage += 40
        st.session_state.dockerfile_progress = progress_percentage
        progress_bar.progress(progress_percentage)

        with st.spinner("Building Docker image..."):
            build_docker_image(dockerfile_path=docker_file_path, image_name=f"{project_type}-automation", tag="latest", fix_count=0)
            st.success("Docker image built.")

        st.session_state.dockerfile_status = "Completed successfully"
        st.session_state.dockerfile_progress = 100
        progress_bar.progress(100)

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        st.session_state.dockerfile_status = f"Error: {e}"
        status_output.error(st.session_state.dockerfile_status)
    finally:
        st.session_state.dockerfile_in_progress = False

# Status and progress outputs
status_output = st.empty()
progress_bar = st.progress(st.session_state.dockerfile_progress)

# Restore previous status and progress
status_output.info(st.session_state.dockerfile_status)

# If Dockerfile generation is in progress, restore the button state
if st.session_state.dockerfile_in_progress:
    st.info("Dockerfile generation is in progress...")
else:
    if st.button("Generate Dockerfile and Build Docker Image"):
        if not git_url:
            st.error("Please enter a Git repository URL.")
        else:
            st.session_state.dockerfile_in_progress = True
            generate_dockerfile_and_image(git_url, git_token, clone_directory, status_output, progress_bar)
