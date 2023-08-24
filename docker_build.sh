#!/bin/bash
download_url="https://github.com/facjxzdt/AnimeScore.git"
# 1. clone
git clone $download_url
cd AnimeScore
# 2. build
docker build -t animescore .