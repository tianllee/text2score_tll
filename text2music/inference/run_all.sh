#!/bin/bash
set -e

accelerate launch --num_processes 1 text2music/inference/inference-custom.py
python text2music/data/batch_abci2abc.py
python text2music/data/batch_abc2xml.py