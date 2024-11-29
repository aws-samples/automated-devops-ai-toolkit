import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from typing import Dict
from langchain_aws import ChatBedrock
from core.custom_logging import logger
from botocore.config import Config

def get_model(
    service_name: str = "bedrock-runtime",
    model_kwargs: Dict[str, any] = {
        "max_tokens": 4096,
        "temperature": 0.0,  
        "top_k": 1,  
        "top_p": 1,  
        "stop_sequences": ["Human"],
    },
    region_name: str = "us-west-2",
    model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
) -> ChatBedrock:
    """
    Creates a ChatBedrock instance with the specified parameters.

    Args:
        service_name (str): The name of the AWS service (e.g., "bedrock-runtime").
        region_name (str): The AWS region name (e.g., "us-west-2").
        model_id (str): The ID of the model to use (e.g., "anthropic.claude-3-sonnet-20240229-v1:0").
        model_kwargs (Dict[str, any]): A dictionary of keyword arguments for the model.

    Returns:
        ChatBedrock: An instance of the ChatBedrock class.

    Raises:
        ClientError: If there is an error communicating with the AWS service.
        NoCredentialsError: If AWS credentials are not provided or are invalid.
        ValueError: If the provided model_id is invalid or not supported.
        Exception: If any other unexpected error occurs.
    """
    try:
        config = Config(read_timeout=1000)
        bedrock_runtime = boto3.client(service_name=service_name, region_name=region_name, config=config)
    except (ClientError, NoCredentialsError) as e:
        logger.info(f"Error creating AWS client: {e}")
        raise Exception(f"Failed to create AWS client: {e}") from e

    try:
        model = ChatBedrock(
            client=bedrock_runtime,
            model_id=model_id,
            model_kwargs=model_kwargs,
        )
    except ValueError as e:
        logger.info(f"Error creating ChatBedrock instance: {e}")
        raise RuntimeError(f"Failed to initialize ChatBedrock: {e}") from e
    except Exception as e:
        logger.info(f"Unexpected error: {e}")
        raise Exception(f"An unexpected error occurred: {e}") from e

    return model
