"""
PredictionEngine — singleton prediction engine for notification responses.

Thread-safe singleton that generates predictions for all notification response types.
Currently implements Slice 0 (foundation) + Slice 1 (yes_no CBR majority vote)
+ Slice 1.5 (qualified yes/no with comment retrieval).

Architecture:
    - Initialized at FastAPI boot via lifespan()
    - Called by notifications.py before WebSocket push (predict hook)
    - Called by notifications.py on response submission (record hook)
    - Uses EmbeddingProvider singleton for vector generation
    - Uses LanceDB via ProxyDecisionEmbeddings pattern for CBR retrieval
    - Writes outcomes to prediction_log table via PredictionLogRepository
"""

from threading import Lock
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

import cosa.utils.util as cu

from cosa.agents.prediction_engine.config import (
    DEFAULT_ENABLED,
    DEFAULT_DEBUG,
    DEFAULT_CBR_TOP_K,
    DEFAULT_CBR_SIMILARITY_THRESHOLD,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_LANCEDB_TABLE,
    STRATEGY_CBR_MAJORITY,
    STRATEGY_COLD_START,
    RESPONSE_TYPE_YES_NO,
    RESPONSE_TYPE_MULTIPLE_CHOICE,
    RESPONSE_TYPE_OPEN_ENDED,
    RESPONSE_TYPE_OPEN_ENDED_BATCH,
)
from cosa.agents.prediction_engine.prediction_result import PredictionResult
from cosa.agents.prediction_engine.notification_category_classifier import NotificationCategoryClassifier
from cosa.agents.prediction_engine.accuracy_comparators import get_comparator, _extract_qualifier


