# CI validation model

The CI workflow separates the fast pull-request development loop from compatibility validation.

- Python 3.11 runs the full Python suite with coverage on pull requests.
- The C++/nanobind quant-engine validation runs independently instead of waiting for the Python matrix.
- Python 3.10 and 3.14 compatibility runs are retained on pushes to `main` and manual workflow runs.
- Pull-request concurrency cancels obsolete runs when a newer commit is pushed.

This changes execution order and removes duplicated PR work; it does not lower the scientific test suite or remove the compatibility matrix from repository validation.
