import pytest
import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch # For mocking async methods

from fastapi.testclient import TestClient

# Application components to be tested or used in tests
# Assuming api.py is in the parent directory or PYTHONPATH is set up
# For the agent environment, we might need to adjust paths or assume they are resolvable.
# Let's assume `sources` and `api.py` are accessible.
import sys
import os

# This is a common way to ensure modules in parent directories are accessible in tests
# current_dir = os.path.dirname(os.path.abspath(__file__))
# parent_dir = os.path.dirname(current_dir)
# sys.path.insert(0, parent_dir)

from api import app as fastapi_app  # Renamed to avoid conflict with 'api' variable name if any test uses it
from api import global_provider, message_queue as global_message_queue, llm_service as global_llm_service, interaction, config
from sources.services.base_service import AgentTask
from sources.agents.casual_agent import CasualAgent
from sources.agents.browser_agent import BrowserAgent # Added for BrowserAgent tests
from sources.llm_provider import Provider # Though we'll mostly mock its methods
from sources.browser import Browser # For type hinting if needed, and for api.global_browser access
# Ensure api.global_browser is imported if used directly for patching
from api import global_browser
from sources.agents.browser_agent import Action # For mock LLM responses


# Pytest marker for async tests
pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="module")
def client():
    """
    Test client for the FastAPI application.
    This will run startup/shutdown events for the "module" scope.
    """
    # We need to ensure that the global components from api.py are fully initialized
    # by the time TestClient(fastapi_app) is called, as it triggers startup.
    # The current api.py structure initializes many things at module level,
    # and then more within startup_event.
    with TestClient(fastapi_app) as c:
        yield c
    # Shutdown events are implicitly called when the 'with' block exits.


# Test 1: /test_llm_task Endpoint Integration
async def test_api_test_llm_task_endpoint(client: TestClient, mocker):
    """
    Tests the /test_llm_task endpoint to ensure it publishes a task
    and that the LLMService would attempt to process it.
    """
    # Mock the respond_async method of the global_provider instance
    # This is the method LLMService will call.
    # Ensure global_provider is initialized by app startup triggered by TestClient
    assert global_provider is not None, "Global provider not initialized by TestClient startup"

    # We need to mock the method on the *actual instance* used by the app.
    # Patching 'api.global_provider.respond_async' should work if global_provider is the instance.
    mocked_respond = mocker.patch('api.global_provider.respond_async', new_callable=AsyncMock)
    mocked_respond.return_value = "Mocked LLM response from provider"

    test_content = "test content from http endpoint integration test"
    response = client.post("/test_llm_task", json={"content": test_content})

    assert response.status_code == 202
    response_json = response.json()
    assert "task_id" in response_json
    assert response_json["message"] == "LLM task accepted for processing."

    # Give a very short time for the published message to be picked up by LLMService
    # and for the mocked_respond to be called.
    await asyncio.sleep(0.2)

    # Assert that the LLM provider's respond_async method was called
    # This confirms the task went through the MessageQueue and LLMService tried to process it.
    mocked_respond.assert_called_once()
    # Check the content of the call if necessary
    # args, kwargs = mocked_respond.call_args
    # called_prompt = args[0]
    # assert test_content in called_prompt # LLMService process_task might modify the prompt

