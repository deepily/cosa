#!/usr/bin/env python3
"""
SWE Engineering Strategy — concrete decision strategy for SWE team operations.

Implements the full classify → gate → decide pipeline for engineering decisions.
Uses EngineeringClassifier for classification and TrustTracker for trust-gated
decision-making.

Dependency Rule:
    This module imports from decision_proxy (Layer 3) for base classes.
    This module NEVER imports from notification_proxy.
"""

from cosa.agents.decision_proxy.base_decision_strategy import BaseDecisionStrategy, DecisionResult
from cosa.agents.decision_proxy.trust_tracker import TrustTracker
from cosa.agents.decision_proxy.circuit_breaker import CircuitBreaker

from cosa.agents.swe_team.proxy.engineering_classifier import EngineeringClassifier
from cosa.agents.swe_team.proxy.engineering_categories import (
    ENGINEERING_CATEGORIES,
    get_category_names,
    get_category_cap_level,
)
from cosa.agents.swe_team.proxy.config import DEFAULT_ACCEPTED_SENDERS


class EngineeringStrategy( BaseDecisionStrategy ):
    """
    Concrete decision strategy for SWE team engineering decisions.

    Wires together:
        - EngineeringClassifier for question → category mapping
        - TrustTracker for per-category trust levels
        - CircuitBreaker for anomaly detection and auto-demotion

    Requires:
        - trust_tracker: TrustTracker instance (categories registered at init)
        - circuit_breaker: CircuitBreaker instance (optional)
        - accepted_senders: List of accepted sender IDs

    Ensures:
        - classify() delegates to EngineeringClassifier
        - gate() enforces trust level caps and mode restrictions
        - decide() provides default decision values per category
        - evaluate() runs the full pipeline with trust_tracker integration
    """

    def __init__(
        self,
        trust_tracker    = None,
        circuit_breaker  = None,
        accepted_senders = None,
        trust_mode       = "shadow",
        debug            = False
    ):
        """
        Initialize the SWE engineering strategy.

        Requires:
            - trust_mode is one of "shadow", "suggest", "active"

        Args:
            trust_tracker: TrustTracker instance (created if None)
            circuit_breaker: CircuitBreaker instance (created if None)
            accepted_senders: List of accepted sender IDs
            trust_mode: Operating mode ("shadow", "suggest", "active")
            debug: Enable debug output
        """
        self.debug            = debug
        self.trust_mode       = trust_mode
        self.accepted_senders = accepted_senders or DEFAULT_ACCEPTED_SENDERS

        # Create trust tracker if not provided
        self.trust_tracker = trust_tracker or TrustTracker( debug=debug )

        # Register all engineering categories with their cap levels
        for cat_name in get_category_names():
            cap = get_category_cap_level( cat_name )
            self.trust_tracker.register_category( cat_name, cap_level=cap )

        # Create circuit breaker if not provided
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            trust_tracker = self.trust_tracker,
            debug         = debug
        )

        # Classifier
        self.classifier = EngineeringClassifier( debug=debug )

    @property
    def name( self ):
        """Strategy identifier."""
        return "swe_engineering"

    @property
    def available( self ):
        """Strategy is always available once constructed."""
        return True

    def can_handle( self, item ):
        """
        Check if the event comes from an accepted SWE sender.

        Requires:
            - item is a dict with optional 'sender_id' key

        Ensures:
            - Returns True if sender_id is in accepted_senders
            - Returns True if no sender_id (allows generic routing)
            - Returns False if sender_id is not in accepted_senders

        Args:
            item: Event payload dict

        Returns:
            bool
        """
        sender_id = item.get( "sender_id", "" ) if isinstance( item, dict ) else ""
        if not sender_id:
            return True  # No sender filtering if sender unknown
        return sender_id in self.accepted_senders

    def classify( self, question, sender_id="", context=None ):
        """
        Classify using the EngineeringClassifier.

        Requires:
            - question is a non-empty string

        Ensures:
            - Returns ( category, confidence ) tuple
            - Records confidence in circuit breaker

        Args:
            question: Decision question text
            sender_id: Requesting agent's sender ID
            context: Optional context dict

        Returns:
            Tuple of ( category_name, confidence )
        """
        category, confidence = self.classifier.classify( question, sender_id, context )

        # Record confidence for circuit breaker monitoring
        self.circuit_breaker.record_confidence( category, confidence )

        return ( category, confidence )

    def gate( self, category, trust_level, confidence ):
        """
        Gate decision based on trust level, mode, and circuit breaker.

        Requires:
            - category is a valid category name
            - trust_level is 1-5
            - confidence is 0.0-1.0

        Ensures:
            - In "shadow" mode: always returns "shadow"
            - In "suggest" mode: returns "suggest" for L2+, "shadow" for L1
            - In "active" mode: trust-level gating (L1=shadow, L2=suggest, L3+=act)
            - Circuit breaker tripped → returns "defer"

        Args:
            category: Decision category name
            trust_level: Current trust level
            confidence: Classification confidence

        Returns:
            Action string: "shadow", "suggest", "act", or "defer"
        """
        # Circuit breaker check
        if not self.circuit_breaker.check( category ):
            if self.debug: print( f"[EngineeringStrategy] Circuit breaker tripped for {category}" )
            return "defer"

        # Shadow mode — always shadow regardless of trust
        if self.trust_mode == "shadow":
            return "shadow"

        # Suggest mode — suggest at L2+, shadow at L1
        if self.trust_mode == "suggest":
            if trust_level >= 2:
                return "suggest"
            return "shadow"

        # Active mode — full trust-level gating
        if trust_level <= 1:
            return "shadow"
        elif trust_level == 2:
            return "suggest"
        else:
            return "act"

    def decide( self, question, category, context=None ):
        """
        Produce a decision value for the given question.

        For now, returns a simple heuristic decision. Future versions will
        use LLM-based reasoning for complex decisions.

        Requires:
            - question is a non-empty string
            - category is a valid category name

        Ensures:
            - Returns a decision value string
            - Returns "approved" for low-risk categories (testing, general)
            - Returns "requires_review" for high-risk categories

        Args:
            question: Decision question text
            category: Classified category
            context: Optional context dict

        Returns:
            Decision value string
        """
        # High-risk categories always suggest review
        if category in ( "deployment", "destructive", "architecture" ):
            return "requires_review"

        # Low-risk categories can be approved directly
        return "approved"

    def evaluate( self, question, sender_id="", context=None ):
        """
        Run the full pipeline with trust tracker integration.

        Overrides base evaluate() to use the trust tracker for accurate
        per-category trust levels instead of the default L1.

        Requires:
            - question is a non-empty string

        Ensures:
            - Returns DecisionResult with accurate trust level
            - Circuit breaker check is performed

        Args:
            question: Decision question text
            sender_id: Requesting agent's sender ID
            context: Optional context dict

        Returns:
            DecisionResult
        """
        category, confidence = self.classify( question, sender_id, context )

        # Get actual trust level from tracker (not default L1)
        trust_level = self.trust_tracker.get_level( category )

        action = self.gate( category, trust_level, confidence )

        value = None
        if action in ( "act", "suggest" ):
            value = self.decide( question, category, context )

        reason = f"Category '{category}' at L{trust_level} ({self.trust_mode} mode) → {action}"

        if self.debug:
            print( f"[EngineeringStrategy] {reason}" )

        return DecisionResult(
            action      = action,
            value       = value,
            category    = category,
            confidence  = confidence,
            trust_level = trust_level,
            reason      = reason
        )
