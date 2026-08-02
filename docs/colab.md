# Google Colab

Two notebooks are provided:

1. `notebooks/VALENCE_Colab_Quickstart.ipynb` uses a source tree already stored
   at `/content/drive/MyDrive/valence/source` or clones the public GitHub tag
   after `REPO_URL` is configured.
2. `notebooks/VALENCE_v0.7_OneClick_Colab.ipynb` embeds the release source and
   requires no separate ZIP or repository clone.

Both notebooks install VALENCE, run the 64-test suite, and execute the healthy,
outage, and finality demonstrations. Results are saved under
`/content/drive/MyDrive/valence/results/public-v0.7.0` or the corresponding
one-click results folder.

The tagged Git release remains the authoritative source. The embedded notebook
is a convenience snapshot whose run metadata records version `0.7.0`.
