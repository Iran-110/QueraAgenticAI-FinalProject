import streamlit as st
import pandas as pd
import numpy as np

st.title("Data Visualization 📊")
st.write("Streamlit makes it incredibly easy to visualize data.")

# Generate some random data
chart_data = pd.DataFrame(
    np.random.randn(20, 3),
    columns=['a', 'b', 'c']
)

st.write("Here is the raw data:", chart_data)

st.subheader("Line Chart")
st.line_chart(chart_data)
