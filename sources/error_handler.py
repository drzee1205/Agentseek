import asyncio
import time
from typing import Callable, Awaitable, TypeVar, Any

T = TypeVar('T')

class ErrorHandler:
    def __init__(self, max_retries: int = 3, delay_factor: float = 1.0):
        """
        Initializes the ErrorHandler.
        :param max_retries: Maximum number of times to retry the function.
        :param delay_factor: Base delay in seconds for exponential backoff.
        """
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative.")
        if delay_factor <= 0:
            raise ValueError("delay_factor must be positive.")

        self.max_retries = max_retries
        self.delay_factor = delay_factor

    async def with_retry(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        """
        Calls an async function with retries using exponential backoff.
        :param func: The async function to call.
        :param args: Positional arguments for the function.
        :param kwargs: Keyword arguments for the function.
        :return: The result of the function call.
        :raises: The last exception if all retries fail.
        """
        last_exception: Optional[Exception] = None
        for attempt in range(self.max_retries + 1): # +1 to include the initial attempt
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt == self.max_retries:
                    # This was the last attempt, re-raise the exception
                    if last_exception is not None: # Should always be true here
                        raise last_exception
                    else:
                        # Should be unreachable if logic is correct
                        raise RuntimeError("Retry failed without a captured exception.")

                delay = self.delay_factor * (2 ** attempt)
                # Log the retry attempt (optional, consider adding a logger instance here if needed)
                print(f"Attempt {attempt + 1}/{self.max_retries + 1} failed for {func.__name__}. Retrying in {delay:.2f} seconds. Error: {e}")
                await asyncio.sleep(delay)

        # This part should be unreachable if max_retries is non-negative
        # as either the function succeeds or the exception is re-raised.
        if last_exception is not None: # Should always be true here
            raise last_exception
        else:
            # Should be unreachable if logic is correct
            raise RuntimeError("Retry mechanism finished unexpectedly without success or final error.")


    def with_retry_sync(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Calls a synchronous function with retries using exponential backoff.
        :param func: The synchronous function to call.
        :param args: Positional arguments for the function.
        :param kwargs: Keyword arguments for the function.
        :return: The result of the function call.
        :raises: The last exception if all retries fail.
        """
        last_exception: Optional[Exception] = None
        for attempt in range(self.max_retries + 1): # +1 to include the initial attempt
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                if attempt == self.max_retries:
                    if last_exception is not None:
                        raise last_exception
                    else:
                        raise RuntimeError("Retry failed without a captured exception.")

                delay = self.delay_factor * (2 ** attempt)
                # Log the retry attempt (optional)
                print(f"Attempt {attempt + 1}/{self.max_retries + 1} failed for {func.__name__} (sync). Retrying in {delay:.2f} seconds. Error: {e}")
                time.sleep(delay)

        # This part should be unreachable
        if last_exception is not None:
            raise last_exception
        else:
            raise RuntimeError("Retry mechanism finished unexpectedly without success or final error (sync).")

# Example Usage (optional, can be removed or kept for testing)
async def example_async_func(succeed_on_attempt: int):
    print(f"Running example_async_func, current_attempt: {example_async_func.current_attempt}")
    if example_async_func.current_attempt < succeed_on_attempt:
        example_async_func.current_attempt += 1
        raise ValueError(f"Simulated error: current_attempt {example_async_func.current_attempt-1} < {succeed_on_attempt}")
    return f"Success on attempt {example_async_func.current_attempt}"

example_async_func.current_attempt = 0 # type: ignore

def example_sync_func(succeed_on_attempt: int):
    print(f"Running example_sync_func, current_attempt: {example_sync_func.current_attempt}")
    if example_sync_func.current_attempt < succeed_on_attempt:
        example_sync_func.current_attempt += 1
        raise ValueError(f"Simulated error: current_attempt {example_sync_func.current_attempt-1} < {succeed_on_attempt}")
    return f"Success on attempt {example_sync_func.current_attempt}"

example_sync_func.current_attempt = 0 # type: ignore

async def main():
    handler = ErrorHandler(max_retries=3, delay_factor=0.1)

    # Test async retry
    example_async_func.current_attempt = 0 # type: ignore
    try:
        print("\nTesting async retry (should succeed):")
        result_async = await handler.with_retry(example_async_func, succeed_on_attempt=2)
        print(f"Async result: {result_async}")
    except Exception as e:
        print(f"Async error: {e}")

    example_async_func.current_attempt = 0 # type: ignore
    try:
        print("\nTesting async retry (should fail):")
        await handler.with_retry(example_async_func, succeed_on_attempt=5) # Will exceed max_retries
    except Exception as e:
        print(f"Async error as expected: {e}")

    # Test sync retry
    handler_sync = ErrorHandler(max_retries=2, delay_factor=0.05)
    example_sync_func.current_attempt = 0 # type: ignore
    try:
        print("\nTesting sync retry (should succeed):")
        result_sync = handler_sync.with_retry_sync(example_sync_func, succeed_on_attempt=1)
        print(f"Sync result: {result_sync}")
    except Exception as e:
        print(f"Sync error: {e}")

    example_sync_func.current_attempt = 0 # type: ignore
    try:
        print("\nTesting sync retry (should fail):")
        handler_sync.with_retry_sync(example_sync_func, succeed_on_attempt=4)
    except Exception as e:
        print(f"Sync error as expected: {e}")


if __name__ == "__main__":
    # This is just for testing the ErrorHandler independently.
    # Note: main() is an async function.
    # To run it:
    # import asyncio
    # asyncio.run(main())
    # For simplicity, we might not run this directly in the agent's environment
    # but it's good for standalone testing.
    # Example:
    # python sources/error_handler.py
    # (and then manually call asyncio.run(main()) in a python interpreter if needed for async)
    pass
