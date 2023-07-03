from aws_cdk import (
    Stack,
    aws_iam as _iam,
    aws_lambda as _lambda,
    aws_s3 as _s3,
    aws_s3_notifications as _s3n,
    aws_glue_alpha as _glue_alpha,
    aws_glue as _glue
)

import aws_cdk as core

from repository.util import util as _util

from constructs import Construct

class ComformedZoneStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        #################### INITIALIZER ####################
        self.properties = self.node.try_get_context("properties").get("properties")
        self.parquet_data_path = self.properties.get("parquet_data_path")
        self.catalog_name = self.properties.get("catalog_name")
        env_prefix = self.node.try_get_context("properties").get("env_prefix")
        self.component_prefix = f"project-{env_prefix}"

        #CREATE COMFORMED ZONE BUCKET
        _conformed_zone_bucket_name = f"{self.component_prefix}-s3-conformedzone"
        self.conformed_zone_bucket = _s3.Bucket(
            self, 
            _conformed_zone_bucket_name,
            encryption=_s3.BucketEncryption.KMS_MANAGED,
            bucket_name=_conformed_zone_bucket_name,
            enforce_ssl=True
        )
        
        _glue_db_name = f"{self.component_prefix}-glue-db"
        glue_db = self.create_db(
            _glue_db_name
        )

        self.db_name = glue_db.database_name

        #GLUE CRAWLER SETUP
        glue_role = self.setup_glue_role()

        self.create_table(glue_db, self.conformed_zone_bucket)

        #################### INITIALIZER (END) ####################

    '''
    SETUP ROLE FOR GLUE TO CRAWL THROUGH S3
    '''
    def setup_glue_role(self):
        _glue_role_name = f"{self.component_prefix}-glue-role"
        glue_role = _iam.Role(
            self,
            _glue_role_name,
            role_name=_glue_role_name,
            assumed_by=_iam.ServicePrincipal('glue.amazonaws.com'),
            managed_policies=[_iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSGlueServiceRole')]
        )

        glue_role.attach_inline_policy(_iam.Policy(
            self, 
            f"{_glue_role_name}-policy",
            statements=[_iam.PolicyStatement(
                actions=["s3:GetObject","s3:PutObject"],
                resources=[f"{self.conformed_zone_bucket.bucket_arn}{self.parquet_data_path}*"]
            )]
        ))
        
        return glue_role

    def create_crawler(self, glue_db, role_arn):
        _glue_crawler_name = f"{self.component_prefix}-glue-crawler"
        cfn_crawler = _glue.CfnCrawler(
            self, 
            _glue_crawler_name,
            role=role_arn,
            targets=_glue.CfnCrawler.TargetsProperty(
                s3_targets=[_glue.CfnCrawler.S3TargetProperty(
                    path=f"s3://{self.conformed_zone_bucket.bucket_name}{self.parquet_data_path}"
                )]
            ),
            database_name=glue_db,
            name=_glue_crawler_name,
            table_prefix="tables-",
            schema_change_policy=_glue.CfnCrawler.SchemaChangePolicyProperty(
                delete_behavior="DEPRECATE_IN_DATABASE",
                update_behavior="UPDATE_IN_DATABASE"
            )
        )

        return cfn_crawler
    
    def create_db(self, _database_name):
        db = _glue_alpha.Database(
            self, 
            _database_name,
            database_name=_database_name
        )
        return db
    
    def create_table(self, db, bucket):
        _glue_table = "glue_table"  
        table = _glue_alpha.Table(
            self,
            id=_glue_table,
            database=db,
            table_name=_glue_table,
            columns=[
                _glue_alpha.Column(
                    name='document.document_name',
                    type=_glue_alpha.Type(
                        input_string='string',
                        is_primitive=True
                    )
                ),
                _glue_alpha.Column(
                    name='document.document_flag',
                    type=_glue_alpha.Type(
                        input_string='string',
                        is_primitive=True
                    )
                ),
            ],
            bucket=bucket,
            s3_prefix=self.parquet_data_path,
            data_format=_glue_alpha.DataFormat.PARQUET
        )
