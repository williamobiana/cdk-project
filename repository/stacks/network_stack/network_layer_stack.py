from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2
)
from constructs import (
    Construct
)

class NetworkLayer(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        env_prefix = self.node.try_get_context("properties").get("env_prefix")
        self.component_prefix = f"project-{env_prefix}"
        
        _vpc_name = f"{self.component_prefix}-ec2-vpc"
        self.vpc = ec2.Vpc(
            self, 
            _vpc_name,
            vpc_name=_vpc_name,
            cidr='10.0.0.0/16',
            max_azs=2,
            subnet_configuration=[
                {
                    'cidrMask': 28,
                    'name' : f"{_vpc_name}-publicsubnet",
                    'subnetType': ec2.SubnetType.PUBLIC
                },
                {
                    'cidrMask': 28,
                    'name' : f"{_vpc_name}-privatesubnet",
                    'subnetType': ec2.SubnetType.PRIVATE_ISOLATED
                }
            ]
        )

        _vpc_endpoint_name = f"{self.component_prefix}-ec2-vpcendpoint"
        
        self.s3_endpoint = self.vpc.add_gateway_endpoint(
            id=_vpc_endpoint_name,
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)]
        )

