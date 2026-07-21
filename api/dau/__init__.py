"""Dấu API domain package.

DSP modules are imported explicitly by development and compatibility tooling.
Keeping package initialization empty prevents that optional native stack from
entering the production FastAPI cold-start path.
"""
