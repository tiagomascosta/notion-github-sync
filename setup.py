#!/usr/bin/env python3
"""
Setup script to help users configure the Notion-GitHub sync application
"""
import os
import sys

def create_env_file():
    """Interactive setup to create .env file"""
    print("Notion-GitHub Sync Setup")
    print("=" * 40)
    
    env_content = []
    
    # Notion Configuration
    print("\nNotion Configuration:")
    notion_token = input("Enter your Notion integration token (starts with 'ntn_'): ").strip()
    if not notion_token.startswith('ntn_'):
        print("Warning: Token should start with 'ntn_'")
    
    notion_db = input("Enter your Notion database ID (32 chars with hyphens): ").strip()
    if len(notion_db.replace('-', '')) != 32:
        print("Warning: Database ID should be 32 characters")
    
    env_content.extend([
        "# Notion Configuration",
        f"NOTION_TOKEN={notion_token}",
        f"NOTION_DATABASE_ID={notion_db}",
        ""
    ])
    
    # GitHub Configuration
    print("\nGitHub Configuration:")
    github_token = input("Enter your GitHub personal access token (starts with 'ghp_'): ").strip()
    if not github_token.startswith('ghp_'):
        print("Warning: Token should start with 'ghp_'")
    
    github_owner = input("Enter your GitHub username/organization: ").strip()
    github_repo = input("Enter your GitHub repository name: ").strip()
    
    env_content.extend([
        "# GitHub Configuration",
        f"GITHUB_TOKEN={github_token}",
        f"GITHUB_OWNER={github_owner}",
        f"GITHUB_REPO={github_repo}",
        ""
    ])
    
    # GitHub Project (Optional)
    print("\nGitHub Project (Optional):")
    use_project = input("Do you want to use GitHub Projects? (y/n): ").strip().lower()
    
    if use_project == 'y':
        project_id = input("Enter GitHub Project ID (starts with 'PVT_'): ").strip()
        status_field_id = input("Enter Status field ID: ").strip()
        backlog_option_id = input("Enter Backlog option ID: ").strip()
        
        env_content.extend([
            "# GitHub Project",
            f"GITHUB_PROJECT_ID={project_id}",
            f"GITHUB_PROJECT_STATUS_FIELD_ID={status_field_id}",
            f"GITHUB_PROJECT_STATUS_BACKLOG_OPTION_ID={backlog_option_id}",
            ""
        ])
    else:
        env_content.extend([
            "# GitHub Project (Optional - leave empty if not using)",
            "GITHUB_PROJECT_ID=",
            "GITHUB_PROJECT_STATUS_FIELD_ID=",
            "GITHUB_PROJECT_STATUS_BACKLOG_OPTION_ID=",
            ""
        ])
    
    # Settings
    print("\nSettings:")
    poll_interval = input("Enter polling interval in seconds (default: 120): ").strip() or "120"
    dry_run = input("Enable dry run mode for testing? (y/n): ").strip().lower()
    dry_run_value = "true" if dry_run == 'y' else "false"
    
    env_content.extend([
        "# Settings",
        f"POLL_INTERVAL_SECONDS={poll_interval}",
        f"DRY_RUN={dry_run_value}",
        ""
    ])
    
    # Write .env file
    env_path = ".env"
    with open(env_path, 'w') as f:
        f.write('\n'.join(env_content))
    
    print(f"\nConfiguration saved to {env_path}")
    print("\nNext steps:")
    print("1. Review your .env file")
    print("2. Run: uvicorn app:app --host 127.0.0.1 --port 8088")
    print("3. Test with a Notion page marked as 'Validated'")

def main():
    if os.path.exists('.env'):
        overwrite = input(".env file already exists. Overwrite? (y/n): ").strip().lower()
        if overwrite != 'y':
            print("Setup cancelled.")
            return
    
    try:
        create_env_file()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled.")
    except Exception as e:
        print(f"\nError during setup: {e}")

if __name__ == "__main__":
    main()