# Test 2: CasualAgent Full Asynchronous LLM Interaction (End-to-End style)
async def test_casual_agent_e2e_llm_interaction(client: TestClient, mocker):
    """
    Tests the CasualAgent's process method, ensuring it uses the new
    asynchronous LLM request mechanism via MessageQueue and LLMService.
    """
    assert global_provider is not None, "Global provider not initialized"
    assert global_message_queue is not None, "Global message queue not initialized"
    assert global_llm_service is not None and global_llm_service.running, "Global LLM service not running"
    assert interaction is not None, "Interaction object not initialized"

    mock_llm_response_text = "Mocked LLM thought: Okay, I will tell a joke. </think>Why did the scarecrow win an award? Because he was outstanding in his field!"

    # Patch the respond_async method on the actual global_provider instance
    mocked_provider_respond = mocker.patch('api.global_provider.respond_async', new_callable=AsyncMock)
    mocked_provider_respond.return_value = mock_llm_response_text

    casual_agent_instance = None
    casual_agent_name_from_config = config.get('MAIN', 'agent_name', fallback='Agent')
    for agent_obj in interaction.agents:
        if agent_obj.agent_name == casual_agent_name_from_config and isinstance(agent_obj, CasualAgent):
            casual_agent_instance = agent_obj
            break

    assert casual_agent_instance is not None, "CasualAgent instance not found in interaction.agents"
    assert casual_agent_instance.message_queue is not None, "CasualAgent message_queue not set"

    # Ensure reply subscription is active (it should be from startup)
    # Forcing it here for test robustness, though it might log "already active"
    if hasattr(casual_agent_instance, 'start_reply_subscription'):
       await casual_agent_instance.start_reply_subscription()
       await asyncio.sleep(0.1) # Give time for subscription if it wasn't active

    test_query = "Tell me a joke"
    answer, reasoning = await casual_agent_instance.process(test_query, None)

    mocked_provider_respond.assert_called_once()
    # The prompt sent to LLM includes memory, so it won't be just "Tell me a joke"
    # We can check if the test_query is part of the prompt sent.
    called_prompt = mocked_provider_respond.call_args[0][0]
    assert test_query in called_prompt

    expected_answer = "Why did the scarecrow win an award? Because he was outstanding in his field!"
    expected_reasoning = "<think>Okay, I will tell a joke. </think>"

    assert answer == expected_answer
    assert reasoning.strip() == expected_reasoning.strip()


# Test 3: WebSocket (/ws) Interaction with CasualAgent
async def test_websocket_ask_casual_agent(client: TestClient, mocker):
    """
    Tests WebSocket interaction with CasualAgent.
    """
    assert global_provider is not None, "Global provider not initialized"

    mock_ws_llm_response_text = "Mocked LLM thought for WebSocket: Hello there! </think>Hello, WebSocket user!"
    mocked_provider_respond_ws = mocker.patch('api.global_provider.respond_async', new_callable=AsyncMock)
    mocked_provider_respond_ws.return_value = mock_ws_llm_response_text

    websocket_query = "hello via websocket"
    with client.websocket_connect("/ws") as websocket:
        websocket.send_json({
            "command": "ask_casual_agent",
            "query": websocket_query
        })
        response_data = websocket.receive_json()

    # Give some time for async operations triggered by WebSocket command to complete
    await asyncio.sleep(0.2) # May need adjustment

    mocked_provider_respond_ws.assert_called_once()
    called_prompt_ws = mocked_provider_respond_ws.call_args[0][0]
    assert websocket_query in called_prompt_ws

    assert "answer" in response_data
    assert response_data["answer"] == "Hello, WebSocket user!"
    assert "reasoning" in response_data
    # The reasoning might have extra spaces depending on extraction, strip for safety
    assert response_data["reasoning"].strip() == "Mocked LLM thought for WebSocket: Hello there!".strip()
    assert "agent_name" in response_data
    # The agent name is configured in config.ini
    assert response_data["agent_name"] == config.get('MAIN', 'agent_name', fallback='Agent')


# A helper fixture to ensure services are reset/restarted if needed between tests,
# though TestClient with module scope should handle this for the app itself.
# For more granular control, one might need function-scoped fixtures that
# manually start/stop services or re-initialize parts of the app state.
# However, the current setup relies on the TestClient's lifecycle.

# To run these tests:
# 1. Ensure Redis server is running on redis://localhost:6379/0
# 2. Install pytest, pytest-asyncio, pytest-mock:
#    pip install pytest pytest-asyncio pytest-mock
# 3. Navigate to the directory containing the `tests` folder and `api.py` (or ensure PYTHONPATH is set).
# 4. Run: pytest
#
# Note on sys.path modification:
# The commented-out sys.path modification at the top is a common pattern if tests
# are not run using a method that automatically handles Python's module resolution
# (e.g., if not installed as a package or using `python -m pytest`).
# For this environment, I'm assuming the execution context handles path resolution.
# If ModuleNotFoundError occurs, uncommenting and adjusting that sys.path part might be needed.

