"""
Decision proxy ratification API endpoints.

Provides REST endpoints for viewing pending decisions and ratifying
(approving/rejecting) them. Used by the morning ratification UI workflow.

Dependency Rule:
    This module NEVER imports from notification_proxy or swe_team.
"""

from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid

from ..db.database import get_db
from ..db.repositories.proxy_decision_repository import (
    ProxyDecisionRepository,
    TrustStateRepository,
)

router = APIRouter( prefix="/api/proxy", tags=[ "decision-proxy" ] )


@router.get( "/pending/{user_email}" )
async def get_pending_decisions(
    user_email: str,
    domain: Optional[str] = Query( None, description="Filter by domain (e.g., 'swe')" ),
    category: Optional[str] = Query( None, description="Filter by category" ),
    limit: int = Query( 100, description="Maximum number of decisions to return" )
):
    """
    Get pending decisions awaiting ratification for a user.

    Requires:
        - user_email is a valid email address

    Ensures:
        - Returns list of pending decisions with full context
        - Applies optional domain and category filters
        - Ordered by created_at ascending (oldest first)

    Raises:
        - HTTPException with 500 for query failures

    Args:
        user_email: User's email address
        domain: Optional domain filter
        category: Optional category filter
        limit: Maximum results

    Returns:
        Dict with pending decisions and summary
    """
    try:
        with get_db() as session:
            repo = ProxyDecisionRepository( session )

            decisions = repo.get_pending( domain=domain, category=category, limit=limit )
            summary   = repo.get_pending_summary( domain=domain )

            result = []
            for d in decisions:
                result.append( {
                    "id"                  : str( d.id ),
                    "notification_id"     : d.notification_id,
                    "domain"              : d.domain,
                    "category"            : d.category,
                    "question"            : d.question,
                    "sender_id"           : d.sender_id,
                    "action"              : d.action,
                    "decision_value"      : d.decision_value,
                    "confidence"          : d.confidence,
                    "trust_level"         : d.trust_level,
                    "reason"              : d.reason,
                    "ratification_state"  : d.ratification_state,
                    "metadata_json"       : d.metadata_json,
                    "created_at"          : d.created_at.isoformat() if d.created_at else None,
                } )

            print( f"[DECISION PROXY] Returning {len( result )} pending decisions for {user_email}" )

            return {
                "status"    : "success",
                "decisions" : result,
                "summary"   : summary,
            }

    except Exception as e:
        print( f"[DECISION PROXY] Error getting pending decisions: {str( e )}" )
        raise HTTPException(
            status_code = 500,
            detail      = f"Failed to get pending decisions: {str( e )}"
        )


@router.post( "/ratify/{decision_id}" )
async def ratify_decision(
    decision_id: str,
    approved: bool = Query( ..., description="True to approve, False to reject" ),
    feedback: str = Query( "", description="Optional feedback text" ),
    user_email: str = Query( ..., description="Email of the ratifying user" )
):
    """
    Ratify (approve or reject) a pending decision.

    Requires:
        - decision_id is a valid UUID
        - approved is a boolean
        - user_email is a valid email address

    Ensures:
        - Decision ratification_state updated to "approved" or "rejected"
        - ratified_by and ratified_at set
        - Trust state counters updated
        - Returns updated decision

    Raises:
        - HTTPException with 404 if decision not found
        - HTTPException with 400 if already ratified
        - HTTPException with 500 for update failures

    Args:
        decision_id: UUID of the decision
        approved: True to approve, False to reject
        feedback: Optional feedback text
        user_email: Ratifying user's email

    Returns:
        Dict with ratification result
    """
    try:
        with get_db() as session:
            decision_repo = ProxyDecisionRepository( session )
            trust_repo    = TrustStateRepository( session )

            # Look up the decision
            decision = decision_repo.get_by_id( uuid.UUID( decision_id ) )
            if not decision:
                raise HTTPException(
                    status_code = 404,
                    detail      = f"Decision {decision_id} not found"
                )

            # Check if already ratified
            if decision.ratification_state in ( "approved", "rejected" ):
                raise HTTPException(
                    status_code = 400,
                    detail      = f"Decision already ratified: {decision.ratification_state}"
                )

            # Ratify
            updated = decision_repo.ratify(
                decision_id = uuid.UUID( decision_id ),
                approved    = approved,
                ratified_by = user_email,
                feedback    = feedback
            )

            # Update trust state
            trust_repo.update_after_ratification(
                user_email = user_email,
                domain     = decision.domain,
                category   = decision.category,
                approved   = approved
            )

            action_word = "approved" if approved else "rejected"
            print( f"[DECISION PROXY] Decision {decision_id} {action_word} by {user_email}" )

            return {
                "status"              : "success",
                "decision_id"         : decision_id,
                "ratification_state"  : updated.ratification_state,
                "ratified_by"         : user_email,
                "ratified_at"         : updated.ratified_at.isoformat() if updated.ratified_at else None,
                "feedback"            : feedback,
                "domain"              : updated.domain,
                "category"            : updated.category,
            }

    except HTTPException:
        raise
    except Exception as e:
        print( f"[DECISION PROXY] Error ratifying decision {decision_id}: {str( e )}" )
        raise HTTPException(
            status_code = 500,
            detail      = f"Failed to ratify decision: {str( e )}"
        )


