class KernelError(Exception):
    """Base exception for all AegisOS kernel errors."""

class CycleDetectedError(KernelError):
    """Raised when a graph definition or dynamic routing forms an illegal cycle."""

    def __init__(self, cycle_path: list[str] | str) -> None:
        if isinstance(cycle_path, list):
            path_str="->".join(cycle_path)
        else:
            path_str=str(cycle_path)
        super().__init__(f"Cycle detected in state machine execution graph: {path_str}")
        self.cycle_path=cycle_path

class StagnationError(KernelError):
    """Raised when an agent repeatedly fails without state progression."""

    def __init__(self,failure_count: int,threshold: int,role: str) -> None:
        super().__init__(
            f"Agent '{role}' reached stagnation threshold ({failure_count}/{threshold} consecutive failures). "
            f"Execution halted to prevent token exhaustion."
        )
        self.failure_count=failure_count
        self.threshold=threshold
        self.role=role

class MaxStepsExceededError(KernelError):
    """Raised when a mission reaches its configured maximum execution budget."""

    def __init__(self,current_steps: int,max_steps: int) -> None:
        super().__init__(
            f"Mission exceeded maximum execution budget: {current_steps}/{max_steps} steps taken. "
            f"Execution halted."
        )
        self.current_steps=current_steps
        self.max_steps=max_steps

class InvalidTransitionError(KernelError):
    """Raised when an illegal state change or transition is attempted."""

    def __init__(self,from_state: str,to_state: str,reason: str="") -> None:
        msg=f"Invalid state transition from '{from_state}' to '{to_state}'."
        if reason:
            msg+=f" Reason: {reason}"
        super().__init__(msg)
        self.from_state=from_state
        self.to_state=to_state
        self.reason=reason

class CheckpointNotFoundError(KernelError):
    """Raised when a requested checkpoint or rollback target does not exist."""

    def __init__(self,session_id: str,step_index: int) -> None:
        super().__init__(
            f"No checkpoint found for session '{session_id}' at step index {step_index}."
        )
        self.session_id=session_id
        self.step_index=step_index