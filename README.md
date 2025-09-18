# Notion-GitHub Sync

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.68+-green.svg)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Automatically sync Notion pages to GitHub issues with full content preservation, media support, and project integration.**

Transform your Notion workflow into GitHub issues seamlessly. When you mark a Notion page as "Validated", it automatically creates a GitHub issue with the complete page content, including images, files, and formatting.

## Features

- **Automatic Sync**: Notion pages → GitHub issues
- **Full Content**: Preserves headings, lists, code blocks, images, files, videos
- **Smart Labels**: Automatic labeling based on Notion properties
- **Project Integration**: Adds issues to GitHub Projects with proper status
- **Error Handling**: Graceful handling of incomplete pages
- **Real-time**: Continuous polling for new pages
- **Customizable**: Easy to adapt for your workflow

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/notion-github-sync.git
cd notion-github-sync
```

### 2. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set Up Environment Variables

Create a `.env` file in the project root:

```bash
# Notion Configuration
NOTION_TOKEN=your_notion_integration_token
NOTION_DATABASE_ID=your_database_id

# GitHub Configuration
GITHUB_TOKEN=your_github_personal_access_token
GITHUB_OWNER=your_github_username
GITHUB_REPO=your_repository_name

# GitHub Project (Optional)
GITHUB_PROJECT_ID=your_project_id
GITHUB_PROJECT_STATUS_FIELD_ID=your_status_field_id
GITHUB_PROJECT_STATUS_BACKLOG_OPTION_ID=your_backlog_option_id

# Settings
POLL_INTERVAL_SECONDS=120
DRY_RUN=false
```

### 4. Run the Application

**Option A: Manual Run**

```bash
# Load environment variables first
set -a; source .env; set +a

# Start the application
uvicorn app:app --host 127.0.0.1 --port 8088
```

**Option B: Using the Run Script (Recommended)**

```bash
# Make the script executable (only needed once)
chmod +x run.sh

# Run the application in background:
nohup ./run.sh > sync.out 2>&1 & echo $! > sync.pid
```

The `run.sh` script automatically:

- Loads environment variables from `.env`
- Activates the virtual environment
- Starts the application on `http://127.0.0.1:8088`

## Setup Guide

### Notion Setup

#### 1. Create a Notion Integration

