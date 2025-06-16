"""State management abstraction for Wyoming Bridge components."""

import asyncio
import logging
from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Optional, Dict, Callable, Awaitable
from dataclasses import dataclass

_LOGGER = logging.getLogger("state")


class BaseState(Enum):
    """Base states that all state machines should support."""
    NOT_STARTED = auto()
    STARTING = auto()
    STARTED = auto()
    STOPPING = auto()
    STOPPED = auto()
    RESTARTING = auto()


@dataclass
class StateTransition:
    """Represents a state transition with optional validation."""
    from_state: BaseState
    to_state: BaseState
    condition: Optional[Callable[[], bool]] = None
    action: Optional[Callable[[], Awaitable[None]]] = None


class StateMachine:
    """Generic state machine with event-driven transitions."""

    def __init__(
        self,
        initial_state: BaseState = BaseState.NOT_STARTED,
        name: str = "state_machine"
    ):
        self.name = name
        self._state = initial_state
        self._state_changed = asyncio.Event()
        self._transitions: Dict[BaseState, Dict[BaseState, StateTransition]] = {}
        self._state_handlers: Dict[BaseState, Callable[[], Awaitable[None]]] = {}

    @property
    def state(self) -> BaseState:
        """Get current state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """True if not stopping/stopped."""
        return self._state not in (BaseState.STOPPED, BaseState.STOPPING)

    def add_transition(self, transition: StateTransition) -> None:
        """Add a valid state transition."""
        if transition.from_state not in self._transitions:
            self._transitions[transition.from_state] = {}
        self._transitions[transition.from_state][transition.to_state] = transition

    def add_state_handler(self, state: BaseState, handler: Callable[[], Awaitable[None]]) -> None:
        """Add a handler for when entering a specific state."""
        self._state_handlers[state] = handler

    async def transition_to(self, new_state: BaseState) -> bool:
        """Attempt to transition to a new state."""
        current_transitions = self._transitions.get(self._state, {})
        transition = current_transitions.get(new_state)

        _LOGGER.debug("Attempting transition in %s: %s -> %s",
                      self.name, self._state.name, new_state.name)

        if transition is None:
            _LOGGER.warning("Invalid transition from %s to %s in %s",
                            self._state.name, new_state.name, self.name)
            return False

        # Check condition if present
        if transition.condition and not transition.condition():
            _LOGGER.debug("Transition condition failed for %s -> %s in %s",
                          self._state.name, new_state.name, self.name)
            return False

        old_state = self._state
        self._state = new_state

        _LOGGER.debug("State transition in %s: %s -> %s",
                      self.name, old_state.name, new_state.name)

        # Execute transition action if present
        if transition.action:
            try:
                await transition.action()
            except Exception:
                _LOGGER.exception("Error executing transition action for %s -> %s in %s",
                                  old_state.name, new_state.name, self.name)
                # Revert state change on action failure
                self._state = old_state
                return False

        # Execute state handler if present
        handler = self._state_handlers.get(new_state)
        if handler:
            try:
                await handler()
            except Exception:
                _LOGGER.exception("Error executing state handler for %s in %s",
                                  new_state.name, self.name)

        # Notify state change
        self._state_changed.set()
        self._state_changed.clear()

        return True

    async def wait_for_state_change(self) -> None:
        """Wait for the next state change."""
        await self._state_changed.wait()

    async def wait_for_state(self, target_state: BaseState, timeout: Optional[float] = None) -> bool:
        """Wait for a specific state, with optional timeout."""
        if self._state == target_state:
            return True

        try:
            while self._state != target_state:
                await asyncio.wait_for(self._state_changed.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False


class BridgeStateMachine(StateMachine):
    """Specialized state machine for bridge components."""

    def __init__(self, name: str = "bridge"):
        super().__init__(BaseState.NOT_STARTED, name)
        self._setup_bridge_transitions()

    def _setup_bridge_transitions(self) -> None:
        """Set up standard bridge state transitions."""
        # Standard startup flow
        self.add_transition(StateTransition(
            BaseState.NOT_STARTED, BaseState.STARTING
        ))
        self.add_transition(StateTransition(
            BaseState.STARTING, BaseState.STARTED
        ))

        # Shutdown flow
        self.add_transition(StateTransition(
            BaseState.STARTED, BaseState.STOPPING
        ))
        self.add_transition(StateTransition(
            BaseState.STARTING, BaseState.STOPPING  # Can stop while starting
        ))
        self.add_transition(StateTransition(
            BaseState.STOPPING, BaseState.STOPPED
        ))

        # Restart flow
        self.add_transition(StateTransition(
            BaseState.STARTED, BaseState.RESTARTING
        ))
        self.add_transition(StateTransition(
            BaseState.STARTING, BaseState.RESTARTING  # Can restart if start fails
        ))
        self.add_transition(StateTransition(
            BaseState.RESTARTING, BaseState.NOT_STARTED
        ))
        self.add_transition(StateTransition(
            BaseState.RESTARTING, BaseState.STOPPING  # Can stop while restarting
        ))


class LifecycleManager(ABC):
    """Abstract base for components with lifecycle management."""

    def __init__(self, name: str):
        self.name = name
        self._state_machine = BridgeStateMachine(name)
        self._setup_lifecycle_handlers()

    @property
    def state(self) -> BaseState:
        """Get current state."""
        return self._state_machine.state

    @property
    def is_running(self) -> bool:
        """True if component is running."""
        return self._state_machine.is_running

    def _setup_lifecycle_handlers(self) -> None:
        """Set up handlers for lifecycle states."""
        self._state_machine.add_state_handler(
            BaseState.STARTING, self._on_starting)
        self._state_machine.add_state_handler(
            BaseState.STARTED, self._on_started)
        self._state_machine.add_state_handler(
            BaseState.STOPPING, self._on_stopping)
        self._state_machine.add_state_handler(
            BaseState.STOPPED, self._on_stopped)
        self._state_machine.add_state_handler(
            BaseState.RESTARTING, self._on_restarting)

    async def start(self) -> bool:
        """Start the component."""
        return await self._state_machine.transition_to(BaseState.STARTING)

    async def stop(self) -> bool:
        """Stop the component."""
        success = await self._state_machine.transition_to(BaseState.STOPPING)
        if success:
            # Wait for stopped state
            await self._state_machine.wait_for_state(BaseState.STOPPED)
        return success

    async def restart(self) -> bool:
        """Restart the component."""
        return await self._state_machine.transition_to(BaseState.RESTARTING)

    async def wait_for_state_change(self) -> None:
        """Wait for the next state change."""
        await self._state_machine.wait_for_state_change()

    # Abstract lifecycle methods - implement in subclasses
    @abstractmethod
    async def _on_starting(self) -> None:
        """Called when transitioning to STARTING state."""
        pass

    @abstractmethod
    async def _on_started(self) -> None:
        """Called when transitioning to STARTED state."""
        pass

    @abstractmethod
    async def _on_stopping(self) -> None:
        """Called when transitioning to STOPPING state."""
        pass

    @abstractmethod
    async def _on_stopped(self) -> None:
        """Called when transitioning to STOPPED state."""
        pass

    @abstractmethod
    async def _on_restarting(self) -> None:
        """Called when transitioning to RESTARTING state."""
        pass
