"""
CVE Security Agent
Lookup and analyze security vulnerabilities using Strands SDK + Claude Sonnet on Bedrock
"""
import boto3
import json
import pandas as pd
import os
import re
from datetime import datetime
from strands import Agent, tool

# Configuration
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cve-database")


def load_cve_data():
    """Load CVE data from local JSON files."""
    filepath = os.path.join(DATA_DIR, "cves.json")
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            return json.load(f)
    return []


# Load data at module level
CVE_DATABASE = load_cve_data()


@tool
def lookup_cve(cve_id: str) -> str:
    """Look up a specific CVE by its ID.

    Args:
        cve_id: The CVE identifier (e.g., 'CVE-2024-3094', 'CVE-2021-44228')

    Returns:
        str: JSON with full CVE details or error message
    """
    print(f"[Tool] lookup_cve: {cve_id}")

    # Normalize CVE ID
    cve_id = cve_id.upper().strip()
    if not cve_id.startswith("CVE-"):
        cve_id = f"CVE-{cve_id}"

    for cve in CVE_DATABASE:
        if cve["cve_id"] == cve_id:
            print(f"[Tool] Found: {cve_id} - {cve['severity']}")
            return json.dumps(cve, indent=2)

    return json.dumps({"error": f"CVE {cve_id} not found in database", "suggestion": "Try searching by product or vendor"})


@tool
def search_cves_by_product(product: str) -> str:
    """Search for CVEs affecting a specific product or software.

    Args:
        product: Product name to search for (e.g., 'nginx', 'OpenSSH', 'Log4j')

    Returns:
        str: JSON list of matching CVEs
    """
    print(f"[Tool] search_cves_by_product: {product}")

    product_lower = product.lower()
    matches = []

    for cve in CVE_DATABASE:
        # Check in affected_products
        for prod in cve.get("affected_products", []):
            if product_lower in prod.lower():
                matches.append({
                    "cve_id": cve["cve_id"],
                    "severity": cve["severity"],
                    "cvss_score": cve["cvss_score"],
                    "description": cve["description"][:200] + "...",
                    "affected_product": prod,
                    "patch_available": cve.get("patch_available", False)
                })
                break

        # Also check description
        if not any(m["cve_id"] == cve["cve_id"] for m in matches):
            if product_lower in cve.get("description", "").lower():
                matches.append({
                    "cve_id": cve["cve_id"],
                    "severity": cve["severity"],
                    "cvss_score": cve["cvss_score"],
                    "description": cve["description"][:200] + "...",
                    "patch_available": cve.get("patch_available", False)
                })

    print(f"[Tool] Found {len(matches)} CVEs for '{product}'")

    if matches:
        return json.dumps({"product": product, "cve_count": len(matches), "cves": matches}, indent=2)
    return json.dumps({"product": product, "cve_count": 0, "message": f"No CVEs found for '{product}'"})


@tool
def search_cves_by_severity(severity: str) -> str:
    """Search for CVEs by severity level.

    Args:
        severity: Severity level - 'CRITICAL', 'HIGH', 'MEDIUM', or 'LOW'

    Returns:
        str: JSON list of matching CVEs
    """
    print(f"[Tool] search_cves_by_severity: {severity}")

    severity = severity.upper().strip()
    matches = []

    for cve in CVE_DATABASE:
        if cve.get("severity") == severity:
            matches.append({
                "cve_id": cve["cve_id"],
                "cvss_score": cve["cvss_score"],
                "description": cve["description"][:150] + "...",
                "affected_vendors": cve.get("affected_vendors", []),
                "published_date": cve.get("published_date"),
                "exploit_available": cve.get("exploit_available", False)
            })

    # Sort by CVSS score descending
    matches.sort(key=lambda x: x["cvss_score"], reverse=True)

    print(f"[Tool] Found {len(matches)} {severity} CVEs")
    return json.dumps({"severity": severity, "count": len(matches), "cves": matches}, indent=2)


@tool
def get_cve_stats() -> str:
    """Get statistics about CVEs in the database.

    Returns:
        str: JSON with CVE statistics
    """
    print("[Tool] get_cve_stats")

    df = pd.DataFrame(CVE_DATABASE)

    if df.empty:
        return json.dumps({"error": "No CVE data available"})

    stats = {
        "total_cves": len(df),
        "by_severity": df["severity"].value_counts().to_dict(),
        "avg_cvss_score": float(df["cvss_score"].mean()),
        "max_cvss_score": float(df["cvss_score"].max()),
        "exploits_available": int(df["exploit_available"].sum()),
        "patches_available": int(df["patch_available"].sum()),
        "recent_cves": df.nlargest(5, "published_date")[["cve_id", "severity", "published_date"]].to_dict("records")
    }

    return json.dumps(stats, indent=2)


