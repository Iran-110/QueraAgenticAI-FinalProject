# Streamlit Examples for Students

This folder contains a progression of Streamlit examples, from a basic "Hello World" to more advanced concepts like Session State and Layouts.

## How to run the examples

First, ensure your environment is set up and dependencies are installed using `uv`:
```bash
uv sync
```

Then, run any of the files using the `uv run streamlit run` command from your terminal:

```bash
uv run streamlit run 01_basic_app.py
```

## Included Examples

1. **[`01_basic_app.py`](./01_basic_app.py)**: A very simple app showing text input and basic output.
2. **[`02_data_viz.py`](./02_data_viz.py)**: Demonstrates how to display dataframes and draw charts easily.
3. **[`03_session_state.py`](./03_session_state.py)**: **CRITICAL CONCEPT!** Shows how to use `st.session_state` to remember variables across user interactions (since Streamlit reruns the script on every interaction).
4. **[`04_advanced_layout.py`](./04_advanced_layout.py)**: Shows how to build more complex UIs using columns, sidebars, and expanders.
