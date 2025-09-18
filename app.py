import os
import asyncio
from datetime import datetime
from typing import Optional, List, Tuple, Dict

import httpx
from fastapi import FastAPI, HTTPException
from notion_client import Client as NotionClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# =========================
# Env & constantes
# =========================
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DB = os.getenv("NOTION_DATABASE_ID")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "120"))
NOTION_WEBHOOK_SECRET = os.getenv("NOTION_WEBHOOK_SECRET", "")  # não usado no polling

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_OWNER = os.getenv("GITHUB_OWNER")
GITHUB_REPO = os.getenv("GITHUB_REPO")
GITHUB_PROJECT_ID = os.getenv("GITHUB_PROJECT_ID", "")  # PVT_...
GITHUB_PROJECT_STATUS_FIELD_ID = os.getenv("GITHUB_PROJECT_STATUS_FIELD_ID", "")
GITHUB_PROJECT_STATUS_BACKLOG_OPTION_ID = os.getenv("GITHUB_PROJECT_STATUS_BACKLOG_OPTION_ID", "")
GITHUB_PROJECT_CREATE_DRAFT = os.getenv("GITHUB_PROJECT_CREATE_DRAFT", "false").lower() == "true"

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

if not (NOTION_TOKEN and NOTION_DB and GITHUB_TOKEN and GITHUB_OWNER and GITHUB_REPO):
    raise RuntimeError("Faltam variáveis de ambiente obrigatórias: NOTION_TOKEN, NOTION_DATABASE_ID, "
                       "GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO.")

# =========================
# Clientes
# =========================
notion = NotionClient(auth=NOTION_TOKEN)
gh_headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

# =========================
# Base de dados (idempotência)
# =========================
engine = create_async_engine("sqlite+aiosqlite:///./sync.db", echo=False, future=True)

async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("""
        CREATE TABLE IF NOT EXISTS mapping (
            notion_page_id TEXT PRIMARY KEY,
            github_issue_number INTEGER,
            created_at TEXT
        );
        """))

async def already_synced(session: AsyncSession, page_id: str) -> bool:
    res = await session.execute(text("SELECT 1 FROM mapping WHERE notion_page_id=:pid"), {"pid": page_id})
    return res.scalar() is not None

async def record_mapping(session: AsyncSession, page_id: str, issue_number: int):
    await session.execute(
        text("INSERT OR REPLACE INTO mapping (notion_page_id, github_issue_number, created_at) "
             "VALUES (:p, :n, :ts)"),
        {"p": page_id, "n": issue_number, "ts": datetime.utcnow().isoformat()}
    )
    await session.commit()

# =========================
# FastAPI
# =========================
app = FastAPI()

@app.get("/health")
async def health():
    return {
        "status": "ok", 
        "timestamp": datetime.now().isoformat(),
        "notion_token_set": bool(NOTION_TOKEN),
        "notion_db_set": bool(NOTION_DB),
        "github_token_set": bool(GITHUB_TOKEN),
        "poll_interval": POLL_INTERVAL,
        "dry_run": DRY_RUN
    }

# =========================
# Utilitários Notion
# =========================
def _find_title_prop(props: Dict) -> str:
    for k, v in props.items():
        if v.get("type") == "title":
            return k
    return "Name"

def _plain(rt: list) -> str:
    return "".join([seg.get("plain_text", "") for seg in (rt or [])])

