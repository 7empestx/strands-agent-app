/**
 * MrRobot Office/VPN IP addresses for security group rules.
 * Source: tf-module-read-only/modules/read_only/main.tf
 *
 * Usage:
 *   const { OFFICE_IPS, addOfficeIngressRules } = require('./constants/office-ips');
 *
 *   // Option 1: Use the helper function
 *   addOfficeIngressRules(securityGroup, ec2.Port.tcp(8080), 'MCP server');
 *
 *   // Option 2: Use the IPs directly
 *   OFFICE_IPS.forEach(ip => {
 *     securityGroup.addIngressRule(ec2.Peer.ipv4(ip.cidr), port, ip.description);
 *   });
 */

const OFFICE_IPS = [
  {
    cidr: '205.197.212.250/32',
    description: 'CMS Office (CentraCom)',
  },
  {
    cidr: '198.91.53.66/32',
    description: 'Sumo Fiber ISP (Failover)',
  },
];

// IPv6 ranges (for future use)
const OFFICE_IP6S = [
  {
    cidr: '2604:f580:0:100::/63',
    description: 'Sumo Fiber ISP - VPN NAT + LAN range',
  },
];

/**
 * Helper function to add ingress rules for all office IPs to a security group.
 *
 * @param {ec2.SecurityGroup} securityGroup - The security group to add rules to
 * @param {ec2.Port} port - The port to allow (e.g., ec2.Port.tcp(8080))
 * @param {string} serviceName - Name of the service for rule descriptions
 * @param {object} ec2 - The aws-cdk-lib/aws-ec2 module
 */
function addOfficeIngressRules(securityGroup, port, serviceName, ec2) {
  OFFICE_IPS.forEach(ip => {
    securityGroup.addIngressRule(
      ec2.Peer.ipv4(ip.cidr),
      port,
      `${serviceName} - ${ip.description}`
    );
  });
}

/**
 * Get all office CIDRs as a simple array of strings.
 * Useful for WAF rules, ALB security groups, etc.
 *
 * @returns {string[]} Array of CIDR strings
 */
function getOfficeCidrs() {
  return OFFICE_IPS.map(ip => ip.cidr);
}

module.exports = {
  OFFICE_IPS,
  OFFICE_IP6S,
  addOfficeIngressRules,
  getOfficeCidrs,
};