# Add a placeholder test to ensure the file is picked up by pytest even if other tests are skipped/fail early
def test_placeholder():
    assert True


# Test 4: BrowserAgent Navigation via BrowserControlService
async def test_browser_agent_navigate_via_service(client: TestClient, mocker):
    """
    Tests that BrowserAgent uses BrowserControlService for navigation.
    """
    assert global_browser is not None, "Global browser not initialized by TestClient startup"

    # Mock the 'go_to' method of the actual browser instance used by BrowserControlService
    mocked_browser_go_to = mocker.patch.object(global_browser, 'go_to', return_value=True)

    browser_agent_instance = next((agent for agent in interaction.agents if isinstance(agent, BrowserAgent)), None)
    assert browser_agent_instance is not None, "BrowserAgent instance not found"
    assert browser_agent_instance.message_queue is not None, "BrowserAgent message_queue not set"

    test_url = "http://example.com/test_navigation"

    # Mock llm_request for BrowserAgent to guide its decision making
    # First LLM call (search query): not relevant for this specific test of navigation itself
    # Second LLM call (after search results): instructs to navigate
    async def llm_side_effect_for_navigate(*args, **kwargs):
        # Assuming the first argument to llm_request is the prompt string
        prompt_content = args[0]
        if "make_newsearch_prompt" in prompt_content or "search_prompt" in prompt_content : # Heuristic to detect initial search prompt
            return ("search for example.com", "reasoning for search")
        # This is the crucial part: LLM decides to navigate based on (mocked) search results
        # The prompt passed to llm_request would be from make_newsearch_prompt in BrowserAgent
        elif "example.com" in prompt_content: # Or some other condition based on mocked search results
             return (f"I will navigate to {test_url}", "reasoning to navigate")
        # Subsequent calls after successful navigation, leading to text extraction etc.
        # For this test, we only care about the navigation call.
        else:
             return ("Note: Navigated. Getting text now.", "reasoning")


    mocker.patch.object(browser_agent_instance, 'llm_request', new_callable=AsyncMock, side_effect=llm_side_effect_for_navigate)

    # Mock search tool to provide a link that the LLM will decide to navigate to.
    # The exact structure of search_result might need to match what BrowserAgent expects.
    mock_search_results = [{"link": test_url, "snippet": "Test page for navigation"}]
    mocker.patch.object(browser_agent_instance.tools['web_search'], 'execute', return_value=browser_agent_instance.stringify_search_results(mock_search_results))


    # Mock other browser actions that might be called by BrowserAgent.process after navigation
    mocker.patch.object(global_browser, 'get_text', return_value="Dummy page text after navigation.")
    mocker.patch.object(global_browser, 'get_navigable', return_value=[])
    mocker.patch.object(global_browser, 'screenshot', return_value=True)
    mocker.patch.object(global_browser, 'get_screenshot', return_value="/fake/path.png")


    # Call process with a user prompt that would trigger the mocked LLM to navigate
    await browser_agent_instance.process(f"Please go to {test_url}", None)

    # Assert that the browser's go_to method was called via the service
    # This happens because _make_service_request (called by BrowserAgent) publishes a task,
    # BrowserControlService picks it up, and its _handle_navigate calls global_browser.go_to.
    mocked_browser_go_to.assert_called_once_with(test_url)


# Test 5: BrowserAgent Get Text via BrowserControlService
async def test_browser_agent_get_text_via_service(client: TestClient, mocker):
    """
    Tests that BrowserAgent.get_page_text() uses BrowserControlService.
    """
    assert global_browser is not None, "Global browser not initialized"
    mocked_browser_get_text = mocker.patch.object(global_browser, 'get_text', return_value="Mocked page content from service")

    browser_agent_instance = next((agent for agent in interaction.agents if isinstance(agent, BrowserAgent)), None)
    assert browser_agent_instance is not None, "BrowserAgent instance not found"

    # Call the refactored get_page_text method
    page_content = await browser_agent_instance.get_page_text()

    mocked_browser_get_text.assert_called_once()
    assert page_content == "Mocked page content from service"


