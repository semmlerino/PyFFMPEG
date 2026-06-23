"""Pure domain layer for PyFFMPEG.

Dependency-free value types (codecs, settings, jobs, status) shared by the Qt
controller/manager/widgets. Imports nothing from the application modules so it
stays a leaf that can be type-checked and unit-tested in isolation.
"""
