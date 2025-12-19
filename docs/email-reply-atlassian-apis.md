# Reply to Adam - Atlassian APIs for Onboarding/Offboarding

**To:** Adam Fairbanks, DevOps  
**Subject:** Re: Atlassian APIs for onboarding/offboarding

---

Adam,

Great timing - we've already implemented this!

**What we built:**

The MrRobot AI MCP server now has 12 Atlassian Admin v2 API tools for user/group management:

| Tool | Description |
|------|-------------|
| `atlassian_list_users` | List all users in the directory |
| `atlassian_search_user` | Find user by email/name |
| `atlassian_suspend_user` | Suspend user access (offboarding) |
| `atlassian_restore_user` | Restore suspended user |
| `atlassian_remove_user` | Completely remove user |
| `atlassian_list_groups` | List all groups |
| `atlassian_create_group` | Create new group |
| `atlassian_delete_group` | Delete group |
| `atlassian_add_user_to_group` | Add user to group (onboarding) |
| `atlassian_remove_user_from_group` | Remove from group (offboarding) |
| `atlassian_grant_group_access` | Grant product access to group |
| `atlassian_revoke_group_access` | Revoke product access |

**How it works:**

1. **Cursor/Claude access**: Developers can query Atlassian directly via MCP tools
2. **DevOps Agent**: Orchestrates onboarding/offboarding workflows
3. **SCIM integration**: Still used for IdP sync - our tools handle manual overrides and complex workflows

**Example workflow:**
```
User: "Offboard john@nex.io"
Agent: 
  1. Searches for user → gets account_id
  2. Suspends user access
  3. Removes from all groups
  4. Logs the action for audit
```

**Next steps:**
- [ ] Add Azure AD integration (sync with SCIM)
- [ ] Add Bitbucket user management
- [ ] Add audit logging/tracing

The MCP server is live at `https://mcp.mrrobot.dev/sse` (VPN required).

Happy to demo or walk through the implementation.

Grant

---

**Attachments:**
- MCP Server code: `mcp-servers/tools/atlassian.py`
- DevOps Agent: `agents/devops_agent.py`

