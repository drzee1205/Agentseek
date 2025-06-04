import asyncio
from typing import Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor # Added
import inspect # Added

from sources.services.base_service import BaseService, AgentTask
from sources.browser import Browser
from sources.message_queue import MessageQueue
from sources.logger import StructuredLogger

class BrowserControlService(BaseService):
    """
    A service dedicated to handling browser control tasks, such as navigation,
    content extraction, and form interaction, using a Browser instance.
    It listens for tasks on a Redis message queue.
    """

    def __init__(self,
                 name: str = "BrowserControlService",
                 browser_instance: Optional[Browser] = None,
                 message_queue: Optional[MessageQueue] = None,
                 task_channel_name: str = "browser_tasks"):
        """
        Initializes the BrowserControlService.

        Args:
            name (str): The name of the service.
            browser_instance (Browser, optional): An instance of a Browser.
            message_queue (MessageQueue, optional): Instance of the message queue for task subscription.
            task_channel_name (str): The name of the channel to subscribe to for tasks.
        """
        super().__init__(name)
        self.browser_instance = browser_instance
        self.message_queue = message_queue
        self.task_channel_name = task_channel_name
        self._subscribe_task: Optional[asyncio.Task] = None
        self.executor = ThreadPoolExecutor(max_workers=1) # Single worker for Selenium safety

        if browser_instance:
            self.logger.info(event="Browser instance configured at initialization.")
        else:
            self.logger.warning(event="Browser instance not configured at initialization. Service may not function correctly.")

        if not message_queue:
            self.logger.error(event="MessageQueue not provided. Cannot subscribe to tasks.")

    async def _execute_browser_method(self, method_name: str, *args, **kwargs):
        """Helper to run a browser method in executor."""
        loop = asyncio.get_event_loop()
        browser_method = getattr(self.browser_instance, method_name)
        return await loop.run_in_executor(self.executor, browser_method, *args, **kwargs)

    async def _handle_navigate(self, task: AgentTask) -> Dict[str, Any]:
        payload = task.payload
        url = payload.get("url")
        self.logger.info(f"Handler called: _handle_navigate", context={"url": url, "task_id": task.id, "correlation_id": task.correlation_id})
        if not url:
            return {"success": False, "error": "URL not provided for navigate"}

        result = await self._execute_browser_method("go_to", url) # result is True/False
        return {"success": result, "data": {"status": "Navigation successful" if result else "Navigation failed"}}

    async def _handle_get_text(self, task: AgentTask) -> Dict[str, Any]:
        # payload = task.payload # No specific payload for get_text other than optional selector (not used by Browser.get_text())
        self.logger.info(f"Handler called: _handle_get_text", context={"task_id": task.id, "correlation_id": task.correlation_id})
        text = await self._execute_browser_method("get_text")
        if text is not None:
            return {"success": True, "data": {"text_content": text}}
        else:
            return {"success": False, "error": "Failed to get text content"}

    async def _handle_click_element(self, task: AgentTask) -> Dict[str, Any]:
        payload = task.payload
        selector = payload.get("selector") # XPath
        self.logger.info(f"Handler called: _handle_click_element", context={"selector": selector, "task_id": task.id, "correlation_id": task.correlation_id})
        if not selector:
            return {"success": False, "error": "Selector (XPath) not provided for click_element"}

        result = await self._execute_browser_method("click_element", selector)
        return {"success": result, "data": {"clicked": result}}

    async def _handle_fill_form(self, task: AgentTask) -> Dict[str, Any]:
        payload = task.payload
        input_list = payload.get("input_list") # Expected: List[str] like ["name1(value1)", "name2(value2)"]
        self.logger.info(f"Handler called: _handle_fill_form", context={"input_list_count": len(input_list) if input_list else 0, "task_id": task.id, "correlation_id": task.correlation_id})
        if not input_list or not isinstance(input_list, list):
            return {"success": False, "error": "input_list (List[str]) not provided or invalid for fill_form"}

        result = await self._execute_browser_method("fill_form", input_list)
        return {"success": result, "data": {"form_filled": result}}

    async def _handle_get_navigable_links(self, task: AgentTask) -> Dict[str, Any]:
        # payload = task.payload # No specific payload needed
        self.logger.info(f"Handler called: _handle_get_navigable_links", context={"task_id": task.id, "correlation_id": task.correlation_id})
        links = await self._execute_browser_method("get_navigable")
        return {"success": True, "data": {"links": links}}

    async def _handle_screenshot(self, task: AgentTask) -> Dict[str, Any]:
        payload = task.payload
        path_payload = payload.get("path") # Optional path from payload
        filename = path_payload if path_payload else 'updated_screen.png'
        self.logger.info(f"Handler called: _handle_screenshot", context={"filename": filename, "task_id": task.id, "correlation_id": task.correlation_id})

        success = await self._execute_browser_method("screenshot", filename)
        if success:
            # get_screenshot() in Browser class returns a fixed path, so we use that.
            actual_path = self.browser_instance.get_screenshot() # This needs to be run in executor if it interacts with driver state.
                                                              # However, it seems to just return a string. Let's assume it's safe.
                                                              # If not, wrap it: actual_path = await self._execute_browser_method("get_screenshot")
            return {"success": True, "data": {"screenshot_path": actual_path}}
        else:
            return {"success": False, "error": "Failed to take screenshot"}

    async def _handle_get_current_url(self, task: AgentTask) -> Dict[str, Any]:
        # payload = task.payload # No specific payload
        self.logger.info(f"Handler called: _handle_get_current_url", context={"task_id": task.id, "correlation_id": task.correlation_id})
        current_url = await self._execute_browser_method("get_current_url")
        return {"success": True, "data": {"url": current_url}}

    async def _handle_go_back(self, task: AgentTask) -> Dict[str, Any]:
        # payload = task.payload # No specific payload
        self.logger.info(f"Handler called: _handle_go_back", context={"task_id": task.id, "correlation_id": task.correlation_id})
        loop = asyncio.get_event_loop()
        # Special case for driver.back() as it's not a method of Browser class directly
        await loop.run_in_executor(self.executor, self.browser_instance.driver.back)
        return {"success": True, "data": {"status": "Navigated back"}}

    async def _handle_get_form_inputs(self, task: AgentTask) -> Dict[str, Any]:
        # payload = task.payload # No specific payload, get_form_inputs gets all on page
        self.logger.info(f"Handler called: _handle_get_form_inputs", context={"task_id": task.id, "correlation_id": task.correlation_id})
        form_inputs = await self._execute_browser_method("get_form_inputs")
        return {"success": True, "data": {"inputs": form_inputs}}

    async def process_task(self, task: AgentTask) -> Dict[str, Any]:
        """
        Processes browser control tasks by dispatching to appropriate handlers.
        """
        self.logger.info(f"Processing browser task: {task.type}",
                         context={"task_id": task.id, "correlation_id": task.correlation_id, "task_type": task.type})

        if not self.browser_instance:
            self.logger.error("Browser instance not available. Cannot process browser task.",
                              context={"task_id": task.id, "correlation_id": task.correlation_id})
            return {"success": False, "error": "Browser instance not configured for this service."}

        task_type_to_handler = {
            "browser_navigate": self._handle_navigate,
            "browser_get_text": self._handle_get_text,
            "browser_click_element": self._handle_click_element,
            "browser_fill_form": self._handle_fill_form,
            "browser_get_navigable_links": self._handle_get_navigable_links,
            "browser_screenshot": self._handle_screenshot,
            "browser_get_current_url": self._handle_get_current_url,
            "browser_go_back": self._handle_go_back,
            "browser_get_form_inputs": self._handle_get_form_inputs,
        }

        handler = task_type_to_handler.get(task.type)
        if handler:
            try:
                # Pass the whole task object to the handler
                return await handler(task)
            except Exception as e:
                self.logger.error(f"Error processing browser task {task.type}",
                                  context={"task_id": task.id, "correlation_id": task.correlation_id, "error": str(e)}, exc_info=True)
                return {"success": False, "error": f"Error in {task.type}: {str(e)}"}
        else:
            self.logger.warning(f"Unsupported browser task type: {task.type}",
                                context={"task_id": task.id, "correlation_id": task.correlation_id})
            return {"success": False, "error": f"Unsupported browser task type: {task.type}"}

    async def _handle_queued_task(self, task_data: Dict[str, Any]):
        """
        Callback for handling tasks received from the message queue.
        Reconstructs an AgentTask and processes it, then sends reply if needed.
        """
        self.logger.info(event="BrowserService received task data from queue",
                         context={"channel": self.task_channel_name, "raw_task_data_snippet": str(task_data)[:200]})
        try:
            if not all(k in task_data for k in ["id", "type", "payload"]):
                self.logger.error(event="Invalid task data for BrowserService", context={"missing_keys": True, "data_keys": list(task_data.keys())})
                return

            agent_task = AgentTask(
                id=task_data["id"],
                type=task_data["type"],
                payload=task_data["payload"],
                priority=task_data.get("priority", 1),
                correlation_id=task_data.get("correlation_id"),
                reply_to_channel=task_data.get("reply_to_channel")
            )

            result = await self.process_task(agent_task)

            self.logger.info(event="BrowserService processed queued task",
                             context={"task_id": agent_task.id,
                                      "correlation_id": agent_task.correlation_id,
                                      "result_success": result.get("success")})

            if agent_task.reply_to_channel and agent_task.correlation_id:
                response_payload = {
                    "correlation_id": agent_task.correlation_id,
                    "data": result
                }
                await self.message_queue.publish(agent_task.reply_to_channel, response_payload)
                self.logger.info(event="BrowserService published response to reply channel",
                                 context={"channel": agent_task.reply_to_channel,
                                          "correlation_id": agent_task.correlation_id})
        except Exception as e:
            self.logger.error(event="BrowserService error handling queued task",
                              context={"error": str(e), "task_data_snippet": str(task_data)[:200]}, exc_info=True)
            reply_to = task_data.get("reply_to_channel")
            corr_id = task_data.get("correlation_id")
            if reply_to and corr_id and self.message_queue:
                error_response = {
                    "correlation_id": corr_id,
                    "data": {"success": False, "error": f"BrowserService failed to process task: {str(e)}"}
                }
                try:
                    await self.message_queue.publish(reply_to, error_response)
                except Exception as pub_e:
                    self.logger.error(event="BrowserService failed to publish error response",
                                      context={"channel": reply_to, "correlation_id": corr_id, "error": str(pub_e)})

    async def _subscribe_to_tasks(self):
        if not self.message_queue:
            self.logger.error("BrowserService: MessageQueue not configured. Cannot subscribe.")
            return
        self.logger.info(f"BrowserService starting task subscription on channel: {self.task_channel_name}")
        try:
            await self.message_queue.subscribe(self.task_channel_name, self._handle_queued_task)
        except Exception as e:
            self.logger.error(f"BrowserService task subscription failed or stopped: {str(e)}", exc_info=True)
        finally:
            self.logger.info(f"BrowserService task subscription loop ended for channel: {self.task_channel_name}")

    async def start(self):
        if self.running:
            self.logger.warning("BrowserService already running.")
            return
        self.running = True
        self.logger.info("BrowserService starting...")
        if not self.message_queue:
            self.logger.error("BrowserService cannot start: MessageQueue not configured.")
            self.running = False
            return
        if not self.browser_instance:
            self.logger.warning("BrowserService starting without a configured Browser instance. Most tasks will fail.")

        self._subscribe_task = asyncio.create_task(self._subscribe_to_tasks())
        self.logger.info(f"BrowserService started, listening on {self.task_channel_name}")

    async def stop(self):
        self.logger.info("BrowserService stopping...")
        self.running = False
        if self._subscribe_task and not self._subscribe_task.done():
            self._subscribe_task.cancel()
            try:
                await self._subscribe_task
            except asyncio.CancelledError:
                self.logger.info("BrowserService subscription task cancelled as expected.")
            except Exception as e:
                self.logger.error(f"Error during BrowserService subscription task shutdown: {str(e)}", exc_info=True)

        await self.close_executor() # Add this line
        await super().stop()
        self.logger.info("BrowserService stopped.")

    async def close_executor(self):
        """Shuts down the ThreadPoolExecutor."""
        if self.executor:
            self.logger.info("Shutting down browser service executor.")
            self.executor.shutdown(wait=True) # Allow pending tasks to complete
            self.logger.info("Browser service executor shut down.")

