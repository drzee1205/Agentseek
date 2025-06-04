import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional # Added Optional

from sources.logger import StructuredLogger

@dataclass
class AgentTask:
    """
    Represents a task to be processed by an agent service.
    """
    id: str
    type: str  # e.g., "navigate", "analyze_content", "execute_code"
    payload: Dict[str, Any]
    priority: int = 1  # Default priority
    correlation_id: Optional[str] = None  # For request-reply matching
    reply_to_channel: Optional[str] = None  # Channel for sending a reply

class BaseService(ABC):
    """
    Abstract base class for all agent services.
    Provides common lifecycle management and task processing interface.
    """
    def __init__(self, name: str):
        """
        Initializes the BaseService.

        Args:
            name (str): The name of the service.
        """
        self.name = name
        self.running = False
        self.logger = StructuredLogger(service_name=f"Service.{self.name}")
        self.logger.info(event="Service initializing")

    @abstractmethod
    async def process_task(self, task: AgentTask) -> Dict[str, Any]:
        """
        Processes a given agent task.

        This method must be implemented by concrete service classes. It is responsible
        for handling the task according to its type and payload, and returning a
        dictionary that represents the outcome of the task processing.

        Args:
            task (AgentTask): The task to be processed.

        Returns:
            Dict[str, Any]: A dictionary containing the result of the task processing.
                            Typically includes a "success": True/False field and other
                            relevant data or error messages.
        """
        pass

    async def start(self):
        """
        Starts the service's main operational loop.

        Services can override this for more complex startup logic. The default
        implementation sets the service to running and enters a simple loop
        that sleeps periodically. In a real scenario, this loop might poll a
        task queue or handle other continuous operations.
        """
        self.running = True
        self.logger.info(event="Service started")
        try:
            while self.running:
                # Placeholder for continuous operations or task polling.
                # For example, a service might check a Redis queue for new tasks.
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            self.logger.info(event="Service start loop cancelled.")
            # Ensure running is false if cancelled externally
            self.running = False
        finally:
            self.logger.info(event="Service run loop ended.")


    async def stop(self):
        """
        Signals the service to stop its operations.

        Sets the `running` flag to False, which should cause the main loop in `start()`
        to terminate. Services can override this for more complex shutdown procedures.
        """
        self.running = False
        self.logger.info(event="Service stopping")
        # Additional cleanup logic can be added here by overriding classes.

    # Example of a generic method that could be part of BaseService or specific services
    async def get_status(self) -> Dict[str, Any]:
        """
        Returns the current status of the service.
        """
        return {
            "service_name": self.name,
            "running": self.running,
            # Add other relevant status information here
        }

if __name__ == '__main__':
    # Example of how a concrete service might be defined and used (for testing purposes)

    class MyTestService(BaseService):
        def __init__(self):
            super().__init__(name="MyTestService")

        async def process_task(self, task: AgentTask) -> Dict[str, Any]:
            self.logger.info(event=f"Processing task in {self.name}", context={"task_id": task.id, "type": task.type})
            await asyncio.sleep(0.5) # Simulate work
            if task.type == "echo":
                return {"success": True, "response": task.payload.get("message", "No message provided")}
            return {"success": False, "error": "Unsupported task type"}

    async def test_service_lifecycle():
        service = MyTestService()

        start_task = asyncio.create_task(service.start())

        await asyncio.sleep(0.2) # Give service time to start its loop

        # Simulate task processing
        task1 = AgentTask(id="task123", type="echo", payload={"message": "Hello World"})
        result1 = await service.process_task(task1)
        print(f"Task 1 Result: {result1}")

        task2 = AgentTask(id="task456", type="unknown", payload={})
        result2 = await service.process_task(task2)
        print(f"Task 2 Result: {result2}")

        status = await service.get_status()
        print(f"Service Status: {status}")

        await service.stop() # Signal service to stop

        # Wait for the start_task to complete (i.e., the run loop to exit)
        # It might take a moment for the loop in start() to check self.running and exit
        try:
            await asyncio.wait_for(start_task, timeout=2.0)
        except asyncio.TimeoutError:
            print("Service did not stop gracefully within timeout.")
        except asyncio.CancelledError:
             print("Service start_task was cancelled externally.")


        status_after_stop = await service.get_status()
        print(f"Service Status after stop: {status_after_stop}")
        print("Test service lifecycle finished.")

    asyncio.run(test_service_lifecycle())
    print("BaseService and AgentTask definition complete.")

# End of sources/services/base_service.py
