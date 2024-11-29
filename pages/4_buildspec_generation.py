import streamlit as st
import time
from core.custom_logging import logger
from generators.buildspec.generate_buildspec import generate_buildspec

st.set_page_config(page_title="BuildSpec Generation", layout="wide")
st.header("BuildSpec Generation")

# Ensure the Dockerfile path is available in session state
if 'docker_file_path' not in st.session_state or st.session_state.docker_file_path is None:
    st.error("Please generate the Dockerfile and build the Docker image first on the Dockerfile Generation page.")
    st.stop()

# Initialize session state variables
if 'buildspec_progress' not in st.session_state:
    st.session_state.buildspec_progress = 0
if 'buildspec_status' not in st.session_state:
    st.session_state.buildspec_status = "Not started"
if 'buildspec_in_progress' not in st.session_state:
    st.session_state.buildspec_in_progress = False

ecr_repository_name = st.text_input("ECR Repository Name", "")
ecr_repository_uri = st.text_input("ECR Repository URI", "")

# Function to generate BuildSpec
def generate_buildspec_code(docker_file_path, ecr_repository_name, ecr_repository_uri):
    try:
        start_time = time.time()

        with st.spinner("Generating BuildSpec..."):
            buildspec_yaml = generate_buildspec(docker_file_path, ecr_repository_name, ecr_repository_uri)
            if buildspec_yaml:
                if buildspec_yaml.startswith("version: 0.2"):
                    st.session_state.buildspec_status = "BuildSpec generation completed successfully."
                    st.success(st.session_state.buildspec_status)
                    st.code(buildspec_yaml, language='yaml')
                else:
                    st.warning("Generated content may not be a valid buildspec.yaml. Please review:")
                    st.code(buildspec_yaml)
            else:
                raise ValueError("Failed to generate BuildSpec.")

        end_time = time.time()
        st.session_state.buildspec_progress = 100
        st.progress(st.session_state.buildspec_progress)
        st.write(f"Time taken: {end_time - start_time:.2f} seconds")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        st.session_state.buildspec_status = f"Error: {e}"
        st.error(st.session_state.buildspec_status)
    finally:
        st.session_state.buildspec_in_progress = False

# Status and progress outputs
status_output = st.empty()
progress_bar = st.progress(st.session_state.buildspec_progress)

# Restore previous status and progress
status_output.info(st.session_state.buildspec_status)

# If BuildSpec is in progress, restore the button state
if st.session_state.buildspec_in_progress:
    st.info("BuildSpec generation is in progress...")
else:
    if st.button("Generate BuildSpec"):
        if not ecr_repository_name or not ecr_repository_uri:
            status_output.error("Please provide ECR Repository Name and URI.")
        else:
            st.session_state.buildspec_in_progress = True
            generate_buildspec_code(st.session_state.docker_file_path, ecr_repository_name, ecr_repository_uri)