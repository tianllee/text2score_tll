## Create a new conda environment
conda create --name text2score python=3.10
conda activate text2score

## Install PyTorch + CUDA only
conda install pytorch==2.3.0 pytorch-cuda=11.8 -c pytorch -c nvidia

## Install other dependencies
pip install -e .