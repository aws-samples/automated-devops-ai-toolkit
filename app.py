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
    from generating Dockerfiles to creating infrastructure as code. This tool is designed to 
    streamline your development and deployment workflows by utilizing AI-driven code generation techniques.

    **👈 Select a page from the sidebar** to start generating Dockerfiles, infrastructure configurations, and more!

    ### Key Features:
    - **Dockerfile Generation:** Automatically generate Dockerfiles tailored to your project's specific needs.
    - **ECS Infrastructure:** Create robust Terraform and CloudFormation configurations for AWS ECS.
    - **EKS Infrastructure:** Generate Kubernetes-native infrastructure code for AWS EKS.
    - **AI-Driven Automation:** Leverage AI to minimize manual coding and reduce the risk of errors.

    ### Container Orchestration Options:
    
    #### AWS ECS (Elastic Container Service)
    - **ECS Terraform Generation:** Fargate and EC2 Auto Scaling configurations
    - **ECS CloudFormation Generation:** Complete ECS infrastructure templates
    
    #### AWS EKS (Elastic Kubernetes Service)  
    - **EKS Terraform Generation:** Fargate and EC2 Node Group configurations
    - **EKS CloudFormation Generation:** Complete EKS infrastructure templates

    ### Get Started:
    1. Navigate to **Dockerfile Generation** to create your container image
    2. Choose your orchestration platform (ECS or EKS)
    3. Select your compute type (Fargate or EC2)
    4. Generate infrastructure code (Terraform or CloudFormation)
    
    ### Upcoming Features:
    - **CI/CD Pipeline Code Generation**
    - **Enhanced Security and Compliance Checks**

    Stay tuned for updates and new features designed to make your DevOps journey as smooth as possible!
    """
)
