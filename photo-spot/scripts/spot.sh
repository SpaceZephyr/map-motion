#!/bin/zsh
# 找机位辅助命令：spot.sh exif|find|ahead|sheet|gif …（见 spot.py 开头说明）
exec uv run -q --with certifi --with pillow --with pillow-heif python "${0:A:h}/spot.py" "$@"
