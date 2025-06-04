import re
import time
from datetime import date
from typing import List, Tuple, Type, Dict
from enum import Enum
import asyncio

from sources.utility import pretty_print, animate_thinking
from sources.agents.agent import Agent
from sources.tools.searxSearch import searxSearch
from sources.browser import Browser
from sources.logger import Logger # Keep this if BrowserAgent has specific old logging, or remove if fully relying on self.logger from base Agent
from sources.memory import Memory
# Ensure AgentTask and dataclasses are available for _make_service_request
from sources.services.base_service import AgentTask
import dataclasses
import uuid # For generating correlation_id in _make_service_request


class Action(Enum):
    REQUEST_EXIT = "REQUEST_EXIT"
    FORM_FILLED = "FORM_FILLED"
    GO_BACK = "GO_BACK"
    NAVIGATE = "NAVIGATE"
    SEARCH = "SEARCH"
    
class BrowserAgent(Agent):
    def __init__(self, name, prompt_path, provider, verbose=False, browser=None, message_queue=None): # Added message_queue
        """
        The Browser agent is an agent that navigate the web autonomously in search of answer
        """
        # Pass message_queue to the base Agent class constructor
        super().__init__(name, prompt_path, provider, verbose, browser, message_queue=message_queue)
        self.tools = {
            "web_search": searxSearch(),
        }
        self.role = "web"
        self.type = "browser_agent"
        # self.browser is already set by super().__init__ if browser parameter is passed there.
        # If Agent base class doesn't handle self.browser, then self.browser = browser is needed here.
        # Based on Agent class, it does set self.browser.

        self.current_page = ""
        self.search_history = []
        self.navigable_links = [] # This will be populated by BrowserControlService responses
        self.last_action = Action.NAVIGATE.value # Enum value
        self.notes = []
        self.date = self.get_today_date()
        # self.logger is initialized in the base Agent class now.
        # self.logger = Logger("browser_agent.log") # This would overwrite the StructuredLogger from base.
        self.memory = Memory(self.load_prompt(prompt_path),
                        recover_last_session=False,
                        memory_compression=False,
                        model_provider=provider.get_model_name())

        # Ensure the browser_task_channel is configurable, for now hardcode or get from config
        self.browser_service_channel = "browser_tasks" # TODO: Make configurable
    
    def get_today_date(self) -> str:
        """Get the date"""
        date_time = date.today()
        return date_time.strftime("%B %d, %Y")

    def extract_links(self, search_result: str) -> List[str]:
        """Extract all links from a sentence."""
        pattern = r'(https?://\S+|www\.\S+)'
        matches = re.findall(pattern, search_result)
        trailing_punct = ".,!?;:)"
        cleaned_links = [link.rstrip(trailing_punct) for link in matches]
        self.logger.info(f"Extracted links: {cleaned_links}")
        return self.clean_links(cleaned_links)
    
    def extract_form(self, text: str) -> List[str]:
        """Extract form written by the LLM in format [input_name](value)"""
        inputs = []
        matches = re.findall(r"\[\w+\]\([^)]+\)", text)
        return matches
        
    def clean_links(self, links: List[str]) -> List[str]:
        """Ensure no '.' at the end of link"""
        links_clean = []
        for link in links:
            link = link.strip()
            if not (link[-1].isalpha() or link[-1].isdigit()):
                links_clean.append(link[:-1])
            else:
                links_clean.append(link)
        return links_clean

    def get_unvisited_links(self) -> List[str]:
        return "\n".join([f"[{i}] {link}" for i, link in enumerate(self.navigable_links) if link not in self.search_history])

    def make_newsearch_prompt(self, user_prompt: str, search_result: dict) -> str:
        search_choice = self.stringify_search_results(search_result)
        self.logger.info(f"Search results: {search_choice}")
        return f"""
        Based on the search result:
        {search_choice}
        Your goal is to find accurate and complete information to satisfy the user’s request.
        User request: {user_prompt}
        To proceed, choose a relevant link from the search results. Announce your choice by saying: "I will navigate to <link>"
        Do not explain your choice.
        """
    
    async def make_navigation_prompt(self, user_prompt: str, page_text: str) -> str: # Changed to async def
        remaining_links = self.get_unvisited_links() 
        remaining_links_text = remaining_links if remaining_links is not None else "No links remaining, do a new search."

        inputs_form_list = []
        try:
            response_data = await self._make_service_request(
                service_channel=self.browser_service_channel,
                task_type="browser_get_form_inputs",
                payload={}
            )
            # BrowserControlService for "browser_get_form_inputs" returns data: {"inputs": list_of_strings}
            inputs_form_list = response_data.get("inputs", [])
            self.logger.info("Successfully retrieved form inputs via service.", context={"count": len(inputs_form_list)})
        except (RuntimeError, TimeoutError) as e:
            self.logger.error(f"Failed to get form inputs via BrowserService: {e}")
            # Keep inputs_form_list as empty or handle error as appropriate
        inputs_form_text = '\n'.join(inputs_form_list) # Construct the text representation

        notes = '\n'.join(self.notes)
        self.logger.info(f"Making navigation prompt with page text: {page_text[:100]}...\nremaining links: {remaining_links_text}")
        self.logger.info(f"Inputs form: {inputs_form_text}") # Log the text representation
        self.logger.info(f"Notes: {notes}")

        return f"""
        You are navigating the web.

        **Current Context**

        Webpage ({self.current_page}) content:
        {page_text}

        Allowed Navigation Links:
        {remaining_links_text}

        Inputs forms:
        {inputs_form_text}

        End of webpage ({self.current_page}.

        # Instruction

        1. **Evaluate if the page is relevant for user’s query and document finding:**
          - If the page is relevant, extract and summarize key information in concise notes (Note: <your note>)
          - If page not relevant, state: "Error: <specific reason the page does not address the query>" and either return to the previous page or navigate to a new link.
          - Notes should be factual, useful summaries of relevant content, they should always include specific names or link. Written as: "On <website URL>, <key fact 1>. <Key fact 2>. <Additional insight>." Avoid phrases like "the page provides" or "I found that."
        2. **Navigate to a link by either: **
          - Saying I will navigate to (write down the full URL) www.example.com/cats
          - Going back: If no link seems helpful, say: {Action.GO_BACK.value}.
        3. **Fill forms on the page:**
          - Fill form only when relevant.
          - Use Login if username/password specified by user. For quick task create account, remember password in a note.
          - You can fill a form using [form_name](value). Don't {Action.GO_BACK.value} when filling form.
          - If a form is irrelevant or you lack informations (eg: don't know user email) leave it empty.
        4. **Decide if you completed the task**
          - Check your notes. Do they fully answer the question? Did you verify with multiple pages?
          - Are you sure it’s correct?
          - If yes to all, say {Action.REQUEST_EXIT}.
          - If no, or a page lacks info, go to another link.
          - Never stop or ask the user for help.
        
        **Rules:**
        - Do not write "The page talk about ...", write your finding on the page and how they contribute to an answer.
        - Put note in a single paragraph.
        - When you exit, explain why.
        
        # Example:
        
        Example 1 (useful page, no need go futher):
        Note: According to karpathy site LeCun net is ...
        No link seem useful to provide futher information.
        Action: {Action.GO_BACK.value}

        Example 2 (not useful, see useful link on page):
        Error: reddit.com/welcome does not discuss anything related to the user’s query.
        There is a link that could lead to the information.
        Action: navigate to http://reddit.com/r/locallama

        Example 3 (not useful, no related links):
        Error: x.com does not discuss anything related to the user’s query and no navigation link are usefull.
        Action: {Action.GO_BACK.value}

        Example 3 (clear definitive query answer found or enought notes taken):
        I took 10 notes so far with enought finding to answer user question.
        Therefore I should exit the web browser.
        Action: {Action.REQUEST_EXIT.value}

        Example 4 (loging form visible):

        Note: I am on the login page, I will type the given username and password. 
        Action:
        [username_field](David)
        [password_field](edgerunners77)

        Remember, user asked:
        {user_prompt}
        You previously took these notes:
        {notes}
        Do not Step-by-Step explanation. Write comprehensive Notes or Error as a long paragraph followed by your action.
        You must always take notes.
        """
    
    async def llm_decide(self, prompt: str, show_reasoning: bool = False) -> Tuple[str, str]:
        animate_thinking("Thinking...", color="status")
        self.memory.push('user', prompt)
        answer, reasoning = await self.llm_request()
        self.last_reasoning = reasoning
        if show_reasoning:
            pretty_print(reasoning, color="failure")
        pretty_print(answer, color="output")
        return answer, reasoning
    
    def select_unvisited(self, search_result: List[str]) -> List[str]:
        results_unvisited = []
        for res in search_result:
            if res["link"] not in self.search_history:
                results_unvisited.append(res) 
        self.logger.info(f"Unvisited links: {results_unvisited}")
        return results_unvisited

    def jsonify_search_results(self, results_string: str) -> List[str]:
        result_blocks = results_string.split("\n\n")
        parsed_results = []
        for block in result_blocks:
            if not block.strip():
                continue
            lines = block.split("\n")
            result_dict = {}
            for line in lines:
                if line.startswith("Title:"):
                    result_dict["title"] = line.replace("Title:", "").strip()
                elif line.startswith("Snippet:"):
                    result_dict["snippet"] = line.replace("Snippet:", "").strip()
                elif line.startswith("Link:"):
                    result_dict["link"] = line.replace("Link:", "").strip()
            if result_dict:
                parsed_results.append(result_dict)
        return parsed_results 
    
    def stringify_search_results(self, results_arr: List[str]) -> str:
        return '\n\n'.join([f"Link: {res['link']}\nPreview: {res['snippet']}" for res in results_arr])
    
    def parse_answer(self, text):
        lines = text.split('\n')
        saving = False
        buffer = []
        links = []
        for line in lines:
            if line == '' or 'action:' in line.lower():
                saving = False
            if "note" in line.lower():
                saving = True
            if saving:
                buffer.append(line.replace("notes:", ''))
            else:
                links.extend(self.extract_links(line))
        self.notes.append('. '.join(buffer).strip())
        return links
    
    def select_link(self, links: List[str]) -> str | None:
        for lk in links:
            if lk == self.current_page:
                self.logger.info(f"Already visited {lk}. Skipping.")
                continue
            self.logger.info(f"Selected link: {lk}")
            return lk
        self.logger.warning("No link selected.")
        return None

    async def _make_service_request(self, service_channel: str, task_type: str, payload: Dict, timeout: float = 60.0) -> Dict:
        """
        Helper method to make a request to a service via MessageQueue and await a response.
        Uses self._llm_response_futures and expects self._llm_reply_handler to be active.
        """
        if not self.message_queue:
            self.logger.error("MessageQueue not configured for agent service request.", context={"task_type": task_type, "service_channel": service_channel})
            raise RuntimeError("MessageQueue not configured for agent.")

        # Ensure reply subscription is active. This should ideally be managed by agent's lifecycle / startup.
        if not self._reply_subscription_task or self._reply_subscription_task.done():
            self.logger.info("Reply subscription not active, attempting to start it for service request.")
            await self.start_reply_subscription()
            await asyncio.sleep(0.1) # Give a moment for subscription to establish

        correlation_id = str(uuid.uuid4())
        task = AgentTask(
            id=str(uuid.uuid4()), # Task's own ID
            type=task_type,
            payload=payload,
            priority=1, # Default priority
            correlation_id=correlation_id,
            reply_to_channel=self.agent_reply_channel
        )

        future = asyncio.Future()
        self._llm_response_futures[correlation_id] = future # Using existing futures dict for now

        await self.message_queue.publish(service_channel, dataclasses.asdict(task))
        self.logger.info(f"Published task to {service_channel}", context={"task_id": task.id, "task_type": task_type, "correlation_id": correlation_id, "reply_channel": self.agent_reply_channel})

        try:
            response_message = await asyncio.wait_for(future, timeout=timeout)
            # response_message is the dict: {"correlation_id": ..., "data": {"success": ..., "data": ..., "error": ...}}
            self.logger.info(f"Received response from {service_channel} for task {task_type}", context={"correlation_id": correlation_id, "response_message": response_message})

            response_data_field = response_message.get("data", {}) # This is the content of "data" key from the MQ message

            if not response_data_field.get("success"):
                error_msg = response_data_field.get("error", f"Task {task_type} failed in service {service_channel}")
                self.logger.error(error_msg, context={"correlation_id": correlation_id, "service_channel": service_channel, "task_type": task_type, "response_data": response_data_field})
                raise RuntimeError(error_msg)
            return response_data_field.get("data", {}) # Return the 'data' sub-field of the service's successful response
        except asyncio.TimeoutError:
            self.logger.error(f"Timeout waiting for response from {service_channel} for task {task_type}", context={"correlation_id": correlation_id})
            self._llm_response_futures.pop(correlation_id, None)
            raise TimeoutError(f"Timeout waiting for {task_type} response from {service_channel}")
        except Exception as e:
            self.logger.error(f"Error in service request to {service_channel} for task {task_type}: {e}", context={"correlation_id": correlation_id}, exc_info=True)
            self._llm_response_futures.pop(correlation_id, None)
            if not isinstance(e, (RuntimeError, TimeoutError)):
                raise RuntimeError(f"Unexpected error in service request: {e}") from e
            raise # Re-raise RuntimeError or TimeoutError
    
    async def get_page_text(self, limit_to_model_ctx = False) -> Optional[str]:
        """Get the text content of the current page using BrowserControlService."""
        self.logger.info("Requesting page text via BrowserControlService.")
        page_text = None
        try:
            response = await self._make_service_request(
                service_channel=self.browser_service_channel,
                task_type="browser_get_text",
                payload={} # No specific payload needed for get_text
            )
            # Expected response format from _make_service_request (after extracting "data" field): {"text_content": "..."}
            page_text = response.get("text_content")
            if page_text is None:
                 self.logger.warning("Received no text_content in successful browser_get_text response.", context=response)
                 return "Error: No text content received from browser service." # Or None
        except (RuntimeError, TimeoutError) as e:
            self.logger.error(f"Failed to get page text via BrowserService: {e}")
            return f"Error: Could not retrieve page content ({e})" # Or None

        if page_text and limit_to_model_ctx:
            # Assuming self.memory.trim_text_to_max_ctx exists and works as intended
            original_len = len(page_text)
            page_text = self.memory.trim_text_to_max_ctx(page_text)
            self.logger.info(f"Page text trimmed for model context.", context={"original_len": original_len, "trimmed_len": len(page_text)})
        return page_text
    
    def conclude_prompt(self, user_query: str) -> str:
        annotated_notes = [f"{i+1}: {note.lower()}" for i, note in enumerate(self.notes)]
        search_note = '\n'.join(annotated_notes)
        pretty_print(f"AI notes:\n{search_note}", color="success")
        return f"""
        Following a human request:
        {user_query}
        A web browsing AI made the following finding across different pages:
        {search_note}

        Expand on the finding or step that lead to success, and provide a conclusion that answer the request. Include link when possible.
        Do not give advices or try to answer the human. Just structure the AI finding in a structured and clear way.
        You should answer in the same language as the user.
        """
    
    def search_prompt(self, user_prompt: str) -> str:
        return f"""
        Current date: {self.date}
        Make a efficient search engine query to help users with their request:
        {user_prompt}
        Example:
        User: "go to twitter, login with username toto and password pass79 to my twitter and say hello everyone "
        You: search: Twitter login page. 

        User: "I need info on the best laptops for AI this year."
        You: "search: best laptops 2025 to run Machine Learning model, reviews"

        User: "Search for recent news about space missions."
        You: "search: Recent space missions news, {self.date}"

        Do not explain, do not write anything beside the search query.
        Except if query does not make any sense for a web search then explain why and say {Action.REQUEST_EXIT.value}
        Do not try to answer query. you can only formulate search term or exit.
        """
    
    def handle_update_prompt(self, user_prompt: str, page_text: str, fill_success: bool) -> str:
        prompt = f"""
        You are a web browser.
        You just filled a form on the page.
        Now you should see the result of the form submission on the page:
        Page text:
        {page_text}
        The user asked: {user_prompt}
        Does the page answer the user’s query now? Are you still on a login page or did you get redirected?
        If it does, take notes of the useful information, write down result and say {Action.FORM_FILLED.value}.
        if it doesn’t, say: Error: Attempt to fill form didn't work {Action.GO_BACK.value}.
        If you were previously on a login form, no need to take notes.
        """
        if not fill_success:
            prompt += f"""
            According to browser feedback, the form was not filled correctly. Is that so? you might consider other strategies.
            """
        return prompt
    
    def show_search_results(self, search_result: List[str]):
        pretty_print("\nSearch results:", color="output")
        for res in search_result:
            pretty_print(f"Title: {res['title']} - ", color="info", no_newline=True)
            pretty_print(f"Link: {res['link']}", color="status")
    
    def stuck_prompt(self, user_prompt: str, unvisited: List[str]) -> str:
        """
        Prompt for when the agent repeat itself, can happen when fail to extract a link.
        """
        prompt = self.make_newsearch_prompt(user_prompt, unvisited)
        prompt += f"""
        You previously said:
        {self.last_answer}
        You must consider other options. Choose other link.
        """
        return prompt
    
    async def process(self, user_prompt: str, speech_module: type) -> Tuple[str, str]:
        """
        Process the user prompt to conduct an autonomous web search.
        Start with a google search with searxng using web_search tool.
        Then enter a navigation logic to find the answer or conduct required actions.
        Args:
          user_prompt: The user's input query
          speech_module: Optional speech output module
        Returns:
            tuple containing the final answer and reasoning
        """
        complete = False

        animate_thinking(f"Thinking...", color="status")
        mem_begin_idx = self.memory.push('user', self.search_prompt(user_prompt))
        ai_prompt, reasoning = await self.llm_request()
        if Action.REQUEST_EXIT.value in ai_prompt:
            pretty_print(f"Web agent requested exit.\n{reasoning}\n\n{ai_prompt}", color="failure")
            return ai_prompt, "" 
        animate_thinking(f"Searching...", color="status")
        self.status_message = "Searching..."
        search_result_raw = self.tools["web_search"].execute([ai_prompt], False)
        search_result = self.jsonify_search_results(search_result_raw)[:16]
        self.show_search_results(search_result)
        prompt = self.make_newsearch_prompt(user_prompt, search_result)
        unvisited = [None]
        while not complete and len(unvisited) > 0 and not self.stop:
            self.memory.clear()
            unvisited = self.select_unvisited(search_result)
            answer, reasoning = await self.llm_decide(prompt, show_reasoning = False)
            if self.stop:
                pretty_print(f"Requested stop.", color="failure")
                break
            if self.last_answer == answer:
                prompt = self.stuck_prompt(user_prompt, unvisited)
                continue
            self.last_answer = answer
            pretty_print('▂'*32, color="status")

            extracted_form = self.extract_form(answer)
            if len(extracted_form) > 0:
                self.status_message = "Filling web form..."
                self.logger.info(f"Attempting to fill form with {len(extracted_form)} extracted elements.", context={"form_elements": extracted_form})
                pretty_print(f"Filling inputs form with {len(extracted_form)} elements...", color="status")

                fill_success = False # Default to False
                try:
                    response_data = await self._make_service_request(
                        service_channel=self.browser_service_channel,
                        task_type="browser_fill_form",
                        payload={"input_list": extracted_form} # extracted_form is List[str] of format "[name](value)"
                    )
                    # BrowserControlService for "browser_fill_form" returns data: {"form_filled": boolean}
                    fill_success = response_data.get("form_filled", False)
                    self.logger.info("Form fill attempt via service reported.", context={"success": fill_success, "response_data": response_data})
                except (RuntimeError, TimeoutError) as e:
                    self.logger.error(f"Failed to fill form via BrowserService: {e}")
                    fill_success = False # Ensure it's false on error

                # page_text should be fetched *after* form submission attempt if fill_success is True.
                # However, handle_update_prompt expects page_text.
                # Let's fetch page_text regardless for now, or adjust handle_update_prompt logic.
                # Assuming form submission might change the page, so get fresh text.
                page_text_after_fill = await self.get_page_text(limit_to_model_ctx=True)
                if page_text_after_fill is None or "Error: Could not retrieve page content" in page_text_after_fill:
                     self.logger.warning("Failed to get page text after form fill attempt. Using placeholder or error for LLM.")
                     page_text_after_fill = "Error: Could not retrieve page content after form submission."


                # The original prompt for llm_decide here was 'prompt' which was the newsearch_prompt.
                # It should be the handle_update_prompt.
                update_prompt_text = self.handle_update_prompt(user_prompt, page_text_after_fill, fill_success)
                answer, reasoning = await self.llm_decide(update_prompt_text) # Use the correct prompt

            if Action.FORM_FILLED.value in answer: # This means LLM confirmed form was filled and page updated
                self.logger.info("LLM confirmed form filled. Handling page update.")
                pretty_print(f"Filled form. Handling page update.", color="status")
                # Page text was already fetched for handle_update_prompt
                # self.navigable_links = self.browser.get_navigable() # This also needs to be a service call
                try:
                    links_response = await self._make_service_request(
                        service_channel=self.browser_service_channel,
                        task_type="browser_get_navigable_links",
                        payload={}
                    )
                    self.navigable_links = links_response.get("links", [])
                except (RuntimeError, TimeoutError) as e:
                    self.logger.error(f"Failed to get navigable links after form fill: {e}")
                    self.navigable_links = []

                # Re-fetch page text if not already fresh for make_navigation_prompt
                current_page_text_for_nav_prompt = await self.get_page_text(limit_to_model_ctx=True)
                if current_page_text_for_nav_prompt is None : current_page_text_for_nav_prompt = "Error: could not load page content."
                prompt = await self.make_navigation_prompt(user_prompt, current_page_text_for_nav_prompt)
                continue

            links = self.parse_answer(answer)
            link = self.select_link(links)
            if link == self.current_page:
                pretty_print(f"Already visited {link}. Search callback.", color="status")
                prompt = self.make_newsearch_prompt(user_prompt, unvisited)
                self.search_history.append(link)
                continue

            if Action.REQUEST_EXIT.value in answer:
                self.status_message = "Exiting web browser..."
                self.logger.info("Agent requested exit based on LLM decision.")
                pretty_print(f"Agent requested exit.", color="status")
                complete = True
                break

            if (link is None and not extracted_form) or Action.GO_BACK.value in answer or (link and link in self.search_history):
                self.logger.info("Deciding to go back to search results or new search.",
                                context={"link": link, "extracted_form_empty": not extracted_form,
                                         "go_back_in_answer": Action.GO_BACK.value in answer,
                                         "link_in_history": link in self.search_history if link else False,
                                         "unvisited_count": len(unvisited)})
                pretty_print(f"Going back to results. Still {len(unvisited)} unvisited from current search.", color="status")
                self.status_message = "Going back to search results..."
                prompt = self.make_newsearch_prompt(user_prompt, unvisited) # Use remaining unvisited links from current search
                if link: self.search_history.append(link) # Mark current link as visited before going back
                self.current_page = None # Reset current page as we are going back to search
                continue

            # Navigate to the selected link
            animate_thinking(f"Navigating to {link}", color="status")
            if speech_module: speech_module.speak(f"Navigating to {link}")

            nav_ok = False
            try:
                nav_response = await self._make_service_request(
                    service_channel=self.browser_service_channel,
                    task_type="browser_navigate",
                    payload={"url": link}
                )
                # BrowserControlService for navigate returns {"success": result}
                # _make_service_request, if successful, returns the "data" field of the service response.
                # If BrowserService._handle_navigate returns {"success": True, "data": {"navigated": True}}
                # then nav_response here would be {"navigated": True} if successful.
                # For now, we assume _handle_navigate returns {"success": result_bool}, so _make_service_request gets this.
                # The current _make_service_request extracts the `data` field from the response.
                # The `BrowserService._handle_navigate` returns `{"success": result}`. This means there is no "data" field.
                # This needs alignment. Let's assume `_make_service_request` is modified to return the full service response if no "data" field.
                # Or, more simply, BrowserService._handle_navigate should return `{"success": result, "data": {"status": "navigated"}}`
                # For now, if _make_service_request doesn't raise error, assume success.
                nav_ok = True # Assume success if _make_service_request doesn't throw.
                self.logger.info(f"Navigation to {link} reported as successful by service call.", context=nav_response if 'nav_response' in locals() else {})

            except (RuntimeError, TimeoutError) as e:
                self.logger.warning(f"Navigation to {link} failed via BrowserService: {e}")
                nav_ok = False

            self.search_history.append(link) # Add to history regardless of nav_ok to avoid retrying same failing link immediately
            if not nav_ok:
                pretty_print(f"Failed to navigate to {link}.", color="failure")
                prompt = self.make_newsearch_prompt(user_prompt, unvisited) # Try a new search or different link
                continue

            self.current_page = link
            self.status_message = f"Extracting text from {link}..."
            page_text = await self.get_page_text(limit_to_model_ctx=True)

            if page_text is None or "Error: Could not retrieve page content" in page_text:
                self.logger.warning(f"Failed to get text from {link}. Going back.", context={"page_text_response": page_text})
                prompt = self.make_newsearch_prompt(user_prompt, unvisited)
                continue

            self.status_message = f"Getting navigable links from {link}..."
            try:
                links_response = await self._make_service_request(
                    service_channel=self.browser_service_channel,
                    task_type="browser_get_navigable_links",
                    payload={}
                )
                self.navigable_links = links_response.get("links", [])
            except (RuntimeError, TimeoutError) as e:
                self.logger.error(f"Failed to get navigable links from {link} via BrowserService: {e}")
                self.navigable_links = []

            prompt = await self.make_navigation_prompt(user_prompt, page_text) # await here
            self.status_message = f"Deciding next action for {link}..."
            # Screenshot can also be a task if needed, e.g. self._make_service_request(..., "browser_screenshot", ...)
            # For now, keeping direct browser.screenshot if it's simple and doesn't block.
            # However, for consistency and thread safety, it should also be a service call.
            # Let's assume self.browser.screenshot() is okay for now or will be refactored later.
            if self.browser: # Check if browser object is available (it might not be if service failed to init)
                 try:
                    screenshot_response = await self._make_service_request(
                        service_channel=self.browser_service_channel,
                        task_type="browser_screenshot",
                        payload={"path": f"{self.agent_name.replace(' ', '_')}_nav_step.png"} # Example path
                    )
                    if screenshot_response.get("screenshot_path"):
                        self.logger.info("Screenshot taken via service.", context=screenshot_response)
                    else:
                        self.logger.warning("Screenshot via service may have failed or returned no path.", context=screenshot_response)
                 except Exception as e:
                     self.logger.error(f"Error taking screenshot via service: {e}")


        pretty_print("Exited navigation, starting to summarize finding...", color="status")
        prompt = self.conclude_prompt(user_prompt)
        mem_last_idx = self.memory.push('user', prompt)
        self.status_message = "Summarizing findings..."
        answer, reasoning = await self.llm_request()
        pretty_print(answer, color="output")
        self.status_message = "Ready"
        self.last_answer = answer
        return answer, reasoning

if __name__ == "__main__":
    pass
