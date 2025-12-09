#!/bin/bash
# Copy app files to EC2 instance

set -e

if [ -z "$1" ]; then
    echo "Usage: ./copy-to-ec2.sh <EC2_PUBLIC_IP>"
    exit 1
fi

EC2_IP=$1
KEY_PATH="${2:-~/.ssh/streamlit-key.pem}"

echo "Copying files to EC2 instance: $EC2_IP"

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"

# Copy app files
scp -i "$KEY_PATH" -r \
    "$APP_DIR/app.py" \
    "$APP_DIR/agent.py" \
    "$APP_DIR/requirements.txt" \
    "$APP_DIR/data" \
    "ec2-user@$EC2_IP:/opt/strands-agent-app/"

echo ""
echo "Files copied successfully!"
echo ""
echo "Now SSH into the instance and start the service:"
echo "  ssh -i $KEY_PATH ec2-user@$EC2_IP"
echo "  sudo systemctl start streamlit"
echo "  sudo systemctl status streamlit"
