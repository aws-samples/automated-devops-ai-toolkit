# DevOps AI Assistant: Streamline Your Development and Deployment Workflows

The DevOps AI Assistant is a comprehensive tool that automates various aspects of DevOps processes, from generating Dockerfiles to creating infrastructure as code using Terraform and CloudFormation.

This AI-powered assistant streamlines development and deployment workflows by leveraging advanced code generation techniques. It aims to minimize manual coding, reduce errors, and enhance the overall efficiency of DevOps practices.

**Note:** 

1. This release is `MVP1`. MVP2 will have more utilities included like GitHub Actions, Gitlab CI, Test cases.
2. The tool is built on Python version 3.12.3

## Repository Structure

- `app/`: Main application directory
  - `core/`: Core functionality modules
    - `bedrock_definition.py`: AWS Bedrock model configuration
    - `build_docker_image.py`: Docker image building logic
    - `custom_logging.py`: Logging configuration
    - `identify_project.py`: Project identification logic
  - `generators/`: Code generation modules
    - `buildspec/`: BuildSpec generation
    - `cloudformation/`: CloudFormation template generation
    - `docker/`: Dockerfile generation
    - `terraform/`: Terraform configuration generation
  - `pages/`: Streamlit pages for different functionalities
  - `streamlit_sample.py`: Main Streamlit application entry point

## Authors and acknowledgment
We would like to thank the following contributors for their valuable input and work on this project (sorted alphabetically):

• Aditya Ambati 
• Anand Krishna Varanasi 
• JAGDISH KOMAKULA 
• Sarat Chandra Pothula 
• T.V.R.L.Phani Kumar Dadi 
• Varun Sharma


## Usage Instructions

### Installation

Prerequisites:
- Python 3.7+
- Docker
- AWS CLI configured with appropriate permissions

Steps:
1. Clone the repository:
   ```
   git clone <repository-url>
   cd devops-ai-assistant
   ```
2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

### Getting Started

1. Run the Streamlit application:
   ```
   streamlit run app.py
   ```
2. Open your web browser and navigate to the URL displayed in the terminal.

3. Use the sidebar to navigate between different functionalities:
   - Dockerfile Generation
   - Terraform Generation
   - CloudFormation Generation
   - BuildSpec Generation

### Configuration Options

- AWS Credentials: Ensure your AWS CLI is configured with the necessary permissions for Bedrock, ECR, and other AWS services used by the application.
- Model Configuration: Adjust the Bedrock model settings in `app/core/bedrock_definition.py` if needed.

### Common Use Cases

1. Dockerfile Generation:
   - Input: Git repository URL
   - Output: Generated Dockerfile and built Docker image

2. Terraform Generation for ECS:
   - Input: Terraform generation requirements
   - Output: Terraform configuration for ECS deployment

3. CloudFormation Generation for ECS:
   - Input: CloudFormation generation requirements
   - Output: CloudFormation template for ECS deployment

4. BuildSpec Generation:
   - Input: ECR repository name and URI
   - Output: BuildSpec YAML file for AWS CodeBuild

### Testing & Quality

- Run unit tests:
  ```
  python -m unittest discover tests
  ```

### Troubleshooting

- If you encounter issues with AWS services, ensure your AWS CLI is properly configured and you have the necessary permissions.
- For Docker-related issues, make sure Docker is running and you have the required permissions to build and run containers.
- Check the application logs for detailed error messages and stack traces.

## Data Flow

The DevOps AI Assistant processes user inputs through a series of AI-powered generation steps:

1. User provides input (e.g., Git repository URL, generation requirements)
2. Application identifies project type and structure
3. AI model generates appropriate code (Dockerfile, Terraform, CloudFormation, or BuildSpec)
4. Generated code is displayed to the user and optionally saved or executed

```
[User Input] -> [Project Identification] -> [AI Code Generation] -> [Output Display/Execution]
```

Key components in the data flow:
- Bedrock AI model: Handles code generation based on prompts and templates
- Streamlit UI: Manages user interactions and displays results
- Docker: Builds and tests generated Dockerfiles
- AWS services: Interact with ECR, ECS, and other AWS resources as needed

Note: Ensure proper error handling and input validation throughout the data flow to maintain robustness and security.

## License
MIT-0
