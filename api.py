#!/usr/bin/env python3

import os, sys
import uvicorn
import aiofiles
import configparser
import asyncio
import time
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uuid
# List is already imported in line 4 by existing code (from typing import List)

from sources.llm_provider import Provider
from sources.interaction import Interaction
from sources.agents import CasualAgent, CoderAgent, FileAgent, PlannerAgent, BrowserAgent
from sources.browser import Browser, create_driver
from sources.utility import pretty_print
from sources.logger import StructuredLogger
from sources.error_handler import ErrorHandler
from sources.schemas import QueryRequest, QueryResponse, LLMTaskRequest
import traceback
import dataclasses # For dataclasses.asdict

# Service and Message Queue Imports
from sources.message_queue import MessageQueue
from sources.services.base_service import AgentTask
from sources.services.llm_service import LLMService
from sources.services.browser_service import BrowserControlService # Added
# Provider is already imported for initialize_system
# uuid is already imported
import json # Ensure json is imported
from typing import Optional # Ensure Optional is imported for type hints


from celery import Celery

api = FastAPI(title="AgenticSeek API", version="0.1.0")
celery_app = Celery("tasks", broker="redis://localhost:6379/0", backend="redis://localhost:6379/0")
celery_app.conf.update(task_track_started=True)
logger = StructuredLogger(service_name="AgenticSeekAPI")
error_handler = ErrorHandler(max_retries=3, delay_factor=1.0) # Default values, can be configured
config = configparser.ConfigParser()
config.read('config.ini')

# Global instances for MessageQueue and LLMService
# These will be initialized in the startup event
message_queue: Optional[MessageQueue] = None
llm_service: Optional[LLMService] = None
browser_service: Optional[BrowserControlService] = None # Added
global_provider: Optional[Provider] = None # To store the provider initialized by initialize_system
global_browser: Optional[Browser] = None # To store the browser instance from initialize_system


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections: # Check if connection exists before removing
            self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

api.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if not os.path.exists(".screenshots"):
    os.makedirs(".screenshots")
api.mount("/screenshots", StaticFiles(directory=".screenshots"), name="screenshots")

def initialize_system():
    global global_browser # Declare global_browser to assign to it
    stealth_mode = config.getboolean('BROWSER', 'stealth_mode')
    personality_folder = "jarvis" if config.getboolean('MAIN', 'jarvis_personality') else "base"
    languages = config["MAIN"]["languages"].split(' ')

    provider = Provider(
        provider_name=config["MAIN"]["provider_name"],
        model=config["MAIN"]["provider_model"],
        server_address=config["MAIN"]["provider_server_address"],
        is_local=config.getboolean('MAIN', 'is_local')
    )
    logger.info(event="Provider initialized", context={"provider_name": provider.provider_name, "model": provider.model})

    browser = Browser(
        create_driver(headless=config.getboolean('BROWSER', 'headless_browser'), stealth_mode=stealth_mode, lang=languages[0]),
        anticaptcha_manual_install=stealth_mode
    )
    logger.info(event="Browser initialized")
    global_browser = browser # Assign the created browser instance to the global variable

    # Agents are initialized without message_queue here, it will be set in startup_event
    agents = [
        CasualAgent(
            name=config["MAIN"]["agent_name"],
            prompt_path=f"prompts/{personality_folder}/casual_agent.txt",
            provider=provider, verbose=False, message_queue=None
        ),
        CoderAgent(
            name="coder",
            prompt_path=f"prompts/{personality_folder}/coder_agent.txt",
            provider=provider, verbose=False, message_queue=None
        ),
        FileAgent(
            name="File Agent",
            prompt_path=f"prompts/{personality_folder}/file_agent.txt",
            provider=provider, verbose=False, message_queue=None
        ),
        BrowserAgent(
            name="Browser",
            prompt_path=f"prompts/{personality_folder}/browser_agent.txt",
            provider=provider, verbose=False, browser=browser, message_queue=None
        ),
        PlannerAgent(
            name="Planner",
            prompt_path=f"prompts/{personality_folder}/planner_agent.txt",
            provider=provider, verbose=False, browser=browser, message_queue=None
        )
    ]
    logger.info(event="Agents initialized (without message_queue yet)")

    interaction_instance = Interaction(
        agents,
        tts_enabled=config.getboolean('MAIN', 'speak'),
        stt_enabled=config.getboolean('MAIN', 'listen'),
        recover_last_session=config.getboolean('MAIN', 'recover_last_session'),
        langs=languages
    )
    logger.info(event="Interaction initialized")

    # Set the global provider instance
    global global_provider
    if agents: # Provider is associated with agents
        global_provider = agents[0].provider
        if global_provider:
            logger.info(event="Global LLM provider configured from initialize_system.")
        else:
            logger.error(event="Failed to get LLM provider from initialized agents.")
    else:
        logger.error(event="No agents initialized, LLM provider not set.")

    return interaction_instance

