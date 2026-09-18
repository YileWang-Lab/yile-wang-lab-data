# incoming/ — files handed over from the desktop

Drop zone, not a source directory. Nothing here is imported by the agent; each
file gets read, graded and then either promoted into the repo proper or left
here as a record of what was considered.

    agents/      runnable .py agents -> graded, then promoted to opponents/
    notebooks/   .ipynb -> stripped to a plain agent, then graded
    notes/       .md / .txt strategy write-ups -> read, claims measured
    reference/   the 参考代码 folder, whatever it turns out to contain

WHY GRADE BEFORE PROMOTING. Section 33 measured 117 agents already on disk and
found exactly two in the band we win 20-80% of. An ungraded file in opponents/
is worse than no file: it silently joins a pool whose composition every result
is measured against.
