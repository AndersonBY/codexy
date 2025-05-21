# -*- coding: utf-8 -*-

import unittest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from typing import List, Dict, Any, Optional

from openai.types.chat import ChatCompletionMessageParam

from codexy.core.agent import Agent
from codexy.config import AppConfig, MemoryConfig, load_config
from codexy.utils.token_utils import approximate_tokens_used # For potential direct use if needed for setup

# Default values that might be used in AppConfig if not overridden
DEFAULT_MODEL_FOR_TESTS = "o4-mini" # or any model expected by get_model_max_tokens
DEFAULT_INSTRUCTIONS_FOR_TESTS = "Test instructions"

def create_test_app_config(memory_settings: Optional[Dict[str, Any]] = None) -> AppConfig:
    """Helper to create a basic AppConfig for testing Agent compression."""
    # Base config which load_config would typically build
    # We are somewhat bypassing load_config here for directness in agent tests,
    # but ensuring the structure is what Agent expects.
    
    base_config: Dict[str, Any] = {
        "api_key": "test_api_key",
        "model": DEFAULT_MODEL_FOR_TESTS,
        "instructions": DEFAULT_INSTRUCTIONS_FOR_TESTS,
        "full_auto_error_mode": "ask-user",
        "notify": False,
        "history": {"max_size": 1000, "save_history": False}, # Dummy history config
        "safe_commands": [],
        "effective_approval_mode": "suggest",
        "flex_mode": False,
        "full_stdout": False,
        "writable_roots": [],
        "base_url": None,
        "timeout": None,
        # Memory will be set below
    }

    if memory_settings:
        # Ensure memory_settings conforms to MemoryConfig structure if passed
        resolved_memory_config: MemoryConfig = {
            "enabled": memory_settings.get("enabled", False), # Default to False if not specified
            "enable_compression": memory_settings.get("enable_compression", False),
            "compression_threshold_factor": memory_settings.get("compression_threshold_factor", 0.8),
            "keep_recent_messages": memory_settings.get("keep_recent_messages", 5),
        }
        base_config["memory"] = resolved_memory_config
    else:
        base_config["memory"] = None # Or a default MemoryConfig if appropriate

    return cast(AppConfig, base_config) # Cast to AppConfig for type hinting

