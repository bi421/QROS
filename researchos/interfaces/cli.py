import click

from researchos.pipeline import ResearchPipeline
from researchos.storage.repository import ResearchRepository


@click.group()
def cli() -> None:
    """ResearchOS Command Line Interface"""
    pass


@cli.command()
@click.option("--topic", prompt="Research topic", help="The topic for the research cycle.")
def run(topic: str) -> None:
    click.echo(f"[-] Initializing research cycle for topic: '{topic}'...")
    repo = ResearchRepository()
    pipeline = ResearchPipeline(repo)

    research = pipeline.start_research(question=topic)

    click.secho(f"[+] Research Cycle completed successfully! ID: {research.id}", fg="green")


@cli.command()
def verify() -> None:
    click.echo("[-] Verifying cryptographic audit chain integrity...")
    repo = ResearchRepository()
    is_valid = repo.verify_audit_chain()

    if is_valid:
        click.secho("[+] Audit chain integrity verified: VALID [OK]", fg="green")
    else:
        click.secho("[X] Audit chain integrity verified: INVALID [FAIL]", fg="red", err=True)


if __name__ == "__main__":
    cli()