def _convert_notion_to_markdown(blocks: list) -> str:
    """Convert Notion blocks to GitHub markdown"""
    markdown_parts = []
    
    for block in blocks:
        block_type = block.get("type", "")
        content = block.get(block_type, {})
        
        if block_type == "paragraph":
            text = _plain(content.get("rich_text", []))
            if text.strip():
                markdown_parts.append(text)
                markdown_parts.append("")
        
        elif block_type == "heading_1":
            text = _plain(content.get("rich_text", []))
            if text.strip():
                markdown_parts.append(f"# {text}")
                markdown_parts.append("")
        
        elif block_type == "heading_2":
            text = _plain(content.get("rich_text", []))
            if text.strip():
                markdown_parts.append(f"## {text}")
                markdown_parts.append("")
        
        elif block_type == "heading_3":
            text = _plain(content.get("rich_text", []))
            if text.strip():
                markdown_parts.append(f"### {text}")
                markdown_parts.append("")
        
        elif block_type == "bulleted_list_item":
            text = _plain(content.get("rich_text", []))
            if text.strip():
                markdown_parts.append(f"- {text}")
        
        elif block_type == "numbered_list_item":
            text = _plain(content.get("rich_text", []))
            if text.strip():
                markdown_parts.append(f"1. {text}")
        
        elif block_type == "to_do":
            text = _plain(content.get("rich_text", []))
            checked = content.get("checked", False)
            checkbox = "- [x]" if checked else "- [ ]"
            if text.strip():
                markdown_parts.append(f"{checkbox} {text}")
        
        elif block_type == "code":
            text = _plain(content.get("rich_text", []))
            language = content.get("language", "")
            if text.strip():
                markdown_parts.append(f"```{language}")
                markdown_parts.append(text)
                markdown_parts.append("```")
                markdown_parts.append("")
        
        elif block_type == "quote":
            text = _plain(content.get("rich_text", []))
            if text.strip():
                markdown_parts.append(f"> {text}")
                markdown_parts.append("")
        
        elif block_type == "callout":
            text = _plain(content.get("rich_text", []))
            icon_obj = content.get("icon") or {}
            icon = icon_obj.get("emoji", "💡") if icon_obj else "💡"
            if text.strip():
                markdown_parts.append(f"> {icon} **{text}**")
                markdown_parts.append("")
        
        elif block_type == "divider":
            markdown_parts.append("---")
            markdown_parts.append("")
        
        elif block_type == "image":
            # Extract image URL and caption
            file_obj = content.get("file") or {}
            external_obj = content.get("external") or {}
            image_url = file_obj.get("url") or external_obj.get("url")
            caption = _plain(content.get("caption", []))
            
            if image_url:
                if caption:
                    markdown_parts.append(f"![{caption}]({image_url})")
                else:
                    markdown_parts.append(f"![Image]({image_url})")
            else:
                # Fallback if no URL found
                if caption:
                    markdown_parts.append(f"![Image: {caption}]")
                else:
                    markdown_parts.append("![Image]")
            markdown_parts.append("")
        
        elif block_type == "file":
            # Handle file attachments
            file_obj = content.get("file") or {}
            external_obj = content.get("external") or {}
            file_url = file_obj.get("url") or external_obj.get("url")
            caption = _plain(content.get("caption", []))
            
            if file_url:
                if caption:
                    markdown_parts.append(f"[📎 {caption}]({file_url})")
                else:
                    markdown_parts.append(f"[📎 File]({file_url})")
            else:
                if caption:
                    markdown_parts.append(f"📎 {caption}")
                else:
                    markdown_parts.append("📎 File")
            markdown_parts.append("")
        
        elif block_type == "video":
            # Handle video embeds
            file_obj = content.get("file") or {}
            external_obj = content.get("external") or {}
            video_url = file_obj.get("url") or external_obj.get("url")
            caption = _plain(content.get("caption", []))
            
            if video_url:
                if caption:
                    markdown_parts.append(f"[🎥 {caption}]({video_url})")
                else:
                    markdown_parts.append(f"[🎥 Video]({video_url})")
            else:
                if caption:
                    markdown_parts.append(f"🎥 {caption}")
                else:
                    markdown_parts.append("🎥 Video")
            markdown_parts.append("")
        
        # Handle children blocks (nested content)
        if block.get("has_children", False):
            # Note: This would require additional API calls to fetch children
            # For now, we'll skip nested content to avoid complexity
            pass
    
    return "\n".join(markdown_parts).strip()

async def get_page_content(page_id: str) -> str:
    """Fetch the full content of a Notion page and convert to markdown"""
    try:
        # Get page blocks
        blocks_response = notion.blocks.children.list(block_id=page_id)
        blocks = blocks_response.get("results", [])
        
        if not blocks:
            return "_(No content found)_"
        
        # Convert to markdown
        markdown_content = _convert_notion_to_markdown(blocks)
        
        if not markdown_content.strip():
            return "_(No readable content found)_"
        
        return markdown_content
        
    except Exception as e:
        print(f"[warn] Failed to fetch page content for {page_id}: {e}")
        return "_(Failed to fetch page content)_"

