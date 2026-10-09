#!/bin/zsh
# 旅行 vlog 辅助命令，见 vlog.py 开头说明
exec uv run -q --with certifi --with pillow --with pillow-heif python "${0:A:h}/vlog.py" "$@"