class PredictionEngine:
    """
    Singleton prediction engine for notification responses.

    Requires:
        - EmbeddingProvider initialized (for vector generation)
        - LanceDB available at configured path (for CBR retrieval)
        - PostgreSQL available (for prediction_log writes)

    Ensures:
        - Thread-safe singleton pattern
        - predict() returns PredictionResult for any notification
        - record_outcome() logs prediction + actual to prediction_log
        - Cold start behavior when insufficient data
    """

    _instance = None
    _lock     = Lock()

    def __new__( cls, *args, **kwargs ):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__( cls )
                    cls._instance._initialized = False
        return cls._instance

    def __init__( self, config_mgr=None, debug=False ):
        """
        Initialize the prediction engine (only runs once due to singleton).

        Requires:
            - config_mgr: ConfigurationManager instance (optional, uses defaults)

        Ensures:
            - Classifier, embedding store, and CBR components initialized
            - Engine ready to accept predict() calls
        """
        if self._initialized:
            return
        self._initialized = True

        self.debug = debug

        # Load config
        if config_mgr:
            self.enabled              = config_mgr.get( "prediction engine enabled", default=str( DEFAULT_ENABLED ), return_type="boolean" )
            self.debug                = config_mgr.get( "prediction engine debug", default=str( DEFAULT_DEBUG ), return_type="boolean" ) or debug
            self.cbr_top_k            = config_mgr.get( "prediction engine cbr top k", default=str( DEFAULT_CBR_TOP_K ), return_type="int" )
            self.similarity_threshold = config_mgr.get( "prediction engine cbr similarity threshold", default=str( DEFAULT_CBR_SIMILARITY_THRESHOLD ), return_type="float" )
            self.confidence_threshold = config_mgr.get( "prediction engine confidence threshold", default=str( DEFAULT_CONFIDENCE_THRESHOLD ), return_type="float" )
            self.lancedb_table        = config_mgr.get( "prediction engine lancedb table", default=DEFAULT_LANCEDB_TABLE )
        else:
            self.enabled              = DEFAULT_ENABLED
            self.cbr_top_k            = DEFAULT_CBR_TOP_K
            self.similarity_threshold = DEFAULT_CBR_SIMILARITY_THRESHOLD
            self.confidence_threshold = DEFAULT_CONFIDENCE_THRESHOLD
            self.lancedb_table        = DEFAULT_LANCEDB_TABLE

        # Initialize classifier
        self.classifier = NotificationCategoryClassifier( debug=self.debug )

        # Initialize embedding store (lazy — created on first use)
        self._embedding_store = None
        self._embedding_provider = None

        if self.debug: print( f"[PredictionEngine] Initialized (enabled={self.enabled}, table={self.lancedb_table})" )

    def _get_embedding_provider( self ):
        """Lazy-load the embedding provider singleton."""
        if self._embedding_provider is None:
            try:
                from cosa.memory.embedding_provider import get_embedding_provider
                self._embedding_provider = get_embedding_provider( debug=self.debug )
            except Exception as e:
                if self.debug: print( f"[PredictionEngine] Failed to load embedding provider: {e}" )
        return self._embedding_provider

    def _get_embedding_store( self ):
        """Lazy-load the LanceDB embedding store."""
        if self._embedding_store is None:
            try:
                from cosa.agents.decision_proxy.proxy_decision_embeddings import ProxyDecisionEmbeddings

                lancedb_path = cu.get_project_root() + "/src/conf/long-term-memory/lupin.lancedb"
                self._embedding_store = ProxyDecisionEmbeddings(
                    db_path       = lancedb_path,
                    table_name    = self.lancedb_table,
                    embedding_dim = 768,
                    debug         = self.debug
                )
            except Exception as e:
                if self.debug: print( f"[PredictionEngine] Failed to load embedding store: {e}" )
        return self._embedding_store

    def predict( self, notification_dict: Dict[str, Any] ) -> PredictionResult:
        """
        Generate a prediction for a notification response.

        Requires:
            - notification_dict contains: message, response_type, sender_id (optional)

        Ensures:
            - Returns PredictionResult (cold_start if insufficient data or disabled)
            - Dispatches to type-specific prediction method
            - Classification always runs (for logging even in cold start)
            - Never raises exceptions (graceful degradation)
        """
        message       = notification_dict.get( "message", "" )
        response_type = notification_dict.get( "response_type", "" )
        sender_id     = notification_dict.get( "sender_id", "" )

        # Classify the notification
        category, class_confidence = self.classifier.classify( message, sender_id=sender_id )

        if self.debug: print( f"[PredictionEngine] predict() type={response_type}, category={category}, conf={class_confidence:.2f}" )

        # If disabled, return cold start with category info
        if not self.enabled:
            return PredictionResult(
                response_type = response_type,
                category      = category,
                strategy      = STRATEGY_COLD_START,
                metadata      = { "reason": "engine_disabled" }
            )

        # Generate embedding for the message
        embedding = self._generate_embedding( message )

        # Dispatch by response type
        try:
            if response_type == RESPONSE_TYPE_YES_NO:
                return self._predict_yes_no( message, category, embedding )

            # Future slices: multiple_choice, open_ended, open_ended_batch
            # For now, return cold start for unsupported types
            return PredictionResult(
                response_type = response_type,
                category      = category,
                strategy      = STRATEGY_COLD_START,
                metadata      = { "reason": f"unsupported_type_{response_type}" }
            )

        except Exception as e:
            if self.debug: print( f"[PredictionEngine] predict() error: {e}" )
            return PredictionResult(
                response_type = response_type,
                category      = category,
                strategy      = STRATEGY_COLD_START,
                metadata      = { "reason": "prediction_error", "error": str( e ) }
            )

    def _predict_yes_no( self, message: str, category: str, embedding: Optional[list] ) -> PredictionResult:
        """
        Predict yes/no response using CBR majority vote with qualifier retrieval.

        Requires:
            - message: The notification message
            - category: Classified category
            - embedding: Message embedding vector (or None)

        Ensures:
            - Retrieves top-k similar past yes/no responses
            - Majority vote on "yes"/"no" values
            - Confidence = max_similarity * consistency
            - Extracts qualifier from highest-similarity winning-side case
            - Returns cold_start if no similar cases found
        """
        if embedding is None:
            return PredictionResult(
                response_type = RESPONSE_TYPE_YES_NO,
                category      = category,
                strategy      = STRATEGY_COLD_START,
                metadata      = { "reason": "no_embedding" }
            )

        store = self._get_embedding_store()
        if store is None:
            return PredictionResult(
                response_type = RESPONSE_TYPE_YES_NO,
                category      = category,
                strategy      = STRATEGY_COLD_START,
                metadata      = { "reason": "no_embedding_store" }
            )

        # Find similar past notifications
        try:
            similar_cases = store.find_similar(
                query_embedding = embedding,
                category        = category,
                limit           = self.cbr_top_k,
                threshold       = self.similarity_threshold
            )
        except Exception as e:
            if self.debug: print( f"[PredictionEngine] find_similar error: {e}" )
            similar_cases = []

        if not similar_cases:
            return PredictionResult(
                response_type      = RESPONSE_TYPE_YES_NO,
                category           = category,
                strategy           = STRATEGY_COLD_START,
                similar_case_count = 0,
                metadata           = { "reason": "no_similar_cases" }
            )

        # Majority vote
        votes = {}
        max_similarity = 0.0

        for similarity_pct, record in similar_cases:
            decision_value = record.get( "decision_value", "" )
            # Extract binary from potential qualified value
            binary_value = "yes" if decision_value.lower().startswith( "yes" ) else "no"
            votes[ binary_value ] = votes.get( binary_value, 0 ) + 1
            max_similarity = max( max_similarity, similarity_pct / 100.0 )

        # Winner and consistency
        total_votes = sum( votes.values() )
        winner      = max( votes, key=votes.get )
        consistency = votes[ winner ] / total_votes if total_votes > 0 else 0.0

        # Confidence = max_similarity * consistency
        confidence = max_similarity * consistency

        # Qualifier retrieval from winning-side cases
        winning_qualifier    = None
        qualifier_similarity = 0.0

        for similarity_pct, record in similar_cases:
            decision_value = record.get( "decision_value", "" )
            binary_value   = "yes" if decision_value.lower().startswith( "yes" ) else "no"

            if binary_value == winner:
                qualifier = _extract_qualifier( decision_value )
                if qualifier and similarity_pct > qualifier_similarity:
                    winning_qualifier    = qualifier
                    qualifier_similarity = similarity_pct

        if self.debug:
            print( f"[PredictionEngine] yes_no: votes={votes}, winner={winner}, conf={confidence:.3f}, qualifier={winning_qualifier}" )

        return PredictionResult(
            response_type       = RESPONSE_TYPE_YES_NO,
            category            = category,
            strategy            = STRATEGY_CBR_MAJORITY,
            predicted_value     = winner,
            confidence          = confidence,
            similar_case_count  = len( similar_cases ),
            predicted_qualifier = winning_qualifier,
            metadata            = {
                "votes"                : votes,
                "max_similarity"       : round( max_similarity, 3 ),
                "qualifier_similarity" : round( qualifier_similarity / 100.0, 3 ) if winning_qualifier else None,
            }
        )

    def record_outcome( self, notification_id: str, prediction_result: PredictionResult,
                        actual_value: Any, response_type: str ) -> None:
        """
        Record the prediction outcome to the prediction_log table.

        Requires:
            - notification_id: UUID string of the notification
            - prediction_result: The PredictionResult from predict()
            - actual_value: The actual response from the user
            - response_type: The response type string

        Ensures:
            - Writes a complete prediction_log row with prediction + outcome
            - Stores embedding in LanceDB for future CBR retrieval
            - Accuracy comparison computed and logged
            - Never raises exceptions (graceful degradation)
        """
        try:
            # Normalize actual_value to dict
            if isinstance( actual_value, str ):
                actual_dict = { "value": actual_value }
            elif isinstance( actual_value, dict ):
                actual_dict = actual_value
            else:
                actual_dict = { "value": str( actual_value ) }

            # Compare prediction against actual
            comparator = get_comparator( response_type )
            predicted_dict = prediction_result._wrap_predicted_value()
            accuracy_match, accuracy_detail = comparator( predicted_dict, actual_dict )

            # Write to prediction_log
            from cosa.rest.db.database import get_db
            from cosa.rest.db.repositories.prediction_log_repository import PredictionLogRepository

            with get_db() as session:
                repo = PredictionLogRepository( session )

                repo.log_prediction(
                    notification_id       = notification_id,
                    response_type         = prediction_result.response_type,
                    category              = prediction_result.category,
                    predicted_value       = predicted_dict,
                    prediction_confidence = prediction_result.confidence,
                    prediction_strategy   = prediction_result.strategy,
                    similar_case_count    = prediction_result.similar_case_count,
                    sender_id             = None,  # Filled by caller if needed
                )

                # Update with outcome
                repo.update_outcome(
                    notification_id = notification_id,
                    actual_value    = actual_dict,
                    accuracy_match  = accuracy_match,
                    accuracy_detail = accuracy_detail
                )

                session.commit()

            # Store in LanceDB for future CBR retrieval
            self._store_decision( notification_id, prediction_result, actual_value, response_type )

            if self.debug:
                print( f"[PredictionEngine] Recorded outcome: id={notification_id}, match={accuracy_match}" )

        except Exception as e:
            if self.debug: print( f"[PredictionEngine] record_outcome error: {e}" )

    def _store_decision( self, notification_id: str, prediction_result: PredictionResult,
                         actual_value: Any, response_type: str ) -> None:
        """
        Store the actual response in LanceDB for future CBR retrieval.

        Ensures:
            - Generates embedding for the original question
            - Stores decision_value as the actual response
            - Uses response_type-specific formatting
        """
        try:
            store    = self._get_embedding_store()
            provider = self._get_embedding_provider()
            if store is None or provider is None:
                return

            # Extract the message from metadata if available
            message = prediction_result.metadata.get( "original_message", "" ) if prediction_result.metadata else ""
            if not message:
                return  # Can't store without the original message

            embedding = provider.generate_embedding( message, content_type="prose" )

            # Format decision_value based on response type
            if isinstance( actual_value, str ):
                decision_value = actual_value
            elif isinstance( actual_value, dict ):
                value = actual_value.get( "value", "" )
                if value:
                    decision_value = str( value )
                else:
                    decision_value = str( actual_value )
            else:
                decision_value = str( actual_value )

            store.add_decision(
                id                 = notification_id,
                question           = message,
                category           = prediction_result.category,
                decision_value     = decision_value,
                ratification_state = "not_required",
                question_embedding = embedding,
                created_at         = datetime.now( timezone.utc ).isoformat(),
                data_origin        = "organic"
            )

        except Exception as e:
            if self.debug: print( f"[PredictionEngine] _store_decision error: {e}" )

    def get_accuracy_summary( self, window_days: int = 30, category: Optional[str] = None,
                              response_type: Optional[str] = None ) -> Dict[str, Any]:
        """
        Get accuracy statistics from the prediction_log table.

        Requires:
            - window_days: Number of days to look back

        Ensures:
            - Returns dict with accuracy metrics
            - Safe to call even if no predictions exist
        """
        try:
            from cosa.rest.db.database import get_db
            from cosa.rest.db.repositories.prediction_log_repository import PredictionLogRepository

            with get_db() as session:
                repo = PredictionLogRepository( session )
                return repo.get_accuracy_summary(
                    window_days   = window_days,
                    category      = category,
                    response_type = response_type
                )
        except Exception as e:
            if self.debug: print( f"[PredictionEngine] get_accuracy_summary error: {e}" )
            return {
                "window_days"       : window_days,
                "total_predictions" : 0,
                "total_responded"   : 0,
                "accuracy_rate"     : 0.0,
                "error"             : str( e )
            }

    def _generate_embedding( self, text: str ) -> Optional[list]:
        """
        Generate embedding vector for a text string.

        Requires:
            - text is a non-empty string

        Ensures:
            - Returns list of floats (768-dim) or None on failure
            - Uses EmbeddingProvider singleton
        """
        if not text or not text.strip():
            return None

        provider = self._get_embedding_provider()
        if provider is None:
            return None

        try:
            return provider.generate_embedding( text, content_type="prose" )
        except Exception as e:
            if self.debug: print( f"[PredictionEngine] Embedding generation failed: {e}" )
            return None

    @classmethod
    def reset( cls ):
        """
        Reset the singleton instance (for testing only).

        Ensures:
            - Next call to PredictionEngine() creates a fresh instance
        """
        with cls._lock:
            cls._instance = None