interaction = initialize_system() # This will also set global_provider
is_generating = False
query_resp_history = []


@api.on_event("startup")
async def startup_event():
    global message_queue, llm_service, global_provider, config # Ensure config is available

    logger.info(event="API startup sequence initiated.")

    redis_url = config.get('REDIS', 'url', fallback="redis://localhost:6379/0")
    message_queue = MessageQueue(redis_url=redis_url, service_name="APIMessageQueue")
    logger.info(event="MessageQueue initialized on startup.", context={"redis_url": redis_url})

    if not global_provider:
        logger.error(event="LLM Provider not available globally after initialize_system. LLMService may not function.")
        # Optionally, try to initialize a default provider here if critical
        # For now, we rely on initialize_system to set it up.

    task_channel_name = config.get('LLM_SERVICE', 'task_channel', fallback="llm_tasks")
    if global_provider:
        llm_service = LLMService(
            provider=global_provider,
            message_queue=message_queue,
            task_channel_name=task_channel_name
        )
        logger.info(event="LLMService initialized.", context={"task_channel": task_channel_name})
        asyncio.create_task(llm_service.start()) # Start LLMService itself
        logger.info(event="LLMService startup task created.")
    else:
        logger.error(event="LLMService could not be initialized: LLM Provider is not available.")

    # Initialize BrowserControlService
    global browser_service # Declare we are using the global variable
    browser_task_channel = config.get('MESSAGE_QUEUE', 'browser_tasks_channel', fallback="browser_tasks")
    if global_browser and message_queue:
        browser_service = BrowserControlService(
            browser_instance=global_browser,
            message_queue=message_queue,
            task_channel_name=browser_task_channel
        )
        logger.info(event="BrowserControlService initialized.", context={"task_channel": browser_task_channel})
        asyncio.create_task(browser_service.start()) # Start BrowserControlService
        logger.info(event="BrowserControlService startup task created.")
    else:
        logger.error("Failed to start BrowserControlService: global_browser or message_queue not initialized.")

    # Assign message_queue to existing agents and start their reply subscriptions
    if interaction and hasattr(interaction, 'agents') and message_queue:
        for agent_instance in interaction.agents:
            if hasattr(agent_instance, 'message_queue') and agent_instance.message_queue is None:
                agent_instance.message_queue = message_queue
                logger.info(f"Assigned MessageQueue to agent: {agent_instance.agent_name}")
                if hasattr(agent_instance, 'start_reply_subscription') and callable(agent_instance.start_reply_subscription):
                    asyncio.create_task(agent_instance.start_reply_subscription())
                    logger.info(f"Created task for {agent_instance.agent_name} to start reply subscription on {getattr(agent_instance, 'agent_reply_channel', 'N/A')}.")
            elif not hasattr(agent_instance, 'message_queue'):
                 logger.warning(f"Agent {agent_instance.agent_name} does not have a message_queue attribute.")

