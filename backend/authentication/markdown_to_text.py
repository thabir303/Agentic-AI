import re

def markdown_to_text(markdown_text):
    """Convert markdown formatting to plain text"""
    # Remove bold formatting **text** -> text
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', markdown_text)
    
    # Remove italic formatting *text* -> text
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    
    # Remove links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    
    # Remove headers ### text -> text
    text = re.sub(r'^#+\s*(.*)$', r'\1', text, flags=re.MULTILINE)
    
    # Remove code blocks ```text``` -> text
    text = re.sub(r'```[^`]*```', '', text)
    
    # Remove inline code `text` -> text
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Clean up extra whitespace
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = text.strip()
    
    return text