class TestAgentCompressHistory(unittest.TestCase):

    def create_test_agent(self, memory_settings: Optional[Dict[str, Any]] = None) -> Agent:
        app_config = create_test_app_config(memory_settings)
        return Agent(config=app_config)

    def test_compress_history_shorter_than_keep_recent(self):
        agent = self.create_test_agent(memory_settings={"keep_recent_messages": 5})
        agent.history = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Message 2"},
        ]
        original_history = list(agent.history)
        agent._compress_history(max_tokens=1000) # max_tokens not strictly used here
        self.assertEqual(agent.history, original_history)

    def test_compress_history_shorter_with_system_prompt(self):
        agent = self.create_test_agent(memory_settings={"keep_recent_messages": 3})
        agent.history = [
            {"role": "system", "content": "System Prompt"},
            {"role": "user", "content": "User 1"},
            {"role": "assistant", "content": "Assistant 1"},
        ]
        original_history = list(agent.history)
        agent._compress_history(max_tokens=1000)
        self.assertEqual(agent.history, original_history)
        self.assertEqual(len(agent.history), 3)

    def test_compress_history_one_message_to_summarize(self):
        agent = self.create_test_agent(memory_settings={"keep_recent_messages": 2})
        agent.history = [
            {"role": "system", "content": "System Prompt"}, # Preserved
            {"role": "user", "content": "User 1"},       # Summarized
            {"role": "user", "content": "User 2"},       # Kept
            {"role": "assistant", "content": "Assistant 2"}, # Kept
        ]
        agent._compress_history(max_tokens=1000)
        self.assertEqual(len(agent.history), 4) # System, Summary, User 2, Assistant 2
        self.assertEqual(agent.history[0]["role"], "system")
        self.assertEqual(agent.history[0]["content"], "System Prompt")
        self.assertEqual(agent.history[1]["role"], "system")
        self.assertTrue("[System: 1 previous message(s) were summarized" in agent.history[1]["content"])
        self.assertEqual(agent.history[2]["content"], "User 2")
        self.assertEqual(agent.history[3]["content"], "Assistant 2")

    def test_compress_history_multiple_messages_to_summarize(self):
        agent = self.create_test_agent(memory_settings={"keep_recent_messages": 1})
        agent.history = [
            {"role": "system", "content": "System Prompt"},
            {"role": "user", "content": "User 1"}, # Summarized
            {"role": "assistant", "content": "Assistant 1"}, # Summarized
            {"role": "user", "content": "User 2"}, # Kept
        ]
        agent._compress_history(max_tokens=1000)
        self.assertEqual(len(agent.history), 3) # System, Summary, User 2
        self.assertEqual(agent.history[0]["role"], "system")
        self.assertEqual(agent.history[1]["role"], "system")
        self.assertTrue("[System: 2 previous message(s) were summarized" in agent.history[1]["content"])
        self.assertEqual(agent.history[2]["content"], "User 2")

    def test_compress_history_no_system_prompt_summarize(self):
        agent = self.create_test_agent(memory_settings={"keep_recent_messages": 1})
        agent.history = [
            {"role": "user", "content": "User 1"}, # Summarized
            {"role": "assistant", "content": "Assistant 1"}, # Summarized
            {"role": "user", "content": "User 2"}, # Kept
        ]
        agent._compress_history(max_tokens=1000)
        self.assertEqual(len(agent.history), 2) # Summary, User 2
        self.assertEqual(agent.history[0]["role"], "system") # Summary message has system role
        self.assertTrue("[System: 2 previous message(s) were summarized" in agent.history[0]["content"])
        self.assertEqual(agent.history[1]["content"], "User 2")

    def test_compress_history_all_compressible_summarized(self):
        # keep_recent_messages = 0 is a bit of an edge case.
        # The current logic means it will try to keep 0 messages from the compressible part,
        # effectively summarizing all of them.
        agent = self.create_test_agent(memory_settings={"keep_recent_messages": 0})
        agent.history = [
            {"role": "system", "content": "System Prompt"},
            {"role": "user", "content": "User 1"},
            {"role": "assistant", "content": "Assistant 1"},
        ]
        agent._compress_history(max_tokens=1000)
        self.assertEqual(len(agent.history), 2) # System, Summary
        self.assertEqual(agent.history[0]["role"], "system")
        self.assertEqual(agent.history[0]["content"], "System Prompt")
        self.assertEqual(agent.history[1]["role"], "system")
        self.assertTrue("[System: 2 previous message(s) were summarized" in agent.history[1]["content"])

    def test_compress_history_empty(self):
        agent = self.create_test_agent(memory_settings={"keep_recent_messages": 5})
        agent.history = []
        agent._compress_history(max_tokens=1000)
        self.assertEqual(len(agent.history), 0)

    def test_compress_history_only_system_prompt(self):
        agent = self.create_test_agent(memory_settings={"keep_recent_messages": 5})
        agent.history = [{"role": "system", "content": "System Prompt"}]
        original_history = list(agent.history)
        agent._compress_history(max_tokens=1000)
        self.assertEqual(agent.history, original_history)

    def test_compress_history_keep_recent_messages_greater_than_history(self):
        agent = self.create_test_agent(memory_settings={"keep_recent_messages": 10})
        agent.history = [
            {"role": "system", "content": "System Prompt"},
            {"role": "user", "content": "User 1"},
            {"role": "assistant", "content": "Assistant 1"},
        ]
        original_history = list(agent.history)
        agent._compress_history(max_tokens=1000)
        self.assertEqual(agent.history, original_history)

