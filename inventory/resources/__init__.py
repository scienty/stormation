import importlib

# Maps resources names as they appear in ARN's to the path name
# of the Python class representing that resource.
ResourceTypes = {
    'aws.apigateway.restapis': 'aws.apigateway.RestAPI',
    'aws.autoscaling.autoScalingGroup': 'aws.autoscaling.AutoScalingGroup',
    'aws.autoscaling.launchConfigurationName': 'aws.autoscaling.LaunchConfiguration',
    'aws.cloudfront.distribution': 'aws.cloudfront.Distribution',
    'aws.cloudformation.stack': 'aws.cloudformation.Stack',
    'aws.cloudwatch.alarm': 'aws.cloudwatch.Alarm',
    'aws.dynamodb.table': 'aws.dynamodb.Table',
    'aws.ec2.address': 'aws.ec2.Address',
    'aws.ec2.customer-gateway': 'aws.ec2.CustomerGateway',
    'aws.ec2.key-pair': 'aws.ec2.KeyPair',
    'aws.ec2.image': 'aws.ec2.Image',
    'aws.ec2.instance': 'aws.ec2.Instance',
    'aws.ec2.network-acl': 'aws.ec2.NetworkAcl',
    'aws.ec2.route-table': 'aws.ec2.RouteTable',
    'aws.ec2.security-group': 'aws.ec2.SecurityGroup',
    'aws.ec2.snapshot': 'aws.ec2.Snapshot',
    'aws.ec2.volume': 'aws.ec2.Volume',
    'aws.ec2.vpc': 'aws.ec2.Vpc',
    'aws.ec2.vpc-peering-connection': 'aws.ec2.VpcPeeringConnection',
    'aws.ec2.subnet': 'aws.ec2.Subnet',
    'aws.elasticache.cluster': 'aws.elasticache.Cluster',
    'aws.elasticache.subnet-group': 'aws.elasticache.SubnetGroup',
    'aws.elasticache.snapshot': 'aws.elasticache.Snapshot',
    'aws.elasticbeanstalk.application': 'aws.elasticbeanstalk.Application',
    'aws.elasticbeanstalk.environment': 'aws.elasticbeanstalk.Environment',
    'aws.elb.loadbalancer': 'aws.elb.LoadBalancer',
    'aws.es.domain': 'aws.es.ElasticsearchDomain',
    'aws.firehose.deliverystream': 'aws.firehose.DeliveryStream',
    'aws.iam.group': 'aws.iam.Group',
    'aws.iam.instance-profile': 'aws.iam.InstanceProfile',
    'aws.iam.role': 'aws.iam.Role',
    'aws.iam.policy': 'aws.iam.Policy',
    'aws.iam.user': 'aws.iam.User',
    'aws.iam.server-certificate': 'aws.iam.ServerCertificate',
    'aws.kinesis.stream': 'aws.kinesis.Stream',
    'aws.lambda.function': 'aws.lambda.Function',
    'aws.rds.db': 'aws.rds.DBInstance',
    'aws.rds.secgrp': 'aws.rds.DBSecurityGroup',
    'aws.redshift.cluster': 'aws.redshift.Cluster',
    'aws.route53.hostedzone': 'aws.route53.HostedZone',
    'aws.route53.healthcheck': 'aws.route53.HealthCheck',
    'aws.s3.bucket': 'aws.s3.Bucket',
    'aws.sqs.queue': 'aws.sqs.Queue',
    'aws.sns.subscription': 'aws.sns.Subscription',
    'aws.sns.topic': 'aws.sns.Topic'
}


def all_providers():
    providers = set()
    for resource_type in ResourceTypes:
        providers.add(resource_type.split('.')[0])
    return list(providers)


def all_services(provider_name):
    services = set()
    for resource_type in ResourceTypes:
        t = resource_type.split('.')
        if t[0] == provider_name:
            services.add(t[1])
    return list(services)


def all_types(provider_name, service_name):
    types = set()
    for resource_type in ResourceTypes:
        t = resource_type.split('.')
        if t[0] == provider_name and t[1] == service_name:
            types.add(t[2])
    return list(types)


def find_resource_class(resource_path):
    """
    dynamically load a class from a string
    """
    class_path = ResourceTypes[resource_path]
    # First prepend our __name__ to the resource string passed in.
    full_path = '.'.join([__name__, class_path])
    class_data = full_path.split(".")
    module_path = ".".join(class_data[:-1])
    class_str = class_data[-1]
    module = importlib.import_module(module_path)
    # Finally, we retrieve the Class
    return getattr(module, class_str)