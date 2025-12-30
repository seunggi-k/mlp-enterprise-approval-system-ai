import boto3
from openai import OpenAI

from app.core.config import settings

# External clients initialized once and reused.
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
s3_client = boto3.client(
    "s3",
    aws_access_key_id=settings.AWS_ACCESS_KEY,
    aws_secret_access_key=settings.AWS_SECRET_KEY,
    region_name=settings.AWS_REGION,
)
