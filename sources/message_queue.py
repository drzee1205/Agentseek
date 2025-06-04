import asyncio
import json
import redis.asyncio as aioredis
from typing import Dict, Any, Callable, Awaitable

from sources.logger import StructuredLogger

class MessageQueue:
    """
    A class to handle message publishing and subscribing using Redis.
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0", service_name: str = "MessageQueue"):
        """
        Initializes the MessageQueue with a Redis connection.

        Args:
            redis_url (str): The URL for the Redis server.
            service_name (str): The name of the service using this message queue, for logging.
        """
        self.redis_url = redis_url
        self.redis = aioredis.from_url(self.redis_url)
        self.logger = StructuredLogger(service_name=service_name)
        self.logger.info(event="MessageQueue initialized", context={"redis_url": self.redis_url})

    async def publish(self, channel: str, message: Dict[str, Any]):
        """
        Publishes a message to a specified Redis channel.

        Args:
            channel (str): The channel to publish the message to.
            message (Dict[str, Any]): The message to publish (must be JSON serializable).
        """
        self.logger.info(event="Attempting to publish message", context={"channel": channel, "message_keys": list(message.keys())})
        try:
            json_message = json.dumps(message)
            await self.redis.publish(channel, json_message)
            self.logger.info(event="Message published successfully", context={"channel": channel})
        except TypeError as e:
            self.logger.error(event="Failed to serialize message to JSON", context={"channel": channel, "error": str(e), "message_type": str(type(message))})
            raise
        except aioredis.RedisError as e:
            self.logger.error(event="Failed to publish message to Redis", context={"channel": channel, "error": str(e)})
            raise

    async def subscribe(self, channel: str, callback: Callable[[Dict[str, Any]], Awaitable[None]]):
        """
        Subscribes to a Redis channel and processes messages using a callback.

        This method will run indefinitely, listening for messages on the specified channel.

        Args:
            channel (str): The channel to subscribe to.
            callback (Callable[[Dict[str, Any]], Awaitable[None]]):
                An asynchronous function that will be called with each received message.
        """
        pubsub = self.redis.pubsub()
        try:
            await pubsub.subscribe(channel)
            self.logger.info(event="Subscribed to channel", context={"channel": channel})
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data_str = message['data'].decode('utf-8') # Ensure data is decoded
                        parsed_data = json.loads(data_str)
                        self.logger.debug(event="Message received", context={"channel": channel, "data": parsed_data})
                        await callback(parsed_data)
                    except json.JSONDecodeError as e:
                        self.logger.error(event="Failed to parse JSON message", context={"channel": channel, "raw_data": message['data'], "error": str(e)})
                    except Exception as e:
                        self.logger.error(event="Error processing message in callback", context={"channel": channel, "error": str(e)})
                elif message['type'] == 'subscribe':
                    self.logger.info(event="Subscription confirmation", context={"channel": message.get('channel', 'N/A'), "pattern": message.get('pattern'), "subscribed_channels": message.get('data')})
                # Other message types like 'unsubscribe', 'punsubscribe', 'psubscribe' could be handled if needed.

        except aioredis.RedisError as e:
            self.logger.error(event="Redis error during subscription", context={"channel": channel, "error": str(e)})
            # Depending on the error, might attempt to reconnect or gracefully exit.
            # For now, just logging and exiting the listen loop.
        except Exception as e:
            self.logger.error(event="Unexpected error in subscribe loop", context={"channel": channel, "error": str(e)})
        finally:
            self.logger.info(event="Unsubscribing and closing pubsub", context={"channel": channel})
            if pubsub: # Ensure pubsub object exists
                try:
                    await pubsub.unsubscribe(channel) # Cleanly unsubscribe
                    await pubsub.close() # Close the pubsub connection object
                except aioredis.RedisError as e:
                    self.logger.error(event="Error during pubsub cleanup", context={"channel": channel, "error": str(e)})


    async def close(self):
        """
        Closes the Redis connection gracefully.
        """
        self.logger.info(event="Closing Redis connection")
        try:
            await self.redis.close()
            # await self.redis.wait_closed() # Ensure connection is fully closed if method exists and is needed
            self.logger.info(event="Redis connection closed successfully")
        except aioredis.RedisError as e:
            self.logger.error(event="Error closing Redis connection", context={"error": str(e)})

# Example Usage
async def example_message_handler(message: Dict[str, Any]):
    """
    A sample callback function to handle received messages.
    """
    print(f"Received message: {message}")
    # In a real application, this could trigger agent actions, update state, etc.

async def main_test():
    """
    Main function to test the MessageQueue.
    """
    # Assuming Redis is running on localhost:6379
    queue = MessageQueue(redis_url="redis://localhost:6379/0", service_name="TestQueueService")

    # Start the subscriber in a background task
    # The channel name can be anything, e.g., "agent_commands", "system_events"
    test_channel = "test_notifications"

    # It's important that the subscribe task is created and starts listening *before* messages are published.
    # Or, ensure Redis queues messages for subscribers that connect later (less typical for pub/sub, more for streams/lists).
    # For pub/sub, if no subscriber is active, messages are typically dropped.

    subscriber_task = asyncio.create_task(queue.subscribe(test_channel, example_message_handler))

    # Allow some time for the subscriber to connect and subscribe
    await asyncio.sleep(0.1) # Small delay to ensure subscription is active

    # Publish some test messages
    await queue.publish(test_channel, {"user_id": 123, "action": "login", "timestamp": "2023-10-27T10:00:00Z"})
    await queue.publish(test_channel, {"item_id": "abc", "status": "processed", "details": {"notes": "all good"}})
    await queue.publish(test_channel, {"event": "system_shutdown_warning", "delay_seconds": 300})

    # Wait a bit for messages to be processed by the subscriber
    await asyncio.sleep(0.5)

    # To stop the subscriber task, you would typically cancel it and await its completion.
    # For this simple test, we'll just let it run for a short while.
    # In a real app, the subscriber might run for the lifetime of the application.
    # For clean shutdown in this test:
    if not subscriber_task.done():
        subscriber_task.cancel()
        try:
            await subscriber_task
        except asyncio.CancelledError:
            print("Subscriber task cancelled successfully.")
        except Exception as e:
            print(f"Exception in subscriber task during cancellation: {e}")


    # Close the Redis connection
    await queue.close()
    print("Test finished.")

if __name__ == "__main__":
    # This part requires a running Redis server on redis://localhost:6379/0
    # You might need to install redis: pip install redis
    # And have a Redis server running.
    # Example: docker run -d -p 6379:6379 redis
    print("Running MessageQueue test...")
    try:
        asyncio.run(main_test())
    except ConnectionRefusedError:
        print("Connection to Redis refused. Please ensure Redis is running at redis://localhost:6379/0")
    except Exception as e:
        print(f"An error occurred during the test: {e}")
