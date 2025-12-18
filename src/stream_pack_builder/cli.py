"""Command line interface for Stream Pack Builder."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv

from .config import PackConfig
from .generator import build_pack
from .postprocess import postprocess_selected
from .utils import packs_root, setup_logging
from .multi_agent.orchestrator import run_multi_agent_workflow

# Load environment variables from .env file
load_dotenv()

app = typer.Typer(help="Batch-generate streaming overlay packs with Gemini.")


@app.callback()
def _init(ctx: typer.Context, verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging.")) -> None:
    """Initialize logging for all commands."""

    setup_logging(level=10 if verbose else 20)  # 10=DEBUG, 20=INFO
    ctx.obj = {}


@app.command()
def build(
    pack_name: str = typer.Argument(..., help="Name of the pack directory under packs/"),
    num_variants: int = typer.Option(2, "--num-variants", "-n", help="Images per screen type."),
    seed: Optional[int] = typer.Option(None, help="Deterministic seed forwarded to the model."),
    dry_run: bool = typer.Option(False, help="Log actions without calling the API."),
) -> None:
    """Generate raw images for a given pack."""

    pack_dir = packs_root() / pack_name
    config_path = pack_dir / "config.yaml"
    config = PackConfig.load(config_path)
    build_pack(config=config, pack_dir=pack_dir, num_variants=num_variants, seed=seed, dry_run=dry_run)


@app.command()
def postprocess(
    pack_name: str = typer.Argument(..., help="Name of the pack directory under packs/"),
    dry_run: bool = typer.Option(False, help="Log actions without writing files."),
) -> None:
    """Resize and rename selected images into final deliverables and mockups."""

    pack_dir = packs_root() / pack_name
    config_path = pack_dir / "config.yaml"
    config = PackConfig.load(config_path)
    postprocess_selected(config=config, pack_dir=pack_dir, dry_run=dry_run)


@app.command(name="multi-agent-build")
def multi_agent_build(
    pack_name: str = typer.Argument(..., help="Name of the pack directory under packs/"),
    max_rounds: int = typer.Option(3, "--max-rounds", help="Maximum number of improvement rounds."),
    threshold: float = typer.Option(8.5, "--threshold", help="Quality threshold for passing (0-10)."),
    seed: Optional[int] = typer.Option(None, help="Deterministic seed for reproducibility."),
    dry_run: bool = typer.Option(False, help="Log actions without calling APIs or writing files."),
) -> None:
    """Run multi-agent workflow with iterative improvement (Phase 2).

    This command executes a multi-round workflow:
    1. PM prepares round brief
    2. Prompt Engineer refines prompts based on previous feedback
    3. Executor generates images and postprocesses them
    4. Critic evaluates quality and suggests improvements
    5. Repeat until quality threshold met or max rounds reached

    Example:
        stream-pack multi-agent-build neon_cyberpunk --max-rounds 3 --threshold 8.5
    """
    typer.echo(f"Starting multi-agent workflow for pack: {pack_name}")
    typer.echo(f"Max rounds: {max_rounds}, Threshold: {threshold}")

    workflow_state = run_multi_agent_workflow(
        pack_name=pack_name,
        max_rounds=max_rounds,
        quality_threshold=threshold,
        dry_run=dry_run,
        seed=seed,
    )

    # Print summary
    typer.echo("\n" + "=" * 60)
    typer.echo("WORKFLOW SUMMARY")
    typer.echo("=" * 60)
    typer.echo(f"Pack: {workflow_state.pack_name}")
    typer.echo(f"Rounds completed: {len(workflow_state.rounds)}/{workflow_state.max_rounds}")

    if workflow_state.score_trend:
        score_str = " → ".join(f"{s:.1f}" for s in workflow_state.score_trend)
        typer.echo(f"Score progression: {score_str}")

    typer.echo(f"Final status: {workflow_state.completion_reason}")

    # Print decision status
    if "PASS" in workflow_state.completion_reason:
        typer.echo("[PASS] Quality threshold met!")
    elif "BLOCKED" in workflow_state.completion_reason:
        typer.echo("[BLOCKED] Critical issues detected")
    else:
        typer.echo("[CONTINUE] Max rounds reached")

    typer.echo("=" * 60)


if __name__ == "__main__":  # pragma: no cover
    app()