# Asynchronous test class for process_turn_stream related tests
class TestAgentCompressionTriggering(unittest.IsolatedAsyncioTestCase):

    def create_test_agent(self, memory_settings: Optional[Dict[str, Any]] = None) -> Agent:
        # Helper to create an agent with specific memory settings for these tests
        app_config = create_test_app_config(memory_settings)
        return Agent(config=app_config)

    async def consume_stream(self, stream_iter):
        """Helper to consume the async iterator from process_turn_stream."""
        return [event async for event in stream_iter]

    @patch('codexy.core.agent.approximate_tokens_used')
    @patch('codexy.core.agent.Agent._compress_history') 
    @patch('codexy.core.agent.AsyncOpenAI') # Mock the OpenAI client
    async def test_compression_triggered_when_tokens_exceed_threshold(
        self, mock_openai_client_class, mock_compress_history, mock_approx_tokens
    ):
        mock_openai_client_instance = mock_openai_client_class.return_value
        mock_chat_completions = mock_openai_client_instance.chat.completions
        mock_chat_completions.create = AsyncMock() # Make create an AsyncMock

        # Configure mock stream response
        mock_choice = MagicMock()
        mock_choice.delta = MagicMock(content="Test response")
        mock_choice.finish_reason = "stop"
        mock_chunk = MagicMock()
        mock_chunk.choices = [mock_choice]
        mock_stream = MagicMock()
        mock_stream.__aiter__.return_value = [mock_chunk] # Simulate async iterator
        mock_chat_completions.create.return_value = mock_stream


        agent = self.create_test_agent(memory_settings={
            "enabled": True, 
            "enable_compression": True, 
            "compression_threshold_factor": 0.5,
            "keep_recent_messages": 1 # Does not affect triggering directly
        })
        agent.history = [{"role": "user", "content": "A long message"}] 
        
        # Mock get_model_max_tokens to return a value that ensures threshold is met
        with patch('codexy.core.agent.get_model_max_tokens', return_value=100):
            mock_approx_tokens.return_value = 60 # 60 tokens > 100 * 0.5 = 50
            
            await self.consume_stream(agent.process_turn_stream(prompt="Another message"))
            
            mock_compress_history.assert_called_once()
            self.assertTrue(agent.compression_attempted_this_turn)

    @patch('codexy.core.agent.approximate_tokens_used')
    @patch('codexy.core.agent.Agent._compress_history')
    @patch('codexy.core.agent.AsyncOpenAI')
    async def test_compression_not_triggered_tokens_below_threshold(
        self, mock_openai_client_class, mock_compress_history, mock_approx_tokens
    ):
        mock_openai_client_instance = mock_openai_client_class.return_value
        mock_chat_completions = mock_openai_client_instance.chat.completions
        mock_chat_completions.create = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.delta = MagicMock(content="Test response")
        mock_choice.finish_reason = "stop"
        mock_chunk = MagicMock()
        mock_chunk.choices = [mock_choice]
        mock_stream = MagicMock()
        mock_stream.__aiter__.return_value = [mock_chunk]
        mock_chat_completions.create.return_value = mock_stream

        agent = self.create_test_agent(memory_settings={
            "enabled": True,
            "enable_compression": True,
            "compression_threshold_factor": 0.5
        })
        agent.history = [{"role": "user", "content": "Short message"}]
        
        with patch('codexy.core.agent.get_model_max_tokens', return_value=100):
            mock_approx_tokens.return_value = 30 # 30 tokens < 100 * 0.5 = 50
            
            await self.consume_stream(agent.process_turn_stream(prompt="Another short one"))
            
            mock_compress_history.assert_not_called()
            self.assertFalse(agent.compression_attempted_this_turn)

    @patch('codexy.core.agent.approximate_tokens_used')
    @patch('codexy.core.agent.Agent._compress_history')
    @patch('codexy.core.agent.AsyncOpenAI')
    async def test_compression_not_triggered_when_disabled(
        self, mock_openai_client_class, mock_compress_history, mock_approx_tokens
    ):
        mock_openai_client_instance = mock_openai_client_class.return_value
        mock_chat_completions = mock_openai_client_instance.chat.completions
        mock_chat_completions.create = AsyncMock()
        mock_choice = MagicMock()
        mock_choice.delta = MagicMock(content="Test response")
        mock_choice.finish_reason = "stop"
        mock_chunk = MagicMock()
        mock_chunk.choices = [mock_choice]
        mock_stream = MagicMock()
        mock_stream.__aiter__.return_value = [mock_chunk]
        mock_chat_completions.create.return_value = mock_stream

        agent = self.create_test_agent(memory_settings={
            "enabled": True, # Memory might be on, but compression itself is off
            "enable_compression": False, # Explicitly disable compression
            "compression_threshold_factor": 0.5
        })
        agent.history = [{"role": "user", "content": "A very long message that would otherwise trigger"}]
        
        with patch('codexy.core.agent.get_model_max_tokens', return_value=100):
            mock_approx_tokens.return_value = 70 # 70 tokens > 100 * 0.5 = 50
            
            await self.consume_stream(agent.process_turn_stream(prompt="Another message"))
            
            mock_compress_history.assert_not_called()
            self.assertFalse(agent.compression_attempted_this_turn)

    @patch('codexy.core.agent.AsyncOpenAI')
    async def test_context_length_error_message_no_compression_attempt(
        self, mock_openai_client_class
    ):
        mock_openai_client_instance = mock_openai_client_class.return_value
        mock_chat_completions = mock_openai_client_instance.chat.completions
        
        # Simulate BadRequestError for context length
        from openai import BadRequestError
        error_response = MagicMock()
        error_response.json.return_value = {"error": {"message": "this is a context_length_exceeded error"}}
        # The actual error object requires a request, let's simplify by mocking what's accessed
        mock_bad_request_error = BadRequestError(
            message="Context length exceeded.", 
            response=error_response, # this is what the code tries to access for .json()
            body={"error": {"message": "this is a context_length_exceeded error"}} # for the error_detail
        )
        mock_chat_completions.create.side_effect = mock_bad_request_error
        
        agent = self.create_test_agent(memory_settings={"enable_compression": True}) # Compression enabled but won't run if error is immediate
        agent.history = [{"role": "user", "content": "Initial prompt"}]
        
        # We are not mocking _compress_history, so it won't be called if the API call fails first.
        # We also don't need to mock token calculation if API call is the first thing that fails.
        # This test assumes the API call itself fails due to context length before compression is even attempted (e.g. a very long initial prompt).
        # Or, more realistically, that compression was *not* triggered for some reason (e.g. threshold not met before this particular failing call)
        agent.compression_attempted_this_turn = False # Explicitly set for clarity
        
        events = await self.consume_stream(agent.process_turn_stream(prompt="A very very long prompt that causes context overflow"))
        
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertIn("exceed the model's maximum context length", events[0]["content"])
        self.assertNotIn("even after attempting history compression", events[0]["content"])


    @patch('codexy.core.agent.AsyncOpenAI')
    async def test_context_length_error_message_with_compression_attempt(
        self, mock_openai_client_class
    ):
        mock_openai_client_instance = mock_openai_client_class.return_value
        mock_chat_completions = mock_openai_client_instance.chat.completions
        
        from openai import BadRequestError
        error_response = MagicMock()
        error_response.json.return_value = {"error": {"message": "this is a context_length_exceeded error"}}
        mock_bad_request_error = BadRequestError(
            message="Context length exceeded.", 
            response=error_response, 
            body={"error": {"message": "this is a context_length_exceeded error"}}
        )
        mock_chat_completions.create.side_effect = mock_bad_request_error
        
        agent = self.create_test_agent(memory_settings={"enable_compression": True})
        agent.history = [{"role": "user", "content": "Initial prompt"}]
        
        # For this test, we manually set compression_attempted_this_turn to True
        # to simulate that compression DID run, but the context was still too long.
        agent.compression_attempted_this_turn = True
        
        events = await self.consume_stream(agent.process_turn_stream(prompt="Another long prompt"))
        
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "error")
        self.assertIn("exceeded model's limit even after attempting history compression", events[0]["content"])

if __name__ == '__main__':
    unittest.main()