# Test 6: BrowserAgent Get Navigable Links via BrowserControlService
async def test_browser_agent_get_links_via_service(client: TestClient, mocker):
    """
    Tests that BrowserAgent gets navigable links via BrowserControlService during its process.
    """
    assert global_browser is not None, "Global browser not initialized"
    mock_links_data = [{"href": "/link1", "text": "Mock Link 1"}, {"href": "http://example.com/link2", "text": "Mock Link 2"}]
    # Browser.get_navigable returns List[str] of cleaned URLs.
    # So, the mock should return List[str].
    mocked_browser_get_navigable = mocker.patch.object(global_browser, 'get_navigable', return_value=["http://example.com/link1", "http://example.com/link2"])

    browser_agent_instance = next((agent for agent in interaction.agents if isinstance(agent, BrowserAgent)), None)
    assert browser_agent_instance is not None, "BrowserAgent instance not found"

    # Mock other browser interactions and LLM responses to guide 'process'
    mocker.patch.object(global_browser, 'go_to', return_value=True)
    mocker.patch.object(global_browser, 'get_text', return_value="Page text with links.")
    mocker.patch.object(global_browser, 'screenshot', return_value=True)
    mocker.patch.object(global_browser, 'get_screenshot', return_value="/fake/path.png")


    test_url_for_links_page = "http://example.com/links_page"
    async def llm_side_effect_for_get_links(*args, **kwargs):
        prompt_content = args[0]
        if "search for example.com" in prompt_content: # Initial search query response
            return ("search for example.com links page", "reasoning for search")
        elif test_url_for_links_page in prompt_content: # LLM decision to navigate
            return (f"I will navigate to {test_url_for_links_page}", "reasoning to navigate")
        elif "Page text with links" in prompt_content: # LLM decision after navigation and get_text
             # This is where get_navigable_links is called by BrowserAgent.process
             # The LLM prompt here (make_navigation_prompt) will use self.navigable_links,
             # which should have been updated by the service call.
             # The test then needs to assert self.navigable_links.
            return ("Note: Found links. Action: REQUEST_EXIT", "reasoning to exit after finding links")
        return ("Fallback LLM response", "reasoning")

    mocker.patch.object(browser_agent_instance, 'llm_request', new_callable=AsyncMock, side_effect=llm_side_effect_for_get_links)

    mock_search_results_links = [{"link": test_url_for_links_page, "snippet": "Page with links"}]
    mocker.patch.object(browser_agent_instance.tools['web_search'], 'execute', return_value=browser_agent_instance.stringify_search_results(mock_search_results_links))

    await browser_agent_instance.process(f"go to {test_url_for_links_page} and list links", None)

    mocked_browser_get_navigable.assert_called_once()
    # BrowserAgent.process updates self.navigable_links after the service call
    assert browser_agent_instance.navigable_links == ["http://example.com/link1", "http://example.com/link2"]