@api.on_event("shutdown")
async def shutdown_event():
    logger.info(event="API shutdown sequence initiated.")

    # Stop agents' reply subscriptions
    if interaction and hasattr(interaction, 'agents'):
        for agent_instance in interaction.agents:
            if hasattr(agent_instance, 'stop_reply_subscription') and callable(agent_instance.stop_reply_subscription):
                logger.info(f"Stopping reply subscription for agent: {agent_instance.agent_name}")
                await agent_instance.stop_reply_subscription()
            if hasattr(agent_instance, 'message_queue') and agent_instance.message_queue is not None: # Ensure agent had a queue
                agent_instance.message_queue = None # Clear queue reference from agent

    if llm_service and llm_service.running: # Check if service is running
        logger.info(event="Stopping LLMService.")
        await llm_service.stop()

    if browser_service and browser_service.running: # Check if service is running
        logger.info("Stopping BrowserControlService.")
        await browser_service.stop()
        logger.info("BrowserControlService stopped.")

    if message_queue: # Message queue is closed last
        logger.info(event="Closing MessageQueue connection.")
        await message_queue.close()

    logger.info(event="API shutdown sequence completed.")


@api.get("/screenshot")
async def get_screenshot():
    logger.info(event="Screenshot endpoint called")
    screenshot_path = ".screenshots/updated_screen.png"
    if os.path.exists(screenshot_path):
        return FileResponse(screenshot_path)
    logger.error(event="No screenshot available", context={"path": screenshot_path})
    return JSONResponse(
        status_code=404,
        content={"error": "No screenshot available"}
    )

@api.get("/health")
async def health_check():
    logger.info(event="Health check endpoint called")
    return {"status": "healthy", "version": "0.1.0"}

@api.get("/is_active")
async def is_active():
    logger.info(event="Is active endpoint called")
    return {"is_active": interaction.is_active}

@api.get("/stop")
async def stop():
    logger.info(event="Stop endpoint called")
    interaction.current_agent.request_stop()
    return JSONResponse(status_code=200, content={"status": "stopped"})

@api.get("/latest_answer")
async def get_latest_answer():
    global query_resp_history
    if interaction.current_agent is None:
        return JSONResponse(status_code=404, content={"error": "No agent available"})
    uid = str(uuid.uuid4())
    if not any(q["answer"] == interaction.current_agent.last_answer for q in query_resp_history):
        query_resp = {
            "done": "false",
            "answer": interaction.current_agent.last_answer,
            "reasoning": interaction.current_agent.last_reasoning,
            "agent_name": interaction.current_agent.agent_name if interaction.current_agent else "None",
            "success": interaction.current_agent.success,
            "blocks": {f'{i}': block.jsonify() for i, block in enumerate(interaction.get_last_blocks_result())} if interaction.current_agent else {},
            "status": interaction.current_agent.get_status_message if interaction.current_agent else "No status available",
            "uid": uid
        }
        interaction.current_agent.last_answer = ""
        interaction.current_agent.last_reasoning = ""
        query_resp_history.append(query_resp)
        return JSONResponse(status_code=200, content=query_resp)
    if query_resp_history:
        return JSONResponse(status_code=200, content=query_resp_history[-1])
    return JSONResponse(status_code=404, content={"error": "No answer available"})

async def think_wrapper(interaction, query):
    try:
        interaction.last_query = query
        logger.info(event="Agent request processing started", context={"query": query})
        success = await error_handler.with_retry(interaction.think)
        if not success:
            interaction.last_answer = "Error: No answer from agent"
            interaction.last_reasoning = "Error: No reasoning from agent"
            interaction.last_success = False
        else:
            interaction.last_success = True
        pretty_print(interaction.last_answer)
        interaction.speak_answer()
        return success
    except Exception as e:
        logger.error(event="Error in think_wrapper", context={"error": str(e), "traceback": traceback.format_exc()})
        interaction.last_answer = f"" # Ensure this is a string, not an f-string with potential undefined vars
        interaction.last_reasoning = f"Error: {str(e)}"
        interaction.last_success = False
        raise e

