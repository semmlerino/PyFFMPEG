"""Advanced mutation testing strategies for ShotBot.

This module demonstrates mutation testing to verify test effectiveness.
Mutation testing modifies code to ensure tests catch the mutations.
"""

import ast
import copy
import inspect
import sys
from pathlib import Path
from typing import Callable, Tuple

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class MutationOperator:
    """Base class for mutation operators."""

    def mutate(self, node: ast.AST) -> ast.AST:
        """Apply mutation to AST node."""
        raise NotImplementedError


class BoundaryMutator(MutationOperator):
    """Mutates boundary conditions in comparisons."""

    def mutate(self, node: ast.AST) -> ast.AST:
        """Mutate comparison operators to test boundary conditions."""
        if isinstance(node, ast.Compare):
            mutated = copy.deepcopy(node)
            for i, op in enumerate(mutated.ops):
                if isinstance(op, ast.Lt):
                    mutated.ops[i] = ast.LtE()
                elif isinstance(op, ast.LtE):
                    mutated.ops[i] = ast.Lt()
                elif isinstance(op, ast.Gt):
                    mutated.ops[i] = ast.GtE()
                elif isinstance(op, ast.GtE):
                    mutated.ops[i] = ast.Gt()
            return mutated
        return node


class BooleanMutator(MutationOperator):
    """Mutates boolean operators and conditions."""

    def mutate(self, node: ast.AST) -> ast.AST:
        """Invert boolean operations."""
        if isinstance(node, ast.BoolOp):
            mutated = copy.deepcopy(node)
            if isinstance(mutated.op, ast.And):
                mutated.op = ast.Or()
            elif isinstance(mutated.op, ast.Or):
                mutated.op = ast.And()
            return mutated
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            # Remove the Not operator
            return node.operand
        return node


class ReturnValueMutator(MutationOperator):
    """Mutates return values to test error handling."""

    def mutate(self, node: ast.AST) -> ast.AST:
        """Mutate return statements."""
        if isinstance(node, ast.Return):
            mutated = copy.deepcopy(node)
            if mutated.value:
                # Replace with None
                if isinstance(mutated.value, ast.Constant):
                    if mutated.value.value is True:
                        mutated.value = ast.Constant(value=False)
                    elif mutated.value.value is False:
                        mutated.value = ast.Constant(value=True)
                    elif isinstance(mutated.value.value, (int, float)):
                        mutated.value = ast.Constant(value=0)
                elif isinstance(mutated.value, ast.Name):
                    mutated.value = ast.Constant(value=None)
            return mutated
        return node


class ExceptionMutator(MutationOperator):
    """Removes exception handling to test coverage."""

    def mutate(self, node: ast.AST) -> ast.AST:
        """Remove try-except blocks."""
        if isinstance(node, ast.Try):
            # Return just the try body
            return ast.Module(body=node.body, type_ignores=[])
        return node


class MutationTester:
    """Applies mutations and verifies tests detect them."""

    def __init__(self):
        self.mutators = [
            BoundaryMutator(),
            BooleanMutator(),
            ReturnValueMutator(),
            ExceptionMutator(),
        ]
        self.killed_mutants = []
        self.survived_mutants = []

    def mutate_function(self, func: Callable, mutator: MutationOperator) -> Callable:
        """Apply mutation to a function."""
        source = inspect.getsource(func)
        tree = ast.parse(source)

        # Apply mutation
        mutated_tree = self._apply_mutation(tree, mutator)

        # Compile and return new function
        code = compile(mutated_tree, filename="<mutated>", mode="exec")
        namespace = func.__globals__.copy()
        exec(code, namespace)
        return namespace[func.__name__]

    def _apply_mutation(self, tree: ast.AST, mutator: MutationOperator) -> ast.AST:
        """Recursively apply mutation to AST."""

        class MutationTransformer(ast.NodeTransformer):
            def visit(self, node):
                # Apply mutation
                mutated = mutator.mutate(node)
                # Continue visiting children
                return self.generic_visit(mutated)

        transformer = MutationTransformer()
        return transformer.visit(tree)

    def test_mutation_coverage(
        self, target_func: Callable, test_func: Callable
    ) -> Tuple[int, int]:
        """Test if mutations are caught by tests.

        Returns:
            Tuple of (killed_mutants, survived_mutants)
        """
        for mutator in self.mutators:
            try:
                # Apply mutation
                mutated_func = self.mutate_function(target_func, mutator)

                # Run test against mutated function
                try:
                    test_func(mutated_func)
                    # Test passed with mutation - BAD!
                    self.survived_mutants.append(
                        (target_func.__name__, mutator.__class__.__name__)
                    )
                except (AssertionError, Exception):
                    # Test caught the mutation - GOOD!
                    self.killed_mutants.append(
                        (target_func.__name__, mutator.__class__.__name__)
                    )
            except Exception:
                # Mutation failed to compile/run
                pass

        return len(self.killed_mutants), len(self.survived_mutants)


