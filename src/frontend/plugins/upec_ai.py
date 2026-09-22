"""Frontend entry point for the UPEC-AI proof workflows."""

import os
import tempfile
import zipfile
from io import BytesIO

import streamlit as st

from src.backend.classes.top_module import TopModule
from src.constants import MITER_SUFFIX
from src.frontend.frontend_utils import (
    create_signal_df,
    create_table,
    load_top_module_manager,
    tab_header,
)
from src.frontend.plugins.upec_dit import print_tcl_script_jg, print_tcl_script_onespin
from src.frontend.print_functions import (
    print_bind_statement,
    print_clocking,
    print_difference_constraint,
    print_equivalence_constraint,
    print_equivalence_function,
    print_miter_circuit,
    print_property,
    print_reset_seq,
    print_sv_comment_separator,
)
from src.utils import sort_names_by_keywords


PROOF_MODES = [
    "End-to-End Proof",
    "Layer-Wise Proof",
    "Single-Cycle Proof",
]


def upec_ai():
    """Display the UPEC-AI proof workflow selector and workspace."""

    tab_header("UPEC-AI")

    st.write(
        "In **UPEC-AI**, we check for parameter-dependent timing side channels "
        "that could lead to model theft."
    )
    st.write(
        "The tool checks the connections between model parameters and the "
        "control output that indicates the execution time."
    )
    st.write(
        "There are three proof methods: **End-to-End Proof**, "
        "**Layer-Wise Proof**, and **Single-Cycle Proof**. At the end of the "
        "selected workflow, an SVA property can be downloaded and proven "
        "using a model checker."
    )
    st.link_button(
        "Research Paper",
        "https://ieeexplore.ieee.org/abstract/document/11049644",
    )

    st.write("---")
    proof_mode = st.radio(
        "Proof Type",
        PROOF_MODES,
        index=0,
        horizontal=True,
    )

    st.write("**UPEC-AI**")
    st.write(f"Selected proof mode: **{proof_mode}**")

    if proof_mode == "End-to-End Proof":
        end_to_end_proof()
    else:
        st.info(f"The {proof_mode} workflow will be developed later.")


def end_to_end_proof():
    """Generate a miter and SVA property for the UPEC-AI end-to-end proof."""

    st.markdown(
        "<h5 style='color: #718DBF;'>End-to-End Proof</h5>",
        unsafe_allow_html=True,
    )

    top_module_manager = load_top_module_manager()
    top_module_name = st.sidebar.selectbox(
        "Top Module",
        top_module_manager.get_top_module_names(),
    )
    top_module = top_module_manager.get_top_module_by_name(top_module_name)

    clock = st.sidebar.selectbox("Clock", top_module.get_clocks())
    reset = st.sidebar.selectbox("Reset", top_module.get_resets())
    selected_condition = st.sidebar.radio(
        "Condition",
        ["Active High", "Active Low"],
        label_visibility="collapsed",
    )
    active_high = selected_condition == "Active High"
    sequential_depth = st.sidebar.number_input(
        "Sequential Depth",
        min_value=1,
        value=10,
        step=1,
    )

    parameter_inputs, control_outputs = parameter_control_selection(top_module, clock, reset)

    st.write(
        "Selected parameter inputs are allowed to differ between the two design "
        "instances. All remaining primary inputs are constrained equal, while "
        "the selected control outputs are checked for equivalence."
    )

    uploaded_files = st.session_state["files"]
    if not parameter_inputs:
        st.warning("Select at least one parameter input to generate the proof.")
    if not control_outputs:
        st.warning("Select at least one control output to generate the proof.")

    if uploaded_files and parameter_inputs and control_outputs:
        primary_inputs = top_module.get_primary_inputs()
        other_inputs = [
            signal
            for signal in primary_inputs
            if signal not in parameter_inputs and signal not in (clock, reset)
        ]
        states = top_module.get_states()
        ports = top_module.get_primary_ports(True)

        with tempfile.TemporaryDirectory() as temp_dir:
            root_dir = os.path.join(temp_dir, f"{top_module_name}-upec-ai")
            rtl_dir = os.path.join(root_dir, "rtl")
            os.makedirs(rtl_dir, exist_ok=True)

            miter_name = top_module_name + MITER_SUFFIX
            miter_filename = miter_name + ".sv"
            miter_filepath = os.path.join(root_dir, miter_filename)

            property_name = "upec_ai_unrolled"
            property_filename = "upec-ai.sv"
            property_filepath = os.path.join(root_dir, property_filename)

            script_filename_onespin = "run-onespin.tcl"
            script_filepath_onespin = os.path.join(root_dir, script_filename_onespin)

            script_filename_jg = "run-jaspergold.tcl"
            script_filepath_jg = os.path.join(root_dir, script_filename_jg)

            for uploaded_file in uploaded_files:
                file_path = os.path.join(rtl_dir, uploaded_file.name)
                with open(file_path, "wb") as file:
                    file.write(uploaded_file.getbuffer())

            with open(miter_filepath, "w") as file:
                file.write(print_miter_circuit(top_module_name, ports, clock, reset))

            with open(property_filepath, "w") as file:
                file.write(
                    print_upec_ai_file(
                        clock,
                        reset,
                        active_high,
                        states,
                        parameter_inputs,
                        other_inputs,
                        control_outputs,
                        miter_name,
                        int(sequential_depth),
                    )
                )

            uploaded_file_names = sort_names_by_keywords(
                [file.name for file in uploaded_files],
                ["pkg", "package"],
            )

            with open(script_filepath_onespin, "w") as file:
                file.write(
                    print_tcl_script_onespin(
                        uploaded_file_names,
                        miter_filename,
                        miter_name,
                        property_filename,
                        property_name,
                    )
                )

            with open(script_filepath_jg, "w") as file:
                file.write(
                    print_tcl_script_jg(
                        uploaded_file_names,
                        miter_filename,
                        miter_name,
                        property_filename,
                        clock,
                        property_name,
                    )
                )

            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                for folder_name, _, filenames in os.walk(temp_dir):
                    for filename in filenames:
                        file_path = os.path.join(folder_name, filename)
                        zip_file.write(file_path, os.path.relpath(file_path, temp_dir))
            zip_buffer.seek(0)

            st.download_button(
                label="Download SVA Proof Files",
                data=zip_buffer,
                file_name=f"{top_module_name}-upec-ai.zip",
                mime="application/zip",
            )


