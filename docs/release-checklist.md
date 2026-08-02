# Public release checklist

## One-time repository setup

- Create the GitHub repository, normally named `valence`.
- Set the default branch to `main`.
- Enable Issues and Discussions as desired.
- Enable private vulnerability reporting.
- Require the test workflow before merging to `main`.
- Add the final GitHub repository URL to `CITATION.cff` and project metadata.

## Before tagging

```bash
pytest
python -m compileall -q src scripts tests
git status --short
```

Confirm:

- version matches in `pyproject.toml`, `src/valence/__init__.py`,
  `CITATION.cff`, and `CHANGELOG.md`;
- no credentials, private paths, participant data, or unpublished traces are
  present;
- synthetic calibration profiles are labeled synthetic;
- frozen configurations and reference outputs are committed; and
- the working tree is clean.

## Tag and release

```bash
git tag -a v0.7.0 -m "VALENCE v0.7.0 public research release"
git push origin main
git push origin v0.7.0
```

The release workflow builds source and wheel artifacts. Attach the paper package
and the self-contained Colab notebook if desired.

## Archival DOI

After the GitHub release is final, connect the repository to an archival service
such as Zenodo, mint a DOI, and add the DOI plus repository URL to
`CITATION.cff`.