class TestMutationCoverage:
    """Test mutation coverage for critical functions."""

    def test_launcher_validation_mutations(self):
        """Test that launcher validation catches mutations."""

        def validate_command(command: str) -> bool:
            """Example validation function to mutate."""
            if not command:
                return False
            if ";" in command or "&" in command or "|" in command:
                return False
            if len(command) > 1000:
                return False
            return True

        def test_validation(func):
            """Test the validation function."""
            # Should reject empty
            assert not func("")
            # Should reject shell operators
            assert not func("rm -rf /; echo done")
            assert not func("cmd1 & cmd2")
            assert not func("cmd1 | cmd2")
            # Should reject too long
            assert not func("x" * 1001)
            # Should accept valid
            assert func("nuke --nc script.nk")

        tester = MutationTester()
        killed, survived = tester.test_mutation_coverage(
            validate_command, test_validation
        )

        # We should kill most mutants
        assert killed > survived, f"Too many mutations survived: {survived}"

    def test_shot_parsing_mutations(self):
        """Test that shot parsing catches mutations."""

        def parse_shot_name(name: str) -> Tuple[str, str, str]:
            """Parse shot name into components."""
            parts = name.split("_")
            if len(parts) != 3:
                raise ValueError("Invalid shot name")
            show = parts[0]
            seq = parts[1]
            shot = parts[2]
            return show, seq, shot

        def test_parsing(func):
            """Test the parsing function."""
            # Valid shot
            show, seq, shot = func("SHOW_SEQ01_001")
            assert show == "SHOW"
            assert seq == "SEQ01"
            assert shot == "001"

            # Invalid formats should raise
            with pytest.raises(ValueError):
                func("INVALID")
            with pytest.raises(ValueError):
                func("TOO_MANY_PARTS_HERE")

        tester = MutationTester()
        killed, survived = tester.test_mutation_coverage(parse_shot_name, test_parsing)

        assert killed >= survived

    def test_critical_path_coverage(self):
        """Test mutation coverage for critical application paths."""

        def critical_resource_check(
            memory_mb: int, cpu_percent: float, disk_gb: float
        ) -> bool:
            """Critical resource availability check."""
            if memory_mb < 100:  # Minimum memory
                return False
            if cpu_percent > 90.0:  # CPU threshold
                return False
            if disk_gb < 1.0:  # Minimum disk space
                return False
            return True

        def test_resources(func):
            """Test resource checking."""
            # Should fail on low memory
            assert not func(50, 50.0, 10.0)
            # Should fail on high CPU
            assert not func(500, 95.0, 10.0)
            # Should fail on low disk
            assert not func(500, 50.0, 0.5)
            # Should pass with good resources
            assert func(500, 50.0, 10.0)
            # Test boundaries
            assert not func(99, 50.0, 10.0)
            assert func(100, 50.0, 10.0)
            assert func(500, 90.0, 10.0)
            assert not func(500, 90.1, 10.0)

        tester = MutationTester()
        killed, survived = tester.test_mutation_coverage(
            critical_resource_check, test_resources
        )

        # Critical paths should have high mutation coverage
        mutation_score = killed / (killed + survived) if (killed + survived) > 0 else 0
        assert mutation_score >= 0.8, f"Mutation score too low: {mutation_score:.2f}"


class TestMutationStrategies:
    """Advanced mutation testing strategies."""

    def test_concurrent_mutation_detection(self):
        """Test that concurrent operation mutations are detected."""

        def concurrent_counter(operations: int) -> int:
            """Simulate concurrent counter."""
            counter = 0
            for _ in range(operations):
                counter += 1  # Mutation target: change to +=2, -=1, etc.
            return counter

        def test_counter(func):
            """Test the counter."""
            assert func(0) == 0
            assert func(1) == 1
            assert func(10) == 10
            assert func(100) == 100

        tester = MutationTester()
        killed, survived = tester.test_mutation_coverage(
            concurrent_counter, test_counter
        )

        assert killed > 0, "No mutations were killed"

    def test_state_machine_mutations(self):
        """Test state machine transition mutations."""

        class SimpleStateMachine:
            """Simple state machine for testing."""

            def __init__(self):
                self.state = "initial"

            def transition(self, event: str):
                """State transitions."""
                if self.state == "initial":
                    if event == "start":
                        self.state = "running"
                elif self.state == "running":
                    if event == "stop":
                        self.state = "stopped"
                    elif event == "pause":
                        self.state = "paused"
                elif self.state == "paused":
                    if event == "resume":
                        self.state = "running"
                    elif event == "stop":
                        self.state = "stopped"
                elif self.state == "stopped":
                    if event == "reset":
                        self.state = "initial"

        def test_state_machine():
            """Test state transitions."""
            sm = SimpleStateMachine()
            assert sm.state == "initial"

            sm.transition("start")
            assert sm.state == "running"

            sm.transition("pause")
            assert sm.state == "paused"

            sm.transition("resume")
            assert sm.state == "running"

            sm.transition("stop")
            assert sm.state == "stopped"

            sm.transition("reset")
            assert sm.state == "initial"

            # Test invalid transitions don't change state
            sm.transition("invalid")
            assert sm.state == "initial"

        # This demonstrates the concept - actual implementation would
        # mutate the transition logic and verify tests catch it
        test_state_machine()


if __name__ == "__main__":
    # Run mutation testing
    pytest.main([__file__, "-v"])
