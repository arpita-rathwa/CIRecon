from cirecon.input_layer import discover_workflow_files


def test_discovers_workflow_files():
    files = discover_workflow_files(".")
    assert len(files) > 0

    for path, content in files:
        assert path.endswith(".yml") or path.endswith(".yaml")
        assert len(content) > 0