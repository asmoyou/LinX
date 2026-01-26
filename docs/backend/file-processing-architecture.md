# File Processing Architecture

## Overview

File processing in the LinX platform is handled through a **skill-based architecture**. Files (images, documents, audio, video) are not processed by the core system directly. Instead, processing is delegated to dynamically loaded agent skills.

## Design Philosophy

### Skill-Based Processing

- **No Built-in Processing**: The core agent system does not have built-in file processing capabilities
- **Dynamic Skills**: File processing is handled by skills loaded from the skill library
- **Graceful Degradation**: If an agent lacks the required skill, files are skipped without errors
- **Extensible**: New file types can be supported by adding new skills

### Benefits

1. **Modularity**: File processing logic is separated from core agent logic
2. **Flexibility**: Different agents can have different file processing capabilities
3. **Scalability**: Skills can be added/removed without changing core code
4. **Resource Efficiency**: Only load processing capabilities when needed
5. **Customization**: Each agent can have tailored file processing skills

## Skill Types for File Processing

### Image Processing Skills

**Skill Name**: `image_processing`

**Capabilities**:
- Image recognition and classification
- Object detection
- Scene understanding
- Visual question answering
- Image captioning

**Example Usage**:
```python
# Agent with image_processing skill
agent = Agent(
    name="Vision Agent",
    skills=["image_processing", "general_chat"]
)

# When user sends image + text
# Skill processes image and extracts information
# Agent receives: "User asked: 'What's in this image?' Image contains: [description]"
```

### Document Processing Skills

**Skill Name**: `document_processing`

**Capabilities**:
- PDF text extraction
- Document structure analysis
- Table extraction
- Metadata extraction
- Multi-page document handling

**Example Usage**:
```python
# Agent with document_processing skill
agent = Agent(
    name="Document Analyst",
    skills=["document_processing", "data_analysis"]
)

# When user uploads PDF
# Skill extracts text and structure
# Agent receives: "Document content: [extracted text]"
```

### OCR Skills

**Skill Name**: `ocr`

**Capabilities**:
- Text extraction from images
- Handwriting recognition
- Multi-language support
- Layout preservation

**Example Usage**:
```python
# Agent with OCR skill
agent = Agent(
    name="OCR Agent",
    skills=["ocr", "text_analysis"]
)

# When user sends image with text
# Skill extracts text via OCR
# Agent receives: "Extracted text: [OCR result]"
```

### Audio Processing Skills

**Skill Name**: `audio_processing`

**Capabilities**:
- Speech-to-text transcription
- Audio classification
- Speaker identification
- Audio analysis

### Video Processing Skills

**Skill Name**: `video_processing`

**Capabilities**:
- Frame extraction
- Video summarization
- Action recognition
- Scene detection

## Processing Flow

### 1. File Upload

```
User → Frontend → Backend API
                    ↓
              File Storage (MinIO)
                    ↓
              File Reference Created
```

### 2. Agent Receives Message

```
Message with Files → Agent Executor
                          ↓
                    Check Agent Skills
                          ↓
              ┌─────────────┴─────────────┐
              ↓                           ↓
        Has Required Skill          No Required Skill
              ↓                           ↓
        Load & Execute Skill         Skip File Processing
              ↓                           ↓
        Process File                 Use Text Only
              ↓                           ↓
        Extract Information          Continue Execution
              ↓                           ↓
        Augment Message              ────┘
              ↓
        Agent Processes Augmented Message
```

### 3. Skill Execution

```python
# Pseudo-code for skill-based file processing

def process_message_with_files(agent, message, files):
    """Process message with attached files using agent skills."""
    
    # Check if agent has file processing skills
    has_image_skill = "image_processing" in agent.skills
    has_doc_skill = "document_processing" in agent.skills
    has_ocr_skill = "ocr" in agent.skills
    
    augmented_message = message
    
    for file in files:
        if file.type == "image":
            if has_image_skill:
                # Load and execute image processing skill
                skill = load_skill("image_processing")
                result = skill.process(file)
                augmented_message += f"\n\nImage analysis: {result}"
            elif has_ocr_skill:
                # Fallback to OCR if no image processing
                skill = load_skill("ocr")
                text = skill.extract_text(file)
                augmented_message += f"\n\nExtracted text: {text}"
            else:
                # Skip image processing
                logger.info(f"Agent {agent.id} lacks image processing skills, skipping image")
        
        elif file.type == "document":
            if has_doc_skill:
                # Load and execute document processing skill
                skill = load_skill("document_processing")
                content = skill.extract_content(file)
                augmented_message += f"\n\nDocument content: {content}"
            else:
                # Skip document processing
                logger.info(f"Agent {agent.id} lacks document processing skills, skipping document")
    
    # Agent processes the augmented message
    return agent.execute(augmented_message)
```

## Implementation Details

### Skill Library Integration

Skills are stored in the `skill_library` module:

```
backend/skill_library/
├── __init__.py
├── skill_registry.py          # Skill registration and loading
├── skill_executor.py           # Skill execution engine
├── default_skills.py           # Built-in skills
└── skills/
    ├── image_processing.py     # Image processing skill
    ├── document_processing.py  # Document processing skill
    ├── ocr.py                  # OCR skill
    ├── audio_processing.py     # Audio processing skill
    └── video_processing.py     # Video processing skill
```

