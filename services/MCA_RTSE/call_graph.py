import ast
import os
from collections import defaultdict
import graphviz


class CallGraphAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.current_function = None
        self.calls = defaultdict(set)
        self.defined_functions = set()

    def visit_FunctionDef(self, node):
        previous_function = self.current_function
        self.current_function = node.name
        self.defined_functions.add(node.name)

        for child in ast.iter_child_nodes(node):
            self.visit(child)

        self.current_function = previous_function

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and self.current_function:
            self.calls[self.current_function].add(node.func.id)

        for child in ast.iter_child_nodes(node):
            self.visit(child)


def analyze_directory(directory_path):
    all_calls = {}
    all_functions = set()

    for file in os.listdir(directory_path):
        if file.endswith('.py'):
            with open(os.path.join(directory_path, file), 'r') as f:
                tree = ast.parse(f.read())

            analyzer = CallGraphAnalyzer()
            analyzer.visit(tree)

            file_prefix = file[:-3] + "."
            prefixed_calls = {
                file_prefix + caller: {file_prefix + callee if callee in analyzer.defined_functions else callee
                                       for callee in callees}
                for caller, callees in analyzer.calls.items()
            }

            all_calls.update(prefixed_calls)
            all_functions.update(file_prefix + f for f in analyzer.defined_functions)

    return all_calls, all_functions


def create_call_graph(calls, functions, output_file="call_graph"):
    """Generate a call graph using Graphviz"""
    dot = graphviz.Digraph(
        comment='Python Call Graph',
        format='pdf',  # Can be changed to 'png', 'svg', etc.
        engine='dot'
    )

    # Graph settings for better readability
    dot.attr(rankdir='LR')  # Left to right layout
    dot.attr('node', shape='box', style='rounded,filled', fontname='Arial', fontsize='12')

    # Add nodes for all functions
    for func in functions:
        dot.node(func, func, fillcolor='lightpink')

    # Add external function nodes with different style
    external_funcs = set()
    for callees in calls.values():
        for callee in callees:
            if callee not in functions:
                external_funcs.add(callee)

    for func in external_funcs:
        dot.node(func, func, fillcolor='lightblue')

    # Add edges for function calls
    for caller, callees in calls.items():
        for callee in callees:
            dot.edge(caller, callee)

    # Save the graph
    dot.render(output_file, view=True, cleanup=True)


if __name__ == "__main__":
    # First make sure graphviz is installed:
    # pip install graphviz

    directory = "."  # Current directory
    calls, functions = analyze_directory(directory)
    create_call_graph(calls, functions)