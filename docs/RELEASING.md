# Release builds

Publish source and the allowlisted easy ZIP. Never upload runtime folders, personal configuration, generated MCP paths, recordings, or character weights.

The engine manifest pins upstream source and base assets. The easy manifest pins official uv and prebuilt wheels. The dependency lock targets Python 3.10 / Windows x64. Consumer installation uses --only-binary :all:.

The fairseq 0.12.2 Windows wheel was built from its PyPI source release with MSVC for CPython 3.10. ANTLR 4.8 is a pure-Python wheel built from its PyPI source, with its upstream license added to wheel metadata. Artifacts have SHA-256 checks, but builds are not claimed to be reproducible. Maintainers need a build toolchain to rebuild fairseq; consumers do not.

Put official uv.exe in release-assets/tools/ and the exact manifest wheels in release-assets/wheels/. Third-party notices are in third_party/. Packaging rejects changed asset hashes.

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe scripts/package-source.py
.venv\Scripts\python.exe scripts/package-easy.py
```

Upload the two ZIPs, two wheel files (for source installs), and SHA256SUMS.txt to the manifest release tag. Source installs fetch wheels from that release; the easy ZIP contains them already. GitHub's automatic source archive contains neither uv nor wheels.

For demonstrations, state the tested hardware and model, compare original/converted audio, and measure local delay separately from Dot's response time. Use models and media whose terms permit the demonstration. Link the release and both READMEs. Native voice replacement, zero latency, and universal model support are not features of this release.
