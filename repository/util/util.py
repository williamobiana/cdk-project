from aws_cdk import (
    aws_lambda as _lambda,
    aws_ec2 as _ec2,
    aws_iam as _iam,
    Duration as _Duration
)

'''
DEFINE LAMBDA FUNCTION
'''
def define_lambda_function(self, function_name, function_path):
    print("Creating LAMBDA function: " + function_name + "/" + function_path)
    return _lambda.Function(
        self, 
        function_name,
        function_name=function_name,
        runtime=_lambda.Runtime.PYTHON_3_9,
        code=_lambda.Code.from_asset(function_path),
        handler=function_name + '.handler',
        timeout=_Duration.minutes(10)
    )
    
def define_lambda_function_on_vpc(self, function_name, function_path, _vpc):
    print("Creating LAMBDA function on VPC: " + function_name + "/" + function_path)
    return _lambda.Function(
        self, 
        function_name,
        function_name=function_name,
        runtime=_lambda.Runtime.PYTHON_3_9,
        code=_lambda.Code.from_asset(function_path),
        handler=function_name + '.handler',
        vpc=_vpc,
        vpc_subnets=_ec2.SubnetSelection(subnet_type=_ec2.SubnetType.PRIVATE_ISOLATED),
        timeout=_Duration.minutes(10)
    )

def define_lambda_function_on_vpc_with_secgroup(self, function_name, function_path, _vpc, sec_group):
    print("Creating LAMBDA function on VPC: " + function_name + "/" + function_path)
    return _lambda.Function(
        self, 
        function_name,
        function_name=function_name,
        runtime=_lambda.Runtime.PYTHON_3_9,
        code=_lambda.Code.from_asset(function_path),
        handler=function_name + '.handler',
        vpc=_vpc,
        vpc_subnets=_ec2.SubnetSelection(subnet_type=_ec2.SubnetType.PRIVATE_ISOLATED),
        timeout=_Duration.minutes(10),
        security_groups=[sec_group]
    )

def define_lambda_function_with_role(self, function_name, function_path, execRole):
    print("Creating LAMBDA function: " + function_name + "/" + function_path)
    
    return _lambda.Function(
        self, 
        function_name,
        function_name=function_name,
        runtime=_lambda.Runtime.PYTHON_3_9,
        code=_lambda.Code.from_asset(function_path),
        handler=function_name + '.handler',
        role=execRole,
        timeout=_Duration.minutes(10)
    )

def define_lambda_function_on_vpc_with_secgroup_and_layer(self, function_name, function_path, _vpc, sec_group, layer):
    print("Creating LAMBDA function on VPC: " + function_name + "/" + function_path)
    return _lambda.Function(
        self, 
        function_name,
        function_name=function_name,
        runtime=_lambda.Runtime.PYTHON_3_9,
        code=_lambda.Code.from_asset(function_path),
        handler=function_name + '.handler',
        vpc=_vpc,
        vpc_subnets=_ec2.SubnetSelection(subnet_type=_ec2.SubnetType.PRIVATE_ISOLATED),
        timeout=_Duration.minutes(10),
        security_groups=[sec_group],
        layers=layer
    )