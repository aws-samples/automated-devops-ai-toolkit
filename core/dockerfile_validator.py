import os
import streamlit as st
from pathlib import Path

def validate_dockerfile_path(dockerfile_path):
    """
    Validates if the Dockerfile path exists and is readable.
    
    Args:
        dockerfile_path (str): Path to the Dockerfile
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not dockerfile_path:
        return False, "Dockerfile path is not provided"
    
    if not os.path.exists(dockerfile_path):
        return False, f"Dockerfile does not exist at path: {dockerfile_path}"
    
    if not os.path.isfile(dockerfile_path):
        return False, f"Path exists but is not a file: {dockerfile_path}"
    
    try:
        with open(dockerfile_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return False, "Dockerfile is empty"
            if not content.upper().startswith('FROM'):
                return False, "Dockerfile does not start with FROM instruction"
    except Exception as e:
        return False, f"Cannot read Dockerfile: {str(e)}"
    
    return True, "Dockerfile is valid"

def get_validated_dockerfile_path():
    """
    Gets and validates the Dockerfile path from session state.
    
    Returns:
        str or None: Valid Dockerfile path or None if invalid
    """
    if 'docker_file_path' not in st.session_state:
        st.error("No Dockerfile path found. Please generate a Dockerfile first.")
        return None
    
    dockerfile_path = st.session_state.docker_file_path
    is_valid, error_msg = validate_dockerfile_path(dockerfile_path)
    
    if not is_valid:
        st.error(f"Dockerfile validation failed: {error_msg}")
        st.info("Please regenerate the Dockerfile on the Dockerfile Generation page.")
        return None
    
    return dockerfile_path
