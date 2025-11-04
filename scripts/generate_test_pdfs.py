"""Helper script to quickly generate a small test dataset.

This script generates a small number of synthetic PDFs for quick testing.
"""

import subprocess
import sys
from pathlib import Path


def main():
    """Generate test PDFs."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate test PDFs quickly")
    parser.add_argument("--n", type=int, default=10, help="Number of PDFs to generate (default: 10)")
    parser.add_argument("--schema", type=Path, default=None, help="Schema file (default: data/samples/dataset.json)")
    parser.add_argument("--label", type=str, default="test", help="Document label (default: test)")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: data/synth/test)")
    parser.add_argument("--archetypes", type=str, default=None, help="Comma-separated archetypes (default: all)")
    parser.add_argument("--no-noise", action="store_true", help="Disable noise/perturbations")
    args = parser.parse_args()
    
    # Defaults
    if args.schema is None:
        args.schema = Path(__file__).parent.parent / "data" / "samples" / "dataset.json"
    
    if args.out is None:
        args.out = Path(__file__).parent.parent / "data" / "synth" / "test"
    
    # Check schema exists
    if not args.schema.exists():
        print(f"Error: Schema file not found: {args.schema}", file=sys.stderr)
        print(f"Please provide a schema file with --schema", file=sys.stderr)
        sys.exit(1)
    
    # Build command
    cmd = [
        sys.executable,
        "-m",
        "data.synth.factory.synth",
        "--schema",
        str(args.schema),
        "--label",
        args.label,
        "--n",
        str(args.n),
        "--out",
        str(args.out),
        "--engine",
        "weasyprint",
    ]
    
    if args.archetypes:
        cmd.extend(["--archetypes", args.archetypes])
    else:
        # Use a mix of archetypes
        cmd.extend(["--archetypes", "generic_card,generic_form,generic_screen"])
    
    if not args.no_noise:
        cmd.append("--with-noise")
    
    print(f"Generating {args.n} test PDFs...")
    print(f"Schema: {args.schema}")
    print(f"Output: {args.out}")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 80)
    
    try:
        result = subprocess.run(cmd, check=True, cwd=Path(__file__).parent.parent)
        
        labels_path = args.out / "labels.jsonl"
        pdfs_dir = args.out / "pdfs"
        
        print("\n" + "=" * 80)
        print("Generation complete!")
        print("=" * 80)
        print(f"PDFs saved to: {pdfs_dir}")
        print(f"Labels saved to: {labels_path}")
        print("\nTo test the generated PDFs, run:")
        print(f"  python scripts/test_synthetic.py --labels {labels_path}")
        print("\nOr test individual PDFs:")
        if pdfs_dir.exists() and list(pdfs_dir.glob("*.pdf")):
            first_pdf = sorted(pdfs_dir.glob("*.pdf"))[0]
            print(f"  python -m src.app.cli --run \\")
            print(f"    --label {args.label} \\")
            print(f"    --schema {args.schema} \\")
            print(f"    --pdf {first_pdf}")
    
    except subprocess.CalledProcessError as e:
        print(f"\nError: Generation failed with exit code {e.returncode}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nGeneration interrupted by user", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

