"""
Configuration for the TestFixExpediter agent.

Follows the BugFixExpediterConfig pattern for INI-driven configuration with
from_config() classmethod. 12 keys defined in the approved plan doc
`12-config-inventory.md`.

See: src/rnd/v0.1.6/2026.04.10-test-fix-expediter/12-config-inventory.md
"""

from dataclasses import dataclass, fields


@dataclass
class TestFixExpediterConfig:
    """
    Configuration for the TestFixExpediter agent.

    Requires:
        - All numeric values are positive
        - trust_mode in {"inherit", "shadow", "fixed_l1", "fixed_l3"}
        - rerun_scope in {"affected", "full"}
        - voice_gate_mode in {"aggregate", "per_cluster"}

    Ensures:
        - Provides sensible defaults for all 12 parameters
        - from_config() loads values from ConfigurationManager INI
    """

    # === Model Selection ===
    lead_model                    : str   = "claude-opus-4-6"
    worker_model                  : str   = "claude-sonnet-4-6"

    # === Feature Flag / Watchdog ===
    auto_fix_enabled              : bool  = False

    # === Clustering limits ===
    max_clusters                  : int   = 8
    max_cluster_seed_failures     : int   = 50

    # === Diagnosis limits ===
    max_diagnosis_iterations      : int   = 4
    min_diagnosis_confidence      : float = 0.65

    # === Fix limits ===
    max_fix_attempts              : int   = 2

    # === Budget + time ===
    cost_cap_usd                  : float = 15.00
    wall_clock_timeout_secs       : int   = 2400

    # === Trust / Git ===
    trust_mode                    : str   = "inherit"

    # === Phase 6 validation ===
    rerun_scope                   : str   = "affected"

    # === Phase 3 behavior ===
    continue_on_cluster_failure   : bool  = True

    # === Voice gate UX ===
    voice_gate_mode               : str   = "aggregate"

    # === COSA Integration ===
    feedback_timeout_seconds      : int   = 300
    narrate_progress              : bool  = True

    # === Aliases for shared FixExecutor compatibility ===
    # FixExecutor reads `budget_usd` from the config (matches BFE naming).
    # Exposed as an alias for `cost_cap_usd`. Populated in __post_init__.
    budget_usd                    : float = 15.00

    def __post_init__( self ):
        # Mirror cost_cap_usd → budget_usd so the shared FixExecutor (which
        # reads `self.config.budget_usd`) works unchanged.
        self.budget_usd = self.cost_cap_usd

    @classmethod
    def from_config( cls, config_mgr, debug: bool = False ):
        """
        Create a TestFixExpediterConfig from ConfigurationManager INI values.

        Requires:
            - config_mgr is a valid ConfigurationManager instance

        Ensures:
            - Returns TestFixExpediterConfig with INI values or defaults
            - Type coercion applied based on field type annotations
            - budget_usd is mirrored from cost_cap_usd post-construction

        Args:
            config_mgr: ConfigurationManager instance
            debug: Enable debug output

        Returns:
            TestFixExpediterConfig: Configured instance
        """
        key_map = {
            "lead_model"                  : "test fix expediter lead model",
            "worker_model"                : "test fix expediter worker model",
            "auto_fix_enabled"            : "test fix expediter auto fix enabled",
            "max_clusters"                : "test fix expediter max clusters",
            "max_cluster_seed_failures"   : "test fix expediter max cluster seed failures",
            "max_diagnosis_iterations"    : "test fix expediter max diagnosis iterations",
            "min_diagnosis_confidence"    : "test fix expediter min diagnosis confidence",
            "max_fix_attempts"            : "test fix expediter max fix attempts",
            "cost_cap_usd"                : "test fix expediter cost cap usd",
            "wall_clock_timeout_secs"     : "test fix expediter wall clock timeout secs",
            "trust_mode"                  : "test fix expediter trust mode",
            "rerun_scope"                 : "test fix expediter rerun scope",
            "continue_on_cluster_failure" : "test fix expediter continue on cluster failure",
            "voice_gate_mode"             : "test fix expediter voice gate mode",
            "feedback_timeout_seconds"    : "test fix expediter feedback timeout seconds",
            "narrate_progress"            : "test fix expediter narrate progress",
        }

        kwargs    = {}
        dc_fields = { f.name: f for f in fields( cls ) }

        for field_name, ini_key in key_map.items():
            dc_field   = dc_fields[ field_name ]
            default    = dc_field.default
            field_type = dc_field.type

            if field_type == "bool" or field_type is bool:
                return_type = "boolean"
            elif field_type == "int" or field_type is int:
                return_type = "int"
            elif field_type == "float" or field_type is float:
                return_type = "float"
            else:
                return_type = "string"

            value = config_mgr.get( ini_key, default=default, return_type=return_type )
            kwargs[ field_name ] = value

            if debug: print( f"  [TestFixExpediterConfig] {field_name} = {value} (from INI: {ini_key})" )

        return cls( **kwargs )


def quick_smoke_test():
    """Quick smoke test for TestFixExpediterConfig."""
    import cosa.utils.util as cu

    cu.print_banner( "TestFixExpediterConfig Smoke Test", prepend_nl=True )

    try:
        # 1: Default instantiation
        config = TestFixExpediterConfig()
        assert config.lead_model == "claude-opus-4-6"
        assert config.worker_model == "claude-sonnet-4-6"
        assert config.auto_fix_enabled == False
        assert config.max_clusters == 8
        assert config.max_cluster_seed_failures == 50
        assert config.max_diagnosis_iterations == 4
        assert config.min_diagnosis_confidence == 0.65
        assert config.max_fix_attempts == 2
        assert config.cost_cap_usd == 15.00
        assert config.wall_clock_timeout_secs == 2400
        assert config.trust_mode == "inherit"
        assert config.rerun_scope == "affected"
        assert config.continue_on_cluster_failure == True
        assert config.voice_gate_mode == "aggregate"
        assert config.budget_usd == 15.00   # mirrored
        print( "✓ Default config values correct (all 12 TFE keys + alias)" )

        # 2: Custom values
        config = TestFixExpediterConfig( auto_fix_enabled=True, max_clusters=5, cost_cap_usd=20.0 )
        assert config.auto_fix_enabled == True
        assert config.max_clusters == 5
        assert config.cost_cap_usd == 20.0
        assert config.budget_usd == 20.0   # mirrored
        print( "✓ Custom config values work (+ budget_usd mirrors cost_cap_usd)" )

        # 3: from_config (may fail without INI keys — expected until step 14 lands)
        try:
            from cosa.config.configuration_manager import ConfigurationManager
            config_mgr = ConfigurationManager( env_var_name="LUPIN_CONFIG_MGR_CLI_ARGS" )
            config = TestFixExpediterConfig.from_config( config_mgr, debug=False )
            print( f"✓ from_config loaded (auto_fix_enabled={config.auto_fix_enabled}, max_clusters={config.max_clusters})" )
        except Exception as e:
            print( f"⚠ from_config skipped (INI keys may not exist yet): {str( e )[ :100 ]}" )

        print( "\n✓ TestFixExpediterConfig smoke test completed successfully" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    quick_smoke_test()
