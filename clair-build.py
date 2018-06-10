# Troposphere to create CloudFormation template to build the Clair image
# By Jason Umiker (jason.umiker@gmail.com)

from troposphere import Output, Join, Ref, Template
from troposphere import AWS_ACCOUNT_ID, AWS_REGION
from troposphere import ecr, s3, iam, codebuild

t = Template()

t.add_description("Template to set up a CodeBuild for the Clair container")

# Create the clair Repository
Repository = t.add_resource(
    ecr.Repository(
        "Repository",
        RepositoryName="clair"
    )
)

# Create the S3 Bucket for Output
S3Bucket = t.add_resource(
    s3.Bucket(
        "ClairBuildOutput"
    )
)

# CodeBuild Service Role
ServiceRole = t.add_resource(iam.Role(
    "InstanceRole",
    AssumeRolePolicyDocument={
        "Statement": [
            {
                'Effect': 'Allow',
                'Principal': {'Service': 'codebuild.amazonaws.com'},
                "Action": "sts:AssumeRole"
            }
        ]
    }
))

# CodeBuild Service Policy
CodeBuildServiceRolePolicy = t.add_resource(iam.PolicyType(
    "CodeBuildServiceRolePolicy",
    PolicyName="CodeBuildServiceRolePolicy",
    PolicyDocument={"Version": "2012-10-17",
                    "Statement": [
                        {
                            "Sid": "CloudWatchLogsPolicy",
                            "Effect": "Allow",
                            "Action": [
                                "logs:CreateLogGroup",
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            "Resource": [
                                "*"
                            ]
                        },
                        {
                            "Sid": "CodeCommitPolicy",
                            "Effect": "Allow",
                            "Action": [
                                "codecommit:GitPull"
                            ],
                            "Resource": [
                                "*"
                            ]
                        },
                        {
                            "Sid": "S3GetObjectPolicy",
                            "Effect": "Allow",
                            "Action": [
                                "s3:GetObject",
                                "s3:GetObjectVersion"
                            ],
                            "Resource": [
                                "*"
                            ]
                        },
                        {
                            "Sid": "S3PutObjectPolicy",
                            "Effect": "Allow",
                            "Action": [
                                "s3:PutObject"
                            ],
                            "Resource": [
                                "*"
                            ]
                        },
                        {'Action': ['ecr:GetAuthorizationToken'],
                         'Resource': ['*'],
                         'Effect': 'Allow'},
                        {'Action': ['ecr:*'],
                         'Resource': [
                             Join("", ["arn:aws:ecr:",
                                       Ref(AWS_REGION),
                                       ":", Ref(AWS_ACCOUNT_ID),
                                       ":repository/",
                                       Ref(Repository)]
                                  ),
                         ],
                         'Effect': 'Allow'},
                    ]},
    Roles=[Ref(ServiceRole)],
))

# Create CodeBuild Projects
# Image Build
ImageArtifacts = codebuild.Artifacts(
    Type='S3',
    Name='artifacts',
    Location=Ref(S3Bucket)
)

ImageEnvironment = codebuild.Environment(
    ComputeType="BUILD_GENERAL1_SMALL",
    Image="aws/codebuild/docker:17.09.0",
    Type="LINUX_CONTAINER",
    EnvironmentVariables=[{'Name': 'AWS_ACCOUNT_ID', 'Value': Ref(AWS_ACCOUNT_ID)},
                          {'Name': 'IMAGE_REPO_NAME', 'Value': Ref(Repository)},
                          {'Name': 'IMAGE_TAG', 'Value': 'latest'}],
    PrivilegedMode=True
)

ImageSource = codebuild.Source(
    Location="https://github.com/jasonumiker/clair-ecs-fargate",
    Type="GITHUB"
)

ImageProject = codebuild.Project(
    "ImageBuildProject",
    Artifacts=ImageArtifacts,
    Environment=ImageEnvironment,
    Name="clair-build",
    ServiceRole=Ref(ServiceRole),
    Source=ImageSource,
    DependsOn=CodeBuildServiceRolePolicy
)
t.add_resource(ImageProject)

# Output clair repository URL
t.add_output(Output(
    "RepositoryURL",
    Description="The docker repository URL",
    Value=Join("", [
        Ref(AWS_ACCOUNT_ID),
        ".dkr.ecr.",
        Ref(AWS_REGION),
        ".amazonaws.com/",
        Ref(Repository)
    ]),
))

print(t.to_json())
