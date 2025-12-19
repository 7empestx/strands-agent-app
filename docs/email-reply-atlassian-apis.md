# Reply to Adam - Atlassian APIs for Onboarding/Offboarding

## Email to Send:

---

Hi Adam,

The MCP server should have tools available to onboard and offboard employees that use API calls to Atlassian, Azure AD, etc. Anything required for onboarding or offboarding I am missing here?

Then we just use the DevOps agent to use the MCP server to onboard/offboard with a prompt like:
"Onboard/Offboard this person with First Name, Last Name, suggested email, etc."

Grant

---

## Current Implementation Status:

### ✅ Implemented (Atlassian):
- 12 Atlassian Admin v2 API tools in MCP server
- User management: list, suspend, restore, remove
- Group management: list, create, delete, add/remove users, grant/revoke access

### ❌ Still Needed for Complete Onboarding/Offboarding:

| System | Priority | What's Needed |
|--------|----------|---------------|
| **Azure AD** | HIGH | Create/disable user, assign licenses, group membership |
| **Bitbucket** | MEDIUM | Add/remove from workspace, repository permissions |
| **Slack** | MEDIUM | Invite to workspace, add to channels, deactivate |
| **AWS IAM** | LOW | Console access, group membership (if applicable) |
| **Google Workspace** | LOW | If we use it for email |

### Example Complete Onboarding Flow:
```
User: "Onboard John Doe (john.doe@nex.io) as a Developer on the Payments team"

DevOps Agent:
  1. Azure AD: Create user account, assign E3 license
  2. Atlassian: Add to 'developers' and 'payments-team' groups
  3. Bitbucket: Add to 'mrrobot-labs' workspace with developer access
  4. Slack: Invite to workspace, add to #payments, #engineering channels
  5. Log all actions for audit trail
```

### Next Steps:
1. Add Azure AD tools to MCP server (Microsoft Graph API)
2. Add Bitbucket workspace membership tools (we have read-only now)
3. Add Slack admin tools (Slack Admin API)
4. Create unified onboard_employee / offboard_employee orchestration tools

