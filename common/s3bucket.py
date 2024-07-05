import logging
from common.awsclient import AWSClient
from botocore.errorfactory import ClientError

logger = logging.getLogger(__name__)

aws_client = AWSClient('s3')

s3_bucket_name = "stormation"
def init(bucket_name):
    global s3_bucket_name
    s3_bucket_name = bucket_name.lower() + "-" + aws_client.account_id
    try:
        aws_client.call("create_bucket", query="@", Bucket=s3_bucket_name, ACL='private', CreateBucketConfiguration={
            'LocationConstraint': 'us-west-2'
        })
    except ClientError as e:
        if e.response['Error']['Code'] not in ["BucketAlreadyOwnedByYou", "BucketAlreadyExists"]:
            raise e

    logger.info("created bucket {}".format(s3_bucket_name))

def put_template(name, body):
    aws_client.call("put_object", Body=body, Bucket=s3_bucket_name, Key=name)
    logger.info("uploaded template to s3 {}".format(name))
    return "https://" + s3_bucket_name + ".s3.amazonaws.com/"+name

def delete_template(name):
    pass