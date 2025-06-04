
from typing import Tuple, Callable, Optional, Dict, Any # Added Optional, Dict, Any
from abc import abstractmethod
import os
import random
import time
import uuid # Added uuid
import dataclasses # For AgentTask to dict conversion

import asyncio
from concurrent.futures import ThreadPoolExecutor

from sources.memory import Memory
from sources.utility import pretty_print
from sources.schemas import executorResult
from sources.logger import StructuredLogger # Added for agent-specific logging
from sources.message_queue import MessageQueue # Added MessageQueue
from sources.services.base_service import AgentTask # Added AgentTask


random.seed(time.time())

class Agent():
    """
    An abstract class for all agents.
    """
    def __init__(self, name: str,
                       prompt_path: str,
                       provider, # This is the LLM provider
                       verbose: bool = False,
                       browser=None,
                       message_queue: Optional[MessageQueue] = None) -> None: # Added message_queue
        """
        Args:
            name (str): Name of the agent.
            prompt_path (str): Path to the prompt file for the agent.
            provider: The provider for the LLM.
            recover_last_session (bool, optional): Whether to recover the last conversation. 
            verbose (bool, optional): Enable verbose logging if True. Defaults to False.
            browser: The browser class for web navigation (only for browser agent).
        """
            
        self.agent_name = name
        self.browser = browser
        self.role = None
        self.type = None
        self.current_directory = os.getcwd()
        self.llm = provider 
        self.memory = None
        self.tools = {}
        self.blocks_result = []
        self.success = True
        self.last_answer = ""
        self.last_reasoning = ""
        self.status_message = "Haven't started yet"
        self.stop = False
        self.verbose = verbose
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.logger = StructuredLogger(service_name=f"Agent.{self.agent_name}") # Agent-specific logger

        # For MessageQueue based LLM interaction
        self.message_queue = message_queue
        self._llm_response_futures: Dict[str, asyncio.Future] = {}
        self._reply_subscription_task: Optional[asyncio.Task] = None
        # Generate a unique reply channel for this agent instance
        self.agent_reply_channel = f"agent_replies:{self.agent_name.replace(' ', '_')}:{uuid.uuid4()}"

        if self.message_queue:
            self.logger.info(f"Agent initialized with MessageQueue. Reply channel: {self.agent_reply_channel}")
        else:
            self.logger.info("Agent initialized without MessageQueue. LLM requests will use direct calls.")

    @property
    def get_agent_name(self) -> str:
        return self.agent_name
    
    @property
    def get_agent_type(self) -> str:
        return self.type
    
    @property
    def get_agent_role(self) -> str:
        return self.role
    
    @property
    def get_last_answer(self) -> str:
        return self.last_answer
    
    @property
    def get_last_reasoning(self) -> str:
        return self.last_reasoning
    
    @property
    def get_blocks(self) -> list:
        return self.blocks_result
    
    @property
    def get_status_message(self) -> str:
        return self.status_message

    @property
    def get_tools(self) -> dict:
        return self.tools
    
    @property
    def get_success(self) -> bool:
        return self.success
    
    def get_blocks_result(self) -> list:
        return self.blocks_result

    def add_tool(self, name: str, tool: Callable) -> None:
        if tool is not Callable:
            raise TypeError("Tool must be a callable object (a method)")
        self.tools[name] = tool
    
    def get_tools_name(self) -> list:
        """
        Get the list of tools names.
        """
        return list(self.tools.keys())
    
    def get_tools_description(self) -> str:
        """
        Get the list of tools names and their description.
        """
        description = ""
        for name in self.get_tools_name():
            description += f"{name}: {self.tools[name].description}\n"
        return description
    
    def load_prompt(self, file_path: str) -> str:
        try:
            with open(file_path, 'r', encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Prompt file not found at path: {file_path}")
        except PermissionError:
            raise PermissionError(f"Permission denied to read prompt file at path: {file_path}")
        except Exception as e:
            raise e
    
    def request_stop(self) -> None:
        """
        Request the agent to stop.
        """
        self.stop = True
        self.status_message = "Stopped"
    
    @abstractmethod
    def process(self, prompt, speech_module) -> str:
        """
        abstract method, implementation in child class.
        Process the prompt and return the answer of the agent.
        """
        pass

    def remove_reasoning_text(self, text: str) -> None:
        """
        Remove the reasoning block of reasoning model like deepseek.
        """
        end_tag = "</think>"
        end_idx = text.rfind(end_tag)
        if end_idx == -1:
            return text
        return text[end_idx+8:]
    
    def extract_reasoning_text(self, text: str) -> None:
        """
        Extract the reasoning block of a reasoning model like deepseek.
        """
        start_tag = "<think>"
        end_tag = "</think>"
        if text is None:
            return None
        start_idx = text.find(start_tag)
        end_idx = text.rfind(end_tag)+8
        return text[start_idx:end_idx]
    
    async def llm_request(self) -> Tuple[str, str]:
        """
        Asynchronously ask the LLM to process the prompt.
        """
        self.status_message = "Thinking..."

        if not self.message_queue:
            self.logger.error("MessageQueue not configured for agent. Cannot make LLM request via queue.")
            # Fallback to old synchronous method if no message queue (optional, or raise error)
            # For this refactoring, we'll raise an error if MQ is expected.
            raise RuntimeError("MessageQueue not configured for agent. LLM requests require MessageQueue.")

        # Ensure reply subscription is active
        # It's better to call this explicitly during agent setup/startup if possible,
        # but calling it here ensures it's running if not already.
        if not self._reply_subscription_task or self._reply_subscription_task.done():
            await self.start_reply_subscription()
            # Add a small delay to ensure subscription is active before publishing
            # This is a bit of a race condition, ideally managed by an explicit state.
            await asyncio.sleep(0.05)


        correlation_id = str(uuid.uuid4())
        # Get the current prompt/memory to send to the LLM
        # The agent's memory should contain the full context needed by the LLM.
        current_prompt_or_memory = self.memory.get() # Assuming this returns the string to be processed by LLM

        # Construct the AgentTask
        # The 'type' should match what LLMService expects, e.g., "analyze_content"
        # The 'payload' should contain what LLMService needs, e.g., the prompt string.
        task = AgentTask(
            id=str(uuid.uuid4()), # Unique ID for the task itself
            type="analyze_content", # Task type for LLMService
            payload={"content": current_prompt_or_memory}, # 'content' is what LLMService's process_task expects
            priority=1,
            correlation_id=correlation_id,
            reply_to_channel=self.agent_reply_channel
        )

        # Create a future for the response
        future = asyncio.Future()
        self._llm_response_futures[correlation_id] = future

        # Publish the task to the LLM service channel (e.g., "llm_tasks")
        # This channel name should be a known configuration, possibly passed to the agent or globally defined.
        llm_service_task_channel = "llm_tasks" # TODO: Make this configurable if needed

        self.logger.info(f"Publishing LLM task {task.id} to {llm_service_task_channel} with correlation_id {correlation_id} for reply on {self.agent_reply_channel}")
        await self.message_queue.publish(llm_service_task_channel, dataclasses.asdict(task))

        try:
            # Wait for the response with a timeout
            # The future result is the entire message from LLMService: {"correlation_id": ..., "data": ...}
            response_message = await asyncio.wait_for(future, timeout=60.0)
            self.logger.info(f"Received LLM response message for correlation_id {correlation_id}", context=response_message)

            response_payload_data = response_message.get("data")

            if response_payload_data is None:
                self.logger.error(f"LLMService response missing 'data' field for correlation_id {correlation_id}", context=response_message)
                raise RuntimeError("Invalid response structure from LLMService: missing 'data' field.")

            if response_payload_data.get("success"):
                thought_like_response = response_payload_data.get("result")
                if thought_like_response is None:
                    self.logger.error(f"LLMService indicated success but 'result' field is missing for correlation_id {correlation_id}", context=response_payload_data)
                    # This case should ideally not happen if LLMService guarantees "result" on success.
                    # Handle gracefully:
                    answer = "Error: LLMService returned success but no result content."
                    reasoning = "No reasoning due to missing result."
                    self.status_message = answer
                else:
                    reasoning = self.extract_reasoning_text(thought_like_response)
                    answer = self.remove_reasoning_text(thought_like_response)
                    self.memory.push('assistant', answer)
                    self.status_message = "Task completed."
                return answer, reasoning
            else:
                error_message = response_payload_data.get("error", "Unknown error from LLMService")
                self.logger.error(f"LLMService returned failure for task {task.id} (correlation_id {correlation_id}): {error_message}", context=response_payload_data)
                self.status_message = f"Error: {error_message}"
                # Raise an exception to signal failure at the agent level
                raise RuntimeError(f"LLMService task failed: {error_message}")

        except asyncio.TimeoutError:
            self.logger.error(f"Timeout waiting for LLM response for correlation_id {correlation_id}")
            self._llm_response_futures.pop(correlation_id, None) # Clean up future
            self.status_message = "Error: LLM request timed out."
            # Raise an exception or return error tuple, consistent with other failures
            raise TimeoutError(f"LLM request timed out for correlation_id {correlation_id}")
        except Exception as e:
            # Catch other exceptions, including the RuntimeError explicitly raised above or others.
            self.logger.error(f"Error during LLM request via queue for correlation_id {correlation_id}: {str(e)}", exc_info=True)
            self._llm_response_futures.pop(correlation_id, None) # Clean up future
            self.status_message = f"Error: {str(e)}"
            # Re-raise or return error tuple. Re-raising is often better for callers to handle.
            if not isinstance(e, RuntimeError) and not isinstance(e, TimeoutError): # Avoid re-wrapping our own specific exceptions
                 raise RuntimeError(f"An unexpected error occurred during LLM request: {str(e)}") from e
            else:
                raise # Re-raise RuntimeError or TimeoutError directly


    async def _llm_reply_handler(self, message: Dict[str, Any]):
        """
        Handles replies received on the agent's dedicated reply channel.
        """
        correlation_id = message.get("correlation_id")
        data = message.get("data") # This 'data' is the result from LLMService process_task

        self.logger.info(f"Received message on reply channel {self.agent_reply_channel}", context={"correlation_id": correlation_id, "has_data": data is not None})

        if correlation_id and correlation_id in self._llm_response_futures:
            future = self._llm_response_futures.pop(correlation_id)
            future.set_result(message) # Resolve the future with the whole message (which includes 'data')
            self.logger.info(f"Future resolved for correlation_id: {correlation_id}")
        else:
            self.logger.warning(f"No matching future found for correlation_id: {correlation_id} on channel {self.agent_reply_channel}. Message might be late or unexpected.", context=message)

    async def start_reply_subscription(self):
        """
        Starts the subscription to the agent's dedicated reply channel if not already active.
        """
        if not self.message_queue:
            self.logger.error("Cannot start reply subscription: MessageQueue not configured.")
            return

        if self._reply_subscription_task and not self._reply_subscription_task.done():
            self.logger.info("Reply subscription task is already active.")
            return

        try:
            self.logger.info(f"Starting reply subscription on channel: {self.agent_reply_channel}")
            self._reply_subscription_task = asyncio.create_task(
                self.message_queue.subscribe(self.agent_reply_channel, self._llm_reply_handler)
            )
            # It's good practice to handle potential exceptions from the task creation itself,
            # though subscribe() in MessageQueue should ideally handle its own internal loop errors.
        except Exception as e:
            self.logger.error(f"Failed to create reply subscription task for channel {self.agent_reply_channel}: {str(e)}")
            self._reply_subscription_task = None # Ensure it's reset if task creation fails

    async def stop_reply_subscription(self):
        """
        Stops the agent's reply subscription task.
        """
        if self._reply_subscription_task and not self._reply_subscription_task.done():
            self.logger.info(f"Stopping reply subscription on channel: {self.agent_reply_channel}")
            self._reply_subscription_task.cancel()
            try:
                await self._reply_subscription_task
                self.logger.info(f"Reply subscription task for {self.agent_reply_channel} cancelled successfully.")
            except asyncio.CancelledError:
                self.logger.info(f"Reply subscription task for {self.agent_reply_channel} was cancelled as expected.")
            except Exception as e: # Catch other potential errors during task cleanup
                self.logger.error(f"Error during reply subscription task ({self.agent_reply_channel}) shutdown: {str(e)}")
        else:
            self.logger.info(f"No active reply subscription task to stop for channel: {self.agent_reply_channel}")
        self._reply_subscription_task = None

    def sync_llm_request(self) -> Tuple[str, str]:
        """
        This method is deprecated. Synchronous calls to LLM via MessageQueue are not supported.
        Please refactor calling code to use `await agent.llm_request()`.
        """
        self.logger.error("sync_llm_request is deprecated. Direct synchronous calls to LLM via MessageQueue are not supported. Refactor usage to async.")
        raise NotImplementedError("sync_llm_request has been deprecated. Please refactor to use the asynchronous llm_request().")

    async def wait_message(self, speech_module):
        if speech_module is None:
            return
        messages = ["Please be patient, I am working on it.",
                    "Computing... I recommand you have a coffee while I work.",
                    "Hold on, I’m crunching numbers.",
                    "Working on it, please let me think."]
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, lambda: speech_module.speak(messages[random.randint(0, len(messages)-1)]))
    
    def get_last_tool_type(self) -> str:
        return self.blocks_result[-1].tool_type if len(self.blocks_result) > 0 else None
    
    def raw_answer_blocks(self, answer: str) -> str:
        """
        Return the answer with all the blocks inserted, as text.
        """
        if self.last_answer is None:
            return
        raw = ""
        lines = self.last_answer.split("\n")
        for line in lines:
            if "block:" in line:
                block_idx = int(line.split(":")[1])
                if block_idx < len(self.blocks_result):
                    raw += self.blocks_result[block_idx].__str__()
            else:
                raw += line + "\n"
        return raw

    def show_answer(self):
        """
        Show the answer in a pretty way.
        Show code blocks and their respective feedback by inserting them in the ressponse.
        """
        if self.last_answer is None:
            return
        lines = self.last_answer.split("\n")
        for line in lines:
            if "block:" in line:
                block_idx = int(line.split(":")[1])
                if block_idx < len(self.blocks_result):
                    self.blocks_result[block_idx].show()
            else:
                pretty_print(line, color="output")

    def remove_blocks(self, text: str) -> str:
        """
        Remove all code/query blocks within a tag from the answer text.
        """
        tag = f'```'
        lines = text.split('\n')
        post_lines = []
        in_block = False
        block_idx = 0
        for line in lines:
            if tag in line and not in_block:
                in_block = True
                continue
            if not in_block:
                post_lines.append(line)
            if tag in line:
                in_block = False
                post_lines.append(f"block:{block_idx}")
                block_idx += 1
        return "\n".join(post_lines)
    
    def show_block(self, block: str) -> None:
        """
        Show the block in a pretty way.
        """
        pretty_print('▂'*64, color="status")
        pretty_print(block, color="code")
        pretty_print('▂'*64, color="status")

    def execute_modules(self, answer: str) -> Tuple[bool, str]:
        """
        Execute all the tools the agent has and return the result.
        """
        feedback = ""
        success = True
        blocks = None
        if answer.startswith("```"):
            answer = "I will execute:\n" + answer # there should always be a text before blocks for the function that display answer

        self.success = True
        for name, tool in self.tools.items():
            feedback = ""
            blocks, save_path = tool.load_exec_block(answer)

            if blocks != None:
                pretty_print(f"Executing {len(blocks)} {name} blocks...", color="status")
                for block in blocks:
                    self.show_block(block)
                    output = tool.execute([block])
                    feedback = tool.interpreter_feedback(output) # tool interpreter feedback
                    success = not tool.execution_failure_check(output)
                    self.blocks_result.append(executorResult(block, feedback, success, name))
                    if not success:
                        self.success = False
                        self.memory.push('user', feedback)
                        return False, feedback
                self.memory.push('user', feedback)
                if save_path != None:
                    tool.save_block(blocks, save_path)
        return True, feedback
