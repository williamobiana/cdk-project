from aws_cdk import (
    Stack,
    aws_iam as _iam,
    aws_lambda as _lambda,
    aws_s3 as _s3,
    aws_s3_notifications as _s3n,
    aws_ec2 as _ec2, 
    aws_ecs as _ecs,
    aws_ecs_patterns as _ecs_patterns,
    aws_neptune as _neptune,
    aws_athena as _athena,
    aws_quicksight as _quicksight
)

import aws_cdk as core

from repository.util import util as _util

from constructs import Construct

class AnalyticsStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, conformed_zone, reception_zone_bucket_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.properties = self.node.try_get_context("properties").get("properties")
        env_prefix = self.node.try_get_context("properties").get("env_prefix")
        self.parquet_data_path = self.properties.get("parquet_data_path")
        self.component_prefix = f"project-{env_prefix}"
        self.quicksight_group_arn = self.properties.get("quicksight_group_arn")
        self.saml_provider_ARN = self.properties.get("saml_provider_ARN")
        self.athena_workgroups_ARN = self.properties.get("athena_workgroups_ARN")
        self.neptune_cluster_ARN = self.properties.get("neptune_cluster_ARN")
        self.saml_provider_ARN = self.properties.get("saml_provider_ARN")

        self.bucket_name = reception_zone_bucket_name

        #Using quicksight default role
        #qs_role = self.create_qs_role(conformed_zone.conformed_zone_bucket.bucket_arn)
        qs_datasource = self.create_datasource(None)
        qs_dataset = self.create_dataset(qs_datasource)

        ########### CREATE FEDERATED USERS ROLE ##############
        users_role = self.create_federated_userRole()

    def create_datasource(self, quicksight_role):
        _quicksight_datasource_name = f"{self.component_prefix}-quicksight-datasource"

        return _quicksight.CfnDataSource(
            self, 
            _quicksight_datasource_name, 
            aws_account_id=core.Aws.ACCOUNT_ID,
            data_source_id=_quicksight_datasource_name,
            type="ATHENA",
            name=_quicksight_datasource_name,
            permissions=[_quicksight.CfnDataSource.ResourcePermissionProperty(
                actions=["quicksight:DescribeDataSource",
                        "quicksight:DescribeDataSourcePermissions",
                        "quicksight:PassDataSource",
                        "quicksight:UpdateDataSource",
                        "quicksight:DeleteDataSource",
                        "quicksight:UpdateDataSourcePermissions"],
                principal=self.quicksight_group_arn
            )],
            data_source_parameters=_quicksight.CfnDataSource.DataSourceParametersProperty(
                athena_parameters=_quicksight.CfnDataSource.AthenaParametersProperty(
                    work_group='primary'
                )
            )
        )
    
    def create_dataset(self, datasource):
        _quicksight_dataset_name = f"{self.component_prefix}-dataset"

        return _quicksight.CfnDataSet(
            self, 
            _quicksight_dataset_name,
            data_set_id=_quicksight_dataset_name,
            name=_quicksight_dataset_name,
            aws_account_id=core.Aws.ACCOUNT_ID,
            import_mode="DIRECT_QUERY",
            permissions=[_quicksight.CfnDataSet.ResourcePermissionProperty(
                actions=["quicksight:DescribeDataSet",
                        "quicksight:DescribeDataSetPermissions",
                        "quicksight:PassDataSet",
                        "quicksight:DescribeIngestion",
                        "quicksight:ListIngestions",
                        "quicksight:UpdateDataSet",
                        "quicksight:DeleteDataSet",
                        "quicksight:CreateIngestion",
                        "quicksight:CancelIngestion",
                        "quicksight:UpdateDataSetPermissions"],
                principal=self.quicksight_group_arn
            )],
            physical_table_map={
                "my-table": _quicksight.CfnDataSet.PhysicalTableProperty(
                    relational_table=_quicksight.CfnDataSet.RelationalTableProperty(
                        data_source_arn=datasource.attr_arn,
                        input_columns=[
                            _quicksight.CfnDataSet.InputColumnProperty(name="document.document_name", type="STRING"),
                            _quicksight.CfnDataSet.InputColumnProperty(name="document.document_flag", type="STRING"),
                        ],
                        name="data-12345",
                        # the properties below are optional
                        catalog="AwsDataCatalog",
                        schema="glue-db"
                    )
                )
            })
    
    # CREATE ROLE FOR GRAPH-EXPLORER ADN QUICKSIGHT
    
    def create_federated_userRole(self):
        role_name = 'users-role'

        saml_provider = _iam.SamlProvider.from_saml_provider_arn(self, "saml-provider", self.saml_provider_ARN)
        
        users_role = _iam.Role(
            self, 
            role_name,
            role_name = role_name,
            assumed_by = _iam.AccountPrincipal(self.account),
            description = "Role to be assumed by Federated users (AD)"
        )
        
        #assumed_by = _iam.FederatedPrincipal(self.saml_provider_ARN),

        perm_policy_ge = self.create_graph_db_policy()

        perm_policy_qs = self.create_quicksight_policy()

        users_role.attach_inline_policy(
            perm_policy_ge
        )

        users_role.attach_inline_policy(
            perm_policy_qs
        )

        self.create_s3_upload_policy(users_role)

        return users_role
    
    def create_s3_upload_policy(self, users_role):

        reception_zone_bucket = _s3.Bucket.from_bucket_name(self, f"get{self.bucket_name}", self.bucket_name)

        perm_policy_reception_bucket =_iam.Policy(
            self, 
            "s3landingzone-permPolicy",
            statements = [_iam.PolicyStatement(
                effect = _iam.Effect.ALLOW,
                actions = ["s3:PutObject", "s3:ListBucket", "s3:GetObject"],
                resources = [f"{reception_zone_bucket.bucket_arn}", f"{reception_zone_bucket.bucket_arn}/*"]
            )]
        )
        users_role.attach_inline_policy(
            perm_policy_reception_bucket
        )

        perm_policy_s3_buckets =_iam.Policy(
            self, 
            "s3Buckets-permPolicy",
            statements = [_iam.PolicyStatement(
                effect = _iam.Effect.ALLOW,
                actions = ["s3:ListAllMyBuckets"],
                resources = ["*"]
            )]
        )
        users_role.attach_inline_policy(
            perm_policy_s3_buckets
        )
    
    
    def create_graph_db_policy(self):
        perm_policy =_iam.Policy(
            self, 
            "graph-db-permPolicy",
            statements = [_iam.PolicyStatement(
                effect = _iam.Effect.ALLOW,
                actions = ["neptune-db:Read*","neptune-db:Get*","neptune-db:List*","neptune-db:Describe*","neptune-db:Select*"],
                resources = [f"{self.neptune_cluster_ARN}"]
            )]
        )        
        return perm_policy
    
    def create_quicksight_policy(self):
        perm_policy =_iam.Policy(
            self, 
            "quicksight-permPolicy",
            statements = [_iam.PolicyStatement(
                effect = _iam.Effect.ALLOW,
                actions = ["athena:StartQueryExecution", 
                        "athena:GetQueryResults", 
                        "athena:GetWorkGroup", 
                        "athena:StopQueryExecution", 
                        "athena:GetQueryExecution"],
                resources = [f"{self.athena_workgroups_ARN}", "*"]
            )]
        )        
        return perm_policy