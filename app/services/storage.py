from app.clients import s3_client
from app.core.config import settings


def presign_get_url(object_key: str) -> str:
    return s3_client.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": settings.AWS_BUCKET, "Key": object_key},
        ExpiresIn=settings.PRESIGN_EXPIRE,
    )