async def get_page_fields(page_id: str) -> dict:
    page = notion.pages.retrieve(page_id=page_id)
    props = page["properties"]

    title_prop = _find_title_prop(props)
    title = "(no title)"
    if props.get(title_prop, {}).get("title"):
        title = _plain(props[title_prop]["title"])

    # Safe property extraction with null checks
    status = None
    if props.get("Status"):
        status = props["Status"].get("select", {}).get("name")
    
    company = ""
    if props.get("Company"):
        company = _plain(props["Company"].get("rich_text", []))
    
    customer_types = []
    if props.get("Customer Type"):
        customer_types = [o.get("name") for o in props["Customer Type"].get("multi_select", []) if o.get("name")]
    
    priority = None
    if props.get("Priority"):
        priority = props["Priority"].get("select", {}).get("name")
    
    size = None
    if props.get("Size"):
        size = props["Size"].get("select", {}).get("name")
    
    in_sync = False
    if props.get("In Sync With Github"):
        in_sync = props["In Sync With Github"].get("checkbox", False)

    details_lines = []
    if company: details_lines.append(f"**Company:** {company}")
    if customer_types: details_lines.append(f"**Customer Type:** {', '.join(customer_types)}")
    if priority: details_lines.append(f"**Priority:** {priority}")
    if size: details_lines.append(f"**Size:** {size}")
    details = "\n".join(details_lines) if details_lines else ""

    return {
        "page_id": page_id,
        "title": title,
        "status": status,
        "company": company,
        "customer_types": customer_types,
        "priority": priority,
        "size": size,
        "in_sync": in_sync,
        "details": details
    }

def validate_page_data(data: dict) -> tuple[bool, str]:
    """Validate that a page has the minimum required information for syncing"""
    missing_fields = []
    
    # Check required fields
    if not data.get("title") or data["title"] == "(no title)":
        missing_fields.append("title")
    
    if not data.get("status"):
        missing_fields.append("status")
    
    # Optional but recommended fields (just warn, don't block)
    warnings = []
    if not data.get("priority"):
        warnings.append("priority")
    if not data.get("size"):
        warnings.append("size")
    
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    
    if warnings:
        return True, f"Warning: Missing optional fields: {', '.join(warnings)}"
    
    return True, "OK"

async def mark_synced(page_id: str):
    try:
        if DRY_RUN:
            print(f"[dry-run] Would set 'In Sync With Github' on {page_id}")
            return
        notion.pages.update(page_id=page_id, properties={"In Sync With Github": {"checkbox": True}})
    except Exception as e:
        print(f"[warn] Failed to set 'In Sync With Github' on {page_id}: {e}")

async def set_status_to_backlog(page_id: str):
    try:
        if DRY_RUN:
            print(f"[dry-run] Would set Status to 'Backlog' on {page_id}")
            return
        notion.pages.update(page_id=page_id, properties={"Status": {"select": {"name": "Backlog"}}})
        print(f"[ok] Status set to 'Backlog' in Notion")
    except Exception as e:
        print(f"[warn] Failed to set Status to 'Backlog' on {page_id}: {e}")

# =========================
# GitHub: Issues & Projects v2
# =========================
def _labels_for_issue(customer_types: List[str], priority: Optional[str], size: Optional[str]) -> List[str]:
    labels = []
    labels.extend(customer_types or [])                      # "Shipper", "Carrier"
    if priority: labels.append(f"Priority:{priority}")       # "Priority:Medium"
    if size: labels.append(f"Size:{size}")                   # "Size:L"
    return labels

async def create_github_issue(title: str, body: str, labels: List[str]) -> dict:
    if DRY_RUN:
        print(f"[dry-run] Would create issue: '{title}' labels={labels}")
        return {"number": -1, "html_url": "https://example/issue", "node_id": "MDU6SXNzdWUx"}
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/issues"
    payload = {"title": title, "body": body}
    if labels: payload["labels"] = labels
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(url, headers=gh_headers, json=payload)
        r.raise_for_status()
        return r.json()

async def gh_graphql(query: str, variables: dict):
    if DRY_RUN:
        print(f"[dry-run] Would call GraphQL with variables={variables}...")
        # devolve estrutura mínima para evitar crashes quando dry-run
        return {"data": {}}
    gql_url = "https://api.github.com/graphql"
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(gql_url, headers=gh_headers, json={"query": query, "variables": variables})
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise HTTPException(status_code=500, detail=f"GitHub GraphQL error: {data['errors']}")
        return data

async def add_issue_to_project(project_id: str, issue_node_id: str) -> Optional[str]:
    mutation = """
    mutation($project:ID!, $content:ID!) {
      addProjectV2ItemById(input: {projectId: $project, contentId: $content}) {
        item { id }
      }
    }
    """
    data = await gh_graphql(mutation, {"project": project_id, "content": issue_node_id})
    try:
        return data["data"]["addProjectV2ItemById"]["item"]["id"]
    except Exception:
        return None

async def create_draft_item_in_project(project_id: str, title: str, body: str) -> Optional[str]:
    mutation = """
    mutation($project:ID!, $title:String!, $body:String) {
      createProjectV2DraftIssue(input: {projectId: $project, title: $title, body: $body}) {
        projectItem { id }
      }
    }
    """
    data = await gh_graphql(mutation, {"project": project_id, "title": title, "body": body})
    try:
        return data["data"]["createProjectV2DraftIssue"]["projectItem"]["id"]
    except Exception:
        return None

