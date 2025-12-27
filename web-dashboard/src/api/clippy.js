/**
 * Clippy API client for the alerts dashboard.
 * Communicates with the MCP server backend.
 */

// In production (when served from /dashboard), use relative path to same server
// In development, proxy is configured in vite.config.js
const API_BASE = import.meta.env.VITE_API_URL || '';

/**
 * Fetch active PagerDuty incidents.
 */
export async function getActiveIncidents() {
  const response = await fetch(`${API_BASE}/api/alerts/active`);
  if (!response.ok) {
    throw new Error(`Failed to fetch incidents: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Fetch recent incidents (last N days).
 */
export async function getRecentIncidents(days = 7) {
  const response = await fetch(`${API_BASE}/api/alerts/recent?days=${days}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch recent incidents: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get AI analysis and code fix suggestions for an incident.
 */
export async function analyzeIncident(incidentId) {
  const response = await fetch(`${API_BASE}/api/alerts/${incidentId}/analyze`, {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error(`Failed to analyze incident: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get detailed incident info with logs and related code.
 */
export async function getIncidentDetails(incidentId) {
  const response = await fetch(`${API_BASE}/api/alerts/${incidentId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch incident details: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Search code in the knowledge base for a query.
 */
export async function searchCode(query) {
  const response = await fetch(`${API_BASE}/api/code/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });
  if (!response.ok) {
    throw new Error(`Failed to search code: ${response.statusText}`);
  }
  return response.json();
}

/**
 * Get error summary across services.
 */
export async function getErrorSummary(hours = 4) {
  const response = await fetch(`${API_BASE}/api/errors/summary?hours=${hours}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch error summary: ${response.statusText}`);
  }
  return response.json();
}