def parameter_control_selection(
    top_module: TopModule,
    clock: str,
    reset: str,
) -> tuple[list[str], list[str]]:
    """Select parameter inputs and timing/control outputs for the proof."""

    input_signals = top_module.get_primary_inputs(full=True)
    input_signals.pop(clock, None)
    input_signals.pop(reset, None)
    output_signals = top_module.get_primary_outputs(full=True)
    input_data, _ = create_signal_df("Parameter Input", input_signals)
    output_data, _ = create_signal_df("Control Output", output_signals)

    st.markdown(
        "<h5 style='color: #718DBF;'>Select the parameter inputs and timing/control outputs:</h5>",
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        parameter_grid = create_table(input_data, selectable=True)
    with col2:
        output_grid = create_table(output_data, selectable=True)

    selected_parameters = [
        input_data["Parameter Input"][index]
        for index in parameter_grid.selection.rows
    ]
    selected_outputs = [
        output_data["Control Output"][index]
        for index in output_grid.selection.rows
    ]
    return selected_parameters, selected_outputs


def print_upec_ai_file(
    clock: str,
    reset: str,
    active_high: bool,
    all_signals: list[str],
    parameter_inputs: list[str],
    other_inputs: list[str],
    control_outputs: list[str],
    miter_name: str,
    sequential_depth: int = 10,
) -> str:
    """Generate the UPEC-AI end-to-end SVA property file."""

    file_str = "module property_checker\n  (\n"
    file_str += f"  input {clock}"
    if reset:
        file_str += f",\n  input {reset}"
    file_str += "\n  );\n\n"

    file_str += print_clocking(clock)
    file_str += f"  localparam SEQUENTIAL_DEPTH = {sequential_depth};\n\n\n"

    if other_inputs:
        file_str += print_sv_comment_separator("Non-Parameter Input Constraint")
        file_str += print_equivalence_constraint("non_parameter_input_c", other_inputs)

    file_str += print_sv_comment_separator("Parameter Difference Constraint")
    file_str += print_difference_constraint("parameter_difference_c", parameter_inputs)

    file_str += print_sv_comment_separator("State Equivalence")
    file_str += print_equivalence_function("state_equivalence", all_signals)

    file_str += print_sv_comment_separator("Control Output Equivalence")
    file_str += print_equivalence_function("control_output_equivalence", control_outputs)

    file_str += print_sv_comment_separator("Reset Sequence")
    file_str += print_reset_seq(reset, active_high)

    file_str += print_sv_comment_separator("UPEC-AI End-to-End Proof")
    file_str += print_property(
        "upec_ai_unrolled",
        "state_equivalence()",
        "control_output_equivalence() [*SEQUENTIAL_DEPTH]",
        reset,
        active_high,
    )

    file_str += "endmodule\n\n"
    file_str += print_bind_statement(miter_name, [clock], reset, active_high)
    return file_str
