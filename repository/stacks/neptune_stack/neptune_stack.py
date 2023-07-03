import os
import aws_cdk as core

from aws_cdk import (
    Stack,
    aws_ec2 as _ec2, 
    aws_ecs as _ecs,
    aws_s3 as _s3,
    aws_iam as _iam,
    aws_s3_notifications as _s3n,
    aws_ecs_patterns as _ecs_patterns,
    aws_neptune as _neptune,
    aws_sagemaker as _sagemaker,
    aws_lambda as _lambda,
    Duration as _Duration
)

from repository.util import util as _util

from constructs import Construct

class NeptuneStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, network_stack, fargate_stack, comformed_zone_stack, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        #testing approvals

        ########## INITIALIZER ##########       
        self.properties = self.node.try_get_context("properties").get("properties")
        self.functions_path = os.path.join(os.path.dirname(__file__), self.properties.get("functions_path"))
        self.neptune_data_path = str(self.properties.get("neptune_data_path"))
        env_prefix = self.node.try_get_context("properties").get("env_prefix")
        self.component_prefix = f"project-{env_prefix}"
        self.saml_provider_ARN = self.properties.get("saml_provider_ARN")
        self.neptune_cluster_ARN = self.properties.get("neptune_cluster_ARN")
        zip_path = os.path.join(os.path.dirname(__file__), "layer/sparqlwrapper.zip")
        
        #CREATING BUCKET TO STORE GRAPH MODELED DATA
        _neptune_zone_bucket_name = f"{self.component_prefix}-s3-neptunezone"
        self.neptune_data_bucket = _s3.Bucket(self, 
            _neptune_zone_bucket_name,
            encryption=_s3.BucketEncryption.KMS_MANAGED,
            bucket_name=_neptune_zone_bucket_name,
            enforce_ssl=True
        )

        # CREATE LAMBDA SEC GROUP ON THE VPC WHERE LAMNDA IS RUNNING
        _lambda_digest_name = f"{self.component_prefix}-digestfunction-sg"
        sg_lambda_digest = _ec2.SecurityGroup(self, _lambda_digest_name,
            vpc=network_stack.vpc,
            allow_all_outbound=True,
            description='security group for lambda digest function',
            security_group_name=_lambda_digest_name
        )

        #CREATE AWS MANAGED AWSSDKPandas LAYER
        AWSSDKPandas_layer_arn = "arn:aws:lambda:eu-west-1:123456789012:layer:AWSSDKPandas-Python39:8"
        AWSSDKPandas_layer = _lambda.LayerVersion.from_layer_version_arn(
            self, 'AWSManagedLayer', AWSSDKPandas_layer_arn)
        
        #CUSTOM SPARQLWrapper LAYER
        sparqlwrapper_layer = self.define_layer(_function_name="sparqlwrapper_layer", _function_path=zip_path)

        #ADD LAYERS TO A LIST
        layer_list = [AWSSDKPandas_layer, sparqlwrapper_layer]

        #CREATE DIGEST FUNCTION
        self.digest_function = _util.define_lambda_function_on_vpc_with_secgroup_and_layer(
            self, 
            'digest_function', 
            self.functions_path,
            network_stack.vpc,
            sg_lambda_digest,
            layer_list
        )

        #ListObjectsV2
        self.digest_function.add_to_role_policy(
            _iam.PolicyStatement( # Allow extra policies for conformed zone S3 Bucket
                effect=_iam.Effect.ALLOW,
                actions=[
                    "s3:ListObjectsV2"
                ],
                resources=[comformed_zone_stack.conformed_zone_bucket.bucket_arn,
                        f"{comformed_zone_stack.conformed_zone_bucket.bucket_arn}/*"]
            )
        )

        #CREATE POLICY SO DIGEST FUNCTION CAN ACCESS S3 FROM THE PRIVATE SUBNETS
        network_stack.s3_endpoint.add_to_policy(
            _iam.PolicyStatement( # Restrict to listing and describing tables
                effect=_iam.Effect.ALLOW,
                principals=[_iam.AnyPrincipal()],
                actions=[
                    "s3:*"
                ],
                resources=[comformed_zone_stack.conformed_zone_bucket.bucket_arn]
            )
        )

        #GRANT READ ACCESS SO THE RECEPTION FUNCTION CAN READ AND WRITE ON THE BUCKET
        comformed_zone_stack.conformed_zone_bucket.grant_read(
            self.digest_function
        )

        #GRANT WRITE PRIVILEGE SO THE DIGEST FUNCTION CAN STORE FILES IN NEPTUNE PREINGESTION BUCKET
        self.neptune_data_bucket.grant_write(
            self.digest_function, 
            objects_key_pattern=self.neptune_data_path
        )

        self.neptune_data_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED, 
            _s3n.LambdaDestination(self.digest_function),
            _s3.NotificationKeyFilter(
                prefix=self.neptune_data_path
            )
        )

        ########## NEPTUNE ##########
        _neptune_cluster_name = f"{self.component_prefix}-neptune-cluster"
        graph_db = self.create_neptune_cluster(
            _neptune_cluster_name, 
            network_stack.vpc, 
            fargate_stack.fargateServiceSecGroup,
            sg_lambda_digest
        )
        
        ########## NEPTUNE [END] ##########
    
    def create_neptune_cluster(self , _cluster_name, _vpc, sg_fargate, sg_lambda_digest):
        sg_graph_db = _ec2.SecurityGroup(self, f"{_cluster_name}-sg",
            vpc=_vpc,
            allow_all_outbound=True,
            description='security group for neptune',
            security_group_name=f"{_cluster_name}-sg"
        )

        sg_graph_db.add_ingress_rule(peer=sg_graph_db, connection=_ec2.Port.tcp(8182), description=f"{_cluster_name}")
        sg_graph_db.add_ingress_rule(peer=sg_fargate, connection=_ec2.Port.tcp(8182), description=f"{_cluster_name}-client")
        sg_graph_db.add_ingress_rule(peer=sg_lambda_digest, connection=_ec2.Port.all_traffic(), description=f"{_cluster_name}-client-lambda-digest")

        _neptune_subnetgroup_name = f"{_cluster_name}-subnet_group"
        graph_db_subnet_group = _neptune.CfnDBSubnetGroup(
            self, 
            _neptune_subnetgroup_name,
            db_subnet_group_description='subnet group for neptune',
            subnet_ids=_vpc.select_subnets(subnet_type=_ec2.SubnetType.PRIVATE_ISOLATED).subnet_ids,
            db_subnet_group_name=_neptune_subnetgroup_name
        )

        graph_db = _neptune.CfnDBCluster(
            self, 
            _cluster_name,
            availability_zones=_vpc.availability_zones,
            db_subnet_group_name=graph_db_subnet_group.db_subnet_group_name,
            db_cluster_identifier=_cluster_name,
            backup_retention_period=1,
            preferred_backup_window='00:00-06:00',
            preferred_maintenance_window='sun:22:00-mon:00:00',
            vpc_security_group_ids=[sg_graph_db.security_group_id]
        )
        graph_db.add_dependency(graph_db_subnet_group)

        graph_db_instance = _neptune.CfnDBInstance(self, f"{_cluster_name}-instance",
            db_instance_class='db.t3.medium',
            #db_instance_class='db.r5.large',
            allow_major_version_upgrade=False,
            auto_minor_version_upgrade=False,
            availability_zone=_vpc.availability_zones[0],
            db_cluster_identifier=graph_db.db_cluster_identifier,
            db_instance_identifier=_cluster_name,
            preferred_maintenance_window='sun:22:00-mon:00:00'
        )
        graph_db_instance.add_dependency(graph_db)

        _neptune_replica_name = f"{_cluster_name}-replica"
        graph_db_replica_instance = _neptune.CfnDBInstance(
            self, 
            _neptune_replica_name,
            db_instance_class='db.t3.medium',
            #db_instance_class='db.r5.large',
            allow_major_version_upgrade=False,
            auto_minor_version_upgrade=False,
            availability_zone=_vpc.availability_zones[-1],
            db_cluster_identifier=graph_db.db_cluster_identifier,
            db_instance_identifier=_neptune_replica_name,
            preferred_maintenance_window='sun:18:00-sun:18:30'
        )
        graph_db_replica_instance.add_dependency(graph_db)
        graph_db_replica_instance.add_dependency(graph_db_instance)

        return graph_db

    def define_layer(self, _function_name, _function_path):
        print("Creating LAMBDA layer: " + _function_name + "/" + _function_path)
        
        return _lambda.LayerVersion(
            self,
            id=_function_name, 
            code=_lambda.Code.from_asset(_function_path)
        )