@router.get( "/trust/{user_email}" )
async def get_trust_state(
    user_email: str,
    domain: Optional[str] = Query( None, description="Filter by domain" )
):
    """
    Get trust state for a user across all domains/categories.

    Requires:
        - user_email is a valid email address

    Ensures:
        - Returns all trust states for the user
        - Applies optional domain filter
        - Ordered by domain, then category

    Raises:
        - HTTPException with 500 for query failures

    Args:
        user_email: User's email address
        domain: Optional domain filter

    Returns:
        Dict with trust states
    """
    try:
        with get_db() as session:
            repo = TrustStateRepository( session )

            states = repo.get_all_for_user( user_email, domain=domain )

            result = []
            for s in states:
                result.append( {
                    "id"                    : str( s.id ),
                    "domain"                : s.domain,
                    "category"              : s.category,
                    "trust_level"           : s.trust_level,
                    "total_decisions"       : s.total_decisions,
                    "successful_decisions"  : s.successful_decisions,
                    "rejected_decisions"    : s.rejected_decisions,
                    "circuit_breaker_state" : s.circuit_breaker_state,
                    "created_at"            : s.created_at.isoformat() if s.created_at else None,
                    "updated_at"            : s.updated_at.isoformat() if s.updated_at else None,
                } )

            print( f"[DECISION PROXY] Returning {len( result )} trust states for {user_email}" )

            return {
                "status"       : "success",
                "user_email"   : user_email,
                "trust_states" : result,
            }

    except Exception as e:
        print( f"[DECISION PROXY] Error getting trust state for {user_email}: {str( e )}" )
        raise HTTPException(
            status_code = 500,
            detail      = f"Failed to get trust state: {str( e )}"
        )


@router.get( "/decisions/{domain}/{category}" )
async def get_decisions_by_domain_category(
    domain: str,
    category: str,
    limit: int = Query( 50, description="Maximum number of decisions to return" )
):
    """
    Get decision history for a specific domain and category.

    Requires:
        - domain is a valid domain identifier
        - category is a valid category name

    Ensures:
        - Returns decisions matching domain+category
        - Ordered by created_at descending (newest first)

    Raises:
        - HTTPException with 500 for query failures

    Args:
        domain: Domain identifier (e.g., "swe")
        category: Decision category (e.g., "testing")
        limit: Maximum results

    Returns:
        Dict with decisions
    """
    try:
        with get_db() as session:
            repo = ProxyDecisionRepository( session )

            decisions = repo.get_by_domain_category( domain, category, limit=limit )

            result = []
            for d in decisions:
                result.append( {
                    "id"                  : str( d.id ),
                    "notification_id"     : d.notification_id,
                    "question"            : d.question,
                    "sender_id"           : d.sender_id,
                    "action"              : d.action,
                    "decision_value"      : d.decision_value,
                    "confidence"          : d.confidence,
                    "trust_level"         : d.trust_level,
                    "reason"              : d.reason,
                    "ratification_state"  : d.ratification_state,
                    "created_at"          : d.created_at.isoformat() if d.created_at else None,
                } )

            return {
                "status"    : "success",
                "domain"    : domain,
                "category"  : category,
                "decisions" : result,
            }

    except Exception as e:
        print( f"[DECISION PROXY] Error getting decisions for {domain}/{category}: {str( e )}" )
        raise HTTPException(
            status_code = 500,
            detail      = f"Failed to get decisions: {str( e )}"
        )