1. Go to [Notion Integrations](https://www.notion.so/my-integrations)
2. Click **"New integration"**
3. Fill in the details:
   - **Name**: `GitHub-Sync` (or your preferred name)
   - **Logo**: Optional
   - **Associated workspace**: Select your workspace
4. Click **"Submit"**
5. Copy the **Internal Integration Token** (starts with `ntn_`)

#### 2. Create Your Database

Create a Notion database with these properties:

| Property Name                 | Type         | Required | Description                             |
| ----------------------------- | ------------ | -------- | --------------------------------------- |
| **Name**                | Title        | Required | Page title (becomes GitHub issue title) |
| **Status**              | Select       | Required | Must include "Validated" option         |
| **In Sync With Github** | Checkbox     | Required | Tracks sync status                      |
| **Priority**            | Select       | Optional | "Low", "Medium", "High"                 |
| **Size**                | Select       | Optional | "XS", "S", "M", "L", "XL"               |
| **Company**             | Rich Text    | Optional | Company information                     |
| **Customer Type**       | Multi-select | Optional | "Type A", "Type B", etc.                |

#### 3. Share Database with Integration

1. Open your database in Notion
2. Click **"Share"** (top-right)
3. Click **"Add people, emails, groups, or integrations"**
4. Search for your integration name (`GitHub-Sync`)
5. Select it and give **"Can edit"** permissions
6. Click **"Invite"**

#### 4. Get Database ID

1. Open your database in a web browser
2. Copy the URL: `https://www.notion.so/your-workspace/DATABASE_NAME?v=DATABASE_ID`
3. Extract the `DATABASE_ID` (32-character string with hyphens)

### GitHub Setup

#### 1. Create Personal Access Token

1. Go to [GitHub Settings &gt; Developer settings &gt; Personal access tokens](https://github.com/settings/tokens)
2. Click **"Generate new token (classic)"**
3. Set expiration and select scopes:
   - ✅ **repo** (Full control of private repositories)
   - ✅ **project** (Full control of user projects)
   - ✅ **read:org** (Read org and team membership)
4. Click **"Generate token"**
5. Copy the token (starts with `ghp_`)

#### 2. Get Repository Information

```bash
# Get your username
gh api user --jq '.login'

# Get repository name (if you don't know it)
gh repo list --limit 10
```

#### 3. GitHub Project Setup (Optional)

If you want to use GitHub Projects:

1. Go to your repository
2. Click **"Projects"** tab
3. Create a new project or use existing one
4. Get the project ID using GraphQL:

```bash
# Install GitHub CLI if you haven't
gh auth login

# Get project ID
gh api graphql -f query='
{
  repository(owner: "YOUR_USERNAME", name: "YOUR_REPO") {
    projectsV2(first: 10) {
      nodes {
        id
        title
      }
    }
  }
}'
```

5. Get field IDs:

```bash
gh api graphql -f query='
{
  node(id: "YOUR_PROJECT_ID") {
    ... on ProjectV2 {
      fields(first: 20) {
        nodes {
          ... on ProjectV2FieldCommon {
            id
            name
          }
          ... on ProjectV2SingleSelectField {
            id
            name
            options {
              id
              name
            }
          }
        }
      }
    }
  }
}'
```

## How It Works

### Workflow

1. **Create** a page in your Notion database
2. **Set Status** to "Validated"
3. **Add content** (text, images, files, etc.)
4. **Wait** for the next polling cycle (default: 2 minutes)
5. **GitHub issue** is automatically created with full content
6. **Status** changes to "Backlog" in Notion
7. **Issue** is added to GitHub Project (if configured)

### Content Conversion

| Notion Element | GitHub Markdown        |
| -------------- | ---------------------- |
| Headings       | `#`, `##`, `###` |
| Bulleted Lists | `- item`             |
| Numbered Lists | `1. item`            |
| Checkboxes     | `- [ ]` / `- [x]`  |
| Code Blocks    | ```language blocks     |
| Images         | `![caption](url)`    |
| Files          | `[filename](url)`    |
| Videos         | `[video](url)`       |
| Quotes         | `> quote`            |
| Callouts       | `> **text**`         |

## Customization

### Custom Status Values

Edit the status filter in `app.py`:

```python
# Line ~505: Change "Validated" to your preferred status
{"property": "Status", "select": {"equals": "Your Status"}}
```

### Custom Priority/Size Mapping

Modify the mapping dictionaries:

```python
# Lines ~483-487: Customize the mappings
PRIORITY_MAP_NOTION_TO_GH = {
    "Critical": "P0",
    "High": "P1", 
    "Medium": "P2",
    "Low": "P3",
}

SIZE_MAP_NOTION_TO_GH = {
    "Tiny": "XS",
    "Small": "S", 
    "Medium": "M",
    "Large": "L",
    "Huge": "XL"
}
```

### Custom Labels

Modify the `_labels_for_issue` function:

```python
def _labels_for_issue(customer_types: List[str], priority: Optional[str], size: Optional[str]) -> List[str]:
    labels = []
    labels.extend(customer_types or [])  # e.g., "Type A", "Type B"
    if priority: labels.append(f"priority-{priority.lower()}")
    if size: labels.append(f"size-{size.lower()}")
    # Add custom labels
    labels.append("notion-sync")
    return labels
```

### Custom Issue Body

Modify the issue body creation in `process_validated_page`:

```python
body_parts = [
    f"Imported from Notion page `{page_id}`.",
    "",
    "---",
    "",
    page_content,
    "",
    "---",
    "",
    "## Additional Information",
    "Add your custom sections here",
    "",
    "> Created automatically when Notion Status moved to **Validated**."
]
```

## Configuration Options

| Environment Variable      | Default | Description                   |
| ------------------------- | ------- | ----------------------------- |
| `NOTION_TOKEN`          | -       | Notion integration token      |
| `NOTION_DATABASE_ID`    | -       | Notion database ID            |
| `GITHUB_TOKEN`          | -       | GitHub personal access token  |
| `GITHUB_OWNER`          | -       | GitHub username/organization  |
| `GITHUB_REPO`           | -       | GitHub repository name        |
| `GITHUB_PROJECT_ID`     | -       | GitHub Project ID (optional)  |
| `POLL_INTERVAL_SECONDS` | 120     | Polling interval in seconds   |
| `DRY_RUN`               | false   | Test mode (no actual changes) |

## Troubleshooting

### Common Issues

#### "Could not find database with ID"

- Verify database is shared with your integration
- Check database ID is correct (32 characters with hyphens)
- Ensure integration has "Can edit" permissions

#### "Missing required fields"

- Ensure page has a title
- Set Status to "Validated"
- Check property names match exactly

#### "Failed to create issue"

- Verify GitHub token has `repo` scope
- Check repository name and owner are correct
- Ensure token hasn't expired

#### "Property type mismatch"

- Ensure Status property is "Select" type (not Multi-select)
- Check property names match your database schema

### Debug Mode

Enable debug logging by setting `DRY_RUN=true` in your `.env` file to test without making changes.

## Monitoring

The application provides a health endpoint:

```bash
curl http://127.0.0.1:8088/health
```

Response:

```json
{
  "status": "ok",
  "poll_interval": 120,
  "dry_run": false
}
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Notion API](https://developers.notion.com/) for the integration capabilities
- [GitHub API](https://docs.github.com/en/rest) for issue and project management
- [FastAPI](https://fastapi.tiangolo.com/) for the web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) for database management

## Support

- **Issues**: [GitHub Issues](https://github.com/YOUR_USERNAME/notion-github-sync/issues)
- **Discussions**: [GitHub Discussions](https://github.com/YOUR_USERNAME/notion-github-sync/discussions)
- **Email**: your-email@example.com

---

**Star this repository if you find it helpful!**

*Made for the Notion and GitHub communities*
