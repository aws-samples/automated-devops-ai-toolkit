import streamlit as st
import time
from core.custom_logging import logger
from core.dockerfile_validator import get_validated_dockerfile_path
from generators.terraform.generate_eks_terraform_code import get_fixed_eks_terraform_code

st.set_page_config(page_title="EKS Terraform Code Generation", layout="wide")
st.header("EKS Terraform Code Generation")

# Validate Dockerfile path
dockerfile_path = get_validated_dockerfile_path()
if dockerfile_path is None:
    st.stop()

# Initialize session state variables
if 'eks_terraform_progress' not in st.session_state:
    st.session_state.eks_terraform_progress = 0
if 'eks_terraform_status' not in st.session_state:
    st.session_state.eks_terraform_status = "Not started"
if 'eks_terraform_in_progress' not in st.session_state:
    st.session_state.eks_terraform_in_progress = False

user_input = st.text_area("User Input EKS Terraform Generation", 
                         placeholder="e.g., Create EKS cluster with Fargate profile for web application")

# Function to generate EKS Terraform code
def generate_eks_terraform_code_for_deployment(docker_file_path, user_input):
    try:
        start_time = time.time()

        with st.spinner("Generating EKS Terraform code..."):
            terraform_code = get_fixed_eks_terraform_code(user_input, docker_file_path)
            st.session_state.eks_terraform_status = "EKS Terraform code generation completed successfully."
            st.success(st.session_state.eks_terraform_status)
            
            # Display Terraform code
            st.subheader("Generated Terraform Configuration")
            st.code(terraform_code, language='hcl')
            
            # Display Kubernetes manifests if available
            try:
                from generators.terraform.generate_eks_terraform_code import kubernetes_manifest_chain, read_dockerfile
                dockerfile_content = read_dockerfile(docker_file_path)
                kubernetes_manifests = kubernetes_manifest_chain.invoke({"dockerfile_content": dockerfile_content})["response"]
                
                st.subheader("Generated Kubernetes Manifests")
                st.code(kubernetes_manifests, language='yaml')
            except Exception as e:
                st.warning(f"Could not display Kubernetes manifests: {str(e)}")

        end_time = time.time()
        st.session_state.eks_terraform_progress = 100
        st.progress(st.session_state.eks_terraform_progress)
        st.write(f"Time taken: {end_time - start_time:.2f} seconds")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        st.session_state.eks_terraform_status = f"Error: {e}"
        st.error(st.session_state.eks_terraform_status)
    finally:
        st.session_state.eks_terraform_in_progress = False

# Status and progress outputs
status_output = st.empty()
progress_bar = st.progress(st.session_state.eks_terraform_progress)

# Restore previous status and progress
status_output.info(st.session_state.eks_terraform_status)

# If EKS Terraform is in progress, restore the button state
if st.session_state.eks_terraform_in_progress:
    st.info("EKS Terraform generation is in progress...")
else:
    if st.button("Generate EKS Terraform Code"):
        if not user_input:
            status_output.error("Please provide User Input for EKS Terraform Generation.")
        else:
            st.session_state.eks_terraform_in_progress = True
            generate_eks_terraform_code_for_deployment(dockerfile_path, user_input)
