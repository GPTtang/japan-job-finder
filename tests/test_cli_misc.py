from job_finder.cli import main


def test_unreadable_query_file_exits_2(tmp_path, capsys):
    assert main(["--query-file", str(tmp_path / "missing.txt")]) == 2
    assert "无法读取" in capsys.readouterr().err
