# Friction log

Two concrete usability improvements I would flag to the team after this take-home.

## Trace view dropdown does not reflect the selected filter

When selecting **Tool calls** or **Errors only**, the UI applies a filter and updates the traces. A separate filter label shows the active condition, but the dropdown still displays **Default view**, with its checkmark unchanged.

The filter is visible, but users naturally look back at the dropdown to confirm their selection. Keeping its label and checkmark consistent with the selected view—or making it clear that the dropdown only applies presets—would avoid conflicting signals. This is an observed usability issue, rather than a confirmed filtering bug.

## Tool docstring errors could be more actionable

`parse_docstring=True` failed with “Found invalid Google-Style docstring,” but did not identify the missing blank line before `Args:`. Adding that line fixed it.

The documentation already explains the formatting requirement and includes an invalid-whitespace example. The improvement is in the runtime error: naming the affected function and identifying the missing separator would make the failure easier to diagnose without searching the documentation.
