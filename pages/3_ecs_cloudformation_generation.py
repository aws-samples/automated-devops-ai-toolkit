import streamlit as st
import time
from core.custom_logging import logger
from core.dockerfile_validator import get_validated_dockerfile_path
from generators.cloudformation.generate_ecs_cloudformation_code import get_fixed_cloudformation_template  

st.set_page_config(page_title="CloudFormation Code Generation", layout="wide")
st.header("CloudFormation Code Generation")

# Validate Dockerfile path
dockerfile_path = get_validated_dockerfile_path()
if dockerfile_path is None:
    st.stop()

# Initialize session state variables
if 'cloudformation_progress' not in st.session_state:
    st.session_state.cloudformation_progress = 0
if 'cloudformation_status' not in st.session_state:
    st.session_state.cloudformation_status = "Not started"
if 'cloudformation_in_progress' not in st.session_state:
    st.session_state.cloudformation_in_progress = False

user_input = st.text_area("User Input CloudFormation Generation", "")

# Function to generate CloudFormation code
def generate_cloudformation_code_for_ecs(docker_file_path, user_input):
    try:
        start_time = time.time()

        with st.spinner("Generating ECS CloudFormation code..."):
            # Call the function with the correct number of arguments
            cloudformation_template = get_fixed_cloudformation_template(user_input, docker_file_path)
            if cloudformation_template:
                st.session_state.cloudformation_status = "CloudFormation code generation completed successfully."
                st.success(st.session_state.cloudformation_status)
                st.code(cloudformation_template, language='yaml')
            else:
                raise ValueError("Failed to generate CloudFormation template.")

        end_time = time.time()
        st.session_state.cloudformation_progress = 100
        st.progress(st.session_state.cloudformation_progress)
        st.write(f"Time taken: {end_time - start_time:.2f} seconds")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        st.session_state.cloudformation_status = f"Error: {e}"
        st.error(st.session_state.cloudformation_status)
    finally:
        st.session_state.cloudformation_in_progress = False

# Status and progress outputs
status_output = st.empty()
progress_bar = st.progress(st.session_state.cloudformation_progress)

# Restore previous status and progress
status_output.info(st.session_state.cloudformation_status)

# If CloudFormation is in progress, restore the button state
if st.session_state.cloudformation_in_progress:
    st.info("CloudFormation generation is in progress...")
else:
    if st.button("Generate CloudFormation Code"):
        if not user_input:
            status_output.error("Please provide User Input for CloudFormation Generation.")
        else:
            st.session_state.cloudformation_in_progress = True
            generate_cloudformation_code_for_ecs(dockerfile_path, user_input)