@tool
def get_remediation(cve_id: str) -> str:
    """Get remediation guidance for a specific CVE.

    Args:
        cve_id: The CVE identifier

    Returns:
        str: JSON with remediation steps and references
    """
    print(f"[Tool] get_remediation: {cve_id}")

    cve_id = cve_id.upper().strip()
    if not cve_id.startswith("CVE-"):
        cve_id = f"CVE-{cve_id}"

    for cve in CVE_DATABASE:
        if cve["cve_id"] == cve_id:
            remediation = {
                "cve_id": cve_id,
                "severity": cve["severity"],
                "remediation": cve.get("remediation", "No specific remediation available"),
                "patch_available": cve.get("patch_available", False),
                "affected_products": cve.get("affected_products", []),
                "references": cve.get("references", []),
                "cwe_id": cve.get("cwe_id"),
                "cwe_name": cve.get("cwe_name")
            }
            return json.dumps(remediation, indent=2)

    return json.dumps({"error": f"CVE {cve_id} not found"})


@tool
def check_software_vulnerabilities(software_list: str) -> str:
    """Check a list of software/versions for known vulnerabilities.

    Args:
        software_list: Comma-separated list of software to check (e.g., 'nginx, OpenSSH 9.0, PHP 8.2')

    Returns:
        str: JSON report of vulnerabilities found
    """
    print(f"[Tool] check_software_vulnerabilities: {software_list}")

    software_items = [s.strip() for s in software_list.split(",")]
    results = []

    for software in software_items:
        software_lower = software.lower()
        found_cves = []

        for cve in CVE_DATABASE:
            for prod in cve.get("affected_products", []):
                if software_lower in prod.lower():
                    found_cves.append({
                        "cve_id": cve["cve_id"],
                        "severity": cve["severity"],
                        "cvss_score": cve["cvss_score"],
                        "patch_available": cve.get("patch_available", False)
                    })
                    break

        results.append({
            "software": software,
            "vulnerable": len(found_cves) > 0,
            "cve_count": len(found_cves),
            "cves": found_cves
        })

    vulnerable_count = sum(1 for r in results if r["vulnerable"])

    return json.dumps({
        "software_checked": len(results),
        "vulnerable_software": vulnerable_count,
        "results": results
    }, indent=2)


def create_cve_agent():
    """Create the CVE security agent using Claude Sonnet on Bedrock."""

    system_prompt = """You are a Security Vulnerability Analyst assistant.

Your role is to help security professionals and developers understand and respond to CVEs (Common Vulnerabilities and Exposures).

AVAILABLE TOOLS:
- lookup_cve: Get full details on a specific CVE by ID
- search_cves_by_product: Find CVEs affecting a specific software/product
- search_cves_by_severity: List CVEs by severity (CRITICAL, HIGH, MEDIUM, LOW)
- get_cve_stats: Get overview statistics of the CVE database
- get_remediation: Get fix/patch guidance for a specific CVE
- check_software_vulnerabilities: Check multiple software items for known vulnerabilities

RESPONSE STYLE:
- Be clear and actionable - security teams need to act fast
- Always highlight severity and whether exploits are available
- Prioritize remediation guidance
- Use bullet points for clarity
- Include CVE IDs so they can be tracked

SEVERITY LEVELS:
- CRITICAL (9.0-10.0): Immediate action required, likely actively exploited
- HIGH (7.0-8.9): High priority, should be patched soon
- MEDIUM (4.0-6.9): Plan to patch in regular maintenance
- LOW (0.1-3.9): Low risk, patch when convenient

When discussing vulnerabilities, always mention:
1. What is affected
2. How severe it is (CVSS score)
3. Whether there's a known exploit
4. How to fix it

Never downplay security risks. If something is critical, emphasize urgency."""

    return Agent(
        model="us.anthropic.claude-sonnet-4-20250514-v1:0",
        tools=[
            lookup_cve,
            search_cves_by_product,
            search_cves_by_severity,
            get_cve_stats,
            get_remediation,
            check_software_vulnerabilities
        ],
        system_prompt=system_prompt
    )


# Create agent instance
cve_agent = create_cve_agent()


def run_cve_agent(prompt: str) -> str:
    """Run the CVE agent with a given prompt."""
    try:
        response = cve_agent(prompt)
        return str(response)
    except Exception as e:
        return f"Error running agent: {str(e)}"


if __name__ == "__main__":
    print("Testing CVE Security Agent...")
    print("-" * 50)

    test_prompt = "What can you tell me about the Log4Shell vulnerability?"

    print(f"Prompt: {test_prompt}\n")
    response = run_cve_agent(test_prompt)
    print(f"\nAgent Response:\n{response}")
