import re


def clean_code_output(text):
    text = text.replace("```python", "")
    text = text.replace("```html", "")
    text = text.replace("```css", "")
    text = text.replace("```javascript", "")
    text = text.replace("```jsx", "")
    text = text.replace("```json", "")
    text = text.replace("```", "")
    return text.strip()


def make_safe_project_name(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = text.strip("_")
    return text[:45] or "generated_app"


def strip_command_prefix(text, prefix):
    pattern = rf"^\s*{re.escape(prefix)}\s*"
    return re.sub(pattern, "", text, flags=re.IGNORECASE).strip()
