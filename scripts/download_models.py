"""Provision pinned HF snapshots after the operator accepts each model's terms.

Run from a provisioned venv. Credentials come from HF_TOKEN or the HF login store,
never from this repository. This command downloads weights; it does not infer.
"""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, required=True,
                        help="Hugging Face hub directory (HF_HOME/hub)")
    parser.add_argument("--accepted-model-terms", action="store_true")
    args = parser.parse_args()
    if not args.accepted_model_terms:
        parser.error("Read model cards, accept gated terms, then explicitly confirm terms")
    from huggingface_hub import snapshot_download

    specs = json.loads(Path(__file__).with_name("model_revisions.json").read_text("utf-8"))
    # Dependencies referenced by repo ID use main in offline mode. Do not silently
    # repoint an existing cache to a different model revision.
    for spec in specs:
        ref = args.cache_dir / ("models--" + spec["repo_id"].replace("/", "--")) / "refs/main"
        if ref.exists() and ref.read_text("utf-8").strip() != spec["revision"]:
            parser.error("Existing main revision differs; choose a new dedicated cache directory")
    for spec in specs:
        snapshot_download(repo_id=spec["repo_id"], revision=spec["revision"],
                          cache_dir=str(args.cache_dir.resolve()),
                          allow_patterns=spec.get("allow_patterns"))
        ref = args.cache_dir / ("models--" + spec["repo_id"].replace("/", "--")) / "refs/main"
        if not ref.exists():
            ref.parent.mkdir(parents=True, exist_ok=True)
            with ref.open("x", encoding="utf-8") as stream:
                stream.write(spec["revision"])


if __name__ == "__main__":
    main()
