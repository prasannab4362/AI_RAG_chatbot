import os
import urllib.parse
import requests
from html.parser import HTMLParser

# 1. Custom DuckDuckGo HTML Parser (No APIs/Keys required)
class DDGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self.in_result = False
        self.current_tag = None
        self.temp_title = ""
        self.temp_snippet = ""
        self.temp_link = ""

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        class_name = attrs_dict.get("class", "")
        
        # Look for result div wrapper
        if tag == "div" and "result" in class_name:
            self.in_result = True
            self.temp_title = ""
            self.temp_snippet = ""
            self.temp_link = ""
            
        if self.in_result:
            if tag == "a" and "result__url" in class_name:
                self.current_tag = "title"
                self.temp_link = attrs_dict.get("href", "")
            elif tag == "a" and "result__snippet" in class_name:
                self.current_tag = "snippet"

    def handle_endtag(self, tag):
        if self.in_result:
            if tag == "a" and self.current_tag in ["title", "snippet"]:
                self.current_tag = None
            elif tag == "div" and not self.current_tag:
                # Store result when the div finishes
                if self.temp_title or self.temp_snippet:
                    self.results.append({
                        "title": self.temp_title.strip(),
                        "link": self.temp_link.strip(),
                        "snippet": self.temp_snippet.strip()
                    })
                self.in_result = False

    def handle_data(self, data):
        if self.in_result:
            if self.current_tag == "title":
                self.temp_title += data
            elif self.current_tag == "snippet":
                self.temp_snippet += data

# --- TOOL 1: Web Search ---
def web_search(query: str) -> str:
    """Searches DuckDuckGo for the query and returns formatted search results."""
    print(f"[Tool: Web Search] Querying: {query}")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    encoded_query = urllib.parse.quote(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return f"Error: Unable to fetch search results (HTTP {response.status_code})"
        
        parser = DDGParser()
        parser.feed(response.text)
        
        results = parser.results[:5]  # Limit to top 5 results
        if not results:
            return "No web results found for this search."
            
        output = []
        for idx, res in enumerate(results, 1):
            title = res["title"]
            link = res["link"]
            
            # Clean up redirection URLs if present
            if link.startswith("//"):
                link = "https:" + link
            if "uddg=" in link:
                parsed_link = urllib.parse.urlparse(link)
                query_params = urllib.parse.parse_qs(parsed_link.query)
                if "uddg" in query_params:
                    link = query_params["uddg"][0]
                    
            snippet = res["snippet"]
            output.append(f"Result #{idx}:\nTitle: {title}\nURL: {link}\nSummary: {snippet}\n")
            
        return "\n".join(output)
    except Exception as e:
        return f"Error executing search: {str(e)}"

# --- TOOL 2: File Writer (for Resumes, Reports, etc.) ---
def write_file(filename: str, content: str) -> str:
    """Writes content to a file in the workspace output folder."""
    print(f"[Tool: File Writer] Creating file: {filename}")
    try:
        # Create output directory in the workspace if it doesn't exist
        output_dir = "output"
        os.makedirs(output_dir, exist_ok=True)
        
        # Clean filename to prevent directory traversal
        safe_name = os.path.basename(filename)
        filepath = os.path.join(output_dir, safe_name)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
        return f"Success: File '{safe_name}' has been created in the 'output/' directory."
    except Exception as e:
        return f"Error writing file: {str(e)}"

# --- TOOL 3: Document Search (RAG) ---
def search_documents(query: str) -> str:
    """Searches the database of uploaded files for matching paragraphs."""
    # This will hook into our rag_engine.py later
    from rag_engine import query_documents
    print(f"[Tool: Document Search] Searching documents for: {query}")
    return query_documents(query)