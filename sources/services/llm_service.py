import asyncio # Added asyncio
from typing import Dict, Any
from sources.logger import StructuredLogger
from sources.llm_provider import Provider
from sources.services.base_service import BaseService, AgentTask
from sources.message_queue import MessageQueue # Added MessageQueue

class LLMService(BaseService):
    """
    A service dedicated to handling LLM-related tasks, such as content analysis,
    text generation, and summarization, using a specified LLM provider.
    It listens for tasks on a Redis message queue.
    """
    def __init__(self,
                 name: str = "LLMService",
                 provider: Provider = None,
                 message_queue: MessageQueue = None,
                 task_channel_name: str = "llm_tasks"):
        """
        Initializes the LLMService.

        Args:
            name (str): The name of the service.
            provider (Provider, optional): An instance of an LLM provider.
            message_queue (MessageQueue, optional): Instance of the message queue for task subscription.
            task_channel_name (str): The name of the channel to subscribe to for tasks.
        """
        super().__init__(name)
        self.provider = provider
        self.message_queue = message_queue
        self.task_channel_name = task_channel_name
        self._subscribe_task = None # To hold the asyncio task for subscription

        if provider:
            self.logger.info(event="LLMProvider configured at initialization", context={"provider_details": str(provider)})
        else:
            self.logger.warning(event="LLMProvider not configured at initialization.")

        if not message_queue:
            self.logger.error(event="MessageQueue not provided to LLMService. Cannot subscribe to tasks.")
            # Or raise ValueError("MessageQueue instance is required")

    async def _handle_queued_task(self, task_data: Dict[str, Any]):
        """
        Callback for handling tasks received from the message queue.
        Reconstructs an AgentTask from the received data and processes it.
        """
        self.logger.info(event="Received task data from queue", context={"channel": self.task_channel_name, "raw_task_data": task_data})
        try:
            # Basic validation and reconstruction of AgentTask
            # This assumes task_data is a dict that can directly map to AgentTask fields
            if not all(k in task_data for k in ["id", "type", "payload"]):
                self.logger.error(event="Invalid task data received from queue", context={"missing_keys": True, "data": task_data})
                return

            # Priority is optional in AgentTask, default is 1
            # Priority and new fields are optional in AgentTask, default is 1 / None
            agent_task = AgentTask(
                id=task_data["id"],
                type=task_data["type"],
                payload=task_data["payload"],
                priority=task_data.get("priority", 1),
                correlation_id=task_data.get("correlation_id"),
                reply_to_channel=task_data.get("reply_to_channel")
            )

            result = await self.process_task(agent_task) # This is Dict[str, Any]
            self.logger.info(event="Processed queued task",
                             context={"task_id": agent_task.id,
                                      "correlation_id": agent_task.correlation_id,
                                      "reply_to_channel": agent_task.reply_to_channel,
                                      "result_success": result.get("success")})

            if agent_task.reply_to_channel and agent_task.correlation_id:
                response_payload = {
                    "correlation_id": agent_task.correlation_id,
                    "data": result  # Send the entire result dict back
                }
                try:
                    await self.message_queue.publish(agent_task.reply_to_channel, response_payload)
                    self.logger.info(event="Published response to reply channel",
                                     context={"channel": agent_task.reply_to_channel,
                                              "correlation_id": agent_task.correlation_id})
                except Exception as pub_e:
                    self.logger.error(event="Failed to publish response to reply channel",
                                      context={"channel": agent_task.reply_to_channel,
                                               "correlation_id": agent_task.correlation_id,
                                               "error": str(pub_e)})
            elif agent_task.reply_to_channel:
                self.logger.warning(event="Reply channel present but no correlation ID in task, cannot send specific reply.",
                                 context={"task_id": agent_task.id, "reply_channel": agent_task.reply_to_channel})

        except Exception as e:
            self.logger.error(event="Error handling queued task",
                              context={"error": str(e),
                                       "task_data": task_data,
                                       "correlation_id": task_data.get("correlation_id")})
            # If there's an error processing but we have reply info, send an error response
            reply_to = task_data.get("reply_to_channel")
            corr_id = task_data.get("correlation_id")
            if reply_to and corr_id:
                error_response = {
                    "correlation_id": corr_id,
                    "data": {"success": False, "error": f"LLMService failed to process task: {str(e)}"}
                }
                try:
                    await self.message_queue.publish(reply_to, error_response)
                    self.logger.info(event="Published error response to reply channel",
                                     context={"channel": reply_to, "correlation_id": corr_id})
                except Exception as pub_e:
                    self.logger.error(event="Failed to publish error response to reply channel",
                                      context={"channel": reply_to, "correlation_id": corr_id, "error": str(pub_e)})

    async def _subscribe_to_tasks(self):
        """
        Subscribes to the task channel on the message queue and listens for tasks.
        """
        if not self.message_queue:
            self.logger.error(event="LLMService cannot subscribe: MessageQueue not configured.")
            return

        self.logger.info(event="LLMService starting task subscription", context={"channel": self.task_channel_name})
        try:
            # The subscribe method in MessageQueue is expected to run indefinitely
            # and handle its own exceptions internally for reconnects or logging.
            await self.message_queue.subscribe(self.task_channel_name, self._handle_queued_task)
        except Exception as e:
            # This part might be reached if message_queue.subscribe itself fails catastrophically
            # before entering its listen loop, or if it re-raises an exception from its loop.
            self.logger.error(event="LLMService task subscription failed or stopped unexpectedly", context={"channel": self.task_channel_name, "error": str(e)})
        finally:
            self.logger.info(event="LLMService task subscription loop ended", context={"channel": self.task_channel_name})


    async def process_task(self, task: AgentTask) -> Dict[str, Any]:
        """
        Processes tasks designated for the LLMService.

        Currently supports 'analyze_content' tasks. It uses the configured LLM provider
        to perform the analysis.

        Args:
            task (AgentTask): The task to be processed. Must have a `type` and `payload`.

        Returns:
            Dict[str, Any]: A dictionary containing the result.
                            If successful, includes {"success": True, "result": ...}.
                            If failed, includes {"success": False, "error": ...}.
        """
        self.logger.info(event="LLMService processing task", context={"task_id": task.id, "task_type": task.type, "correlation_id": task.correlation_id})

        if task.type == "analyze_content":
            if not self.provider:
                self.logger.error(event="LLMProvider not configured for LLMService", context={"task_id": task.id, "correlation_id": task.correlation_id})
                return {"success": False, "error": "LLMProvider not configured for LLMService"}

            # The agent's llm_request now sends 'content' in the payload directly.
            content_to_analyze = task.payload.get("content") # This should match what Agent.llm_request sends
            if not content_to_analyze:
                self.logger.error(event="No content provided for analysis in task payload", context={"task_id": task.id, "correlation_id": task.correlation_id, "payload_keys": list(task.payload.keys())})
                return {"success": False, "error": "No content provided for analysis in task payload"}

            try:
                # The content_to_analyze is expected to be the full prompt/memory from the agent.
                prompt = content_to_analyze

                if hasattr(self.provider, 'respond_async') and callable(self.provider.respond_async):
                    response_text = await self.provider.respond_async(prompt)
                elif hasattr(self.provider, 'generate_response') and callable(self.provider.generate_response):
                    response_text = await self.provider.generate_response(prompt)
                else:
                    self.logger.warning(event="Provider does not have a standard async response method. Using placeholder.", context={"task_id": task.id, "correlation_id": task.correlation_id})
                    response_text = f"Placeholder analysis of content: '{content_to_analyze[:50]}...'. LLM interaction successful."

                self.logger.info(event="LLM analysis successful", context={"task_id": task.id, "correlation_id": task.correlation_id})
                return {"success": True, "result": response_text}
            except Exception as e:
                self.logger.error(event="LLM processing error during analysis", context={"task_id": task.id, "correlation_id": task.correlation_id, "error": str(e)}, exc_info=True)
                return {"success": False, "error": f"Error during LLM processing: {str(e)}"}
        else:
            self.logger.warning(event="Unsupported task type for LLMService", context={"task_id": task.id, "task_type": task.type, "correlation_id": task.correlation_id})
            return {"success": False, "error": f"Unsupported task type for LLMService: {task.type}"}

    def set_provider(self, provider: Provider):
        """
        Configures or updates the LLM provider for this service.

        Args:
            provider (Provider): An instance of an LLM provider.
        """
        if not provider:
            self.logger.error(event="Attempted to set an invalid (None) provider.")
            # Optionally raise an error: raise ValueError("Provider cannot be None")
            return

        self.provider = provider
        self.logger.info(event="LLMProvider configured for LLMService", context={"provider_details": str(provider)})

    async def start(self):
        """
        Starts the LLMService.
        This involves starting the base service lifecycle and initiating
        the task subscription loop.
        """
        # Call super().start() if it does more than set self.running and log.
        # The current BaseService.start() has a loop, so we don't call it directly
        # as we need this service's loop to be the subscription.
        # Instead, we manage self.running directly and start our specific task.
        if self.running:
            self.logger.warning(event="LLMService already running.")
            return

        self.running = True
        self.logger.info(event="LLMService starting...")

        if not self.message_queue:
            self.logger.error(event="LLMService cannot start: MessageQueue not configured.")
            self.running = False # Ensure service doesn't stay in a broken running state
            return

        if not self.provider:
            self.logger.warning(event="LLMService starting without a configured LLM provider. Some tasks may fail.")


        # Create a task for the subscription loop
        # This allows self.start() to return while the subscription runs in the background.
        self._subscribe_task = asyncio.create_task(self._subscribe_to_tasks())
        self.logger.info(event="LLMService started and listening for tasks.", context={"channel": self.task_channel_name})

        # Keep the service "running" notionally. The actual work is in _subscribe_task.
        # The original BaseService.start() had an `await asyncio.sleep(0.1)` loop.
        # We might want a similar health-check or monitoring loop here if _subscribe_to_tasks
        # doesn't cover all "running" state activities. For now, _subscribe_task is the main activity.
        # If _subscribe_task exits, the service effectively stops processing new queue messages.
        # We can await it during stop() to ensure graceful shutdown.

    async def stop(self):
        """
        Stops the LLMService.
        This involves stopping new task processing and cleaning up resources.
        """
        self.logger.info(event="LLMService stopping...")
        self.running = False # Signal loops to stop

        if self._subscribe_task and not self._subscribe_task.done():
            self._subscribe_task.cancel()
            try:
                await self._subscribe_task
                self.logger.info(event="Subscription task cancelled successfully.")
            except asyncio.CancelledError:
                self.logger.info(event="Subscription task was cancelled as expected.")
            except Exception as e:
                self.logger.error(event="Error during subscription task shutdown", context={"error": str(e)})

        # MessageQueue.close() should be handled by the creator of MessageQueue (e.g., in api.py shutdown)
        # Provider cleanup, if any, could also be handled here or by the provider's owner.

        await super().stop() # Call base class stop for any generic cleanup
        self.logger.info(event="LLMService stopped.")


