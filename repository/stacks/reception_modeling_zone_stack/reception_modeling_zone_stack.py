from aws_cdk import (
    Stack,
    aws_iam as _iam,
    aws_lambda as _lambda,
    aws_s3 as _s3,
    aws_s3_notifications as _s3n,
    aws_kms as _kms,
    aws_s3_deployment as _aws_s3_deployment
)

import os

from constructs import Construct
from repository.util import util as _util

class ReceptionAndModelingZoneStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        #################### INITIALIZER ####################
        self.properties = self.node.try_get_context("properties").get("properties")

        self.functions_path = os.path.join(os.path.dirname(__file__), self.properties.get("functions_path"))
        self.reception_bucket_structure_path = os.path.join(os.path.dirname(__file__), "reception_bucket_folder_structure")
        
        self.input_data_path = str(self.properties.get("input_data_path"))
        self.raw_data_path = str(self.properties.get("raw_data_path"))
        self.processed_data_path = str(self.properties.get("processed_data_path"))

        self.dev_role_ARN = self.properties.get("dev_role")
        self.saml_provider_ARN = self.properties.get("saml_provider_ARN")
        env_prefix = self.node.try_get_context("properties").get("env_prefix")
        self.component_prefix = f"project-{env_prefix}"

        #CREATE CHECKIN AND MODELING FUNCTIONS
        self.lambda_checkin_function = _util.define_lambda_function(self, "lambda_checkin_function", self.functions_path)
        self.lambda_modeling_function = _util.define_lambda_function(self, "lambda_modeling_function", self.functions_path)
        
        #CREATE OCR FUNCTIONS
        self.lambda_ocr_form4e = _util.define_lambda_function_with_role(self, "lambda_ocr_form4e", self.functions_path, self.create_lambda_ocr_role("lambda_ocr_form4e"))
        self.lambda_ocr_ebcd = _util.define_lambda_function_with_role(self, "lambda_ocr_ebcd", self.functions_path, self.create_lambda_ocr_role("lambda_ocr_ebcd"))
        self.lambda_ocr_itd = _util.define_lambda_function_with_role(self, "lambda_ocr_itd", self.functions_path, self.create_lambda_ocr_role("lambda_ocr_itd"))

        #CREATE LANDINGZONE BUCKET (secured by KMS with key rotation)
        self._reception_zone_bucket_name = f"{self.component_prefix}-s3-receptionzone"
        self.landing_zone_bucket = _s3.Bucket(
            self, 
            self._reception_zone_bucket_name,
            bucket_name=self._reception_zone_bucket_name,
            encryption=_s3.BucketEncryption.KMS_MANAGED,
            enforce_ssl=True
        )
        
        #CREATING THE BASE FOLDER STRUCTURE
        _aws_s3_deployment.BucketDeployment(
            self, 
            "DeployBaseFileStructure",
            sources=[_aws_s3_deployment.Source.asset(self.reception_bucket_structure_path)],
            destination_bucket=self.landing_zone_bucket
        )
        
        #GRANT READ ACCESS SO THE RECEPTION FUNCTION CAN READ AND WRITE ON THE BUCKET
        self.landing_zone_bucket.grant_read(
            self.lambda_checkin_function, 
            objects_key_pattern=self.input_data_path
        )

        self.landing_zone_bucket.grant_write(
            self.lambda_checkin_function, 
            objects_key_pattern=self.raw_data_path
        )

        #GRANT READ AND WRITE ACCESS SO THE OCR FORM4E FUNCTION CAN READ AND WRITE ON THE BUCKET        
        self.landing_zone_bucket.grant_read(
            self.lambda_ocr_form4e, 
            objects_key_pattern=f"{self.raw_data_path}/2022/form4e/*"
        )
        
        self.landing_zone_bucket.grant_write(
            self.lambda_ocr_form4e, 
            objects_key_pattern=f"{self.processed_data_path}/2022/form4e/*"
        )
       
        self.landing_zone_bucket.grant_read(
            self.lambda_ocr_form4e, 
            objects_key_pattern=f"{self.raw_data_path}/2023/form4e/*"
        )
        
        self.landing_zone_bucket.grant_write(
            self.lambda_ocr_form4e, 
            objects_key_pattern=f"{self.processed_data_path}/2023/form4e/*"
        )
        
        #GRANT READ AND WRITE ACCESS SO THE OCR EBCD FUNCTION CAN READ AND WRITE ON THE BUCKET        
        self.landing_zone_bucket.grant_read(
            self.lambda_ocr_ebcd, 
            objects_key_pattern=f"{self.raw_data_path}/2022/ebcd/*"
        )
        
        self.landing_zone_bucket.grant_write(
            self.lambda_ocr_ebcd, 
            objects_key_pattern=f"{self.processed_data_path}/2022/ebcd/*"
        )
   
        self.landing_zone_bucket.grant_read(
            self.lambda_ocr_ebcd, 
            objects_key_pattern=f"{self.raw_data_path}/2023/ebcd/*"
        )
        
        self.landing_zone_bucket.grant_write(
            self.lambda_ocr_ebcd, 
            objects_key_pattern=f"{self.processed_data_path}/2023/ebcd/*"
        )

        #GRANT READ AND WRITE ACCESS SO THE OCR ITD FUNCTION CAN READ AND WRITE ON THE BUCKET        
        self.landing_zone_bucket.grant_read(
            self.lambda_ocr_itd, 
            objects_key_pattern=f"{self.raw_data_path}/2022/itd/*"
        )
        
        self.landing_zone_bucket.grant_write(
            self.lambda_ocr_itd, 
            objects_key_pattern=f"{self.processed_data_path}/2022/itd/*"
        )
   
        self.landing_zone_bucket.grant_read(
            self.lambda_ocr_itd, 
            objects_key_pattern=f"{self.raw_data_path}/2023/itd/*"
        )
        
        self.landing_zone_bucket.grant_write(
            self.lambda_ocr_itd, 
            objects_key_pattern=f"{self.processed_data_path}/2023/itd/*"
        )

        #ADD THE EVENT NOTIFICATION SO THE OCR FUNCTION GETS TRIGGERED ONCE A NEW FILE IS UPLOADED TO THE BUCKET
        self.landing_zone_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED, 
            _s3n.LambdaDestination(self.lambda_checkin_function),
            _s3.NotificationKeyFilter(
                prefix=self.input_data_path
            )
        )

        #ADD THE EVENT NOTIFICATION SO THE OCR FORM4E FUNCTION GETS TRIGGERED ONCE A NEW FILE IS UPLOADED TO THE BUCKET
        self.landing_zone_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED, 
            _s3n.LambdaDestination(self.lambda_ocr_form4e),
            _s3.NotificationKeyFilter(
                prefix=f"{self.raw_data_path}/2022/form4e/"
            )
        )

        self.landing_zone_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED, 
            _s3n.LambdaDestination(self.lambda_ocr_form4e),
            _s3.NotificationKeyFilter(
                prefix=f"{self.raw_data_path}/2023/form4e/"
            )
        )

        #ADD THE EVENT NOTIFICATION SO THE OCR EBCD FUNCTION GETS TRIGGERED ONCE A NEW FILE IS UPLOADED TO THE BUCKET
        self.landing_zone_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED, 
            _s3n.LambdaDestination(self.lambda_ocr_ebcd),
            _s3.NotificationKeyFilter(
                prefix=f"{self.raw_data_path}/2022/ebcd/"
            )
        )

        self.landing_zone_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED, 
            _s3n.LambdaDestination(self.lambda_ocr_ebcd),
            _s3.NotificationKeyFilter(
                prefix=f"{self.raw_data_path}/2023/ebcd/"
            )
        )

        #ADD THE EVENT NOTIFICATION SO THE OCR EBCD FUNCTION GETS TRIGGERED ONCE A NEW FILE IS UPLOADED TO THE BUCKET
        self.landing_zone_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED, 
            _s3n.LambdaDestination(self.lambda_ocr_itd),
            _s3.NotificationKeyFilter(
                prefix=f"{self.raw_data_path}/2022/itd/"
            )
        )

        self.landing_zone_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED, 
            _s3n.LambdaDestination(self.lambda_ocr_itd),
            _s3.NotificationKeyFilter(
                prefix=f"{self.raw_data_path}/2023/itd/"
            )
        )

        #ADD THE EVENT NOTIFICATION SO THE MODELING FUNCTION GETS TRIGGERED ONCE A NEW FILE IS UPLOADED TO THE BUCKET
        self.landing_zone_bucket.add_event_notification(
            _s3.EventType.OBJECT_CREATED, 
            _s3n.LambdaDestination(self.lambda_modeling_function),
            _s3.NotificationKeyFilter(
                prefix=self.processed_data_path
            )
        )

        #################### INITIALIZER [END] ####################

    def create_lambda_ocr_role(self, func_name):
        role_name = f"{self.component_prefix}-lambda-ocrrole-{func_name}"

        return _iam.Role(scope=self, id=role_name,
            assumed_by =_iam.ServicePrincipal('lambda.amazonaws.com'),
            role_name=role_name,
            managed_policies=[
            _iam.ManagedPolicy.from_aws_managed_policy_name('AmazonS3ReadOnlyAccess'),
            _iam.ManagedPolicy.from_aws_managed_policy_name('service-role/AWSLambdaBasicExecutionRole'),
            _iam.ManagedPolicy.from_aws_managed_policy_name('AmazonTextractFullAccess')
        ])