def get_prediction_engine( config_mgr=None, debug=False ) -> PredictionEngine:
    """
    Convenience function to get the PredictionEngine singleton.

    Requires:
        - config_mgr: ConfigurationManager (only needed for first call)

    Ensures:
        - Returns the singleton PredictionEngine instance
        - Thread-safe initialization
    """
    return PredictionEngine( config_mgr=config_mgr, debug=debug )


def quick_smoke_test():
    """Quick smoke test for PredictionEngine."""
    import cosa.utils.util as du

    du.print_banner( "PredictionEngine Smoke Test", prepend_nl=True )

    try:
        # Reset any existing singleton
        PredictionEngine.reset()

        # Test 1: Singleton creation
        print( "Testing singleton creation..." )
        engine1 = PredictionEngine( debug=True )
        engine2 = PredictionEngine( debug=True )
        assert engine1 is engine2, "Singleton pattern broken"
        print( "✓ Singleton pattern works" )

        # Test 2: Cold start prediction (no embedding store)
        print( "Testing cold start prediction..." )
        result = engine1.predict( {
            "message"       : "Should I proceed with the deployment?",
            "response_type" : "yes_no",
            "sender_id"     : "test@lupin.deepily.ai"
        } )
        assert result.response_type == "yes_no"
        assert result.category in [ "permission", "workflow", "uncategorized" ]
        assert result.strategy in [ STRATEGY_COLD_START, STRATEGY_CBR_MAJORITY ]
        print( f"✓ Cold start prediction: category={result.category}, strategy={result.strategy}" )

        # Test 3: Unsupported type returns cold start
        print( "Testing unsupported type..." )
        result = engine1.predict( {
            "message"       : "Pick a database",
            "response_type" : "multiple_choice",
            "sender_id"     : "test@lupin.deepily.ai"
        } )
        assert result.strategy == STRATEGY_COLD_START
        print( f"✓ Unsupported type returns cold start" )

        # Test 4: Disabled engine
        print( "Testing disabled engine..." )
        engine1.enabled = False
        result = engine1.predict( {
            "message"       : "Should I proceed?",
            "response_type" : "yes_no"
        } )
        assert result.strategy == STRATEGY_COLD_START
        assert result.metadata.get( "reason" ) == "engine_disabled"
        engine1.enabled = True
        print( "✓ Disabled engine returns cold start with reason" )

        # Test 5: Convenience function
        print( "Testing get_prediction_engine()..." )
        engine3 = get_prediction_engine()
        assert engine3 is engine1
        print( "✓ get_prediction_engine() returns same singleton" )

        # Test 6: PredictionResult with qualifier populates hint_dict
        print( "Testing PredictionResult qualifier in hint_dict..." )
        qualified_result = PredictionResult(
            response_type       = RESPONSE_TYPE_YES_NO,
            category            = "permission",
            strategy            = STRATEGY_CBR_MAJORITY,
            predicted_value     = "yes",
            confidence          = 0.9,
            similar_case_count  = 3,
            predicted_qualifier = "only the old files"
        )
        hint = qualified_result.to_hint_dict()
        assert hint[ "predicted_qualifier" ] == "only the old files"
        print( "✓ Qualifier appears in hint_dict" )

        # Cleanup
        PredictionEngine.reset()

        print( "\n✓ All PredictionEngine smoke tests passed!" )

    except Exception as e:
        print( f"\n✗ Smoke test failed: {e}" )
        du.print_stack_trace( e, caller="prediction_engine.quick_smoke_test()" )
        PredictionEngine.reset()


if __name__ == "__main__":
    quick_smoke_test()
