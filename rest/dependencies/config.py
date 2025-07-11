"""
Configuration and shared service dependencies for FastAPI
"""

from cosa.config.configuration_manager import ConfigurationManager
from cosa.memory.solution_snapshot_mgr import SolutionSnapshotManager
from cosa.agents.v010.two_word_id_generator import TwoWordIdGenerator

# Global instances (initialized once)
_config_mgr = None
_snapshot_mgr = None
_id_generator = None

def get_config_manager():
    """Dependency to get configuration manager"""
    global _config_mgr
    if _config_mgr is None:
        _config_mgr = ConfigurationManager(env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS")
    return _config_mgr

def get_snapshot_manager():
    """Dependency to get snapshot manager"""
    global _snapshot_mgr
    if _snapshot_mgr is None:
        _snapshot_mgr = SolutionSnapshotManager()
    return _snapshot_mgr

def get_id_generator():
    """Dependency to get ID generator"""
    global _id_generator
    if _id_generator is None:
        _id_generator = TwoWordIdGenerator()
    return _id_generator