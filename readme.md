## Create a new conda environment
conda create --name text2score python=3.10

conda activate text2score

## Install PyTorch + CUDA only
conda install pytorch=2.3.0 pytorch-cuda=11.8 numpy -c pytorch -c nvidia

## Install other dependencies
pip install -e .

## Install other packages
pip install transformers accelerate optimum

## Run pretrain with:
```python
accelerate launch /data/home/acw769/text2score/text2music/pretrain/train-gen-custom.py
```
Make sure accelerate configs are set up properly.