async def set_project_status(project_id: str, item_id: str, status_field_id: str, status_option_id: str):
    mutation = """
    mutation($project:ID!, $item:ID!, $field:ID!, $option: String!) {
      updateProjectV2ItemFieldValue(
        input: { projectId: $project, itemId: $item, fieldId: $field,
                 value: { singleSelectOptionId: $option } }
      ) { projectV2Item { id } }
    }
    """
    await gh_graphql(mutation, {
        "project": project_id,
        "item": item_id,
        "field": status_field_id,
        "option": status_option_id
    })

# Cache simples por (project_id -> {field_name -> field_obj})
_PROJECT_FIELDS_CACHE: Dict[Tuple[str], Dict[str, dict]] = {}

async def get_project_field_and_option_ids(project_id: str, field_name: str, option_label: str) -> Tuple[str, str]:
    cache_key = (project_id,)
    field_map = _PROJECT_FIELDS_CACHE.get(cache_key)
    if not field_map:
        query = """
        query($project: ID!) {
          node(id: $project) {
            ... on ProjectV2 {
              fields(first: 50) {
                nodes {
                  __typename
                  ... on ProjectV2FieldCommon { id name }
                  ... on ProjectV2SingleSelectField { id name options { id name } }
                }
              }
            }
          }
        }
        """
        data = await gh_graphql(query, {"project": project_id})
        nodes = (((data or {}).get("data") or {}).get("node") or {}).get("fields", {}).get("nodes", []) if data else []
        field_map = { n["name"]: n for n in nodes if n.get("__typename") == "ProjectV2SingleSelectField" }
        _PROJECT_FIELDS_CACHE[cache_key] = field_map

    f = field_map.get(field_name)
    if not f:
        raise HTTPException(status_code=500, detail=f"Field '{field_name}' not found in Project.")
    opt = next((o for o in f.get("options", []) if o.get("name") == option_label), None)
    if not opt:
        raise HTTPException(status_code=500, detail=f"Option '{option_label}' not found in field '{field_name}'.")
    return f["id"], opt["id"]

async def set_project_single_select(project_id: str, item_id: str, field_id: str, option_id: str):
    mutation = """
    mutation($project:ID!, $item:ID!, $field:ID!, $option:String!) {
      updateProjectV2ItemFieldValue(
        input: { projectId: $project, itemId: $item, fieldId: $field,
                 value: { singleSelectOptionId: $option } }
      ) { projectV2Item { id } }
    }
    """
    await gh_graphql(mutation, {
        "project": project_id, "item": item_id, "field": field_id, "option": option_id
    })

# =========================
# Mapeamentos Notion -> Project (Priority/Size)
# Ajusta livremente estes dicionários para corresponder ao teu Project
# =========================
PRIORITY_MAP_NOTION_TO_GH = {
    "Large": "Extremo",
    "Medium": "Médio",
    "Low": "Baixa",
}
SIZE_MAP_NOTION_TO_GH = {k: k for k in ["XS", "S", "M", "L", "XL"]}

