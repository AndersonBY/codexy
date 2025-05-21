# -*- coding: utf-8 -*-

import unittest
import json
import yaml
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, Any, Optional

from codexy.config import (
    load_config,
    AppConfig,
    MemoryConfig,
    DEFAULT_MEMORY_ENABLED,
    DEFAULT_MEMORY_ENABLE_COMPRESSION,
    DEFAULT_MEMORY_COMPRESSION_THRESHOLD_FACTOR,
    DEFAULT_MEMORY_KEEP_RECENT_MESSAGES,
    EMPTY_STORED_CONFIG
)

class TestConfigLoadingMemory(unittest.TestCase):

    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        # Create a dummy instructions file to prevent warnings/errors
        (self.temp_path / "instructions.md").write_text("Test instructions")

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_config(self, data: Dict[str, Any], format: str = "json") -> Path:
        if format == "json":
            config_file = self.temp_path / "config.json"
            with open(config_file, "w") as f:
                json.dump(data, f, indent=2)
            return config_file
        elif format == "yaml":
            config_file = self.temp_path / "config.yaml"
            with open(config_file, "w") as f:
                yaml.dump(data, f)
            return config_file
        raise ValueError("Unsupported format")

    def test_load_config_no_memory_section(self):
        """Test loading config when memory section is entirely missing."""
        config_data: Dict[str, Any] = {
            "model": "test-model",
            # No memory section
        }
        config_file = self._write_config(config_data)
        app_config = load_config(config_path=config_file, instructions_path=(self.temp_path / "instructions.md"))

        # Memory should be None if not enabled and not present
        self.assertIsNone(app_config.get("memory"))

    def test_load_config_memory_disabled_explicitly(self):
        """Test loading config when memory.enabled is false."""
        config_data: Dict[str, Any] = {
            "model": "test-model",
            "memory": {
                "enabled": False,
                "enable_compression": True, # This should be ignored if memory is disabled
            }
        }
        config_file = self._write_config(config_data)
        app_config = load_config(config_path=config_file, instructions_path=(self.temp_path / "instructions.md"))
        
        loaded_memory_config = app_config.get("memory")
        self.assertIsNotNone(loaded_memory_config)
        if loaded_memory_config: # for type checker
            self.assertFalse(loaded_memory_config.get("enabled"))
            # Other fields should still be populated with defaults even if memory is disabled
            self.assertEqual(loaded_memory_config.get("enable_compression"), DEFAULT_MEMORY_ENABLE_COMPRESSION)
            self.assertEqual(loaded_memory_config.get("compression_threshold_factor"), DEFAULT_MEMORY_COMPRESSION_THRESHOLD_FACTOR)
            self.assertEqual(loaded_memory_config.get("keep_recent_messages"), DEFAULT_MEMORY_KEEP_RECENT_MESSAGES)


    def test_load_config_memory_enabled_no_compression_settings(self):
        """Test loading config when memory is enabled, but no specific compression settings."""
        config_data: Dict[str, Any] = {
            "model": "test-model",
            "memory": {
                "enabled": True
            }
        }
        config_file = self._write_config(config_data)
        app_config = load_config(config_path=config_file, instructions_path=(self.temp_path / "instructions.md"))
        
        loaded_memory_config = app_config.get("memory")
        self.assertIsNotNone(loaded_memory_config)
        if loaded_memory_config: # for type checker
            self.assertTrue(loaded_memory_config.get("enabled"))
            self.assertEqual(loaded_memory_config.get("enable_compression"), DEFAULT_MEMORY_ENABLE_COMPRESSION)
            self.assertEqual(loaded_memory_config.get("compression_threshold_factor"), DEFAULT_MEMORY_COMPRESSION_THRESHOLD_FACTOR)
            self.assertEqual(loaded_memory_config.get("keep_recent_messages"), DEFAULT_MEMORY_KEEP_RECENT_MESSAGES)

    def test_load_config_partial_memory_compression_settings(self):
        """Test loading config with memory enabled and partial compression settings."""
        config_data: Dict[str, Any] = {
            "model": "test-model",
            "memory": {
                "enabled": True,
                "enable_compression": True,
                "keep_recent_messages": 10
                # compression_threshold_factor is missing
            }
        }
        config_file = self._write_config(config_data)
        app_config = load_config(config_path=config_file, instructions_path=(self.temp_path / "instructions.md"))
        
        loaded_memory_config = app_config.get("memory")
        self.assertIsNotNone(loaded_memory_config)
        if loaded_memory_config: # for type checker
            self.assertTrue(loaded_memory_config.get("enabled"))
            self.assertTrue(loaded_memory_config.get("enable_compression"))
            self.assertEqual(loaded_memory_config.get("compression_threshold_factor"), DEFAULT_MEMORY_COMPRESSION_THRESHOLD_FACTOR) # Should be default
            self.assertEqual(loaded_memory_config.get("keep_recent_messages"), 10) # Should be custom

    def test_load_config_full_memory_compression_settings(self):
        """Test loading config with memory enabled and all compression settings specified."""
        custom_threshold = 0.7
        custom_keep_recent = 3
        config_data: Dict[str, Any] = {
            "model": "test-model",
            "memory": {
                "enabled": True,
                "enable_compression": True,
                "compression_threshold_factor": custom_threshold,
                "keep_recent_messages": custom_keep_recent
            }
        }
        config_file = self._write_config(config_data)
        app_config = load_config(config_path=config_file, instructions_path=(self.temp_path / "instructions.md"))
        
        loaded_memory_config = app_config.get("memory")
        self.assertIsNotNone(loaded_memory_config)
        if loaded_memory_config: # for type checker
            self.assertTrue(loaded_memory_config.get("enabled"))
            self.assertTrue(loaded_memory_config.get("enable_compression"))
            self.assertEqual(loaded_memory_config.get("compression_threshold_factor"), custom_threshold)
            self.assertEqual(loaded_memory_config.get("keep_recent_messages"), custom_keep_recent)

    def test_load_config_yaml_format(self):
        """Test loading config with memory settings from a YAML file."""
        custom_threshold = 0.65
        custom_keep_recent = 7
        config_data: Dict[str, Any] = {
            "model": "test-model-yaml",
            "memory": {
                "enabled": True,
                "enable_compression": False,
                "compression_threshold_factor": custom_threshold,
                "keep_recent_messages": custom_keep_recent
            }
        }
        config_file = self._write_config(config_data, format="yaml")
        app_config = load_config(config_path=config_file, instructions_path=(self.temp_path / "instructions.md"))
        
        loaded_memory_config = app_config.get("memory")
        self.assertIsNotNone(loaded_memory_config)
        if loaded_memory_config: # for type checker
            self.assertTrue(loaded_memory_config.get("enabled"))
            self.assertFalse(loaded_memory_config.get("enable_compression"))
            self.assertEqual(loaded_memory_config.get("compression_threshold_factor"), custom_threshold)
            self.assertEqual(loaded_memory_config.get("keep_recent_messages"), custom_keep_recent)

    def test_empty_stored_config_defaults(self):
        """Verify that EMPTY_STORED_CONFIG has the correct default memory settings."""
        memory_defaults = EMPTY_STORED_CONFIG.get("memory")
        self.assertIsNotNone(memory_defaults)
        if memory_defaults: # for type checker
            self.assertEqual(memory_defaults.get("enabled"), DEFAULT_MEMORY_ENABLED)
            self.assertEqual(memory_defaults.get("enable_compression"), DEFAULT_MEMORY_ENABLE_COMPRESSION)
            self.assertEqual(memory_defaults.get("compression_threshold_factor"), DEFAULT_MEMORY_COMPRESSION_THRESHOLD_FACTOR)
            self.assertEqual(memory_defaults.get("keep_recent_messages"), DEFAULT_MEMORY_KEEP_RECENT_MESSAGES)


if __name__ == '__main__':
    unittest.main()