# Example usage (for testing or direct invocation if needed)
if __name__ == "__main__":
    # This example assumes a running Redis server and a Browser class implementation.
    # For standalone testing, a mock Browser and MessageQueue might be needed.

    async def main_test_browser_service():
        logger_main = StructuredLogger("BrowserServiceTest")
        logger_main.info("Starting BrowserService test setup...")

        # Mock a Browser instance
        class MockBrowser:
            async def go_to(self, url): logger_main.info(f"MockBrowser: Navigating to {url}"); await asyncio.sleep(0.1)
            # ... other methods with async sleep ...

        mock_browser = MockBrowser()

        # Setup MessageQueue (requires Redis server)
        redis_url = "redis://localhost:6379/0"
        try:
            r_check = aioredis.from_url(redis_url) # Requires import redis.asyncio as aioredis
            await r_check.ping()
            await r_check.close()
            logger_main.info("Successfully connected to Redis for test.")
        except Exception as e:
            logger_main.error(f"Redis connection failed at {redis_url}. Skipping test. Error: {e}")
            return

        mq = MessageQueue(redis_url=redis_url, service_name="TestMQForBrowser")

        browser_service = BrowserControlService(
            browser_instance=mock_browser,
            message_queue=mq,
            task_channel_name="test_browser_tasks_channel"
        )

        await browser_service.start()
        logger_main.info("BrowserService started for test.")

        # Simulate publishing a task
        test_task_id = f"task_{uuid.uuid4()}"
        test_corr_id = f"corr_{uuid.uuid4()}"
        reply_channel = "test_browser_replies"

        async def reply_handler(data):
            logger_main.info(f"Test reply handler received: {data}")
            if data.get("correlation_id") == test_corr_id:
                # In a real test, you might set an asyncio.Event or Future here
                logger_main.info(f"SUCCESS: Received reply for {test_corr_id}")

        reply_sub_task = asyncio.create_task(mq.subscribe(reply_channel, reply_handler))
        await asyncio.sleep(0.1) # Ensure subscriber is active

        task_payload = {
            "id": test_task_id,
            "type": "browser_navigate",
            "payload": {"url": "https://example.com"},
            "correlation_id": test_corr_id,
            "reply_to_channel": reply_channel
        }
        await mq.publish(browser_service.task_channel_name, task_payload)
        logger_main.info(f"Published test task {test_task_id} to {browser_service.task_channel_name}")

        await asyncio.sleep(1) # Wait for task processing and reply

        # Cleanup
        logger_main.info("Stopping test components...")
        if not reply_sub_task.done(): reply_sub_task.cancel()
        await browser_service.stop()
        await mq.close()
        logger_main.info("Test components stopped.")

    # To run this test, ensure sources.browser.Browser and other dependencies are available
    # and a Redis server is running.
    # asyncio.run(main_test_browser_service()) # Commented out by default
    pass # Placeholder if asyncio.run is commented.
