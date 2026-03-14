import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)


def convert_to_kepub(epub_path: Path, kepubify_bin: str = "kepubify") -> Path:
    """Convert an EPUB file to KEPUB using kepubify.

    Args:
        epub_path: Path to the source .epub file.
        kepubify_bin: Path to the kepubify binary (default: on PATH).

    Returns:
        Path to the converted .kepub.epub file.

    Raises:
        RuntimeError: If kepubify fails.
        FileNotFoundError: If the source EPUB doesn't exist.
    """
    epub_path = Path(epub_path)
    if not epub_path.exists():
        raise FileNotFoundError(f"EPUB not found: {epub_path}")

    output_dir = epub_path.parent

    result = subprocess.run(
        [kepubify_bin, "-o", str(output_dir), str(epub_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        log.error("kepubify failed: %s", result.stderr.strip())
        raise RuntimeError(f"kepubify conversion failed: {result.stderr.strip()}")

    # kepubify outputs <stem>.kepub.epub in the output dir
    kepub_path = output_dir / f"{epub_path.stem}.kepub.epub"

    if not kepub_path.exists():
        # Some versions may use slightly different naming; search for it
        candidates = list(output_dir.glob(f"{epub_path.stem}*.kepub.epub"))
        if candidates:
            kepub_path = candidates[0]
        else:
            raise RuntimeError(
                f"kepubify ran successfully but output not found: {kepub_path}"
            )

    # Remove the original EPUB
    epub_path.unlink()
    log.info("Converted: %s -> %s", epub_path.name, kepub_path.name)

    return kepub_path