# Test 7: BrowserAgent Screenshot via BrowserControlService
async def test_browser_agent_screenshot_via_service(client: TestClient, mocker):
    """
    Tests that BrowserAgent takes a screenshot via BrowserControlService during its process.
    """
    assert global_browser is not None, "Global browser not initialized"
    mocked_browser_screenshot = mocker.patch.object(global_browser, 'screenshot', return_value=True)
    mocked_browser_get_screenshot = mocker.patch.object(global_browser, 'get_screenshot', return_value="/screenshots/mock_screenshot.png")

    browser_agent_instance = next((agent for agent in interaction.agents if isinstance(agent, BrowserAgent)), None)
    assert browser_agent_instance is not None, "BrowserAgent instance not found"

    mocker.patch.object(global_browser, 'go_to', return_value=True)
    mocker.patch.object(global_browser, 'get_text', return_value="Page text for screenshot test.")
    mocker.patch.object(global_browser, 'get_navigable', return_value=[]) # No links to simplify flow

    test_url_for_screenshot_page = "http://example.com/screenshot_page"
    async def llm_side_effect_for_screenshot(*args, **kwargs):
        prompt_content = args[0]
        if "search for example.com" in prompt_content:
            return ("search for example.com screenshot page", "reasoning for search")
        elif test_url_for_screenshot_page in prompt_content:
            return (f"I will navigate to {test_url_for_screenshot_page}", "reasoning to navigate")
        elif "Page text for screenshot test" in prompt_content:
            # Screenshot is taken after navigation and get_text in the process loop
            return ("Note: Page loaded. Action: REQUEST_EXIT", "reasoning to exit after screenshot (implicitly taken)")
        return ("Fallback LLM response", "reasoning")

    mocker.patch.object(browser_agent_instance, 'llm_request', new_callable=AsyncMock, side_effect=llm_side_effect_for_screenshot)

    mock_search_results_screenshot = [{"link": test_url_for_screenshot_page, "snippet": "Page for screenshot"}]
    mocker.patch.object(browser_agent_instance.tools['web_search'], 'execute', return_value=browser_agent_instance.stringify_search_results(mock_search_results_screenshot))

    await browser_agent_instance.process(f"go to {test_url_for_screenshot_page} then take screenshot and exit", None)

    mocked_browser_screenshot.assert_called_once()
    # We don't directly check the path returned by screenshot in BrowserAgent.process usually,
    # but we confirm the underlying browser method was called via the service.
    # The screenshot path is logged by BrowserControlService.
    # If we wanted to assert path, BrowserAgent would need to store it or return it from process().


# Test 8: BrowserAgent Get Form Inputs via BrowserControlService
async def test_browser_agent_get_form_inputs_via_service(client: TestClient, mocker):
    """
    Tests that BrowserAgent retrieves form inputs via BrowserControlService,
    and these inputs are part of the prompt for a subsequent LLM call.
    """
    assert global_browser is not None, "Global browser not initialized"

    mocked_form_inputs_data = ["[username]("")", "[password]("")", "[remember_me](unchecked)"]
    mocked_get_form_inputs = mocker.patch.object(global_browser, 'get_form_inputs', return_value=mocked_form_inputs_data)

    browser_agent_instance = next((agent for agent in interaction.agents if isinstance(agent, BrowserAgent)), None)
    assert browser_agent_instance is not None, "BrowserAgent instance not found"

    # Mock other browser interactions and LLM to guide 'process' to the point of make_navigation_prompt
    mocker.patch.object(global_browser, 'go_to', return_value=True)
    mocker.patch.object(global_browser, 'get_text', return_value="Login page content.")
    mocker.patch.object(global_browser, 'get_navigable', return_value=[])
    mocker.patch.object(global_browser, 'screenshot', return_value=True)
    mocker.patch.object(global_browser, 'get_screenshot', return_value="/fake/path.png")

    llm_call_count = 0
    generated_nav_prompt_with_forms = None
    test_form_page_url = "http://example.com/login_with_form"

    async def llm_side_effect_for_get_forms(*args, **kwargs):
        nonlocal llm_call_count, generated_nav_prompt_with_forms
        llm_call_count += 1
        prompt_text = args[0]
        if llm_call_count == 1: # Initial search query
            return ("search: login page with form", "reasoning")
        elif llm_call_count == 2: # Decision to navigate
            return (f"I will navigate to {test_form_page_url}", "reasoning")
        elif llm_call_count == 3: # This is the llm_decide call using make_navigation_prompt
                                  # make_navigation_prompt internally calls get_form_inputs via service
            generated_nav_prompt_with_forms = prompt_text
            return (f"Note: I see the form. Action: {Action.REQUEST_EXIT.value}", "reasoning") # Exit to stop
        return ("Unexpected LLM call", "reasoning")

    mocker.patch.object(browser_agent_instance, 'llm_request', new_callable=AsyncMock, side_effect=llm_side_effect_for_get_forms)
    mocker.patch.object(browser_agent_instance.tools['web_search'], 'execute', return_value=browser_agent_instance.stringify_search_results(
        [{"link": test_form_page_url, "snippet": "Login page with a form"}]
    ))

    await browser_agent_instance.process("go to login page and show me the form", None)

    mocked_get_form_inputs.assert_called_once()
    assert generated_nav_prompt_with_forms is not None, "Navigation prompt was not generated"
    for expected_input_str in mocked_form_inputs_data:
        assert expected_input_str in generated_nav_prompt_with_forms, f"{expected_input_str} not in navigation prompt"


