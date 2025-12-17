#!/bin/bash
# Deploy app to EC2 instance
# Usage: ./scripts/deploy-to-ec2.sh [--start]

set -e

EC2_IP="34.202.219.55"
SSH_KEY="~/.ssh/streamlit-key.pem"
REMOTE_DIR="/opt/strands-agent-app"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Files/dirs to exclude from sync (infra/ is CDK, not needed on server)
EXCLUDES="--exclude='.git' --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' --exclude='node_modules' --exclude='infra' --exclude='.DS_Store'"

echo "Deploying to $EC2_IP..."

# Sync app code
rsync -avz --delete \
  $EXCLUDES \
  -e "ssh -i $SSH_KEY -o StrictHostKeyChecking=no" \
  "$LOCAL_DIR/" \
  "ec2-user@$EC2_IP:$REMOTE_DIR/"

echo "Installing dependencies..."
ssh -i $SSH_KEY ec2-user@$EC2_IP << 'EOF'
cd /opt/strands-agent-app
python3.11 -m pip install -r requirements.txt --quiet
EOF

# Start services if --start flag provided
if [[ "$1" == "--start" ]]; then
  echo "Starting services..."
  ssh -i $SSH_KEY ec2-user@$EC2_IP << 'EOF'
sudo systemctl restart mcp-server || sudo systemctl start mcp-server
sudo systemctl restart streamlit || sudo systemctl start streamlit
sudo systemctl status mcp-server --no-pager
sudo systemctl status streamlit --no-pager
EOF
fi

echo ""
echo "Deploy complete!"
echo "  MCP Server: http://$EC2_IP:8080"
echo "  Streamlit:  http://$EC2_IP:8501"
echo ""
echo "To start services: ./scripts/deploy-to-ec2.sh --start"
echo "To SSH: ssh -i $SSH_KEY ec2-user@$EC2_IP"
