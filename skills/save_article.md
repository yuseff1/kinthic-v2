# Save & Index Article Skill

## Description
This skill enables Silex to download any web article or link, summarize it, save it directly into the user's Obsidian Second Brain vault, and register its core concepts in Silex's persistent causal memory graph.

## Workflow

### 1. Web Fetching
*   Use the `read_url_content` or `browser` tool to fetch the full content of the user-provided URL.
*   If the user uploads a document file (e.g. PDF, text file) instead of a link, read its content directly from the workspace or attachment.

### 2. Content Extraction & Summarization
*   Identify the main title, author (if available), publication date, and origin URL.
*   Produce a high-fidelity summary including:
    *   **Executive Summary**: A concise 2-3 paragraph overview of the article's core thesis.
    *   **Key Takeaways**: A bulleted list of the most actionable insights.
    *   **Detailed Notes**: Structured outline of the main sections.

### 3. Save to Second Brain
*   Target directory: `D:\second-brain\articles\` (or `/mnt/d/second-brain/articles/` if running in Linux/WSL).
*   Create a clean, URL-safe file name: `D:\second-brain\articles\<Sanitized_Title>.md`.
*   Construct a standard YAML frontmatter block at the top of the file:
    ```markdown
    ---
    title: "<Title>"
    url: "<URL>"
    downloaded_at: <ISO-Timestamp>
    tags: [article, second-brain, knowledge]
    ---
    ```
*   Save the formatted summary, takeaways, and full text inside this markdown file.

### 4. Epistemic Graph Registration (Understanding)
*   To ensure you "understand" the article and can recall it later:
    *   Extract the **core facts, hypotheses, or principles** introduced in the article.
    *   Register these as new nodes in Silex's persistent knowledge graph.
    *   Create causal edges linking these concepts to relevant prior nodes in your memory.
    *   Add an observation mapping the article title to its file path so you can reference the full document later when queried.