@api.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    global is_generating, query_resp_history
    logger.info(event="Processing query", context={"query": request.query})
    query_resp = QueryResponse(
        done="false",
        answer="",
        reasoning="",
        agent_name="Unknown",
        success="false",
        blocks={},
        status="Ready",
        uid=str(uuid.uuid4())
    )
    if is_generating:
        logger.warning(event="Query rejected: another query processing", context={"query": request.query})
        return JSONResponse(status_code=429, content=query_resp.jsonify())

    try:
        is_generating = True
        success = await think_wrapper(interaction, request.query)
        is_generating = False

        if not success:
            query_resp.answer = interaction.last_answer
            query_resp.reasoning = interaction.last_reasoning
            return JSONResponse(status_code=400, content=query_resp.jsonify())

        if interaction.current_agent:
            blocks_json = {f'{i}': block.jsonify() for i, block in enumerate(interaction.current_agent.get_blocks_result())}
        else:
            logger.error(event="No current agent found post-think")
            blocks_json = {}
            query_resp.answer = "Error: No current agent"
            return JSONResponse(status_code=400, content=query_resp.jsonify())

        logger.info(event="Query response", context={"answer": interaction.last_answer, "blocks_count": len(blocks_json)})
        query_resp.done = "true"
        query_resp.answer = interaction.last_answer
        query_resp.reasoning = interaction.last_reasoning
        query_resp.agent_name = interaction.current_agent.agent_name
        query_resp.success = str(interaction.last_success)
        query_resp.blocks = blocks_json
        
        query_resp_dict = {
            "done": query_resp.done,
            "answer": query_resp.answer,
            "agent_name": query_resp.agent_name,
            "success": query_resp.success,
            "blocks": query_resp.blocks,
            "status": query_resp.status,
            "uid": query_resp.uid
        }
        query_resp_history.append(query_resp_dict)

        logger.info(event="Query processed successfully", context={"uid": query_resp.uid})
        return JSONResponse(status_code=200, content=query_resp.jsonify())
    except Exception as e:
        logger.error(event="Critical error in process_query", context={"error": str(e), "traceback": traceback.format_exc()})
        return JSONResponse(status_code=500, content={"error": "An internal server error occurred."})
    finally:
        logger.info(event="Query processing finished", context={"query": request.query})
        if config.getboolean('MAIN', 'save_session'):
            interaction.save_session()


@api.post("/test_llm_task", status_code=202)
async def test_llm_task_endpoint(request_data: LLMTaskRequest):
    """
    Test endpoint to publish a task to the LLMService via MessageQueue.
    Expects a JSON body with a "content" field.
    """
    logger.info(event="LLM test task endpoint called", context={"request_content_snippet": request_data.content[:50]+"..."})

    if not message_queue:
        logger.error(event="MessageQueue not initialized. Cannot publish LLM task.")
        return JSONResponse(status_code=503, content={"error": "MessageQueue service is not available."})
    if not llm_service:
         logger.error(event="LLMService not initialized. Cannot process LLM task.")
         return JSONResponse(status_code=503, content={"error": "LLMService is not available."})


    task_id = str(uuid.uuid4())
    task_payload = {"content": request_data.content}

    agent_task = AgentTask(
        id=task_id,
        type="analyze_content",
        payload=task_payload,
        priority=1
    )

    try:
        task_dict = dataclasses.asdict(agent_task)
        # Use the channel name configured for the LLMService instance
        llm_task_channel = llm_service.task_channel_name
        await message_queue.publish(
            channel=llm_task_channel,
            message=task_dict
        )
        logger.info(event="LLM task published to queue successfully", context={"task_id": task_id, "channel": llm_task_channel})
        return {"message": "LLM task accepted for processing.", "task_id": task_id}
    except Exception as e:
        logger.error(event="Failed to publish LLM task to queue", context={"error": str(e), "task_id": task_id})
        return JSONResponse(status_code=500, content={"error": f"Failed to publish LLM task: {str(e)}"})


