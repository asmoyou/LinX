# User Manual

Welcome to LinX (灵枢)! This manual will guide you through using the platform to manage AI agents, submit tasks, and leverage the knowledge base.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Dashboard Overview](#dashboard-overview)
3. [Managing Agents](#managing-agents)
4. [Task Management](#task-management)
5. [Knowledge Base](#knowledge-base)
6. [Memory System](#memory-system)
7. [User Settings](#user-settings)
8. [Best Practices](#best-practices)

## Getting Started

### First Login

1. Open your browser and navigate to the platform URL
2. Enter your username and password
3. Click "Sign In"

**Default Admin Credentials** (change immediately):
- Username: `admin`
- Password: `admin123`

### Dashboard Overview

After logging in, you'll see the main dashboard with:
- **Active Agents**: Number of currently running agents
- **Goals Completed**: Total completed tasks
- **Throughput**: Tasks completed per hour
- **Compute Load**: System resource usage
- **Task Distribution Chart**: Visual breakdown of task types
- **Recent Events**: Timeline of recent activities

## Managing Agents

### Viewing Agents

Navigate to **Workforce** in the sidebar to see all your agents.

Each agent card shows:
- Agent name and type
- Current status (Working, Idle, Offline)
- Assigned skills
- Recent activity

### Creating a New Agent

1. Click the **"+ Add Agent"** button
2. Choose a template or create custom:
   - **Data Analyst**: For data processing and analysis
   - **Content Writer**: For content generation
   - **Code Assistant**: For code-related tasks
   - **Research Assistant**: For research and information gathering
3. Configure agent settings:
   - **Name**: Give your agent a descriptive name
   - **Description**: Describe the agent's purpose
   - **Skills**: Select required skills
   - **Resource Limits**: Set CPU and memory limits
4. Click **"Create Agent"**

### Agent Templates

**Data Analyst**:
- Skills: data_processing, sql_query, data_visualization
- Use for: Data analysis, report generation, database queries

**Content Writer**:
- Skills: text_generation, summarization, translation
- Use for: Article writing, content creation, document summarization

**Code Assistant**:
- Skills: code_generation, code_review, debugging
- Use for: Code development, bug fixing, code review

**Research Assistant**:
- Skills: web_search, document_analysis, information_extraction
- Use for: Research, information gathering, document analysis

### Managing Agent Status

- **Start Agent**: Click the play button to activate an idle agent
- **Pause Agent**: Click the pause button to temporarily stop an agent
- **Terminate Agent**: Click the stop button to permanently stop an agent
- **View Logs**: Click "View Logs" to see agent activity

### Agent Details

Click on an agent card to view detailed information:
- **Overview**: Agent configuration and status
- **Activity Log**: Recent actions and tasks
- **Performance Metrics**: CPU, memory, task completion rate
- **Assigned Tasks**: Current and completed tasks

## Task Management

### Submitting a Goal

1. Navigate to **Tasks** in the sidebar
2. Enter your goal in the text box
3. Click **"Submit Goal"**

**Example Goals**:
- "Analyze sales data from Q4 and create a summary report"
- "Write a blog post about AI trends in 2024"
- "Review the codebase and identify potential bugs"
- "Research competitors and create a comparison table"

### Goal Clarification

If your goal is ambiguous, the system may ask clarification questions:
1. Review the questions
2. Provide answers
3. Click **"Submit Answers"**

### Task Decomposition

The system automatically breaks down your goal into sub-tasks:
- View the task tree in the **Task Timeline**
- See dependencies between tasks
- Monitor progress for each sub-task

### Task Flow Visualization

The **Task Flow** tab shows a visual graph of:
- Task nodes with status indicators
- Dependencies (arrows between tasks)
- Agent assignments
- Real-time progress updates

**Status Indicators**:
- 🔵 Blue: Pending
- 🟡 Yellow: In Progress
- 🟢 Green: Completed
- 🔴 Red: Failed

### Monitoring Task Progress

- **Timeline View**: See tasks in chronological order
- **Flow View**: See task dependencies and relationships
- **Details Panel**: Click a task to see detailed information

### Task Results

When a task completes:
1. Click on the completed task
2. View the result in the details panel
3. Download artifacts if available
4. Provide feedback (optional)

## Knowledge Base

### Uploading Documents

1. Navigate to **Knowledge** in the sidebar
2. Click **"Upload Documents"** or drag files to the upload zone
3. Supported formats:
   - Documents: PDF, DOCX, TXT, MD
   - Images: PNG, JPG (with OCR)
   - Audio: MP3, WAV (with transcription)
   - Video: MP4, AVI (audio extraction + transcription)
4. Wait for processing to complete

### Document Processing

After upload, documents are:
1. **Validated**: File type and size checks
2. **Processed**: Text extraction, OCR, or transcription
3. **Chunked**: Split into manageable pieces
4. **Indexed**: Embedded and stored for search

### Searching Documents

1. Enter search query in the search bar
2. Use filters:
   - **Type**: Filter by document type
   - **Date**: Filter by upload date
   - **Tags**: Filter by tags
3. View search results with relevance scores
4. Click a document to view details

### Document Viewer

Click on a document to:
- View content
- See metadata (upload date, size, type)
- Download original file
- Edit access permissions
- Add tags
- Delete document

### Access Control

Set document permissions:
- **Public**: All users can access
- **Internal**: Only authenticated users
- **Confidential**: Specific users/roles only
- **Restricted**: Admin only

## Memory System

The platform uses a reset-era memory pipeline:

### User Memory

- **Long-term facts about the user**
- Stores preferences, relationships, background, skills, goals, and important events
- Used for personalization and better future assistance
- Private to the owning user by default

### Skill Proposals

- **Agent-owned learned successful paths**
- Stores reusable execution methods that worked in practice
- Requires review before becoming a published skill
- Scoped to the owning agent account

### Knowledge Base

- **Shared documents and reference knowledge**
- Use the Knowledge Base for company or project documents
- Not mixed into long-term user memory

### Browsing Memory

1. Navigate to **Memory** in the sidebar
2. Select a product surface:
   - User Memory
   - Skill Proposals
3. Use search to find specific memories
4. Filter by:
   - Product type
   - Date range
   - Tags
5. View memory details and relevance scores

### Skill Proposal Review

Review learned successful paths:
1. Select a skill proposal
2. Click **"审核"** or the review action in the detail panel
3. Choose whether to publish, reject, or request revision
4. Add an optional review note
5. Confirm the review action

## User Settings

### Profile Settings

1. Click your avatar in the top right
2. Select **"Settings"**
3. Update:
   - Display name
   - Email
   - Password
   - Language preference
   - Theme (Light/Dark/System)

### Notifications

Configure notification preferences:
- Task completion alerts
- Agent status changes
- System updates
- Email notifications

### API Keys

Generate API keys for programmatic access:
1. Go to Settings → API Keys
2. Click **"Generate New Key"**
3. Copy and save the key securely
4. Set expiration date (optional)

## Best Practices

### Writing Effective Goals

**Good Goals**:
- ✅ "Analyze Q4 sales data and identify top 3 products"
- ✅ "Write a 500-word blog post about renewable energy"
- ✅ "Review pull request #123 and suggest improvements"

**Poor Goals**:
- ❌ "Do something with data"
- ❌ "Write stuff"
- ❌ "Fix things"

**Tips**:
- Be specific and clear
- Include context and constraints
- Specify desired output format
- Mention any deadlines

### Organizing Knowledge

- **Use descriptive filenames**
- **Add relevant tags**
- **Set appropriate access levels**
- **Keep documents up to date**
- **Remove outdated content**

### Agent Management

- **Start with templates** for common use cases
- **Monitor resource usage** to optimize performance
- **Review agent logs** regularly
- **Terminate unused agents** to free resources
- **Update agent skills** as needs change

### Security

- **Change default passwords** immediately
- **Use strong passwords** (12+ characters)
- **Enable two-factor authentication** (if available)
- **Review access permissions** regularly
- **Don't share credentials**
- **Log out when finished**

### Performance

- **Limit concurrent tasks** to avoid overload
- **Use appropriate agent types** for tasks
- **Monitor system resources**
- **Archive old data** periodically
- **Optimize large documents** before upload

## Keyboard Shortcuts

- `Ctrl/Cmd + K`: Quick search
- `Ctrl/Cmd + N`: New agent
- `Ctrl/Cmd + T`: New task
- `Ctrl/Cmd + U`: Upload document
- `Ctrl/Cmd + ,`: Settings
- `Esc`: Close modal

## Troubleshooting

### Task Not Starting

- Check if agents are available
- Verify agent has required skills
- Check system resource limits
- Review task requirements

### Document Upload Failing

- Check file size (regular files max 200MB, ZIP archives max 3GB)
- Verify file format is supported
- Check storage quota
- Try uploading smaller files

### Agent Not Responding

- Check agent status
- Review agent logs
- Restart agent if needed
- Contact administrator

### Search Not Working

- Check search query syntax
- Verify documents are indexed
- Try different keywords
- Check access permissions

## Getting Help

- **Documentation**: Browse docs at `/docs`
- **FAQ**: Common questions at `/faq`
- **Support**: Email support@example.com
- **Community**: Join our Discord/Slack
- **GitHub**: Report issues on GitHub

## Glossary

- **Agent**: AI worker that performs tasks
- **Goal**: High-level objective submitted by user
- **Task**: Sub-component of a goal
- **Skill**: Capability that an agent can perform
- **Template**: Pre-configured agent type
- **Memory**: Stored knowledge and experiences
- **Knowledge Base**: Document repository
- **Embedding**: Vector representation of text

## Updates and Changelog

Check the [Changelog](../../CHANGELOG.md) for latest updates and new features.

## Feedback

We value your feedback! Please:
- Report bugs on GitHub
- Suggest features via email
- Rate your experience
- Share success stories

Thank you for using LinX (灵枢)!