# Test 9: BrowserAgent Fill Form via BrowserControlService
async def test_browser_agent_fill_form_via_service(client: TestClient, mocker):
    """
    Tests that BrowserAgent uses BrowserControlService to fill a form.
    """
    assert global_browser is not None, "Global browser not initialized"

    mocked_browser_fill_form = mocker.patch.object(global_browser, 'fill_form', return_value=True) # Assume fill_form returns True on success

    browser_agent_instance = next((agent for agent in interaction.agents if isinstance(agent, BrowserAgent)), None)
    assert browser_agent_instance is not None, "BrowserAgent instance not found"

    # Mock other browser interactions
    mocker.patch.object(global_browser, 'go_to', return_value=True)
    mocker.patch.object(global_browser, 'get_text', return_value="Page with a form to be filled.")
    mocker.patch.object(global_browser, 'get_navigable', return_value=[])
    mocker.patch.object(global_browser, 'screenshot', return_value=True)
    mocker.patch.object(global_browser, 'get_screenshot', return_value="/fake/path.png")
    # Mock get_form_inputs as it's called by make_navigation_prompt
    mocker.patch.object(global_browser, 'get_form_inputs', return_value=["[username]("")", "[password]("")"])


    llm_call_count_fill = 0
    form_data_to_fill_by_llm = ["[username](testuser)", "[password](testpass)"]
    test_login_page_url = "http://example.com/login_for_fill"

    async def mock_llm_for_filling_form(*args, **kwargs):
        nonlocal llm_call_count_fill
        llm_call_count_fill += 1
        prompt_text = args[0]
        # print(f"LLM Call {llm_call_count_fill} with prompt: {prompt_text[:200]}") # For debugging

        if llm_call_count_fill == 1: # Search for login page
            return ("search: login page to fill", "reasoning")
        elif llm_call_count_fill == 2: # Navigate to login page
            return (f"I will navigate to {test_login_page_url}", "reasoning")
        elif llm_call_count_fill == 3: # LLM sees the form (via make_navigation_prompt) and decides to fill it
            return (f"Note: I see login form. Action: {' '.join(form_data_to_fill_by_llm)}", "reasoning for filling form")
        elif llm_call_count_fill == 4: # LLM processes result of form fill (handle_update_prompt)
            # This prompt contains page text after form fill attempt
            return (f"Note: Form submitted. Action: {Action.FORM_FILLED.value}", "reasoning, form filled")
        elif llm_call_count_fill == 5: # LLM processes page after FORM_FILLED state (make_navigation_prompt again)
            return (f"Note: Login successful. Action: {Action.REQUEST_EXIT.value}", "reasoning, exiting")
        return ("Unexpected LLM call in fill_form test", "reasoning")

    mocker.patch.object(browser_agent_instance, 'llm_request', new_callable=AsyncMock, side_effect=mock_llm_for_filling_form)
    mocker.patch.object(browser_agent_instance.tools['web_search'], 'execute', return_value=browser_agent_instance.stringify_search_results(
        [{"link": test_login_page_url, "snippet": "Login page for filling test"}]
    ))

    await browser_agent_instance.process("login with testuser and testpass", None)

    mocked_browser_fill_form.assert_called_once()
    # Check arguments passed to fill_form
    args_passed, _ = mocked_browser_fill_form.call_args
    assert args_passed[0] == form_data_to_fill_by_llm # Expected: input_list
