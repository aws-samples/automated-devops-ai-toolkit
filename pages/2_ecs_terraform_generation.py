import streamlit as st
import time
from core.custom_logging import logger
from core.dockerfile_validator import get_validated_dockerfile_path
from generators.terraform.generate_ecs_terraform_code import get_fixed_terraform_code

st.set_page_config(page_title="Terraform Code Generation", layout="wide")
st.header("Terraform Code Generation")

# Validate Dockerfile path
dockerfile_path = get_validated_dockerfile_path()
if dockerfile_path is None:
    st.stop()

# Initialize session state variables
if 'terraform_progress' not in st.session_state:
    st.session_state.terraform_progress = 0
if 'terraform_status' not in st.session_state:
    st.session_state.terraform_status = "Not started"
if 'terraform_in_progress' not in st.session_state:
    st.session_state.terraform_in_progress = False

user_input = st.text_area("User Input Terraform Generation", "")

# Function to generate Terraform code for ECS
def generate_terraform_code_for_ecs(docker_file_path, user_input):
    try:
        start_time = time.time()

        with st.spinner("Generating ECS Terraform code..."):
            terraform_code = get_fixed_terraform_code(user_input, docker_file_path)
            st.session_state.terraform_status = "Terraform code generation completed successfully."
            st.success(st.session_state.terraform_status)
            st.code(terraform_code, language='hcl')

        end_time = time.time()
        st.session_state.terraform_progress = 100
        st.progress(st.session_state.terraform_progress)
        st.write(f"Time taken: {end_time - start_time:.2f} seconds")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        st.session_state.terraform_status = f"Error: {e}"
        st.error(st.session_state.terraform_status)
    finally:
        st.session_state.terraform_in_progress = False

# Status and progress outputs
status_output = st.empty()
progress_bar = st.progress(st.session_state.terraform_progress)

# Restore previous status and progress
status_output.info(st.session_state.terraform_status)

# If Terraform is in progress, restore the button state
if st.session_state.terraform_in_progress:
    st.info("Terraform generation is in progress...")
else:
    if st.button("Generate Terraform Code"):
        if not user_input:
            status_output.error("Please provide User Input for Terraform Generation.")
        else:
            st.session_state.terraform_in_progress = True
            generate_terraform_code_for_ecs(dockerfile_path, user_input)