### Skill Definition

Each skill follows a standard interface:

```python
from skill_library.skill_model import Skill, SkillParameter

class ImageProcessingSkill(Skill):
    """Skill for processing images."""
    
    name = "image_processing"
    description = "Processes images and extracts visual information"
    version = "1.0.0"
    
    parameters = [
        SkillParameter(
            name="image_path",
            type="string",
            description="Path to image file",
            required=True
        ),
        SkillParameter(
            name="analysis_type",
            type="string",
            description="Type of analysis: caption, objects, scene",
            required=False,
            default="caption"
        )
    ]
    
    def execute(self, image_path: str, analysis_type: str = "caption") -> dict:
        """Execute image processing."""
        # Load image
        image = load_image(image_path)
        
        # Process based on analysis type
        if analysis_type == "caption":
            result = generate_caption(image)
        elif analysis_type == "objects":
            result = detect_objects(image)
        elif analysis_type == "scene":
            result = analyze_scene(image)
        
        return {
            "success": True,
            "result": result,
            "metadata": {
                "image_size": image.size,
                "format": image.format
            }
        }
```

### Agent Configuration

Agents specify their skills in configuration:

```python
# Create agent with file processing skills
agent = Agent(
    name="Multimodal Assistant",
    type="general",
    skills=[
        "general_chat",
        "image_processing",
        "document_processing",
        "web_search"
    ],
    system_prompt="You are a helpful assistant that can process images and documents."
)
```

### Frontend Integration

The frontend prepares files for upload:

```typescript
// User attaches files
const attachedFiles = [
  { type: 'image', file: imageFile },
  { type: 'document', file: pdfFile }
];

// Send to backend
await agentsApi.testAgent(agentId, message, {
  files: attachedFiles,
  history: conversationHistory
});
```

### Backend Processing

The backend handles file upload and skill execution:

```python
@router.post("/{agent_id}/test")
async def test_agent(agent_id: str, request: TestAgentRequest, files: List[UploadFile] = None):
    """Test agent with message and optional files."""
    
    # Get agent and check skills
    agent = get_agent(agent_id)
    
    # Upload files to storage
    file_refs = []
    if files:
        for file in files:
            file_path = await upload_to_minio(file)
            file_refs.append({
                "path": file_path,
                "type": detect_file_type(file),
                "name": file.filename
            })
    
    # Process message with files using agent skills
    augmented_message = await process_with_skills(
        agent=agent,
        message=request.message,
        files=file_refs
    )
    
    # Execute agent with augmented message
    result = await agent.execute(augmented_message)
    
    return result
```

## Graceful Degradation

### No Skills Available

If an agent has no file processing skills:

```python
# Agent without file processing skills
agent = Agent(
    name="Text-Only Agent",
    skills=["general_chat", "web_search"]
)

# User sends image + text
# System behavior:
# 1. Detects no image_processing skill
# 2. Logs: "Agent lacks image processing skills, skipping image"
# 3. Processes only the text message
# 4. Agent responds based on text only
```

### Partial Skills

If an agent has some but not all file processing skills:

```python
# Agent with only OCR skill
agent = Agent(
    name="OCR Agent",
    skills=["general_chat", "ocr"]
)

# User sends image + PDF
# System behavior:
# 1. Image: Uses OCR skill to extract text
# 2. PDF: No document_processing skill, skips PDF
# 3. Agent receives: "User message + OCR text from image"
```

## Future Enhancements

### 1. Skill Marketplace

- Users can browse and install skills
- Community-contributed skills
- Skill ratings and reviews

### 2. Skill Chaining

- Combine multiple skills for complex processing
- Example: OCR → Translation → Summarization

### 3. Skill Versioning

- Multiple versions of same skill
- Backward compatibility
- Automatic updates

### 4. Skill Analytics

- Track skill usage
- Performance metrics
- Error rates

### 5. Custom Skills

- Users can create custom skills
- Upload Python code
- Sandbox execution

## Best Practices

### For Agent Creators

1. **Choose Appropriate Skills**: Select skills based on agent's purpose
2. **Test with Files**: Verify file processing works as expected
3. **Provide Clear Instructions**: Tell users what file types are supported
4. **Handle Failures Gracefully**: Agent should work even if file processing fails

### For Skill Developers

1. **Follow Skill Interface**: Implement standard Skill class
2. **Handle Errors**: Return meaningful error messages
3. **Optimize Performance**: Process files efficiently
4. **Document Capabilities**: Clear description of what skill does
5. **Version Properly**: Use semantic versioning

### For System Administrators

1. **Monitor Skill Usage**: Track which skills are most used
2. **Update Skills**: Keep skills up to date
3. **Manage Resources**: Ensure sufficient resources for file processing
4. **Security**: Validate and sanitize file inputs

## Security Considerations

### File Validation

- Check file types and sizes
- Scan for malware
- Validate file content

### Skill Sandboxing

- Execute skills in isolated environment
- Limit resource usage
- Prevent unauthorized access

### Access Control

- Skills respect agent permissions
- Users can only process their own files
- Audit skill execution

## References

- [Skill Library Documentation](./skill-library.md)
- [Agent Framework](./agent-framework.md)
- [File Upload API](../api/file-upload.md)
- [MinIO Integration](./minio-integration.md)
