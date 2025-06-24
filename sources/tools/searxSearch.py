import requests
from bs4 import BeautifulSoup
import os
import sys

if __name__ == "__main__": # if running as a script for individual testing
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sources.tools.tools import Tools
from sources.utility import is_running_in_docker

class searxSearch(Tools):
    def __init__(self, base_url: str = None):
        """
        A tool for searching a SearxNG instance and extracting URLs and titles.
        """
        super().__init__()
        self.tag = "web_search"
        self.name = "searxSearch"
        self.description = "A tool for searching a SearxNG for web search"
        
        # Get base URL from environment or use intelligent default
        env_url = os.getenv("SEARXNG_BASE_URL")
        dynamic_url = os.getenv("SEARXNG_DYNAMIC_URL", "").lower() == "true"
        
        if env_url:
            # Only apply dynamic URL conversion if explicitly enabled
            if dynamic_url and is_running_in_docker() and ('127.0.0.1' in env_url or 'localhost' in env_url):
                self.base_url = env_url.replace('127.0.0.1', 'searxng').replace('localhost', 'searxng')
                print(f"Dynamic URL enabled: Using {self.base_url} instead of {env_url} in Docker")
            else:
                self.base_url = env_url
        else:
            # No env var set, use intelligent default
            self.base_url = "http://searxng:8080" if is_running_in_docker() else "http://127.0.0.1:8080"
            
        self.user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
        self.paywall_keywords = [
            "Member-only", "access denied", "restricted content", "404", "this page is not working"
        ]
        if not self.base_url:
            raise ValueError("SearxNG base URL must be provided either as an argument or via the SEARXNG_BASE_URL environment variable.")

    def link_valid(self, link):
        """check if a link is valid."""
        # TODO find a better way
        if not link.startswith("http"):
            return "Status: Invalid URL"
        
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            response = requests.get(link, headers=headers, timeout=5)
            status = response.status_code
            if status == 200:
                content = response.text.lower()
                if any(keyword in content for keyword in self.paywall_keywords):
                    return "Status: Possible Paywall"
                return "Status: OK"
            elif status == 404:
                return "Status: 404 Not Found"
            elif status == 403:
                return "Status: 403 Forbidden"
            else:
                return f"Status: {status} {response.reason}"
        except requests.exceptions.RequestException as e:
            return f"Error: {str(e)}"

    def check_all_links(self, links):
        """Check all links, one by one."""
        # TODO Make it asyncromous or smth
        statuses = []
        for i, link in enumerate(links):
            status = self.link_valid(link)
            statuses.append(status)
        return statuses
    
    def execute(self, blocks: list, safety: bool = False) -> str:
        """Executes a search query against a SearxNG instance using POST and extracts URLs and titles."""
        if not blocks:
            return "Error: No search query provided."

        query = blocks[0].strip()
        if not query:
            return "Error: Empty search query provided."

        search_url = f"{self.base_url}/search"
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Pragma': 'no-cache',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': self.user_agent
        }
        data = f"q={query}&categories=general&language=auto&time_range=&safesearch=0&theme=simple".encode('utf-8')
        try:
            response = requests.post(search_url, headers=headers, data=data, verify=False)
            response.raise_for_status()
            html_content = response.text
            soup = BeautifulSoup(html_content, 'html.parser')
            results = []
            for article in soup.find_all('article', class_='result'):
                url_header = article.find('a', class_='url_header')
                if url_header:
                    url = url_header['href']
                    title = article.find('h3').text.strip() if article.find('h3') else "No Title"
                    description = article.find('p', class_='content').text.strip() if article.find('p', class_='content') else "No Description"
                    results.append(f"Title:{title}\nSnippet:{description}\nLink:{url}")
            if len(results) == 0:
                # Check for common SearxNG error messages
                if 'CAPTCHA' in html_content:
                    return "Search temporarily unavailable: Some search engines are experiencing CAPTCHA challenges. Please try again in a moment - SearxNG will use alternative search engines."
                elif 'No results found' in html_content:
                    return f"No results found for query: {query}"
                else:
                    return "No search results found. The search engines may be temporarily unavailable."
            return "\n\n".join(results)  # Return results as a single string, separated by newlines
        except requests.exceptions.ConnectionError as e:
            # More specific error for connection issues
            if is_running_in_docker():
                raise Exception("\nCannot connect to SearxNG. Please check:\n1. Docker services are running (docker ps)\n2. SearxNG container is healthy\n3. Try: docker-compose restart searxng") from e
            else:
                raise Exception("\nCannot connect to SearxNG at http://127.0.0.1:8080. Please check:\n1. SearxNG is running (./start_services.sh)\n2. Port 8080 is not blocked") from e
        except requests.exceptions.RequestException as e:
            # Generic request errors
            if response.status_code == 503:
                return "Search service temporarily overloaded. SearxNG is switching to alternative search engines. Please try again."
            elif response.status_code == 429:
                return "Search rate limit reached. Please wait a moment before searching again."
            else:
                raise Exception(f"\nSearch request failed (HTTP {response.status_code}). SearxNG may be experiencing issues.") from e

    def execution_failure_check(self, output: str) -> bool:
        """
        Checks if the execution failed based on the output.
        """
        return "Error" in output

    def interpreter_feedback(self, output: str) -> str:
        """
        Feedback of web search to agent.
        """
        if self.execution_failure_check(output):
            return f"Web search failed: {output}"
        return f"Web search result:\n{output}"

if __name__ == "__main__":
    search_tool = searxSearch(base_url="http://127.0.0.1:8080")
    result = search_tool.execute(["are dog better than cat?"])
    print(result)