async def process_agent_command(data: str, websocket: WebSocket):
    """
    Processes a command received from an agent via WebSocket.
    For now, logs the command and echoes it back.
    Later, this will parse commands and interact with agents.
    """
    logger.info(event="WebSocket command received", context={"client": websocket.client, "raw_data": data})

    try:
        message_payload = json.loads(data)
    except json.JSONDecodeError:
        logger.error(event="WebSocket JSONDecodeError", context={"client": websocket.client, "data": data})
        await manager.send_personal_message(json.dumps({"error": "Invalid JSON format"}), websocket)
        return

    command = message_payload.get("command")
    query = message_payload.get("query")

    if not command or not query:
        logger.error(event="WebSocket missing command or query", context={"client": websocket.client, "payload": message_payload})
        await manager.send_personal_message(json.dumps({"error": "Missing command or query field"}), websocket)
        return

    logger.info(event="WebSocket command processing", context={"client": websocket.client, "command": command, "query": query})

    if command == "ask_casual_agent":
        target_agent = None
        # Ensure interaction object and agents list are available
        if interaction and hasattr(interaction, 'agents'):
            casual_agent_name_from_config = config.get('MAIN', 'agent_name', fallback='Agent') # Default if not in config

            for agent_instance in interaction.agents:
                if agent_instance.agent_name == casual_agent_name_from_config and \
                   isinstance(agent_instance, CasualAgent): # Check type directly
                    target_agent = agent_instance
                    break

        if target_agent:
            try:
                logger.info(event="CasualAgent processing query via WebSocket",
                            context={"client": websocket.client, "agent_name": target_agent.agent_name, "query": query})

                if not target_agent.message_queue: # Check if agent is configured for MQ
                    logger.error(event="CasualAgent message_queue not configured", context={"agent_name": target_agent.agent_name})
                    await manager.send_personal_message(json.dumps({"error": "CasualAgent not properly configured (missing MessageQueue)."}), websocket)
                    return

                # Agent's process method should internally use the new llm_request
                answer, reasoning = await target_agent.process(query, None) # speech_module is None

                response = {
                    "answer": answer,
                    "reasoning": reasoning,
                    "agent_name": target_agent.agent_name
                }
                await manager.send_personal_message(json.dumps(response), websocket)
                logger.info(event="Sent response from CasualAgent via WebSocket", context={"client": websocket.client, "agent_name": target_agent.agent_name})

            except NotImplementedError as nie:
                logger.error(event="NotImplementedError in CasualAgent processing via WebSocket",
                             context={"client": websocket.client, "agent_name": target_agent.agent_name, "error": str(nie)})
                await manager.send_personal_message(json.dumps({"error": "Agent processing error: Functionality not implemented for async.", "detail": str(nie)}), websocket)
            except RuntimeError as re:
                 logger.error(event="RuntimeError in CasualAgent processing via WebSocket",
                             context={"client": websocket.client, "agent_name": target_agent.agent_name, "error": str(re)})
                 await manager.send_personal_message(json.dumps({"error": "Agent processing error: Agent not configured correctly for MessageQueue.", "detail": str(re)}), websocket)
            except Exception as e:
                logger.error(event="Error processing with CasualAgent via WebSocket",
                             context={"client": websocket.client, "agent_name": target_agent.agent_name, "error": str(e), "traceback": traceback.format_exc()})
                await manager.send_personal_message(json.dumps({"error": "An error occurred with CasualAgent", "detail": str(e)}), websocket)
        else:
            logger.error(event="CasualAgent not found for WebSocket request", context={"client": websocket.client})
            await manager.send_personal_message(json.dumps({"error": "CasualAgent not available"}), websocket)
    else:
        logger.warning(event="Unknown WebSocket command", context={"client": websocket.client, "command": command})
        await manager.send_personal_message(json.dumps({"error": "Unknown command"}), websocket)


@api.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    logger.info(event="WebSocket client connected", context={"client": websocket.client})
    try:
        while True:
            data = await websocket.receive_text()
            await process_agent_command(data, websocket)
    except WebSocketDisconnect:
        manager.disconnect(websocket) # No await here, disconnect is synchronous in list removal
        logger.info(event="WebSocket client disconnected", context={"client": websocket.client})
    except Exception as e:
        logger.error(event="WebSocket error", context={"client": websocket.client, "error": str(e), "traceback": traceback.format_exc()})
        # Ensure disconnection on other errors too
        if websocket in manager.active_connections:
            manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run(api, host="0.0.0.0", port=8000)