if __name__ == '__main__':
    import dataclasses # For AgentTask to dict conversion in test

    # Mock Provider for testing
    class MockLLMProvider(Provider):
        def __init__(self, model_name="mock_model"):
            # Adjust Provider.__init__ call as needed.
            # Assuming Provider's __init__ is: provider_name, model, server_address=None, is_local=False
            super().__init__(provider_name="MockProvider", model=model_name, is_local=True)
            self.logger = StructuredLogger(service_name="MockLLMProvider")

        async def respond_async(self, prompt: str, **kwargs) -> str:
            self.logger.info(event="MockLLMProvider respond_async called", context={"prompt_start": prompt[:50]})
            await asyncio.sleep(0.01) # Simulate small delay
            return f"Mocked LLM response to: {prompt[:60]}..."

        def __str__(self):
            return f"MockLLMProvider(model={self.model})"

    async def test_llm_service_with_queue():
        mock_provider = MockLLMProvider()
        # Use a separate logger for the test setup to avoid confusion with service loggers
        test_logger = StructuredLogger(service_name="TestLLMServiceSetup")

        # Setup MessageQueue
        # Ensure Redis is running at this URL for the test to pass
        redis_url = "redis://localhost:6379/0"
        try:
            # Check Redis connection briefly
            r_check = aioredis.from_url(redis_url)
            await r_check.ping()
            await r_check.close()
            test_logger.info("Successfully connected to Redis for test.")
        except Exception as e:
            test_logger.error(f"Redis connection failed at {redis_url}. Skipping test. Error: {e}")
            print(f"SKIPPING TEST: Redis connection failed at {redis_url}. Error: {e}")
            return

        message_queue = MessageQueue(redis_url=redis_url, service_name="TestMessageQueue")

        llm_service = LLMService(
            provider=mock_provider,
            message_queue=message_queue,
            task_channel_name="test_llm_channel"
        )

        # Start the LLMService (which starts its subscription)
        await llm_service.start()

        # Give a moment for subscription to establish
        await asyncio.sleep(0.2)

        # Create a sample task and publish it
        analyze_task_dict = {
            "id": "llm_queue_task_001",
            "type": "analyze_content",
            "payload": {"content": "This is a test document from the queue about AI and its future implications."},
            "priority": 2
        }

        test_logger.info(event="Publishing test task to queue", context=analyze_task_dict)
        await message_queue.publish(llm_service.task_channel_name, analyze_task_dict)

        # Wait for the service to process the task
        await asyncio.sleep(0.5) # Adjust as needed for processing time

        # To verify, check logs for "Processed queued task" or "LLM analysis successful" for task_id="llm_queue_task_001"
        # For a more robust test, the service could publish results back to another queue,
        # or this test could inspect internal state if that were exposed (generally not ideal).

        # Test with an unsupported task type via queue
        unsupported_task_dict = {
            "id": "llm_queue_task_002",
            "type": "generate_image",
            "payload": {"prompt": "A cat playing chess from queue"}
        }
        test_logger.info(event="Publishing unsupported test task to queue", context=unsupported_task_dict)
        await message_queue.publish(llm_service.task_channel_name, unsupported_task_dict)
        await asyncio.sleep(0.2)

        # Stop the service and the message queue
        await llm_service.stop()
        await message_queue.close() # Close the queue connection

        test_logger.info("LLMService with queue test finished. Check service logs for processing details.")
        print("LLMService with queue test finished. Check service logs for processing details.")

    print("Defining LLMService. Running example test requires Provider and MessageQueue definitions, and a running Redis server.")
    # asyncio.run(test_llm_service_with_queue()) # Commented out for CI/automated runs without Redis by default.
                                               # Needs `Provider` from `sources.llm_provider` to be fully working.
                                               # And `MessageQueue` from `sources.message_queue`.

# End of sources/services/llm_service.py
