# Clair running on AWS ECS Fargate
The Clair image scanner service from CoreOS (https://github.com/coreos/clair) can be used to scan a particular Docker image for known vulnerabilities as part of your build or deployment pipeline. This project is to package and deploy the scanner in a way that can run on AWS ECS via Fargate.

I use it in conjunction with a commandline tool called Klar (https://github.com/optiopay/klar) which I invoke as the last step of a CodeBuild to ask Clair to scan the new image once it has been pushed to the Elastic Container Registry (ECR). An example of how to do that is here - https://github.com/jasonumiker/ghost-ecs-fargate-pipeline/blob/master/ghost-container/buildspec.yml

## Example of using klar to invoke clair on an image in ECR in your CodeBuild
    wget https://github.com/optiopay/klar/releases/download/v2.3.0/klar-2.3.0-linux-amd64
    chmod +x ./klar-2.3.0-linux-amd64
    mv ./klar-2.3.0-linux-amd64 ./klar
    DOCKER_LOGIN=`aws ecr get-login --region $AWS_DEFAULT_REGION`
    PASSWORD=`echo $DOCKER_LOGIN | cut -d' ' -f6`
    DOCKER_USER=AWS DOCKER_PASSWORD=${PASSWORD} CLAIR_ADDR=$CLAIR_URL ./klar $IMAGE_URI

## Why do we need to build our own image?
One minor change was required to the upstream CoreOS Clair (https://github.com/coreos/clair) Docker image to get it to run in Fargate. Clair doesn't take options like the configuration of its database via environment variables but from a config file - and there is not a capability currently to mount that into the container at runtime in ECS Fargate. 
As such, we rebuild the Clair image to incorporate the config file in the image as well as convert the DB host and password environment variable to values in that file at runtime.

If you don't want to build this yourself it is available at `jasonumiker/clair:latest` on hub.docker.com.

## Prerequisites
A Fargate task requires a VPC ID and at least one subnet ID to deploy to. Ideally these will be private subnet(s) as there is not any login/password/token on the use of Clair as configured.

I suggest using the Quick Start for creating this VPC if you don't already have one - https://aws.amazon.com/quickstart/architecture/vpc/ 

## Deployment Instructions
The CloudFormation template `clair-deploy-fargate.template` deploys the Clair service including creating the:
1. Task and task execution IAM Roles
1. PostgreSQL RDS database
1. Application Load Balancer (ALB)
1. Security Groups set up to limit access so that:
    1. Only the tasks can talk to the database
    1. Only the ALB can talk to the tasks
1. The ECS task definition and associated service set up to run on Clair on Fargate

The parameters it requires are:
1. The name of the ECS cluster to deploy to
1. The clair docker image to deploy
    1. If you don't want to build this yourself you can use `jasonumiker/clair:latest` from the Docker Hub
1. The VPC ID and two subnet IDs to run the tasks, ALB and RDS database in
    1. Ideally these should be private subnets which will prevent any access to the service from the Internet
1. The database password to use
    1. This will be set as the master password on the RDS and set as the DB_PASSWORD environment variable for the task in plaintext
        1. This is a not fully secure approach however this RDS is dedicated just to Clair, the security group for the database only allows network connections from the Clair tasks and there is no sensitive information stored in this database. I'll investigate storing this in Secrets Manager a future release though.

## Building the Container
If you'd prefer to build and host the container yourself rather than use `jasonumiker/clair:latest` on Docker Hub there is an included `buildspec.yml` CodeBuild build spec and `clair-build.template` CloudFormation template. These are what I use to build the image on the Docker Hub.

The CloudFormation stack will create an ECR repository as well as S3 bucket for storing the results as well as all necessary IAM roles.
