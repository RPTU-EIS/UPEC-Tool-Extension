"""Frontend page for the scientific paper related to UPEC-AI."""

import streamlit as st

from src.frontend.frontend_utils import tab_header


SCIENTIFIC_PAPER_URL = "https://ieeexplore.ieee.org/abstract/document/11049644"


def scientific_paper():
    """Display the scientific paper link."""

    tab_header("Scientific Paper")
    st.write("The scientific paper related to UPEC-AI is available here:")
    st.link_button("Open Scientific Paper", SCIENTIFIC_PAPER_URL)
