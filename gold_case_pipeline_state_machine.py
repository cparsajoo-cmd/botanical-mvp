"""gold_case_pipeline_state_machine.py

Gold Case Generation Pipeline State Machine

Defines mandatory stages that every case must pass through.
No case may skip a state.
Pipeline stops automatically if any mandatory stage fails.

States:
  DISCOVERED → SOURCE_RETRIEVED → SOURCE_VERIFIED → EVIDENCE_EXTRACTED →
  READY_FOR_ENGINE → ENGINE_VALIDATED → TEST_VALIDATED → SUPERVISOR_APPROVED

Transitions are one-way and sequential. No backtracking or skipping.
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List
from enum import Enum
from datetime import datetime


class PipelineState(str, Enum):
    """Mandatory pipeline states"""
    DISCOVERED = "DISCOVERED"
    SOURCE_RETRIEVED = "SOURCE_RETRIEVED"
    SOURCE_VERIFIED = "SOURCE_VERIFIED"
    EVIDENCE_EXTRACTED = "EVIDENCE_EXTRACTED"
    READY_FOR_ENGINE = "READY_FOR_ENGINE"
    ENGINE_VALIDATED = "ENGINE_VALIDATED"
    TEST_VALIDATED = "TEST_VALIDATED"
    SUPERVISOR_APPROVED = "SUPERVISOR_APPROVED"


class PipelineErrorType(str, Enum):
    """Error types that halt pipeline"""
    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    SOURCE_NOT_VERIFIED = "SOURCE_NOT_VERIFIED"
    METADATA_FABRICATED = "METADATA_FABRICATED"
    EVIDENCE_NOT_VERBATIM = "EVIDENCE_NOT_VERBATIM"
    ENGINE_EVALUATION_FAILED = "ENGINE_EVALUATION_FAILED"
    TEST_INTEGRATION_FAILED = "TEST_INTEGRATION_FAILED"
    REGRESSION_FAILED = "REGRESSION_FAILED"
    REPORT_VALIDATION_FAILED = "REPORT_VALIDATION_FAILED"


@dataclass
class StateTransition:
    """Record of a state transition"""
    from_state: PipelineState
    to_state: PipelineState
    timestamp: datetime
    reason: str
    details: Dict = field(default_factory=dict)


@dataclass
class PipelineHalt:
    """Pipeline halt record"""
    state: PipelineState
    error_type: PipelineErrorType
    message: str
    timestamp: datetime
    evidence: Dict = field(default_factory=dict)


class GoldCasePipelineState:
    """State machine for Gold Case generation"""
    
    # State order - CANNOT be reordered
    STATE_SEQUENCE = [
        PipelineState.DISCOVERED,
        PipelineState.SOURCE_RETRIEVED,
        PipelineState.SOURCE_VERIFIED,
        PipelineState.EVIDENCE_EXTRACTED,
        PipelineState.READY_FOR_ENGINE,
        PipelineState.ENGINE_VALIDATED,
        PipelineState.TEST_VALIDATED,
        PipelineState.SUPERVISOR_APPROVED,
    ]
    
    def __init__(self, case_id: str):
        self.case_id = case_id
        self.current_state = None
        self.transitions: List[StateTransition] = []
        self.halts: List[PipelineHalt] = []
        self.state_data: Dict = {}
        self.is_halted = False
        self.halt_reason = None
    
    def advance(self, to_state: PipelineState, reason: str, details: Dict = None) -> bool:
        """
        Advance to next state.
        
        Returns: True if successful, False if halt
        """
        if self.is_halted:
            print(f"❌ Pipeline halted: {self.case_id}")
            print(f"   Reason: {self.halt_reason}")
            return False
        
        # Validate state transition is legal
        if self.current_state is None:
            if to_state != PipelineState.DISCOVERED:
                self.halt(
                    PipelineState.DISCOVERED,
                    PipelineErrorType.SOURCE_NOT_FOUND,
                    f"First state must be DISCOVERED, not {to_state}",
                    {"attempted_state": to_state}
                )
                return False
        else:
            current_index = self.STATE_SEQUENCE.index(self.current_state)
            to_index = self.STATE_SEQUENCE.index(to_state)
            
            if to_index != current_index + 1:
                self.halt(
                    self.current_state,
                    PipelineErrorType.SOURCE_NOT_FOUND,
                    f"Cannot jump from {self.current_state} to {to_state}. "
                    f"Must advance sequentially.",
                    {"current": self.current_state, "attempted": to_state}
                )
                return False
        
        # Record transition
        transition = StateTransition(
            from_state=self.current_state,
            to_state=to_state,
            timestamp=datetime.utcnow(),
            reason=reason,
            details=details or {}
        )
        self.transitions.append(transition)
        self.current_state = to_state
        
        print(f"✓ {self.case_id}: {to_state}")
        return True
    
    def halt(self, state: PipelineState, error_type: PipelineErrorType,
             message: str, evidence: Dict = None):
        """Halt pipeline"""
        halt = PipelineHalt(
            state=state,
            error_type=error_type,
            message=message,
            timestamp=datetime.utcnow(),
            evidence=evidence or {}
        )
        self.halts.append(halt)
        self.is_halted = True
        self.halt_reason = message
        
        print(f"❌ Pipeline halted at {state}")
        print(f"   Error: {error_type}")
        print(f"   Message: {message}")
    
    def get_status(self) -> Dict:
        """Get current pipeline status"""
        return {
            "case_id": self.case_id,
            "current_state": self.current_state,
            "is_halted": self.is_halted,
            "halt_reason": self.halt_reason,
            "transition_count": len(self.transitions),
            "halt_count": len(self.halts),
            "states_completed": [t.to_state for t in self.transitions],
        }
    
    def is_approved(self) -> bool:
        """Check if case reached SUPERVISOR_APPROVED state"""
        return self.current_state == PipelineState.SUPERVISOR_APPROVED
    
    def require_state(self, required_state: PipelineState) -> bool:
        """
        Require that case has reached this state.
        Used in assertions before proceeding to next stage.
        """
        if self.current_state != required_state:
            self.halt(
                self.current_state,
                PipelineErrorType.SOURCE_NOT_FOUND,
                f"Case must be in {required_state} state, currently {self.current_state}",
                {"required": required_state, "actual": self.current_state}
            )
            return False
        return True


if __name__ == "__main__":
    print("\nGold Case Pipeline State Machine")
    print("="*60)
    print("\nMandatory state sequence:")
    for i, state in enumerate(GoldCasePipelineState.STATE_SEQUENCE, 1):
        print(f"  {i}. {state}")
    
    print("\nNo case may skip a state.")
    print("Pipeline stops automatically if any stage fails.")
    print("\nExample: Case 008 (Ginkgo biloba)")
    print("-" * 60)
    
    state = GoldCasePipelineState("CASE_008_GINKGO_BILOBA")
    
    # Successful progression
    state.advance(PipelineState.DISCOVERED, "Discovered from catalog")
    state.advance(PipelineState.SOURCE_RETRIEVED, "Retrieved Cochrane URL")
    state.advance(PipelineState.SOURCE_VERIFIED, "Verified DOI and metadata")
    state.advance(PipelineState.EVIDENCE_EXTRACTED, "Extracted exact quote with locators")
    state.advance(PipelineState.READY_FOR_ENGINE, "Prepared for evaluation")
    state.advance(PipelineState.ENGINE_VALIDATED, "Engine produced correct output")
    state.advance(PipelineState.TEST_VALIDATED, "Integration tests pass")
    state.advance(PipelineState.SUPERVISOR_APPROVED, "Supervisor approved")
    
    print("\n" + "-" * 60)
    print("Final status:")
    import json
    status = state.get_status()
    print(json.dumps(status, indent=2, default=str))
    print(f"\nApproved: {state.is_approved()}")
