#!/bin/bash
# Deployment script for Strands Agent App

set -e

echo "=========================================="
echo "Strands Agent App Deployment"
echo "=========================================="

# Check AWS credentials
echo "Checking AWS credentials..."
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "ERROR: AWS credentials not configured"
    echo "Run: aws configure"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_DEFAULT_REGION:-us-west-2}
echo "Account: $ACCOUNT_ID"
echo "Region: $REGION"

# Create EC2 key pair if it doesn't exist
KEY_NAME="streamlit-key"
echo ""
echo "Checking EC2 key pair..."
if ! aws ec2 describe-key-pairs --key-names $KEY_NAME --region $REGION > /dev/null 2>&1; then
    echo "Creating key pair: $KEY_NAME"
    aws ec2 create-key-pair \
        --key-name $KEY_NAME \
        --query 'KeyMaterial' \
        --output text \
        --region $REGION > ~/.ssh/$KEY_NAME.pem
    chmod 400 ~/.ssh/$KEY_NAME.pem
    echo "Key saved to: ~/.ssh/$KEY_NAME.pem"
else
    echo "Key pair already exists: $KEY_NAME"
fi

# Bootstrap CDK if needed
echo ""
echo "Bootstrapping CDK..."
cd "$(dirname "$0")/../infra"
npm install

if ! aws cloudformation describe-stacks --stack-name CDKToolkit --region $REGION > /dev/null 2>&1; then
    echo "Running CDK bootstrap..."
    npx cdk bootstrap aws://$ACCOUNT_ID/$REGION
else
    echo "CDK already bootstrapped"
fi

# Deploy the stack
echo ""
echo "Deploying CDK stack..."
npx cdk deploy --require-approval never

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Copy your app code to the EC2 instance:"
echo "   scp -i ~/.ssh/$KEY_NAME.pem -r ../app.py ../agent.py ../data ec2-user@<EC2_PUBLIC_IP>:/opt/strands-agent-app/"
echo ""
echo "2. SSH into the instance and start the service:"
echo "   ssh -i ~/.ssh/$KEY_NAME.pem ec2-user@<EC2_PUBLIC_IP>"
echo "   sudo systemctl start streamlit"
echo ""
echo "3. Access your app via the CloudFront URL shown above"
