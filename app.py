import streamlit as st

st.set_page_config(
    page_title="DevOps AI Assistant",
    page_icon="🤖",
    layout="wide",
)

st.write("# Welcome to the DevOps AI Assistant! 🤖")

st.sidebar.success("Select a page above to begin.")

st.markdown(
    """
    The DevOps AI Assistant is your comprehensive tool for automating various aspects of DevOps processes, 
    from generating Dockerfiles to creating Terraform infrastructure as code. This tool is designed to 
    streamline your development and deployment workflows by utilizing AI-driven code generation techniques.

    **👈 Select a page from the sidebar** to start generating Dockerfiles, Terraform configurations, and more!

    ### Key Features:
    - **Dockerfile Generation:** Automatically generate Dockerfiles tailored to your project’s specific needs.
    - **Terraform Code Generation:** Create robust, production-ready Terraform configurations for your infrastructure.
    - **CloudFormation Code Generation:** Create CloudFormation Templates with AWS Best Practices.
    - **AI-Driven Automation:** Leverage AI to minimize manual coding and reduce the risk of errors.

    ### Get Started:
    - Navigate to the **Dockerfile Generation** page to begin creating Dockerfiles.
    - Use the **Terraform Code Generation** page to generate Terraform configurations based on your Docker setup.
    
    ### Upcoming Features:
    - **CI/CD Pipeline Code Generation**
    - **Kubernetes Configuration Generation**
    - **Enhanced Security and Compliance Checks**

    Stay tuned for updates and new features designed to make your DevOps journey as smooth as possible!
    """
)
