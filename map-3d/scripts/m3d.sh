#!/bin/zsh
# 3D 地形片辅助命令：m3d.sh check|make|gif …（见 m3d.py）
exec python3 "${0:A:h}/m3d.py" "$@"