# =========================
# Core: processamento de uma página Validated
# =========================
async def process_validated_page(page_id: str):
    try:
        data = await get_page_fields(page_id)
        print(f"[info] Processing page: '{data['title']}' (Status: {data['status']})")
        
        # Validate page data
        is_valid, validation_message = validate_page_data(data)
        if not is_valid:
            print(f"[skip] Page '{data['title']}' skipped: {validation_message}")
            return
        
        if validation_message != "OK":
            print(f"[warn] Page '{data['title']}': {validation_message}")
        
        if data["status"] != "Validated":
            print(f"[debug] Skipping page - status is '{data['status']}', not 'Validated'")
            return

        async with AsyncSession(engine) as session:
            if await already_synced(session, page_id):
                print(f"[debug] Skipping page - already synced")
                return

        # Get full page content
        page_content = await get_page_content(page_id)
        
        # Corpo do Issue
        body_parts = [
            f"Imported from Notion page `{page_id}`.",
            "",
            "---",
            "",
            page_content,
            "",
            "---",
            "",
            "> Created automatically when Notion Status moved to **Validated**."
        ]
        labels = _labels_for_issue(data["customer_types"], data["priority"], data["size"])

        # 1) Criar Issue OU Draft
        project_item_id = None
        issue = None

        print(f"[info] Creating GitHub issue: '{data['title']}'")
        body_text = '\n'.join(body_parts)

        if GITHUB_PROJECT_CREATE_DRAFT and GITHUB_PROJECT_ID:
            # Draft Item no Project (sem Issue no repo)
            print(f"[info] Creating draft item in project...")
            project_item_id = await create_draft_item_in_project(GITHUB_PROJECT_ID, data["title"], body_text)
            if project_item_id:
                print(f"[ok] Draft created in Project: item_id={project_item_id}")
            else:
                print(f"[error] Failed to create draft item")
        else:
            # Issue no repo (recomendado)
            print(f"[info] Creating GitHub issue...")
            issue = await create_github_issue(data["title"], body_text, labels)
            if issue:
                print(f"[ok] Issue created: #{issue.get('number')} {issue.get('html_url')}")
            else:
                print(f"[error] Failed to create issue")

        # 2) Guardar idempotência se for Issue
        if issue and not DRY_RUN:
            async with AsyncSession(engine) as session:
                await record_mapping(session, page_id, issue["number"])

        # 3) Marcar Notion como sincronizado e mudar status para Backlog
        await mark_synced(page_id)
        await set_status_to_backlog(page_id)

        # 4) Se houver Project, adicionar e setar campos
        if GITHUB_PROJECT_ID:
            # a) Status = Backlog
            if not project_item_id:
                if issue and issue.get("node_id"):
                    project_item_id = await add_issue_to_project(GITHUB_PROJECT_ID, issue["node_id"])
                    print(f"[ok] Added to Project: item_id={project_item_id}")

            # Definir Status via env IDs (mais rápido)
            if project_item_id and GITHUB_PROJECT_STATUS_FIELD_ID and GITHUB_PROJECT_STATUS_BACKLOG_OPTION_ID:
                try:
                    await set_project_status(
                        GITHUB_PROJECT_ID,
                        project_item_id,
                        GITHUB_PROJECT_STATUS_FIELD_ID,
                        GITHUB_PROJECT_STATUS_BACKLOG_OPTION_ID
                    )
                    print("[ok] Project Status set to Backlog.")
                except Exception as e:
                    print(f"[warn] Could not set Status=Backlog: {e}")

            # b) Priority
            if project_item_id and data["priority"]:
                gh_priority = PRIORITY_MAP_NOTION_TO_GH.get(data["priority"], data["priority"])
                try:
                    pr_field_id, pr_opt_id = await get_project_field_and_option_ids(GITHUB_PROJECT_ID, "Priority", gh_priority)
                    await set_project_single_select(GITHUB_PROJECT_ID, project_item_id, pr_field_id, pr_opt_id)
                    print(f"[ok] Project Priority set to {gh_priority}.")
                except Exception as e:
                    print(f"[warn] Could not set Project Priority: {e}")

            # c) Size
            if project_item_id and data["size"]:
                gh_size = SIZE_MAP_NOTION_TO_GH.get(data["size"], data["size"])
                try:
                    sz_field_id, sz_opt_id = await get_project_field_and_option_ids(GITHUB_PROJECT_ID, "Size", gh_size)
                    await set_project_single_select(GITHUB_PROJECT_ID, project_item_id, sz_field_id, sz_opt_id)
                    print(f"[ok] Project Size set to {gh_size}.")
                except Exception as e:
                    print(f"[warn] Could not set Project Size: {e}")
    
    except Exception as e:
        print(f"[error] Failed to process page {page_id}: {e}")
        # Don't re-raise - let other pages continue processing

# =========================
# Polling loop
# =========================
async def poll_loop():
    print(f"[info] Polling every {POLL_INTERVAL} seconds for pages to sync")
    try:
        while True:
            try:
                query = {
                    "database_id": NOTION_DB,
                    "filter": {
                        "and": [
                            {"property": "Status", "select": {"equals": "Validated"}},
                            {"property": "In Sync With Github", "checkbox": {"equals": False}}
                        ]
                    },
                    "page_size": 50
                }
                res = notion.databases.query(**query)
                results = res.get("results", [])
                if results:
                    print(f"[info] Found {len(results)} page(s) to sync")
                for r in results:
                    page_id = r["id"]
                    try:
                        await process_validated_page(page_id)
                        print(f"[ok] Successfully synced page: {page_id}")
                    except Exception as e:
                        print(f"[error] Failed to sync page {page_id}: {e}")
            except Exception as e:
                print(f"[error] Polling cycle failed: {e}")
            await asyncio.sleep(POLL_INTERVAL)
    except Exception as e:
        print(f"[error] Polling loop crashed: {e}")
        import traceback
        traceback.print_exc()

@app.on_event("startup")
async def on_startup():
    print("[info] Notion-GitHub Sync starting up...")
    await init_db()
    asyncio.create_task(poll_loop())
    print("[info] Polling loop started")

# Application ready
